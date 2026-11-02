#!/usr/bin/env python3
"""Plot only the eight new, successful, independently replayed Offboard runs.

This offline tool reads native ULog samples and never starts ROS or a simulator.
It deliberately does not depend on analyze.py's derived metrics schema.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

SYSTEMS = ('PID', 'STA2', 'RSTA', 'RISTA')
TASKS = ('position', 'velocity')
COLORS = dict(zip(SYSTEMS, ('#0072B2', '#D55E00', '#009E73', '#CC79A7')))
MAX_GAP_US = 500000
TARGET_ATOL = 1e-5


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def read_json(path):
    path = Path(path)
    require(path.is_file(), 'Missing evidence file: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8'))


def native_clock(data, prefer_sample=True):
    field = 'timestamp_sample' if prefer_sample and 'timestamp_sample' in data else 'timestamp'
    require(field in data, 'Missing native clock: ' + field)
    raw = np.asarray(data[field])
    require(raw.ndim == 1 and len(raw) >= 2 and np.isfinite(raw).all(), 'Invalid native clock')
    require(np.all(raw > 0) and np.all(raw < np.iinfo(np.int64).max), 'Invalid native clock range')
    times = raw.astype(np.int64)
    require(np.array_equal(raw, times) and np.all(np.diff(times) > 0),
            'Native clock must be integer and strictly increasing; no sorting/deduplication')
    return times, field


def column(data, field, length):
    require(field in data, 'Missing native field: ' + field)
    value = np.asarray(data[field], dtype=float)
    require(value.shape == (length,), 'Wrong native field shape: ' + field)
    return value


def trajectory_z(data):
    times, unused = native_clock(data, prefer_sample=False)
    scalar = 'z' in data and 'vz' in data
    array = 'position[2]' in data and 'velocity[2]' in data
    require(scalar != array, 'Missing or ambiguous native trajectory Z layout')
    names = ('z', 'vz') if scalar else ('position[2]', 'velocity[2]')
    return times, column(data, names[0], len(times)), column(data, names[1], len(times))


def phase_window(events, phase):
    """Ignore control_change and additional fields; pair the requested unique phase."""
    edges = {}
    for event in events:
        if event.get('name') not in (phase + '_start', phase + '_end'):
            continue
        edge = event['name'].rsplit('_', 1)[1]
        require(edge not in edges, 'Ambiguous repeated response phase: ' + phase)
        timestamp = event.get('timestamp_us')
        require(type(timestamp) is int and timestamp > 0, 'Invalid event timestamp: ' + phase)
        edges[edge] = timestamp
    require(set(edges) == {'start', 'end'} and edges['start'] < edges['end'],
            'Missing/reversed phase boundaries: ' + phase)
    return edges['start'], edges['end']


def unique_event(events, name):
    matches = [event.get('timestamp_us') for event in events if event.get('name') == name]
    require(len(matches) == 1 and type(matches[0]) is int and matches[0] > 0,
            'Missing/ambiguous event: ' + name)
    return matches[0]


def response_metrics(times_us, actual, t0_us, end_us, requested_target, minimum_settle_s=1.0):
    """Native-sample response; null means not observed within this command window.

    Baseline is the last actual sample strictly before native target receipt.
    Crossing times are first observed samples, accompanied by their original
    sampling brackets. No interpolated timing or eventual-response extrapolation.
    """
    t, unused = native_clock({'timestamp': times_us})
    y = np.asarray(actual, dtype=float)
    require(y.shape == t.shape, 'Actual/clock shape mismatch')
    require(type(t0_us) is int and type(end_us) is int and 0 < t0_us < end_us,
            'Invalid response interval')
    require(math.isfinite(float(requested_target)) and minimum_settle_s > 0,
            'Invalid response target or settling duration')
    predecessor = int(np.searchsorted(t, t0_us, side='left') - 1)
    require(predecessor >= 0 and t0_us - t[predecessor] <= MAX_GAP_US,
            'Missing recent native baseline before target receipt')
    selected = np.flatnonzero((t >= t0_us) & (t < end_us))
    require(len(selected) >= 2, 'Missing native response samples')
    indices = np.r_[predecessor, selected]
    require(np.isfinite(y[indices]).all(), 'Nonfinite actual response sample')
    require(t[selected[0]] - t0_us <= MAX_GAP_US and end_us - t[selected[-1]] <= MAX_GAP_US,
            'Missing native response window edge')
    require(np.max(np.diff(t[indices])) <= MAX_GAP_US, 'Native response gap exceeds 0.5 s')
    baseline = float(y[predecessor])
    delta = float(requested_target) - baseline
    require(abs(delta) > 1e-9, 'Requested target equals measured baseline; response is undefined')
    progress = (y[selected] - baseline) / delta

    def crossing(fraction):
        # Only absorb floating-point arithmetic roundoff, not measurement error
        # or a physical tolerance that would advance a genuine crossing.
        hits = np.flatnonzero(progress >= fraction - 8 * np.finfo(float).eps)
        if not len(hits):
            return None
        index = int(selected[int(hits[0])])
        before = index - 1
        return dict(first_observed_s=float((t[index] - t0_us) * 1e-6),
                    sample_bracket_us=[int(t[before]), int(t[index])],
                    relative_sample_bracket_s=[float((t[before] - t0_us) * 1e-6),
                                               float((t[index] - t0_us) * 1e-6)],
                    actual_bracket=[float(y[before]), float(y[index])])

    c10, c90 = crossing(.1), crossing(.9)
    rise = None
    rise_bounds = None
    if c10 is not None and c90 is not None:
        rise = max(0.0, c90['first_observed_s'] - c10['first_observed_s'])
        lo10, hi10 = c10['relative_sample_bracket_s']
        lo90, hi90 = c90['relative_sample_bracket_s']
        rise_bounds = [max(0.0, lo90 - hi10), max(0.0, hi90 - lo10)]
    band = .05 * abs(delta)
    in_band = np.abs(y[selected] - requested_target) <= band + 1e-12
    outside = np.flatnonzero(~in_band)
    candidate = int(outside[-1] + 1) if len(outside) else 0
    settling = None
    settled_duration = None
    settling_bracket = None
    if candidate < len(selected):
        index = int(selected[candidate])
        observed_duration = float((t[selected[-1]] - t[index]) * 1e-6)
        if observed_duration + 1e-12 >= minimum_settle_s:
            settling = float((t[index] - t0_us) * 1e-6)
            settled_duration = observed_duration
            settling_bracket = [int(t[index - 1]), int(t[index])]
    peak_progress = float(np.max(progress))
    return dict(
        t0_us=t0_us, end_us=end_us, command_window_s=(end_us - t0_us) * 1e-6,
        baseline=baseline, baseline_sample_us=int(t[predecessor]),
        baseline_age_s=float((t0_us - t[predecessor]) * 1e-6),
        requested_target=float(requested_target), requested_change=delta,
        threshold_10=baseline + .1 * delta, threshold_90=baseline + .9 * delta,
        crossing_10=c10, crossing_90=c90, rise_10_90_s=rise,
        rise_10_90_native_bounds_s=rise_bounds,
        settling_5pct_s=settling, settling_sample_bracket_us=settling_bracket,
        settling_band_absolute=band, minimum_settle_s=minimum_settle_s,
        observed_final_in_band_duration_s=settled_duration,
        overshoot_percent=max(0.0, peak_progress - 1.0) * 100.0,
        overshoot_absolute=max(0.0, peak_progress - 1.0) * abs(delta),
        response_samples=len(selected), final_sample_us=int(t[selected[-1]]),
        final_sample_to_command_end_s=float((end_us - t[selected[-1]]) * 1e-6),
        native_max_interval_s=float(np.max(np.diff(t[indices])) * 1e-6),
        interpretation='Single descriptive run; null means not observed in this finite command window, not a flight failure.')


def command_windows(task, events, trajectory):
    """Find command receipt in trajectory_setpoint, never from takeoff commands."""
    times, position_z, velocity_z = trajectory_z(trajectory)
    commands = []
    if task == 'position':
        for phase in ('step_up', 'step_down'):
            start, end = phase_window(events, phase)
            candidates = np.flatnonzero((times >= start) & (times < end))
            changes = [int(i) for i in candidates if i > 0 and np.isfinite(position_z[i])
                       and np.isfinite(position_z[i - 1])
                       and not np.isclose(position_z[i], position_z[i - 1], rtol=0, atol=TARGET_ATOL)]
            require(changes, 'Missing received native position target step: ' + phase)
            index = changes[0]
            require(times[index] - start <= MAX_GAP_US, 'Late native position target receipt: ' + phase)
            target = float(position_z[index])
            require((target < position_z[index - 1]) == (phase == 'step_up'), 'Wrong native position step direction')
            # A second changed target ends the command. Same-target recovery
            # cannot extend this prescribed phase's response observation.
            later = np.flatnonzero((times > times[index]) & (times < end)
                                   & (~np.isfinite(position_z) | ~np.isclose(position_z, target, rtol=0, atol=TARGET_ATOL)))
            actual_end = min(end, int(times[later[0]]) if len(later) else end)
            commands.append(dict(name=phase, kind='position', t0_us=int(times[index]),
                                 end_us=actual_end, target=target, display_seconds=8.0,
                                 scheduled_start_us=start, scheduled_end_us=end))
    elif task == 'velocity':
        start, end = phase_window(events, 'velocity')
        indices = np.flatnonzero((times >= start) & (times < end) & np.isfinite(velocity_z))
        require(len(indices) >= 4, 'Missing received native velocity pulse sequence')
        changes = [int(indices[0])]
        for index in indices[1:]:
            if not np.isclose(velocity_z[index], velocity_z[changes[-1]], rtol=0, atol=TARGET_ATOL):
                changes.append(int(index))
        values = velocity_z[changes]
        require(len(changes) == 4 and np.allclose(values, [-.2, 0., .2, 0.], rtol=0, atol=TARGET_ATOL),
                'Native velocity sequence must be up 2 s / zero 4 s / down 2 s / zero 4 s')
        require(times[changes[0]] - start <= MAX_GAP_US, 'Late native velocity target receipt')
        boundaries = [int(times[index]) for index in changes] + [end]
        for duration, left, right in zip((2., 4., 2., 4.), boundaries, boundaries[1:]):
            require(abs((right - left) * 1e-6 - duration) <= .5, 'Wrong native velocity segment duration')
        for label, offset in (('pulse_up', 0), ('pulse_down', 2)):
            index = changes[offset]
            commands.append(dict(name=label, kind='velocity', t0_us=int(times[index]),
                                 end_us=int(times[changes[offset + 1]]), target=float(velocity_z[index]),
                                 display_seconds=2.0, scheduled_start_us=start,
                                 scheduled_end_us=end, short_pulse=True))
    else:
        raise ValueError('Unknown task')
    return commands


def audit_inputs(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    manifest = read_json(manifest_path)
    jobs = manifest.get('jobs')
    expected = [(f'O{index:03d}', task, system) for index, (task, system) in
                enumerate(((task, system) for task in TASKS for system in SYSTEMS), 1)]
    require(isinstance(jobs, list) and len(jobs) == 8, 'Require exactly eight new jobs')
    require([(job.get('id'), job.get('task'), job.get('system')) for job in jobs] == expected,
            'Require new O001–O008 task/system order')
    require(manifest.get('order') == [row[0] for row in expected], 'Invalid manifest order')
    root = Path(manifest.get('data_root', ''))
    require(root.is_absolute(), 'Manifest data_root must be absolute')
    root = root.resolve()
    manifest_digest = sha256(manifest_path)
    records, selected_hashes = [], set()
    for job in jobs:
        run_dir = root / 'runs' / job['id']
        result_path = run_dir / 'result.json'
        result = read_json(result_path)
        require(all(result.get(key) == job[key] for key in ('id', 'task', 'system')), 'Result identity mismatch')
        require(result.get('success') is True and result.get('independent_replay_passed') is True,
                'Require success and independent_replay_passed: ' + job['id'])
        require(result.get('manifest_sha256') == manifest_digest, 'Result manifest SHA256 mismatch')
        origin = read_json(run_dir / 'origin.json')
        require(isinstance(origin, dict) and all(type(origin.get(k)) in (int, float)
                and math.isfinite(origin[k]) for k in ('x', 'y', 'z', 'heading')), 'Missing/invalid origin')
        logs = result.get('logs')
        require(isinstance(logs, list) and logs, 'Missing archived native ULog')
        checked = []
        for row in logs:
            path = Path(row.get('archive', ''))
            path = path if path.is_absolute() else run_dir / path
            path = path.resolve()
            require(path.parent == run_dir.resolve() and re.fullmatch(r'native_\d+\.ulg', path.name),
                    'Native archive must belong to this new run')
            require(path.is_file(), 'Missing archived native ULog: ' + str(path))
            require(type(row.get('bytes')) is int and row['bytes'] == path.stat().st_size and row['bytes'] > 0,
                    'Native archive byte count mismatch')
            checked.append((row, path))
        selected, path = max(checked, key=lambda pair: pair[1].stat().st_size)
        digest = sha256(path)
        require(digest == selected.get('sha256'), 'Native largest ULog SHA256 mismatch')
        require(digest not in selected_hashes, 'Reused native ULog across new runs')
        selected_hashes.add(digest)
        events = result.get('events')
        require(isinstance(events, list) and all(isinstance(event, dict) for event in events), 'Missing task events')
        records.append(dict(job=job, result=result, origin=origin, events=events, path=path,
                            sha256=digest, result_path=result_path))
    return manifest, records


def one_topic(log, name):
    matches = [item for item in log.data_list if item.name == name and item.multi_id == 0]
    require(len(matches) == 1, 'Missing/ambiguous native topic: ' + name)
    return matches[0].data


def load_run(record, ulog_class=None):
    if ulog_class is None:
        from pyulog import ULog
        ulog_class = ULog
    log = ulog_class(str(record['path']), message_name_filter_list=['vehicle_local_position', 'trajectory_setpoint'])
    require(not getattr(log, 'file_corruption', False) and not getattr(log, 'dropouts', []),
            'Corrupt/dropped native ULog cannot be plotted as accepted evidence')
    local = one_topic(log, 'vehicle_local_position')
    times, clock_field = native_clock(local)
    position = np.column_stack([column(local, key, len(times)) for key in ('x', 'y', 'z')])
    velocity = np.column_stack([column(local, key, len(times)) for key in ('vx', 'vy', 'vz')])
    trajectory = one_topic(log, 'trajectory_setpoint')
    start = unique_event(record['events'], 'climb_start')
    end = unique_event(record['events'], 'landed_disarmed')
    require(start < end, 'Reversed flight display window')
    mask = (times >= start) & (times <= end)
    require(np.count_nonzero(mask) >= 2 and np.isfinite(position[mask]).all()
            and np.isfinite(velocity[mask]).all(), 'Missing/nonfinite native flight samples')
    require(np.max(np.diff(times[mask])) <= MAX_GAP_US, 'Native flight gap exceeds 0.5 s')
    require(times[mask][0] - start <= MAX_GAP_US and end - times[mask][-1] <= MAX_GAP_US,
            'Missing native flight display edges')
    commands = command_windows(record['job']['task'], record['events'], trajectory)
    responses = []
    for command in commands:
        actual = position[:, 2] if command['kind'] == 'position' else velocity[:, 2]
        metrics = response_metrics(times, actual, command['t0_us'], command['end_us'], command['target'])
        responses.append(dict(command=command, metrics=metrics))
    return dict(record, time=times, position=position, velocity=velocity, clock_field=clock_field,
                display_start_us=start, display_end_us=end, display_mask=mask,
                trajectory=trajectory, responses=responses)


def pyplot():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.fonttype': 'none', 'savefig.dpi': 180})
    return plt


def save_figure(fig, output, stem):
    for suffix in ('png', 'svg'):
        fig.savefig(output / (stem + '.' + suffix), bbox_inches='tight')


def plot_xyz(task, runs, quantity, output):
    plt = pyplot()
    fig, axes = plt.subplots(3, 1, figsize=(10.5, 8), sharex=True, layout='constrained')
    for run in runs:
        system = run['job']['system']
        mask = run['display_mask']
        x = (run['time'][mask] - run['display_start_us']) * 1e-6
        values = run[quantity][mask].copy()
        if quantity == 'position':
            values -= np.asarray([run['origin'][key] for key in ('x', 'y', 'z')])
        for axis, data in zip(axes, values.T):
            axis.plot(x, data, color=COLORS[system], linestyle='-', linewidth=1.25, label=system)
    for index, axis in enumerate(axes):
        axis.set_ylabel(('Δ' if quantity == 'position' else 'V') + 'XYZ'[index]
                        + (' (m)' if quantity == 'position' else ' (m/s)'))
        axis.grid(alpha=.22)
        require(len(axis.lines) == 4 and all(line.get_linestyle() == '-' for line in axis.lines),
                'XYZ figures must contain exactly four solid actual curves')
    axes[0].legend(ncol=4, frameon=False)
    axes[-1].set_xlabel('Time from climb phase start (s)')
    title = 'Actual velocity' if quantity == 'velocity' else 'Position relative to each saved starting origin'
    fig.suptitle(task.capitalize() + ' task — ' + title + '\nNative EKF samples; NED north/east/down; one run per system')
    stem = f'{task}_actual_{quantity}_xyz'
    save_figure(fig, output, stem)
    plt.close(fig)
    return stem


def plot_responses(task, runs, output):
    plt = pyplot()
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 7), sharex=True, layout='constrained')
    for run in runs:
        system = run['job']['system']
        for index, response in enumerate(run['responses']):
            command = response['command']
            mask = (run['time'] >= command['t0_us']) & (run['time'] < command['end_us'])
            actual = run['position'][:, 2] - run['origin']['z'] if task == 'position' else run['velocity'][:, 2]
            axes[index].plot((run['time'][mask] - command['t0_us']) * 1e-6, actual[mask],
                             color=COLORS[system], linestyle='-', linewidth=1.35, label=system)
    for index, axis in enumerate(axes):
        axis.set_title(('Step up', 'Step down')[index] if task == 'position' else ('Upward 2 s pulse', 'Downward 2 s pulse')[index])
        axis.set_ylabel('Relative Z, down (m)' if task == 'position' else 'Vz, down (m/s)')
        axis.grid(alpha=.22)
        axis.set_xlim(0, 8 if task == 'position' else 2)
        require(len(axis.lines) == 4 and all(line.get_linestyle() == '-' for line in axis.lines),
                'Response figures must contain four solid actual curves')
    axes[0].legend(ncol=4, frameon=False)
    axes[-1].set_xlabel('Time from each native trajectory target receipt (s)')
    fig.suptitle(task.capitalize() + ' task — airborne Z response\nIndividual native receipt alignment; no time warping or takeoff-command alignment')
    stem = task + '_airborne_z_response'
    save_figure(fig, output, stem)
    plt.close(fig)
    return stem


def generate(manifest_path, output, ulog_class=None):
    output = Path(output).resolve()
    require(not output.exists(), 'Output already exists; choose a new directory')
    manifest, records = audit_inputs(manifest_path)
    runs = [load_run(record, ulog_class) for record in records]
    # All eight inputs must pass before any deliverable directory is created.
    output.mkdir(parents=True, exist_ok=False)
    figures = []
    for task in TASKS:
        selected = [run for run in runs if run['job']['task'] == task]
        for quantity in ('velocity', 'position'):
            figures.append(plot_xyz(task, selected, quantity, output))
        figures.append(plot_responses(task, selected, output))
    report = dict(schema=1, manifest=str(Path(manifest_path).resolve()), manifest_sha256=sha256(manifest_path),
                  interpretation='Descriptive n=1 per system/task; no statistical inference or historical supplementation.',
                  coordinate_frame='Local NED: X north, Y east, Z down; EKF measurements, not simulator truth.',
                  response_definition='Last native pre-receipt sample baseline to requested native target; first crossing sample brackets; 5% final suffix observed at least 1 s.',
                  figures=figures, runs=[])
    for run in runs:
        responses = []
        for response in run['responses']:
            value = dict(response['command'], **response['metrics'])
            value['target_relative_to_start'] = (value['target'] - run['origin']['z']) if value['kind'] == 'position' else None
            responses.append(value)
        report['runs'].append(dict(id=run['job']['id'], system=run['job']['system'], task=run['job']['task'],
            native_ulog=str(run['path']), native_ulog_sha256=run['sha256'],
            result_sha256=sha256(run['result_path']), origin=run['origin'], native_clock_field=run['clock_field'],
            display_start_us=run['display_start_us'], display_end_us=run['display_end_us'], responses=responses))
    (output / 'metrics.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    links = '\n'.join(f'- [{stem} PNG]({stem}.png) · [SVG]({stem}.svg)' for stem in figures)
    readme = '''# New Offboard replay: descriptive actual-state plots

Eight new runs only, one PID/STA2/RSTA/RISTA run per task. Every run must have
success=true, independent_replay_passed=true, a matching manifest fingerprint,
saved origin, and a verified run-local largest native ULog. No old samples fill gaps.

Velocity and relative-position figures are separate, with three XYZ subplots and
exactly four solid actual curves each. Coordinates are NED north/east/down; these
are native EKF measurements, not Gazebo truth. Each position origin is origin.json.
Flight time is aligned to climb phase start; no resampling, smoothing, or time warping.

Airborne Z figures align each run to its actual received trajectory target change.
The position display windows are 8 s. Velocity shows only the two nonzero 2 s pulses;
the complete native sequence is up 2 s / zero 4 s / down 2 s / zero 4 s. These short
pulses can end before 90% crossing or settling occurs. Metrics end at the actual
next target change, bounded by the phase end; exact observed duration is recorded.

The response baseline is the last actual native sample before target receipt.
10% and 90% thresholds are fractions of baseline-to-requested-target change, with
first-observed times and original native sampling brackets, not interpolated times.
Settling uses a 5% change-amplitude band and a final in-band observed suffix lasting
at least 1 s through the end of the command's available native samples. Null means
not observed within the command window, not a failed flight. Overshoot is relative
to requested change amplitude. Sampling coverage is checked; continuous behavior
between samples is not asserted. No target lines are repeated on actual-state plots.

These are n=1 descriptive comparisons, not statistical evidence of superiority.
See [metrics and provenance](metrics.json) for timings, hashes, and definitions.

''' + links + '\n'
    (output / 'README.md').write_text(readme, encoding='utf-8')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New output directory; existing paths are refused')
    args = parser.parse_args(argv)
    report = generate(args.manifest, args.output)
    print(json.dumps(dict(output=str(args.output.resolve()), runs=len(report['runs']), figures=report['figures'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
