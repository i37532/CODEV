#!/usr/bin/env python3
"""R00 read-only baseline audit. Prints JSON; never starts/builds a simulator.

Raw-log sampling is intentionally four AX05 main ULogs: the earliest PID and
XYZ record for each H/V task. This is not a new 320-run acceptance replay.
"""
import hashlib
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[5]
AX04 = REPO / 'research/sta-velocity-control/axis_ablation/ax04'
AX05 = REPO / 'research/sta-velocity-control/axis_ablation/ax05'
EXTERNAL = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-AXIS-ABLATION-20261008/AX05')
for dependency in (REPO / '.px4-python', Path('/home/yr/Desktop/codev doc/experiments/M00-20260912/python')):
    sys.path.insert(0, str(dependency))
sys.path.append(str(REPO / 'research/sta-velocity-control/scripts'))
import numpy as np
from pyulog import ULog
from capture_v00 import persisted_bson

RESULT_HEAD = '0a5796c3ed69d2e415696cf2450fbde74d56e6ea'
SOURCE_HEAD = '794301664cc0aacee6b5c62987531ab6f0b33fdf'
GROUPS = ('pid', 'x', 'y', 'xy', 'z', 'xz', 'yz', 'xyz')
INVARIANTS = {'MC_RTC_MODE': 0, 'MC_STA_AXES': 0, 'MC_RTC_DIV': 1,
              'MC_RATT_TEST': 0, 'MC_STA_TKO_MGT': 0, 'MPC_VC_DIV': 1}


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def command(argv):
    run = subprocess.run(argv, cwd=REPO, text=True, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, check=False)
    return dict(argv=argv, exit_code=run.returncode, stdout=run.stdout)


def intervals(stamps):
    values = np.asarray(stamps, dtype=np.int64)
    if values.size < 2:
        raise ValueError('At least two timestamps are required')
    dt = np.diff(values)
    if np.any(dt <= 0):
        raise ValueError('Timestamps must be strictly increasing; no deduplication')
    unique, counts = np.unique(dt, return_counts=True)
    return dict(samples=int(values.size), intervals=int(dt.size),
                duration_s=float((values[-1] - values[0]) / 1e6),
                mean_hz=float(1e6 / np.mean(dt)),
                min_us=int(dt.min()), max_us=int(dt.max()),
                p01_p50_p99_us=np.quantile(dt, [.01, .5, .99]).tolist(),
                histogram_us={str(int(v)): int(n) for v, n in zip(unique, counts)})


def parameters(configurations):
    base = configurations['pid']
    shared = {k: v for k, v in base.items() if k not in ('MPC_VC_MODE', 'MPC_VC_AXES')}
    rows = {}
    for mask, group in enumerate(GROUPS):
        p = configurations[group]
        if {k: v for k, v in p.items() if k not in ('MPC_VC_MODE', 'MPC_VC_AXES')} != shared:
            raise ValueError('Non-selector parameters differ across configurations: ' + group)
        if p['MPC_VC_MODE'] != int(mask > 0) or p['MPC_VC_AXES'] != mask:
            raise ValueError('Wrong mode/mask: ' + group)
        if any(p[k] != v for k, v in INVARIANTS.items()):
            raise ValueError('Inner-loop or cadence invariant violated: ' + group)
        rows[group] = dict(parameter_count=len(p), mode=p['MPC_VC_MODE'], axes=mask)
    return dict(common_parameters=shared, configurations=rows)


