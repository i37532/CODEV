#!/usr/bin/env python3
"""Daily Iris SITL commands; frozen M06 ESTA / M08 ISTA configurations."""
import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'sim_scripts'
RESEARCH = ROOT / 'research/sta-rate-control'
BIN = ROOT / 'build/px4_sitl_default/bin'
ROOTFS = ROOT / 'build/px4_sitl_default/tmp/rootfs'
STATE = HERE / '.state'
BACKUP = STATE / 'parameters-before.json'
AXES = {'roll': 1, 'rp': 3, 'rpy': 7}
MODES = {'pid': 0, 'esta': 1, 'ista': 2}
MODE_NAMES = {value: name for name, value in MODES.items()}


def load(path):
    return json.loads(path.read_text())


def frozen_config(mode=1):
    if mode == 2:
        path = RESEARCH / 'm08/iris_ista_rpy_candidate02.json'
        expected = load(RESEARCH / 'm08/FROZEN_BASELINE.json')['accepted_configurations'][path.name]
        milestone = 'M08 ISTA候选02'
    elif mode in (0, 1):
        path = RESEARCH / 'm06/iris_esta_rpy.json'
        expected = load(RESEARCH / 'm06/FROZEN_BASELINE.json')['configuration_sha256']
        milestone = 'M06 ESTA'
    else:
        raise ValueError('不支持的控制器模式。')
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise RuntimeError(milestone + ' 冻结参数指纹不匹配，请先核实配置。')
    return load(path)


def environment():
    env = os.environ.copy()
    # Existing local caches; no package installation or network required.
    candidates = [ROOT / '.px4-python', Path('/home/yr/Desktop/codev doc/experiments/M00-20260912/python')]
    paths = [str(p) for p in candidates if p.is_dir()]
    if env.get('PYTHONPATH'):
        paths.append(env['PYTHONPATH'])
    env['PYTHONPATH'] = os.pathsep.join(paths)
    env['PATH'] = str(ROOT / '.px4-python/bin') + os.pathsep + env.get('PATH', '')
    # Fixed local configuration, never inherited research-runner overrides.
    for name in list(env):
        if name.startswith(('M04_', 'M05_', 'M06_', 'M08_')) or name in ('DONT_RUN', 'NO_PXH', 'PX4_SIM_SPEED_FACTOR', 'HEADLESS'):
            env.pop(name)
    env['PX4_SITL_WORLD'] = str(ROOT / 'sitl/worlds/empty_grey.world')
    env['GAZEBO_MASTER_URI'] = 'http://127.0.0.1:11345'
    return env


def processes(names):
    result = []
    for entry in Path('/proc').iterdir():
        if entry.name.isdigit():
            try:
                if (entry / 'comm').read_text().strip() in names:
                    result.append(entry)
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                pass
    return result


def no_simulator(include_qgc=False):
    names = {'px4', 'gzserver', 'gzclient', 'gazebo'}
    if include_qgc:
        names.add('QGroundControl')
    found = processes(names)
    if found:
        raise RuntimeError('请先退出已有仿真' + ('和 QGroundControl' if include_qgc else '') +
                           '，进程 PID：' + ', '.join(p.name for p in found))


def local_instance():
    found = processes({'px4'})
    if len(found) != 1:
        raise RuntimeError('需要且只允许一个本仓库 SITL；请先运行 ./sim_scripts/start.sh。')
    proc = found[0]
    args = (proc / 'cmdline').read_bytes().split(b'\0')
    if ((proc / 'exe').resolve() != (BIN / 'px4').resolve() or
            (proc / 'cwd').resolve() != ROOTFS.resolve()):
        raise RuntimeError('正在运行的 PX4 不属于本仓库 rootfs，拒绝操作。')
    for i, arg in enumerate(args):
        if arg == b'-i' and (i + 1 == len(args) or args[i + 1] != b'0'):
            raise RuntimeError('这些脚本仅连接本机 SITL instance 0。')


