#!/usr/bin/env python3
"""Run a small position task on the selected controller of the open Iris SITL."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import threading
import time

import numpy as np
from pymavlink import mavutil
from pyulog import ULog
import toolbox as t

PROTOCOL = dict(version=1, takeoff_height_m=2.5, hover_seconds=10.,
                figure8_seconds=40., figure8_north_amplitude_m=2., figure8_east_amplitude_m=1.,
                yaw_seconds=40., yaw_amplitude_deg=45., yaw_cycles=2,
                setpoint_hz=20, tilt_limit_deg=15., horizontal_radius_limit_m=6., height_limit_m=5.)


def figure8(elapsed, duration=40.):
    """Closed NED position curve with zero endpoint velocity/acceleration."""
    u = min(1., max(0., elapsed / duration))
    phase = 2 * math.pi * (10*u**3 - 15*u**4 + 6*u**5)
    return 2 * math.sin(phase), math.sin(2 * phase)


def yaw_sweep(elapsed, duration=40., amplitude=math.radians(45), cycles=2):
    """Smooth zero-end-rate yaw excitation returning to the initial heading."""
    u = min(1., max(0., elapsed / duration))
    phase = 2 * math.pi * cycles * (10*u**3 - 15*u**4 + 6*u**5)
    return amplitude * math.sin(phase)


def yaw_from_quaternion(q):
    if len(q) != 4 or not all(math.isfinite(v) for v in q):
        raise RuntimeError('姿态测量无效。')
    w, x, y, z = q
    return math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))


def angle_error(value, reference):
    return math.atan2(math.sin(value-reference), math.cos(value-reference))


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Link:
    """One local GCS/position publisher; never publish rate or actuator targets."""
    def __init__(self, directory):
        self.connection = mavutil.mavlink_connection('udpin:127.0.0.1:14550', source_system=255, source_component=190)
        self.stop = threading.Event()
        self.ready = False
        self.error = None
        self.last_rx = 0.
        self.sim_time = 0.
        self.target = None  # dict(center xyz, initial yaw, task, phase start or None)
        self.sent = 0
        self.stream = (directory / 'reference.jsonl').open('x')
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def loop(self):
        last_heartbeat = last_manual = last_target = 0.
        requested_stream = False
        try:
            while not self.stop.is_set():
                message = self.connection.recv_match(blocking=True, timeout=.01)
                if message is not None and message.get_srcSystem() == 1:
                    self.ready = True
                    if message.get_type() == 'LOCAL_POSITION_NED':
                        self.sim_time = message.time_boot_ms / 1000.
                        self.last_rx = time.monotonic()
                now = time.monotonic()
                if not self.ready:
                    continue
                mav = self.connection.mav
                if not requested_stream:
                    mav.command_long_send(1, 1, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                                          mavutil.mavlink.MAVLINK_MSG_ID_LOCAL_POSITION_NED, 20000, 0, 0, 0, 0, 0)
                    requested_stream = True
                if now - last_heartbeat >= .5:
                    mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
                    last_heartbeat = now
                if now - last_manual >= .1:
                    mav.manual_control_send(1, 0, 0, 500, 0, 0)
                    last_manual = now
                target = self.target
                if target is not None and now - last_target >= 1. / PROTOCOL['setpoint_hz']:
                    center, yaw, start, task = target['center'], target['yaw'], target['start'], target['task']
                    elapsed = self.sim_time - start if start is not None else 0.
                    dx, dy = figure8(elapsed) if start is not None and task == 'figure8' else (0., 0.)
                    yaw += yaw_sweep(elapsed) if start is not None and task == 'yaw' else 0.
                    position = (center[0] + dx, center[1] + dy, center[2])
                    # position + yaw only; ignore velocity, acceleration and yaw rate.
                    mav.set_position_target_local_ned_send(int(self.sim_time * 1000) & 0xffffffff, 1, 1,
                        mavutil.mavlink.MAV_FRAME_LOCAL_NED, 2552, *position, 0, 0, 0, 0, 0, 0, yaw, 0)
                    self.stream.write(json.dumps(dict(time_s=self.sim_time, position=position, yaw=yaw)) + '\n')
                    self.sent += 1
                    last_target = now
        except Exception as exc:
            self.error = repr(exc)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)
        self.connection.close()
        self.stream.close()


def assert_controller(diagnostic, mode, axes):
    if (diagnostic.get('effective_mode') != mode or diagnostic.get('effective_axes') != axes or
            diagnostic.get('requested_mode') != mode or diagnostic.get('requested_axes') != axes or
            diagnostic.get('pending') or diagnostic.get('config_pending') or
            not diagnostic.get('config_valid') or not t.healthy(diagnostic)):
        raise RuntimeError('控制器模式、参数或故障状态变化，任务中止。')
    if diagnostic.get('armed') and (not diagnostic.get('output_valid') or
            not diagnostic.get('measurement_valid') or diagnostic.get('timing_status') != 0):
        raise RuntimeError('控制器测量、时间或输出无效，任务中止。')


def analyze(directory, result):
    start = next(e['timestamp'] for e in result['events'] if e['name'] == 'task_start')
    end = next(e['timestamp'] for e in result['events'] if e['name'] == 'task_end')
    log = None
    for item in result['logs']:
        candidate = ULog(str(directory / item['file']))
        try:
            d = candidate.get_dataset('sta_rate_ctrl_status').data
            if d['timestamp'][0] <= start and d['timestamp'][-1] >= end:
                log = candidate
                break
        except (KeyError, IndexError):
            pass
    if log is None:
        raise RuntimeError('没有覆盖任务窗口的完整ULog。')
    d = log.get_dataset('sta_rate_ctrl_status').data
    mask = (d['timestamp'] >= start) & (d['timestamp'] <= end)
    if np.count_nonzero(mask) < 100:
        raise RuntimeError('实际控制诊断样本不足。')
    for key, expected in [('effective_mode', result['mode']), ('effective_axes', result['axes']), ('fault', 0), ('abort_requested', 0)]:
        if not np.all(d[key][mask] == expected):
            raise RuntimeError('ULog实际状态不符合选择：' + key)
    rate = np.column_stack([d[f's[{i}]'][mask] for i in range(3)])
    if not np.all(np.isfinite(rate)):
        raise RuntimeError('角速度误差非有限值。')
    p = log.get_dataset('vehicle_local_position').data
    sp = log.get_dataset('vehicle_local_position_setpoint').data
    pm = (p['timestamp'] >= start) & (p['timestamp'] <= end)
    pi = np.searchsorted(sp['timestamp'], p['timestamp'][pm], side='right') - 1
    if np.count_nonzero(pm) < 100 or np.any(pi < 0):
        raise RuntimeError('位置或参考样本不足。')
    error = np.column_stack([p[k][pm] - sp[k][pi] for k in ('x', 'y', 'z')])
    if not np.all(np.isfinite(error)):
        raise RuntimeError('位置误差非有限值。')
    sequence = np.diff(d['update_seq'][mask].astype(np.int64))
    summary = dict(task=result['task'], mode=result['mode'], axes=result['axes'],
                   task_seconds=(end-start)/1e6, samples=int(np.count_nonzero(mask)),
                   rate_rmse_rad_s=np.sqrt(np.mean(rate.astype(float)**2, axis=0)).tolist(),
                   position_rmse_m=np.sqrt(np.mean(error.astype(float)**2, axis=0)).tolist(),
                   position_error_norm_max_m=float(np.max(np.linalg.norm(error, axis=1))),
                   control_updates_missing=int(np.sum(np.maximum(sequence-1, 0))),
                   limits_fraction=[float(np.mean(d[f'limits[{i}]'][mask] != 0)) for i in range(3)],
                   pid_updates_in_task=int(np.sum(d['pid_updated'][mask])),
                   scope='日常轨迹任务指标；不是M06/M08原协议验收或独立统计结论')
    if result['mode'] in (1, 2) and summary['pid_updates_in_task'] != 0:
        raise RuntimeError('全轴ESTA/ISTA不应计算闲置PID。')
    if result['task'] == 'figure8':
        reference_span = [float(np.ptp(sp[k][pi])) for k in ('x', 'y')]
        actual_span = [float(np.ptp(p[k][pm])) for k in ('x', 'y')]
        if reference_span[0] < 3.5 or reference_span[1] < 1.5 or actual_span[0] < 3. or actual_span[1] < 1.:
            raise RuntimeError('8字轨迹的两轴实际覆盖范围不足。')
        summary.update(reference_span_ne_m=reference_span, actual_span_ne_m=actual_span)
    if result['task'] == 'yaw':
        attitude = log.get_dataset('vehicle_attitude').data
        attitude_sp = log.get_dataset('vehicle_local_position_setpoint').data
        am = (attitude['timestamp'] >= start) & (attitude['timestamp'] <= end)
        ai = np.searchsorted(attitude_sp['timestamp'], attitude['timestamp'][am], side='right') - 1
        if np.count_nonzero(am) < 100 or np.any(ai < 0):
            raise RuntimeError('yaw姿态或参考样本不足。')
        q = np.column_stack([attitude[f'q[{i}]'][am] for i in range(4)]).astype(float)
        actual_yaw = np.arctan2(2*(q[:,0]*q[:,3]+q[:,1]*q[:,2]), 1-2*(q[:,2]**2+q[:,3]**2))
        reference_yaw = attitude_sp['yaw'][ai].astype(float)
        yaw_error = np.arctan2(np.sin(actual_yaw-reference_yaw), np.cos(actual_yaw-reference_yaw))
        if not np.all(np.isfinite(reference_yaw)) or not np.all(np.isfinite(yaw_error)):
            raise RuntimeError('yaw姿态误差非有限值。')
        reference_span = float(np.degrees(np.ptp(np.unwrap(reference_yaw))))
        actual_span = float(np.degrees(np.ptp(np.unwrap(actual_yaw))))
        if reference_span < 85 or actual_span < 75:
            raise RuntimeError('yaw实际往返覆盖范围不足。')
        summary.update(yaw_attitude_rmse_deg=float(np.degrees(np.sqrt(np.mean(yaw_error**2)))),
                       yaw_attitude_error_max_deg=float(np.degrees(np.max(np.abs(yaw_error)))),
                       yaw_reference_span_deg=reference_span, yaw_actual_span_deg=actual_span,
                       rp_rate_rmse_rad_s=summary['rate_rmse_rad_s'][:2],
                       horizontal_position_rmse_m=summary['position_rmse_m'][:2])
    save(directory / 'metrics.json', summary)
    print('位置 RMSE [N,E,D] (m)：' + str([round(v, 4) for v in summary['position_rmse_m']]), flush=True)
    print('角速度 RMSE [R,P,Y] (rad/s)：' + str([round(v, 5) for v in summary['rate_rmse_rad_s']]), flush=True)
    if result['task'] == 'yaw':
        print(f'yaw姿态 RMSE/峰值 (deg)：{summary["yaw_attitude_rmse_deg"]:.3f} / '
              f'{summary["yaw_attitude_error_max_deg"]:.3f}', flush=True)
        print('yaw实际往返范围 (deg)：' + f'{summary["yaw_actual_span_deg"]:.3f}' +
              '；R/P耦合角速度RMSE：' + str([round(v, 5) for v in summary['rp_rate_rmse_rad_s']]), flush=True)


def run(task):
    t.ground()
    if t.processes({'QGroundControl'}):
        raise RuntimeError('请关闭QGC，自动任务需要本机14550端口。Gazebo保持打开。')
    mode, axes = int(t.parameter('MC_RTC_MODE')), int(t.parameter('MC_STA_AXES'))
    if (mode, axes) not in ((0, 0), (1, 7), (2, 7)) or t.parameter('MC_RATT_TEST') != 0:
        raise RuntimeError('请先执行 switch.sh pid、switch.sh esta 或 switch.sh ista。')
    t.wait_selection(mode, axes)
    algorithm = t.MODE_NAMES[mode]
    directory = t.HERE / 'experiments' / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-' + algorithm + '-' + task)
    directory.mkdir(parents=True, exist_ok=False)
    print('使用当前算法：' + ('PID' if mode == 0 else '三轴 ' + algorithm.upper()) + '；任务：' + task, flush=True)
    print('日志目录：' + str(directory), flush=True)
    result = dict(success=False, task=task, mode=mode, axes=axes, algorithm=algorithm, protocol=PROTOCOL,
                  controller_parameters={key: t.parameter(key) for key in t.controlled_names()},
                  source_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=t.ROOT, text=True).strip(),
                  binary_sha256=sha(t.BIN / 'px4'), script_sha256=sha(Path(__file__)), events=[], logs=[])
    save(directory / 'result.json', result)
    shutil.copy2(__file__, directory / 'flight_source.py')
    (directory / 'params_before.txt').write_text(t.cli('param', 'show', '-a'))
    originals = {key: t.parameter(key) for key in ('SDLOG_PROFILE', 'MIS_TAKEOFF_ALT')}
    save(directory / 'parameters_before.json', originals)
    old_logs = set(t.ROOTFS.glob('log/**/*.ulg'))
    link = None
    logger_changed = False
    grounded = True
    origin = None
    commands = (directory / 'commands.jsonl').open('x')
    samples = (directory / 'samples.jsonl').open('x')

    def command(module, *args):
        text = t.cli(module, *args)
        commands.write(json.dumps(dict(module=module, args=args, response=text)) + '\n')
        commands.flush()
        return text

    def sample(check=True):
        state = dict(position=t.topic('vehicle_local_position'), attitude=t.topic('vehicle_attitude'),
                     status=t.topic('vehicle_status'), land=t.topic('vehicle_land_detected'),
                     control=t.topic('sta_rate_ctrl_status'))
        samples.write(json.dumps(state) + '\n'); samples.flush()
        if check:
            assert_controller(state['control'], mode, axes)
            if link and (link.error or (link.ready and time.monotonic()-link.last_rx > 3)):
                raise RuntimeError('MAVLink位置流中断：' + str(link.error))
            if state['status'].get('failsafe'):
                raise RuntimeError('飞控报告failsafe。')
            if state['status'].get('arming_state') == 2:
                q = state['attitude']['q']
                yaw_from_quaternion(q)
                tilt = math.degrees(math.acos(max(-1., min(1., 1-2*(q[1]**2+q[2]**2)))))
                p = state['position']
                if not all(math.isfinite(p[k]) for k in ('x','y','z')) or tilt > PROTOCOL['tilt_limit_deg']:
                    raise RuntimeError('姿态或位置越界。')
                if origin and (math.hypot(p['x']-origin[0], p['y']-origin[1]) > PROTOCOL['horizontal_radius_limit_m'] or
                               abs(p['z']-origin[2]) > PROTOCOL['height_limit_m']):
                    raise RuntimeError('超出任务位置边界。')
        return state

    def event(name, state):
        result['events'].append(dict(name=name, timestamp=state['position']['timestamp']))
        save(directory / 'result.json', result)

    def wait_for(predicate, timeout=120, check=True):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = sample(check)
            if predicate(state):
                return state
            time.sleep(.2)
        raise RuntimeError('等待飞行阶段超时。')

    def land(check=True):
        nonlocal grounded
        command('commander', 'mode', 'auto:land')
        if link:
            link.target = None
        state = wait_for(lambda s: s['land'].get('landed') and s['status'].get('arming_state') == 1, check=check)
        grounded = True
        event('landed_disarmed', state)
        return state

    try:
        link = Link(directory)
        print('等待定位和模拟遥控连接…', flush=True)
        state = wait_for(lambda s: s['position'].get('xy_global') and s['position'].get('z_valid') and
                         s['position']['timestamp'] > 30e6 and link.last_rx and
                         not s['status'].get('rc_signal_lost', True), check=False)
        assert_controller(state['control'], mode, axes)
        origin = tuple(state['position'][k] for k in ('x', 'y', 'z'))
        result['ground_position'] = origin
        t.set_parameter('MIS_TAKEOFF_ALT', PROTOCOL['takeoff_height_m'])
        command('logger', 'stop'); logger_changed = True
        time.sleep(1.1)
        t.set_parameter('SDLOG_PROFILE', int(originals['SDLOG_PROFILE']) | 16)
        command('logger', 'start', '-b', '256', '-r', '1000', '-t', '-f')
        print('起飞至约2.5米…', flush=True)
        command('commander', 'takeoff')
        grounded = False
        event('takeoff_command', state)
        stable_since = None
        hold_requested = False

        def settled(s):
            nonlocal stable_since, hold_requested
            p, v = s['position'], s['status']
            if v.get('nav_state') == 2 and v.get('arming_state') == 2 and not hold_requested:
                command('commander', 'mode', 'auto:loiter'); hold_requested = True
            stable = v.get('nav_state') == 4 and v.get('arming_state') == 2 and origin[2]-p['z'] > 1.8 and abs(p['vz']) < .2
            stable_since = (stable_since or p['timestamp']) if stable else None
            return stable_since is not None and p['timestamp']-stable_since >= 2e6

        state = wait_for(settled)
        if task in ('figure8', 'yaw'):
            center = tuple(state['position'][k] for k in ('x', 'y', 'z'))
            yaw = state['position']['heading']
            result.update(center_ned=center, yaw=yaw)
            link.target = dict(center=center, yaw=yaw, start=None, task=task)
            before = link.sent
            wait_for(lambda s: link.sent-before >= 30, timeout=15)
            command('commander', 'mode', 'offboard')
            state = wait_for(lambda s: s['status'].get('nav_state') == 14, timeout=15)
            link.target = dict(center=center, yaw=yaw, start=state['position']['timestamp']/1e6, task=task)
            duration = PROTOCOL['figure8_seconds'] if task == 'figure8' else PROTOCOL['yaw_seconds']
            if task == 'figure8':
                print('正在飞一圈8字：40秒，范围约4米×2米…', flush=True)
            else:
                print('正在定点做yaw测试：40秒，两轮±45°平滑摆动…', flush=True)
        else:
            duration = PROTOCOL['hover_seconds']
            print('悬停10秒…', flush=True)
        event('task_start', state)
        start = state['position']['timestamp']
        expected_nav = 14 if task in ('figure8', 'yaw') else 4

        def complete(s):
            if s['status'].get('nav_state') != expected_nav or s['status'].get('arming_state') != 2:
                raise RuntimeError('飞行任务模式发生变化。')
            return s['position']['timestamp'] - start >= duration * 1e6

        state = wait_for(complete, timeout=duration*4+30)
        event('task_end', state)
        if task in ('figure8', 'yaw'):
            link.target = dict(center=center, yaw=yaw, start=None, task=task)
            wait_for(lambda s: (math.hypot(s['position']['x']-center[0], s['position']['y']-center[1]) < .25 and
                     (task != 'yaw' or abs(angle_error(yaw_from_quaternion(s['attitude']['q']), yaw)) < math.radians(5))), timeout=20)
        print('下降并等待自动上锁…', flush=True)
        land()
        result['success'] = True
    except (Exception, KeyboardInterrupt) as exc:
        result['error'] = str(exc) or '用户中断'
        print('任务中止：' + result['error'], flush=True)
        try:
            state = sample(check=False)
            if state['status'].get('arming_state') == 2:
                if not t.healthy(state['control']) or not state['control'].get('measurement_valid'):
                    raise RuntimeError('控制器故障，停止本地SITL。')
                land(check=False)
            else:
                grounded = state['land'].get('landed') is True
        except Exception as cleanup:
            result['abort_reason'] = str(cleanup)
            try:
                command('shutdown')
            except Exception:
                pass
    finally:
        try:
            if logger_changed:
                command('logger', 'stop')
                time.sleep(.5)
            for path in sorted(set(t.ROOTFS.glob('log/**/*.ulg'))-old_logs):
                dest = directory / path.name
                shutil.copy2(path, dest)
                result['logs'].append(dict(file=dest.name, sha256=sha(dest)))
            if grounded:
                for key, value in originals.items():
                    t.set_parameter(key, value)
                command('param', 'save')
                if logger_changed:
                    command('logger', 'start')
                restored = {key: t.parameter(key) for key in originals}
                if restored != originals:
                    raise RuntimeError('任务辅助参数恢复失败。')
                save(directory / 'parameters_restored.json', restored)
        except Exception as exc:
            result.update(success=False, cleanup_error=str(exc))
        if link:
            link.close()
        commands.close(); samples.close()
        save(directory / 'result.json', result)
    if result['success']:
        try:
            analyze(directory, result)
        except Exception as exc:
            result.update(success=False, analysis_error=str(exc))
            save(directory / 'result.json', result)
    if not result['success']:
        raise RuntimeError('本轮未通过，请查看 ' + str(directory / 'result.json'))
    print('完成，飞机已落地上锁。可以 switch.sh 换算法，再执行同一 fly.sh 任务。', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='使用当前PID/ESTA/ISTA，在已经打开的Iris仿真中飞行。')
    parser.add_argument('task', choices=('hover', 'figure8', 'yaw'))
    args = parser.parse_args()
    try:
        with t.lock():
            run(args.task)
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        raise SystemExit('错误：' + str(exc))