def log_sample(job, index):
    run = EXTERNAL / 'formal01' / job['id']
    record = read(run / 'result.json')
    path = run / 'log001.ulg'
    entry = next(e for e in index if e['archive'] == str(path))
    before = digest(path)
    assert before == entry['sha256'] and path.stat().st_size == entry['bytes']
    assert record['success'] and record['source_head'] == SOURCE_HEAD
    # Filtered decoding still parses the complete ULog stream. It is not the
    # full AX05 all-topic integrity/health/reset revalidation.
    topics = ['sta_velocity_ctrl_status', 'velocity_ctrl_selection', 'vehicle_local_position_log']
    ulog = ULog(str(path), topics)
    assert not ulog.dropouts and not getattr(ulog, 'file_corruption', False)
    data = ulog.get_dataset('sta_velocity_ctrl_status').data
    events = {e['name']: e['timestamp_us'] for e in record['events']}
    window = ((data['timestamp'] >= events['hover_start']) &
              (data['timestamp'] < events['hover_end']) &
              (data['excitation_time'] >= 0) & (data['excitation_time'] < 64))
    assert np.count_nonzero(window) > 0
    values = {k: np.unique(data[k][window]).astype(int).tolist() for k in
              ('effective_mode', 'effective_axes', 'active_axes', 'committed_axes',
               'pid_axes', 'inner_mode', 'inner_axes', 'inner_divisor', 'z_phase', 'timing')}
    expected = dict(effective_mode=job['mode'], effective_axes=job['axes'],
                    active_axes=job['axes'], committed_axes=job['axes'],
                    pid_axes=7 ^ job['axes'], inner_mode=0, inner_axes=0, inner_divisor=1)
    assert all(values[k] == [v] for k, v in expected.items())
    runtime = read(run / 'runtime_parameters_start.json')
    assert all(np.isclose(runtime[k], v, rtol=1e-6, atol=1e-7) for k, v in job['parameters'].items())
    assert all(runtime[k] == v for k, v in INVARIANTS.items())
    selection = ulog.get_dataset('velocity_ctrl_selection').data
    selected = np.isin(selection['timestamp_sample'], data['timestamp_sample'][window])
    assert np.count_nonzero(selected) == np.count_nonzero(window)
    assert np.all(selection['control_updated'][selected])
    assert np.all(~selection['control_held'][selected].astype(bool))
    fields = {name: dict(min=float(np.min(data[name][window])), max=float(np.max(data[name][window])),
                        values=np.unique(data[name][window]).astype(float).tolist())
              for name in ('raw_dt', 'input_dt', 'used_dt')}
    # Store at most the small set of actual h values, not a whole time series.
    result = dict(id=job['id'], task=job['task'], candidate=job['candidate'], seed=job['seed'],
                  archive=str(path), bytes=entry['bytes'], sha256=before,
                  source_head=record['source_head'], firmware_sha256=record['binary_sha256'],
                  sampling='earliest PID and XYZ per H/V, full 64 s excitation window',
                  filtered_topics=topics, stream_dropouts=0, stream_corruption=False,
                  sample_clock=intervals(data['timestamp_sample'][window]),
                  input_publication_clock=intervals(data['input_timestamp'][window]),
                  diagnostic_publication_clock=intervals(data['timestamp'][window]),
                  actual_mode_values=values, dt_fields_s=fields,
                  selection_h_s=np.unique(selection['h'][selected]).astype(float).tolist(),
                  runtime_parameters_sha256=digest(run / 'runtime_parameters_start.json'),
                  model_manifest=read(run / 'model_manifest.json'),
                  world_process=read(run / 'world_process.json'))
    assert digest(path) == before
    return result