def cli(module, *args):
    local_instance()
    result = subprocess.run([str(BIN / ('px4-' + module)), *map(str, args)],
                            cwd=ROOTFS, capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError(f'PX4 {module} 执行失败：{result.stdout}{result.stderr}')
    return result.stdout


def topic(name):
    raw = cli('listener', name, '-n', '1')
    age = re.search(r'timestamp:\s+\d+\s+\(([\d.eE+-]+) seconds ago\)', raw)
    if not age or not 0 <= float(age.group(1)) <= 1:
        raise RuntimeError(f'{name} 缺失或过期，请等待仿真启动完成。')
    fields = {}
    for line in raw.splitlines():
        match = re.match(r'\s*(\w+):\s*(.*)', line)
        if not match:
            continue
        key, value = match.groups()
        if value.startswith('['):
            fields[key] = [float(x) for x in value.split(']')[0][1:].replace(',', ' ').split()]
        elif value in ('True', 'False'):
            fields[key] = value == 'True'
        else:
            try:
                fields[key] = float(value.split()[0])
            except (ValueError, IndexError):
                pass
    return fields


def parameter(name):
    raw = cli('param', 'show', name)
    match = re.search(r'\b' + re.escape(name) + r'\s+\[[\d,]+\]\s*:\s*([-+\d.eE]+)', raw)
    if not match or not math.isfinite(float(match.group(1))):
        raise RuntimeError('无法读取参数 ' + name)
    return float(match.group(1))


def ground():
    if parameter('SYS_AUTOSTART') != 10016:
        raise RuntimeError('仅支持 Iris / SYS_AUTOSTART=10016。')
    vehicle = topic('vehicle_status')
    landed = topic('vehicle_land_detected')
    if vehicle.get('arming_state') != 1 or landed.get('landed') is not True:
        raise RuntimeError('请先降落并上锁，再切换算法或停止仿真；当前操作未执行。')


def healthy(status):
    return status.get('fault') == 0 and status.get('abort_requested') is False


def accepted(status, mode, axes):
    return (healthy(status) and status.get('requested_mode') == mode and
            status.get('requested_axes') == axes and status.get('effective_mode') == mode and
            status.get('effective_axes') == (axes if mode else 0) and status.get('pending') is False and
            status.get('config_pending') is False and status.get('config_valid') is True and
            status.get('armed') is False and status.get('nu') == [0, 0, 0])


def wait_selection(mode, axes):
    deadline = time.monotonic() + 15
    previous = None
    while time.monotonic() < deadline:
        ground()
        status = topic('sta_rate_ctrl_status')
        if not healthy(status):
            raise RuntimeError('控制器存在故障 latch，请排查后重启仿真。')
        if accepted(status, mode, axes):
            sequence = status.get('publish_seq')
            if previous is not None and sequence != previous:
                return status
            previous = sequence
        else:
            previous = None
        time.sleep(.2)
    raise RuntimeError('参数尚未实际生效或状态未清零，请排查后重启仿真。')


@contextmanager
def lock():
    STATE.mkdir(exist_ok=True)
    with (STATE / 'operation.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('另一个便捷脚本正在操作，请等待它完成。') from None
        yield


def controlled_names():
    return [*frozen_config(), 'MC_RATT_TEST', *load(RESEARCH / 'm06/protocol.json')['scenario_parameters']]


def backup():
    if BACKUP.exists():
        saved = load(BACKUP)
        if saved.get('repository') != str(ROOT) or set(saved.get('parameters', {})) != set(controlled_names()):
            raise RuntimeError('本地参数备份不匹配，请检查 ' + str(BACKUP))
        return
    saved = dict(repository=str(ROOT), created=datetime.now().isoformat(),
                 parameters={name: parameter(name) for name in controlled_names()})
    with BACKUP.open('x') as stream:
        json.dump(saved, stream, indent=2)
        stream.write('\n')


def set_parameter(name, value):
    ground()  # Recheck before each write, including when another UI is open.
    cli('param', 'set', name, value)
    actual = parameter(name)
    if not math.isclose(actual, value, rel_tol=1e-6, abs_tol=1e-5):
        raise RuntimeError(f'参数读回不一致：{name} 期望 {value}，读回 {actual}')


def apply_parameters(values):
    set_parameter('MC_RTC_MODE', 0)
    set_parameter('MC_STA_AXES', 0)
    set_parameter('MC_RATT_TEST', 0)
    wait_selection(0, 0)
    for name, value in values.items():
        if name not in ('MC_RTC_MODE', 'MC_STA_AXES', 'MC_RATT_TEST'):
            set_parameter(name, value)
    set_parameter('MC_STA_AXES', values['MC_STA_AXES'])
    set_parameter('MC_RTC_MODE', values['MC_RTC_MODE'])
    wait_selection(values['MC_RTC_MODE'], values['MC_STA_AXES'])
    set_parameter('MC_RATT_TEST', values.get('MC_RATT_TEST', 0))


def switch(mode, axes):
    ground()
    if not healthy(topic('sta_rate_ctrl_status')):
        raise RuntimeError('控制器故障尚未清除，请排查后重启仿真。')
    config = frozen_config(mode)
    if mode:
        for path, expected in load(RESEARCH / 'm06/calibration.json')['files'].items():
            if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
                raise RuntimeError('标定模型文件发生变化：' + path)
    backup()
    values = config if mode else {}
    values.update(load(RESEARCH / 'm06/protocol.json')['scenario_parameters'])
    values.update(MC_RTC_MODE=mode, MC_STA_AXES=axes, MC_RATT_TEST=0)
    apply_parameters(values)
    print(f'已生效：{MODE_NAMES[mode].upper()}，AXES={axes}；已应用相同场景参数。')
    if mode == 2:
        print('ISTA使用M08候选02：pitch lambda1=2.0；ESTA冻结值为2.4，非同增益离散化比较。')
    print('现在可以执行 ./sim_scripts/fly.sh hover、figure8 或 yaw。')


def restore():
    ground()
    if not BACKUP.exists():
        raise RuntimeError('没有本工具保存的参数备份。')
    backup()  # Validate ownership and schema without overwriting the backup.
    values = load(BACKUP)['parameters']
    if values['MC_RTC_MODE'] not in MODE_NAMES or values['MC_STA_AXES'] not in (0, 1, 3, 7):
        raise RuntimeError('备份包含本工具不支持的模式/轴，请人工核查。')
    apply_parameters(values)
    ground()
    cli('param', 'save')
    archive = STATE / ('restored-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
    BACKUP.rename(archive)
    print('原参数已恢复并保存；备份归档于 ' + str(archive))


def show_status():
    status = topic('sta_rate_ctrl_status')
    print('Iris airframe:', parameter('SYS_AUTOSTART'))
    for name in ('requested_mode', 'effective_mode', 'requested_axes', 'effective_axes', 'armed', 'landed',
                 'config_valid', 'pending', 'config_pending', 'fault', 'abort_requested', 'nu', 'pid_updated'):
        print(f'{name}: {status.get(name, "缺失")}')
    print('MODE: 0=PID，1=ESTA，2=ISTA；AXES: 1=roll，3=roll/pitch，7=三轴')


def stop_simulator():
    ground()
    shutdown_error = None
    try:
        cli('shutdown')
    except RuntimeError as exc:
        # PX4 may close its command socket before replying to its client.
        shutdown_error = exc
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if not processes({'px4', 'gzserver', 'gzclient', 'gazebo'}):
            print('PX4 与 Gazebo 已退出。')
            return
        time.sleep(.2)
    raise RuntimeError('仿真进程尚未全部退出，请检查启动终端。' +
                       (str(shutdown_error) if shutdown_error else ''))


def experiment(kind, output):
    no_simulator(include_qgc=True)
    env = environment()
    subprocess.run([sys.executable, '-c', 'import numpy, pymavlink, pyulog'], env=env, check=True)
    frozen_config()
    folder = output.resolve() if output else HERE / 'experiments' / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-' + kind)
    folder.mkdir(parents=True, exist_ok=False)
    print('实验输出：' + str(folder), flush=True)
    scripts = RESEARCH / 'scripts'
    plan = [('pid', 0), ('esta', 1)] if kind == 'compare' else [(kind, int(kind == 'esta'))]
    for label, mode in plan:
        for index in range(1, 4 if kind == 'compare' else 2):
            name = f'{label}{index:02d}'
            run = folder / name
            run_env = dict(env, M06_MODE=str(mode))
            print(f'运行 {name}（起飞→60秒悬停/激励→降落），控制台文件：{name}.run.log', flush=True)
            with (folder / (name + '.run.log')).open('x') as stream:
                subprocess.run([sys.executable, str(scripts / 'run_m06.py'), '--output', str(run)],
                               cwd=ROOT, env=run_env, stdout=stream, stderr=subprocess.STDOUT, check=True)
            with (folder / (name + '.analysis.log')).open('x') as stream:
                subprocess.run([sys.executable, str(scripts / 'analyze_m06.py'), str(run)],
                               cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
            print(name + ' 流程及日志验收通过。', flush=True)
    if kind == 'compare':
        cmd = [sys.executable, str(scripts / 'compare_m06.py'), '--pid']
        cmd += [str(folder / f'pid{i:02d}') for i in range(1, 4)]
        cmd += ['--esta'] + [str(folder / f'esta{i:02d}') for i in range(1, 4)]
        cmd += ['--output', str(folder / 'comparison.json')]
        subprocess.run(cmd, cwd=ROOT, env=env, check=True)
        print('PID/ESTA 各三轮比较通过：' + str(folder / 'comparison.json'))
    print('数据和失败记录均保留在：' + str(folder))


def main():
    parser = argparse.ArgumentParser(description='Iris SITL 便捷工具；在普通 Linux 终端运行。')
    commands = parser.add_subparsers(dest='command', required=True)
    start = commands.add_parser('start', help='使用项目启动脚本打开 Gazebo + PX4')
    start.add_argument('--headless', action='store_true', help='无图形界面')
    commands.add_parser('build', help='编译当前 SITL 固件')
    commands.add_parser('pid', help='地面切回 PID，并使用 M06 场景')
    select = commands.add_parser('switch', help='选择飞行任务使用的控制算法')
    select.add_argument('algorithm', choices=MODES)
    flight = commands.add_parser('fly', help='使用当前算法，在已经打开的仿真中执行任务')
    flight.add_argument('task', choices=('hover', 'figure8', 'yaw'), nargs='?', default='hover')
    esta = commands.add_parser('esta', help='地面加载 M06 ESTA 参数')
    esta.add_argument('axes', choices=AXES, nargs='?', default='rpy')
    commands.add_parser('status', help='查看实际模式、轴及状态')
    commands.add_parser('restore', help='恢复首次切换前的参数并保存')
    commands.add_parser('stop', help='降落上锁后关闭本仓库 SITL')
    exp = commands.add_parser('experiment', help='自动起降、激励、解码与比较')
    exp.add_argument('kind', choices=('pid', 'esta', 'compare'))
    exp.add_argument('--output', type=Path, help='新的输出目录（必须不存在）')
    args = parser.parse_args()
    if args.command == 'fly':
        os.execve(sys.executable, [sys.executable, str(HERE / '_internal/flight.py'), args.task], environment())
    if args.command == 'status':
        show_status()
        return
    with lock():
        if args.command == 'build':
            no_simulator()
            subprocess.run(['make', 'px4_sitl_default'], cwd=ROOT, env=environment(), check=True)
        elif args.command == 'start':
            no_simulator()
            if not (BIN / 'px4').is_file():
                raise RuntimeError('尚未构建SITL，请先执行 make px4_sitl_default。')
            command = ['./sitl/run.sh', '--backend', 'gazebo', '--model', 'iris']
            if args.headless:
                command.append('--headless')
            print('启动后在另一个终端执行 switch.sh pid|esta|ista，再执行 fly.sh hover|figure8|yaw。', flush=True)
            # Release the short-operation lock before the foreground launcher.
        elif args.command == 'pid':
            switch(0, 0)
        elif args.command == 'switch':
            switch(MODES[args.algorithm], 0 if args.algorithm == 'pid' else 7)
        elif args.command == 'esta':
            switch(1, AXES[args.axes])
        elif args.command == 'restore':
            restore()
        elif args.command == 'stop':
            stop_simulator()
        elif args.command == 'experiment':
            experiment(args.kind, args.output)
    if args.command == 'start':
        os.chdir(ROOT)
        os.execve(str(ROOT / command[0]), command, environment())


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print('错误：' + str(exc), file=sys.stderr)
        print('请根据错误信息排查；切换和飞行必须在地面上锁状态开始。', file=sys.stderr)
        sys.exit(1)
