#!/usr/bin/env python3
"""Freeze a three-attempt descriptive experiment without changing controllers."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

REPO = Path('/home/yr/Desktop/Codev-autopilot')
ORIGINAL = Path('/home/yr/Desktop/Codev-SuperTwisting2-original')
DATA = Path('/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-HOVER-20261102')
HERE = Path(__file__).resolve().parent
PACKAGE = REPO/'research/sta-velocity-control/regularized_ista/ri07/results/final01/package.json'
MODEL = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-HOVER-20261031/batch01/H001/models/iris')


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def git(repo, *args):
    return subprocess.check_output(['git', *args], cwd=repo, text=True).strip()


def save(path, data):
    with Path(path).open('x') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def snapshot():
    DATA.mkdir(parents=True, exist_ok=False)
    names = set(git(REPO, 'diff', '--name-only', 'HEAD').splitlines())
    names.update(git(REPO, 'ls-files', '--others', '--exclude-standard').splitlines())
    files = {n: sha(REPO/n) for n in sorted(names)
             if not n.startswith('research/upstream-supertwisting2/') and (REPO/n).is_file()}
    save(DATA/'entry.json', dict(branch=git(REPO, 'branch', '--show-current'),
        head=git(REPO, 'rev-parse', 'HEAD'), status=git(REPO, 'status', '--short'),
        dirty_files=files, submodules=git(REPO, 'submodule', 'status', '--recursive'),
        original_head=git(ORIGINAL, 'rev-parse', 'HEAD'),
        firmware_sha256=sha(REPO/'build/px4_sitl_default/bin/px4')))
    print('Snapshot:', DATA, len(files), 'protected files')


def freeze():
    entry = json.loads((DATA/'entry.json').read_text())
    assert git(REPO, 'branch', '--show-current') == 'research/upstream-supertwisting2'
    assert git(REPO, 'rev-parse', 'HEAD') == entry['head']
    assert git(ORIGINAL, 'rev-parse', 'HEAD') == 'fc3720f67767c78cfab668777de13f68562fe2fd'
    assert not git(ORIGINAL, 'diff', '--ignore-submodules=dirty', '--name-only', 'HEAD'), 'Original tracked source changed'
    gazebo = ORIGINAL/'Tools/simulation/gazebo-classic/sitl_gazebo-classic'
    # The upstream jinja generator appends this ignore entry itself; no algorithm/model-template edit.
    assert git(gazebo, 'diff', '--name-only', 'HEAD') in ('', '.gitignore')
    assert all(sha(REPO/n) == h for n, h in entry['dirty_files'].items())
    assert git(REPO, 'submodule', 'status', '--recursive') == entry['submodules']
    assert sha(PACKAGE) == 'df95cdfaa7de7299917bbd6b6db1f4459b730033c48bb7eae5f7c829675a123f'
    models = DATA/'assets/models/iris'
    shutil.copytree(MODEL, models, symlinks=True)
    plugin = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/plugins01/libm10_imu.so')
    assert plugin.is_file()
    env = dict(HEADLESS='1', PX4_SIM_SPEED_FACTOR='1', GAZEBO_MASTER_URI='http://127.0.0.1:11345',
               GAZEBO_MODEL_PATH='', GAZEBO_PLUGIN_PATH='', LD_LIBRARY_PATH='', PX4_SITL_WORLD='')
    common = dict(MIS_TAKEOFF_ALT=2.5, SDLOG_MODE=1)
    original_build = ORIGINAL/'build/px4_sitl_default'
    author_params = json.loads((original_build/'parameters.json').read_text())['parameters']
    author_expected = {p['name']: p['default'] for p in author_params if p['name'].startswith(('ATT_STA_', 'POS_STA_'))}
    original_files = ['src/lib/rate_control/attitude_sta_control.cpp', 'src/lib/rate_control/rate_control.cpp',
        'src/modules/mc_rate_control/MulticopterRateControl.cpp',
        'src/modules/mc_pos_control/PositionControl/PositionControl.cpp',
        'src/modules/mc_pos_control/PositionControl/PositionStaControl.cpp',
        'Tools/simulation/gazebo-classic/sitl_run.sh']
    jobs = [dict(id='S001', label='Upstream STA2', repo=str(ORIGINAL), bin=str(original_build/'bin'),
        rootfs=str(original_build/'rootfs'), parameters=common,
        expected_parameters={**author_expected, **common, 'SYS_AUTOSTART':10015},
        firmware_sha256=sha(original_build/'bin/px4'), source_head=git(ORIGINAL, 'rev-parse', 'HEAD'),
        source_assets={n:sha(ORIGINAL/n) for n in original_files},
        parameter_files=['parameters.bson', 'parameters_backup.bson'],
        diagnostic_expectations={'attitude_sta_status':{}},
        launch_env=dict(env), launch_command=['bash', str(ORIGINAL/'Tools/simulation/gazebo-classic/sitl_run.sh'),
            str(original_build/'bin/px4'), 'none', 'iris', 'none', str(ORIGINAL), str(original_build)])]
    package = json.loads(PACKAGE.read_text())
    for i, name in enumerate(('RSTA', 'RISTA'), 2):
        source = package['parameters']['B/H/'+name]
        parameters = {**source['parameters'], **common, 'MPC_VCT_TEST':0, 'SDLOG_PROFILE':3089}
        build = REPO/'build/px4_sitl_default'
        jobs.append(dict(id='S%03d'%i, label=name, repo=str(REPO), bin=str(build/'bin'),
            rootfs=str(build/'tmp/rootfs'), parameters=parameters, expected_parameters=parameters,
            source_parameters_sha256=source['sha256'],
            parameter_deviation='MPC_VCT_TEST 6 to 0 disables task waves; common 2.5m takeoff/logging; no gain tuning',
            source_head=entry['head'], firmware_sha256=sha(build/'bin/px4'),
            source_assets={**entry['dirty_files'], 'Tools/sitl_run.sh':sha(REPO/'Tools/sitl_run.sh')},
            launch_command=['bash', str(REPO/'Tools/sitl_run.sh'), str(build/'bin/px4'),
                            'none', 'gazebo', 'iris', 'none', str(REPO), str(build)],
            launch_env={**env, 'PX4_SITL_WORLD':str(REPO/'sitl/worlds/empty_grey.world'),
                'GAZEBO_MODEL_PATH':str(models.parent)+':'+str(REPO/'Tools/sitl_gazebo/models'),
                'GAZEBO_PLUGIN_PATH':str(build/'build_gazebo'),
                'M10_IMU_SEED':'93001', 'M10_IMU_LOG':str(DATA/('S%03d_imu.csv'%i))},
            diagnostic_expectations={'sta_velocity_ctrl_status':{'effective_mode':parameters['MPC_VC_MODE'],
                'effective_axes':7}, 'sta_rate_ctrl_status':{'effective_mode':0,'effective_axes':0}},
            hover_diagnostic_expectations={'sta_velocity_ctrl_status':{'effective_mode':parameters['MPC_VC_MODE'],
                'effective_axes':7,'active_axes':7,'inner_mode':0,'inner_axes':0,'fault':0},
                'sta_rate_ctrl_status':{'effective_mode':0,'effective_axes':0,'fault':0}}))
    assets = {str(p):sha(p) for p in [*HERE.glob('*.py'), models/'iris.sdf', models/'model.config', plugin,
        REPO/'sitl/worlds/empty_grey.world', gazebo/'models/iris/iris.sdf',
        gazebo/'models/iris/iris.sdf.jinja',gazebo/'worlds/empty.world',
        *sorted((original_build/'build_gazebo-classic').glob('*.so'))]}
    save(DATA/'manifest.json', dict(max_attempts=3, order=[j['id'] for j in jobs], jobs=jobs,
        data_root=str(DATA), hover_s=10, takeoff_alt_m=2.5, assets=assets,
        scope='Unmodified upstream full system versus existing RSTA/RISTA systems; n=1 each; descriptive, not velocity-only causal comparison',
        authorization='User requested original 2.0 and simple quick hover comparison; first failure stops, no tuning/retries',
        safety=dict(tilt_deg=15, xy_speed_m_s=1, xy_displacement_m=2, height_range_m=[-.5,4],
                    vertical_speed_m_s=3.5, hover_height_deviation_m=1, hover_vertical_speed_m_s=.6),
        entry=dict(height_tolerance_m=.3, vertical_speed_m_s=.2, stable_s=3, relative_warmup_s=30),
        interpretation='Different PX4 versions/rate controllers/contact assets; no guaranteed ranking; actual EKF states, not truth; no exact cross-version seed pairing',
        original_submodules=git(ORIGINAL,'submodule','status','--recursive')))
    print('Frozen', DATA/'manifest.json')


def freeze_startup_revision():
    """One bounded tooling-only startup correction; preserve original attempt."""
    old = json.loads((DATA/'manifest.json').read_text())
    prior = json.loads((DATA/'runs/S001/result.json').read_text())
    assert not prior['success'] and not prior['events'] and prior['parameter_restore_exact']
    assert prior['error'] == "ValueError('Missing topic vehicle_attitude')"
    assert not prior['remaining_simulators']
    old['historical_startup_failures'] = [dict(id='S001', takeoffs=0,
        result=str(DATA/'runs/S001/result.json'), sha256=sha(DATA/'runs/S001/result.json'))]
    old['maximum_total_process_launches_including_history'] = 4
    old['maximum_total_takeoffs'] = 3
    old['revision_reason'] = 'Bounded disarmed first-publication wait before unchanged 30s warmup; no gains/safety/flight rules changed'
    old['prior_manifest_sha256'] = sha(DATA/'manifest.json')
    for i, job in enumerate(old['jobs'],1):
        job['id'] = 'S10%d'%i
        if 'M10_IMU_LOG' in job['launch_env']:
            job['launch_env']['M10_IMU_LOG'] = str(DATA/(job['id']+'_imu.csv'))
    old['order'] = [j['id'] for j in old['jobs']]
    for path in HERE.glob('*.py'):
        old['assets'][str(path)] = sha(path)
    save(DATA/'manifest02.json', old)
    print('Frozen startup-only correction', DATA/'manifest02.json')


def freeze_diagnostic_revision():
    old = json.loads((DATA/'manifest02.json').read_text())
    passed = json.loads((DATA/'runs/S101/result.json').read_text())
    prior = json.loads((DATA/'runs/S102/result.json').read_text())
    assert passed['success'] and passed['parameter_restore_exact']
    assert not prior['success'] and not prior['events'] and prior['parameter_restore_exact']
    assert 'Out of range float values are not JSON compliant: nan' in prior['error']
    assert not prior['remaining_simulators']
    old['historical_startup_failures'].append(dict(id='S102', takeoffs=0,
        result=str(DATA/'runs/S102/result.json'),sha256=sha(DATA/'runs/S102/result.json')))
    old['maximum_total_process_launches_including_history'] = 5
    old['previous_complete_flight_preserved'] = dict(id='S101',sha256=sha(DATA/'runs/S101/result.json'),
        reason='Same experiment; subsequent change serializes only N/A diagnostic receipts, no control/task/envelope changes')
    old['revision_reason'] = 'Serialize diagnostic-only NaN/Inf as explicit strings; numerical admission checks stay strict; preserve original completed flight'
    old['prior_manifest_sha256'] = sha(DATA/'manifest02.json')
    for i, job in enumerate(old['jobs'][1:],2):
        job['id'] = 'S20%d'%i
        job['launch_env']['M10_IMU_LOG'] = str(DATA/(job['id']+'_imu.csv'))
    old['order'] = [j['id'] for j in old['jobs']]
    for path in HERE.glob('*.py'):
        old['assets'][str(path)] = sha(path)
    save(DATA/'manifest03.json', old)
    print('Frozen diagnostic-only correction', DATA/'manifest03.json')


def freeze_pid_addition():
    """Append one authorized PID; never relaunch or rewrite the three completed flights."""
    old = json.loads((DATA/'manifest03.json').read_text())
    entry = json.loads((DATA/'entry.json').read_text())
    assert git(REPO, 'branch', '--show-current') == 'research/upstream-supertwisting2'
    assert git(REPO, 'rev-parse', 'HEAD') == entry['head']
    assert git(REPO, 'submodule', 'status', '--recursive') == entry['submodules']
    assert all(sha(REPO/n) == h for n, h in entry['dirty_files'].items())
    assert sha(REPO/'build/px4_sitl_default/bin/px4') == entry['firmware_sha256']
    assert sha(PACKAGE) == 'df95cdfaa7de7299917bbd6b6db1f4459b730033c48bb7eae5f7c829675a123f'
    prior = {}
    for job in old['jobs']:
        path = DATA/'runs'/job['id']/'result.json'
        result = json.loads(path.read_text())
        assert result['success'] and result['parameter_restore_exact'] and not result['remaining_simulators']
        prior[job['id']] = sha(path)
        job['result_path'] = str(path)
    source = json.loads(PACKAGE.read_text())['parameters']['B/H/PID']
    pid = copy.deepcopy(old['jobs'][1])
    pid.update(id='S304', label='PID', result_path=str(DATA/'runs/S304/result.json'),
        parameters={**source['parameters'], 'MIS_TAKEOFF_ALT':2.5, 'SDLOG_MODE':1,
                    'MPC_VCT_TEST':0, 'SDLOG_PROFILE':3089}, source_parameters_sha256=source['sha256'])
    pid['expected_parameters'] = dict(pid['parameters'])
    pid['launch_env']['M10_IMU_LOG'] = str(DATA/'S304_imu.csv')
    pid['diagnostic_expectations'] = {'sta_velocity_ctrl_status':{'effective_mode':0,'effective_axes':0},
        'sta_rate_ctrl_status':{'effective_mode':0,'effective_axes':0}}
    pid['hover_diagnostic_expectations'] = {'sta_velocity_ctrl_status':{'effective_mode':0,
        'effective_axes':0,'active_axes':0,'inner_mode':0,'inner_axes':0,'fault':0},
        'sta_rate_ctrl_status':{'effective_mode':0,'effective_axes':0,'fault':0}}
    old['jobs'].append(pid)
    old.update(max_attempts=4, order=[j['id'] for j in old['jobs']],
        maximum_total_process_launches_including_history=6, maximum_total_takeoffs=4,
        pid_addition=dict(new_attempts=1, preserved_results=prior,
            source_parameters='RI07 B/H/PID selected candidate; no tuning',
            same_seed='93001 shared with RSTA/RISTA; not identical upstream random realization'),
        prior_manifest_sha256=sha(DATA/'manifest03.json'),
        revision_reason='User requested adding PID; existing three flights remain immutable; one PID only',
        authorization='Add PID to comparison; no tuning, repeats, changed thresholds or other flights',
        scope='Unmodified upstream full system versus PID/RSTA/RISTA; n=1 each; descriptive system comparison')
    for path in HERE.glob('*.py'):
        old['assets'][str(path)] = sha(path)
    save(DATA/'manifest04_pid.json', old)
    print('Frozen one-PID extension', DATA/'manifest04_pid.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['snapshot','freeze','startup-revision','diagnostic-revision','pid-addition'])
    args = parser.parse_args()
    {'snapshot':snapshot,'freeze':freeze,'startup-revision':freeze_startup_revision,
     'diagnostic-revision':freeze_diagnostic_revision,'pid-addition':freeze_pid_addition}[args.action]()
