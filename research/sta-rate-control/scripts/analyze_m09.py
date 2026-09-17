#!/usr/bin/env python3
"""M09 actual-update semantics, host wall costs, TV and anti-aliased spectra."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from analyze_m00 import analyze, plain
from analyze_m03 import vector, pid_output, require, sequence_stats
from analyze_m04 import check_gyro_events
from m08_ista_reference import ideal


def spectrum(x, hz):
    x = np.asarray(x, dtype=float)
    window = np.hanning(len(x))
    f = np.fft.rfftfreq(len(x), 1/hz)
    fft = np.fft.rfft((x-x.mean(axis=0))*window[:, None], axis=0)
    psd = abs(fft)**2/(hz*np.sum(window**2))
    # Odd lengths have no Nyquist bin: their final positive bin also doubles.
    psd[1:-1 if len(x)%2 == 0 else None] *= 2
    return f, psd


def common_band(x, callback_hz):
    # 513-tap symmetric Blackman FIR, 22 Hz cutoff at nominal 250 Hz.
    # Valid convolution drops edges (no zero-padded flight transient).
    m = np.arange(513)-256
    cutoff = .088 * callback_hz
    kernel = 2*cutoff/callback_hz*np.sinc(2*cutoff/callback_hz*m)*np.blackman(513)
    kernel /= kernel.sum()
    filtered = np.column_stack([np.convolve(x[:, i], kernel, mode='valid') for i in range(3)])
    return filtered[::4], callback_hz/4


def tv(t, command, window_seconds=None):
    require(len(t) > 2 and np.all(np.diff(t) > 0), 'TV requires real ordered updates')
    duration = (int(t[-1])-int(t[0]))*1e-6
    total = np.sum(np.abs(np.diff(command.astype(float), axis=0)), axis=0)
    normalization = duration if window_seconds is None else window_seconds
    require(normalization >= duration-1e-9 and normalization > 0, 'Invalid TV window')
    return dict(actual_update_span_s=duration, duration_s=normalization, tv=total.tolist(), tv_per_s=(total/normalization).tolist())


def main(run, suffix=''):
    result = json.loads((run/'result.json').read_text())
    require(result['success'], 'Scenario failed')
    config = json.loads((run/'m04_config.json').read_text())
    profile = json.loads((run/'m03_logging.json').read_text())
    require(profile['research_profile'] == profile['original_profile'] | 16, 'Logger bit preservation')
    logs = []
    for index, item in enumerate(result['logs']):
        path = Path(item['archive'])
        require(hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], 'ULog fingerprint')
        log = ULog(str(path))
        if log.initial_parameters.get('SDLOG_PROFILE') == profile['research_profile']:
            logs.append((index, log, str(path)))
    require(len(logs) == 1, 'Exactly one research log required')
    index, log, log_path = logs[0]
    analyze(run, log_index=index)
    metrics = json.loads((run/'metrics.json').read_text())
    d = log.get_dataset('sta_rate_ctrl_status').data
    t = d['timestamp_sample'].astype(np.int64)
    armed = d['armed'].astype(bool)
    update = d['updated'].astype(bool)
    held = d['held'].astype(bool)
    div = int(config['MC_RTC_DIV']); mode = int(config['MC_RTC_MODE'])
    require(np.all(np.diff(t) > 0), 'Nonmonotonic sample time')
    require(np.all(np.diff(d['publish_seq'].astype(np.int64)) == 1), 'Missing diagnostics: no TV/spectrum acceptance')
    require(np.all(np.diff(d['update_seq'].astype(np.int64)) == update[1:]), 'Actual update counter')
    require(np.all(np.diff(d['pid_update_seq'].astype(np.int64)) == d['pid_updated'][1:]), 'PID counter')
    require(np.all(d['div_eff'] == div) and np.all(d['effective_mode'] == mode), 'Effective config drift')
    require(np.all(d['effective_axes'] == (7 if mode else 0)), 'Axes mismatch')
    for key in ('fault', 'abort_requested', 'pending', 'div_wait', 'termination'):
        require(not np.any(d[key]), key)
    for key in ('measurement_valid', 'output_valid', 'div_ok', 'config_valid'):
        require(np.all(d[key][armed]), key)
    require(np.all(d['timing_status'][armed] == 0), 'Raw callback time invalid')
    require(np.all(update[armed] ^ held[armed]), 'Update/hold partition')
    require(np.all(d['pid_updated'][armed] == (update[armed] if mode == 0 else False)), 'Idle/missing PID execution')
    require(np.all(np.isnan(d['dt'][held])), 'Held cycle must not claim new dt')
    require(np.all(d['kern_ns'][held] == 0), 'Held cycle evaluated kernel')
    require(np.all(d['clock'] == 1) and np.all(d['mod_ns'] > 0), 'Missing host clock')
    require(np.all(d['kern_ns'][update] > 0), 'Missing measured kernel cost')
    nu = vector(d, 'nu'); before = vector(d, 'nu_before')
    command = vector(d, 'c_held'); applied = vector(d, 'c_applied')
    require(np.array_equal(nu[held], before[held]), 'Nu advanced on hold')
    require(np.array_equal(vector(d, 'pid_integral_before')[held], vector(d, 'pid_integral_after')[held]), 'PID integrated on hold')
    hidx = np.flatnonzero(held); hidx = hidx[hidx > 0]
    require(np.array_equal(command[hidx], command[hidx-1]), 'Held torque changed')
    require(np.array_equal(applied[armed], (command*d['battery_scale'][:, None])[armed]), 'Battery scale/cached output mismatch')
    require(np.all(np.isfinite(applied[armed])), 'Invalid output')
    require(np.all(np.abs(vector(d,'rate')[armed]) <= 1), 'Rate boundary')
    require(np.all(np.abs(applied[armed,:2]) <= .150001), 'R/P command boundary')
    require(np.all(np.abs(applied[armed,2]) <= (0.150001 if mode else 1.000001)), 'Yaw boundary')
    require(np.all(np.abs(nu[armed]) <= 3.000001), 'Nu boundary')
    # Compare the real actuator publication, including held callbacks and thrust.
    act = log.get_dataset('actuator_controls_0').data
    common,di,ai = np.intersect1d(t[armed],act['timestamp_sample'],return_indices=True)
    di = np.flatnonzero(armed)[di]
    actual = np.column_stack([act[f'control[{i}]'][ai] for i in range(3)])
    require(len(common)>1000 and np.array_equal(actual,applied[di]), 'Published actuator torque differs')
    require(np.array_equal(act['control[3]'][ai],d['thrust'][di]), 'Published thrust differs')
    if div > 1:
        require(np.count_nonzero(d['thrust'][hidx] != d['thrust'][hidx-1]) > 100, 'Thrust apparently frozen with torque')
    continuous = np.flatnonzero((d['reset_reason'] == 0) & armed)
    continuous = continuous[continuous>0]
    require(np.array_equal(before[continuous],nu[continuous-1]), 'Stale/cross-cycle nu')
    check_gyro_events(log.get_dataset('gyro_sample_status').data, t)
    hover = (t >= metrics['hover_start_us']) & (t <= metrics['hover_end_us'])
    idx = np.flatnonzero(hover & update)
    require(len(idx) > 1000 and np.all(np.diff(idx) == div), 'Measured update spacing/count')
    expected_h = np.diff(t[idx]).astype(np.float32)*np.float32(1e-6)
    require(np.allclose(d['dt'][idx[1:]], expected_h, atol=2e-9, rtol=0), 'Actual sensor update interval')
    require(np.all(d['sat_n'][idx[1:]] == div), 'Saturation interval count')
    all_updates = np.flatnonzero(update)
    for left,right in zip(all_updates[:-1],all_updates[1:]):
        if np.all(d['rate_enabled'][left:right+1]) and not np.any(d['fault'][left:right+1]):
            require(np.isclose(d['dt'][right],np.float32(t[right]-t[left])*np.float32(1e-6),rtol=0,atol=2e-9),
                    'Lifecycle update lost actual elapsed sensor time')
    # Independently recompute the interval OR and validity from consumed feedback.
    for j in idx[1:]:
        bits = np.bitwise_or.reduce(d['motor_saturation'][j-div+1:j+1])
        valid = bool(np.all(d['motor_valid'][j-div+1:j+1]))
        expected_bits = int(bits) if valid else int(bits) & ~1
        require(d['sat_bits'][j] == expected_bits and bool(d['sat_valid'][j]) == valid, 'Interval feedback mismatch')
    if mode == 0:
        predicted = pid_output(d)
        require(np.array_equal(predicted[update], command[update]), 'PID output is not bitwise original expression')
    else:
        use = armed & update
        s = vector(d,'s')[use]; old = before[use]; h = d['dt'][use,None]
        l1 = vector(d,'lambda1')[use]; l2 = vector(d,'lambda2')[use]; g = vector(d,'g')[use]
        if mode == 1:
            a = -l1*np.sqrt(np.abs(s))*np.sign(s)+old
            candidate = old-h*l2*np.sign(s)
        else:
            r = ideal(s,old,h,l1,l2,g); a=r['a']; candidate=r['nu']
            require(np.allclose(vector(d,'xi')[use],r['xi'],atol=2e-6), 'ISTA xi')
            require(np.array_equal(vector(d,'ista_branch')[use], r['branch']), 'ISTA branch')
        require(np.allclose(vector(d,'a_raw')[use],a,atol=3e-6,rtol=2e-6), 'Ideal algorithm dt/output')
        require(np.allclose(vector(d,'nu_candidate')[use],candidate,atol=2e-6), 'Ideal nu candidate')
        protected_a = a if mode == 1 else a + (nu[use]-candidate)
        require(np.allclose(command[use],np.clip(protected_a/g,-.15,.15),atol=2e-7), 'Protected output mapping')
    tracking = hover & (d['research_elapsed'] >= 0) & (d['research_elapsed'] <= 36)
    require(np.count_nonzero(tracking) > 8000, 'Incomplete 36 s excitation')
    callback_dt = np.diff(t[tracking])
    require(np.max(callback_dt) == np.min(callback_dt), 'Nonuniform flight: spectrum not valid without resampling design')
    hz = 1e6/float(np.median(callback_dt))
    uidx = np.flatnonzero(tracking & update)
    native_hz = (len(uidx)-1)/((t[uidx[-1]]-t[uidx[0]])*1e-6)
    native_f,native_psd = spectrum(applied[uidx],native_hz)
    filtered,common_hz = common_band(applied[tracking],hz)
    cf,cp = spectrum(filtered,common_hz)
    np.savez_compressed(run/f'm09_spectra{suffix}.npz',native_hz=native_f,native_psd=native_psd,common_hz=cf,common_psd=cp)
    def costs(values):
        return dict(count=len(values),median_ns=float(np.median(values)),p95_ns=float(np.percentile(values,95)),
                    p99_ns=float(np.percentile(values,99)),max_ns=int(np.max(values)))
    motor = log.get_dataset('multirotor_motor_limits').data
    mm = (motor['timestamp'] >= metrics['hover_start_us']) & (motor['timestamp'] <= metrics['hover_end_us'])
    output = dict(success=True,analysis_version=2,mode=mode,div=div,ulog=log_path,callback_hz=hz,update_hz=native_hz,
                  hover_updates=len(idx),hover_callbacks=int(np.count_nonzero(hover)),
                  actual_dt_s=dict(min=float(d['dt'][idx].min()),max=float(d['dt'][idx].max())),
                  tv_actual_updates=tv(t[uidx],applied[uidx],36.0),
                  actuator_samples_checked=len(common),
                  rmse_tracking=np.sqrt(np.mean(vector(d,'s')[tracking].astype(float)**2,axis=0)).tolist(),
                  rmse_hover=np.sqrt(np.mean(vector(d,'s')[hover].astype(float)**2,axis=0)).tolist(),
                  kernel_cost=costs(d['kern_ns'][hover & update]),module_cost=costs(d['mod_ns'][hover]),
                  kernel_wall_ns_per_sim_second=float(np.sum(d['kern_ns'][hover]))/metrics['hover_duration_s'],
                  module_wall_ns_per_sim_second=float(np.sum(d['mod_ns'][hover]))/metrics['hover_duration_s'],
                  native_highband_rms=np.sqrt(np.sum(native_psd[native_f>20],axis=0)*(native_f[1]-native_f[0])).tolist(),
                  common_0_20hz_rms=np.sqrt(np.sum(cp[cf<=20],axis=0)*(cf[1]-cf[0])).tolist(),
                  common_grid_hz=common_hz,spectrum_edge_trim_s=256/hz,
                  ulog_dropouts=len(log.dropouts),
                  motor_original=sequence_stats(motor['update_seq'][mm],motor['timestamp'][mm]))
    require(metrics['tilt_deg']['max_abs'] <= 15, 'Tilt boundary')
    require(metrics['position_error_m']['max_abs'][2] <= 1, 'Height boundary')
    (run/f'm09_analysis{suffix}.json').write_text(json.dumps(output,indent=2,default=plain)+'\n')
    print(json.dumps(output,indent=2,default=plain))
    return output


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--suffix',default='')
    args=p.parse_args();main(args.run.resolve(),args.suffix)