def main():
    calls = [command(argv) for argv in (
        ['git', 'branch', '--show-current'], ['git', 'rev-parse', 'HEAD'],
        ['git', 'status', '--porcelain=v1', '--untracked-files=all'],
        ['git', 'submodule', 'status', '--recursive'],
        ['git', 'submodule', 'foreach', '--quiet', '--recursive', 'git status --porcelain --untracked-files=all'],
        ['git', 'diff', SOURCE_HEAD, RESULT_HEAD, '--stat', '--', 'src', 'msg', 'Tools', 'sitl', 'ROMFS'],
        ['g++', '--version'], ['cmake', '--version'], ['ninja', '--version'],
        ['gazebo', '--version'], ['uname', '-a'], ['df', '-B1', str(REPO), '/dev/shm'],
        ['pgrep', '-a', '-x', 'px4|gzserver|gzclient'])]
    assert calls[0]['stdout'].strip() == 'research/sta-velocity-regularized'
    ancestor = command(['git', 'merge-base', '--is-ancestor', RESULT_HEAD, 'HEAD'])
    calls.append(ancestor)
    assert ancestor['exit_code'] == 0
    subs = calls[3]['stdout'].splitlines()
    assert len(subs) == 33 and all(line.startswith(' ') for line in subs)
    assert calls[4]['exit_code'] == 0 and not calls[4]['stdout'].strip()
    assert calls[5]['exit_code'] == 0 and not calls[5]['stdout'].strip()
    frozen = read(AX04 / 'frozen.json')
    mismatches = []
    for table, root in (('assets', REPO), ('external_assets', Path('/'))):
        for file, sha in frozen[table].items():
            path = root / file
            if not path.is_file() or digest(path) != sha:
                mismatches.append(str(path))
    assert not mismatches, mismatches
    configs = {group: read(AX04 / 'parameters' / (group + '.json')) for group in GROUPS}
    params = parameters(configs)
    params['files'] = {str(AX04 / 'parameters' / (group + '.json')):
                       digest(AX04 / 'parameters' / (group + '.json')) for group in GROUPS}
    manifest = read(AX04 / 'manifest.json')
    index = read(AX05 / 'results/ulog_index.json')
    chosen = [next(j for j in manifest if j['task'] == task and j['candidate'] == group)
              for task in ('H', 'V') for group in ('PID', 'XYZ')]
    sampled = [log_sample(j, index) for j in chosen]
    runtime_firmware = REPO / 'build/px4_sitl_default/bin/px4'
    model_path = REPO / 'research/sta-velocity-control/axis_ablation/ax02/models/iris.sdf'
    model = ET.parse(model_path).getroot().find('model')
    physical = dict(path=str(model_path), sha256=digest(model_path),
        link_masses_kg={link.attrib['name']: float(link.findtext('inertial/mass'))
                        for link in model.findall('link')},
        base_inertia_kg_m2={entry.tag: float(entry.text) for entry in
                           model.find("link[@name='base_link']/inertial/inertia")},
        includes=[entry.findtext('uri') for entry in model.findall('include')],
        motor_plugins=[dict(name=entry.attrib['name'], filename=entry.attrib['filename'],
                            time_constant_up_s=float(entry.findtext('timeConstantUp')),
                            time_constant_down_s=float(entry.findtext('timeConstantDown')),
                            motor_constant=float(entry.findtext('motorConstant')),
                            moment_constant=float(entry.findtext('momentConstant')))
                       for entry in model.findall('plugin') if entry.find('timeConstantUp') is not None])
    storage = {str(p): dict(total=shutil.disk_usage(p).total, used=shutil.disk_usage(p).used,
                           free=shutil.disk_usage(p).free) for p in (REPO, Path('/dev/shm'))}
    usage = command(['du', '-s', '--block-size=1', str(EXTERNAL / 'formal01'),
                     str(EXTERNAL / 'replay01'), str(EXTERNAL / 'audit01')])
    calls.append(usage)
    assert usage['exit_code'] == 0
    occupied = {line.split('\t', 1)[1]: int(line.split('\t', 1)[0])
                for line in usage['stdout'].splitlines()}
    estimated = sum(occupied.values()) * 290 / 320
    storage_plan = dict(basis='Measured AX05 formal01+replay01+audit01 allocated bytes; no symlink following',
        measured_bytes=occupied, reference_attempts=320, planned_attempts=290,
        projected_290_bytes=estimated, reserve_bytes=10 * 1024 ** 3,
        required_with_reserve_bytes=estimated + 10 * 1024 ** 3,
        currently_free_bytes=storage[str(REPO)]['free'],
        planning_capacity_sufficient=storage[str(REPO)]['free'] >= estimated + 10 * 1024 ** 3,
        caution='Not an upper bound or flight authorization; rebuilds, extra logs and other writers consume space. Recheck each stage.')
    eeprom = REPO / 'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    defaults = {p['name']: p['default'] for p in read(REPO / 'build/px4_sitl_default/parameters.json')['parameters']}
    effective_offline = dict(defaults, **persisted_bson(eeprom.read_bytes()))
    assert all(effective_offline[k] == v for k, v in INVARIANTS.items())
    offline_parameters = dict(path=str(eeprom), sha256=digest(eeprom), runtime_verified=False,
        note='Generated defaults plus persisted overrides only; actual runtime proof is sampled old ULogs.',
        invariant_values={k: effective_offline[k] for k in INVARIANTS})
    out = dict(stage='R00', audit='baseline-parameters-assets-four-raw-log-periods', success=True,
               source_head=SOURCE_HEAD, result_and_branch_origin_head=RESULT_HEAD,
               audited_head=calls[1]['stdout'].strip(),
               commands=calls, submodule_count=len(subs), submodules=subs,
               assets_checked=len(frozen['assets']), external_assets_checked=len(frozen['external_assets']),
               asset_mismatches=mismatches, frozen_sha256=digest(AX04 / 'frozen.json'),
               parameters=params, raw_log_samples=sampled, physical_model=physical,
               script_sha256=digest(__file__), python=sys.version, platform=platform.platform(),
               numpy=dict(version=np.__version__, path=np.__file__), storage_bytes=storage,
               capacity_projection=storage_plan, current_offline_parameters=offline_parameters,
               current_on_disk_firmware=dict(path=str(runtime_firmware), sha256=digest(runtime_firmware)),
               counts=dict(configuration_files=8, raw_main_ulogs_decoded=4,
                           cxx_tests=0, flight_attempts=0, source_builds=0),
               not_executed=['new flights', 'MATLAB', 'full 320-run replay', 'production builds',
                             'fresh seed allocation', 'V09 holdout reads'],
               limitations=['Sampled periods do not bound all future callbacks.',
                            'Current firmware hash is observation, not new-source qualification.',
                            'Shared external trajectories do not imply equal consumed velocity targets.',
                            'Only existing IMU engine seed was controlled; other sources and scheduling were not.'])
    print(json.dumps(out, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
