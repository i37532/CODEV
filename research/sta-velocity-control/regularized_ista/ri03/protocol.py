"""RI03 X-only nine-job protocol. Registration is not a build qualification."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ENTRY_HEAD = 'e7fb67112e4cf605f5ddf362f120c320a64d2cf5'
REVISION = 'ri03'
DATA_ROOT = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI03')
AUTHORIZATION = HERE / 'AUTHORIZATION_CN.md'
AUTHORIZATION_SHA = '8081b26ac07d3992db68151f04a70b8cc387985f670217c96db65aecac161302'
GATES = {'A': dict(task='X', axes=1, test=1, duration=32, seeds=[81001, 81002, 81003])}
REGISTRATION_NAMES = ('seed_audit_initial.json', 'execution.json', 'manifest.json', 'outcomes_unattempted.json')
SOURCE = HERE.parent / 'ri00/results/interface.json'
SOURCE_SHA = '37729b3d84309c899dce52803c234ef109f738ac0d1a4e1520a729dd18cbeb81'
OVERRIDES = REPO / 'research/sta-velocity-control/axis_ablation/ax04/execution.json'
OVERRIDES_SHA = '308aa5a4e52828585bbf6ee3ec0be339a8081475663ceb759de0aee40167d2d3'
MIN_CPP = 675
MIN_PYTHON = 709
REQUIRED_TARGETS = {
    'unit-RegularizedIstaNonSitl', 'unit-RegularizedIstaPosition',
    'unit-RegularizedIstaRegression', 'unit-RegularizedIstaProtection',
    'unit-RegularizedIstaVelocityControl', 'functional-RegularizedIstaVelocityModule',
    'functional-RegularizedIstaVelocityParam', 'functional-VehicleIMU',
    'functional-EKF2SelectorTiming', 'functional-EKF2Selector',
    'functional-EstimatorDiagnosticTopics', 'unit-PositionControl',
    'unit-ControlMath', 'unit-Takeoff', 'unit-RateControl',
    'unit-RegularizedVelocityRegression', 'unit-VelocityResearchTask', 'unit-StaVelocityProtection',
}
REQUIRED_TARGETS.update('unit-'+name for name in (
    'VelocityControl', 'StaVelocityControl', 'RegularizedStaVelocityControl',
    'VelocityEsta', 'VelocityEstaZ', 'VelocityZIntegration', 'VelocityXYIntegration',
    'VelocityXYZIntegration', 'VelocityAxes', 'VelocityDecimation', 'RegularizedVelocityIntegration',
    'VelocityAblationTask', 'RateControlDispatcher', 'StaRateControl', 'ControllerSelection',
    'StaProtection', 'StaAxesApplication', 'TakeoffNuManager', 'IstaRateControl', 'IstaIntegration',
    'ProperIstaRateControl', 'ProperIstaIntegration', 'ProperIstaProtection', 'ControlDecimation', 'AttitudeControl'))
REQUIRED_TARGETS.update('functional-'+name for name in (
    'VelocitySelectionParam', 'VelocityDiagnosticInput', 'VelocityModule',
    'RegularizedVelocityParam', 'RegularizedVelocityModule'))


def read(path):
    return json.loads(Path(path).read_text())


def fingerprint(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1048576), b''):
            h.update(part)
    return h.hexdigest()


def exact(a, b):
    return json.dumps(a, sort_keys=True, separators=(',', ':'), allow_nan=False) == json.dumps(b, sort_keys=True, separators=(',', ':'), allow_nan=False)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_gate(gate):
    if gate not in GATES:
        raise ValueError('RI03 admits only X gate A')
    return copy.deepcopy(GATES[gate])


def budget(gate='A'):
    valid_gate(gate)
    return dict(maximum_attempts=9, new_matrix_attempts=9, total_maximum_attempts=9,
                historical_attempts=0, required_pairs=6, required_replays=9,
                n_per_algorithm=3, logging_profile=3089)


def design():
    if fingerprint(SOURCE) != SOURCE_SHA or fingerprint(OVERRIDES) != OVERRIDES_SHA:
        raise ValueError('Frozen parameter/threshold source changed')
    fixed = read(SOURCE)['full_r03_parameters']
    if len(fixed) != 127:
        raise ValueError('Incomplete parameter source')
    jobs = []
    for block, seed in enumerate(GATES['A']['seeds']):
        order = [('RSTA', 3), ('RISTA', 4)] if block % 2 == 0 else [('RISTA', 4), ('RSTA', 3)]
        for position, (candidate, mode) in enumerate([('PID', 0), *order], 1):
            axes = 1 if mode else 0
            parameters = {**fixed, 'MPC_VC_MODE': mode, 'MPC_VC_AXES': axes,
                          'MPC_VC_DIV': 1, 'MPC_VCT_TEST': 1}
            jobs.append(dict(id=f'run{len(jobs)+1:03d}', revision=REVISION, gate='A', task='X',
                             phase='development', role='matrix', seed=seed, block=block+1,
                             position=position, candidate=candidate, mode=mode, axes=axes,
                             divisor=1, main_duration_s=32, parameters=parameters))
    return dict(stage='RI03-A', revision=REVISION, entry_head=ENTRY_HEAD, **budget(),
                status='authorized_pending_current_clean_qualification',
                execution_authorized=True, flight_authorized=True, execution_ready=True,
                fixed_parameters=fixed, jobs=jobs, protocol_overrides=read(OVERRIDES)['protocol_overrides'],
                parameter_sources={str(SOURCE): SOURCE_SHA}, threshold_source={str(OVERRIDES): OVERRIDES_SHA},
                authority='Only current user RI03 request; no old continuous or push authority',
                order='Each seed PID first; RSTA/RISTA, RISTA/RSTA, RSTA/RISTA; first mandatory failure stops',
                post_logger_warmup_us=30000000, simulation_speed=1,
                history='Old R03 97 attempts retained separately; none count toward these nine new jobs',
                statistics='Paired development n=3, only IMU explicitly seeded; no superiority requirement')


def validate_manifest(value=None):
    expected = design()
    if not exact(expected, read(HERE/'execution.json') if value is None else value):
        raise ValueError('RI03 execution changed')
    if not exact(read(HERE/'manifest.json'), expected['jobs']):
        raise ValueError('RI03 manifest changed')
    outcomes = [{k: j[k] for k in ('id', 'gate', 'task', 'seed', 'candidate', 'mode', 'axes')} |
                {'status': 'unattempted'} for j in expected['jobs']]
    if not exact(outcomes, read(HERE/'outcomes_unattempted.json')):
        raise ValueError('Initial registration must remain unattempted')
    return True


def load_protocol(gate='A'):
    cfg = valid_gate(gate)
    scripts = REPO/'research/sta-velocity-control/scripts'
    if str(scripts) not in sys.path:
        sys.path.append(str(scripts))
    from v04_protocol10 import load_protocol as inherited
    d = design()
    p = inherited()
    p.update(copy.deepcopy(d['protocol_overrides']))
    p.update(stage='RI03-A', revision=REVISION, gate=gate, gate_config=cfg,
             jobs=d['jobs'], seeds=cfg['seeds'], **budget(),
             execution_authorized=True, flight_authorized=True, execution_ready=True,
             config_dir=str(HERE/'gates'/gate), execution_path=str(HERE/'execution.json'),
             qualification_path=str(DATA_ROOT/gate/'qualification02/evidence.json'),
             post_logger_warmup_us=30000000, simulation_speed=1,
             status=d['status'], scope='Iris SITL X only: PID/RSTA/RISTA; Y/Z and rate PID; no tuning')
    p['artifacts'] = {**p['artifacts'], 'new_run_root': str(DATA_ROOT/gate/'batch01')}
    # Safe pre-job representation; the runner still merges and verifies every
    # complete frozen job before writing BSON. Never inherit run029 MODE3/AXES7.
    p['startup_overrides'] = {**p['startup_overrides'], **d['jobs'][0]['parameters']}
    p['candidate'] = {k: v for k, v in d['fixed_parameters'].items()
                      if k.startswith(('MPC_VC_L', 'MPC_VC_NU', 'MPC_VC_A_', 'MPC_VC_EPS_'))}
    p['authorization'] = dict(basis=d['authority'], maximum_attempts=9, this_gate_attempts=9,
                              execution_authorized=True, source=str(AUTHORIZATION))
    p['not_authorized'] = ['RI04', 'old R04/R05', 'hardware', 'DIV2/4', 'tuning', 'push',
                            'replacement flights', 'MODE4 axes2/3/4/5/6/7', 'new ESTA statistics']
    p['current_turn_not_run'] = ['RI04', 'old R04/R05', 'formal holdout', 'hardware', 'tuning', 'push']
    p['diagnostic_gate'].update(minimum_excitation_samples=3190, minimum_excitation_span_s=31.96)
    p['pair_gate'].update(maximum_candidate_flights_before_reauthorization=9, candidates=2,
                          order=d['order'], window='32s main and two16s halves;90s position/yaw',
                          calculation='RSTA and RISTA separately versus same-seed PID; six pairs, no superiority requirement')
    p['excitation'] = dict(parameter=1, duration_s=32, settle_after_auto_loiter_s=12, task='X',
                           source='Original Navigator/FlightTask plus existing task adapter; one setpoint source; no added derivative FF',
                           definition_file=str(HERE/'PROTOCOL_CN.md'))
    p['metrics'].update(primary='Time-weighted consumed per-axis velocity RMSE; J=arithmetic mean;32s main/two16s halves',
                         missing='First mandatory failure stops; require nine accepted/nine independent replays/six pairs; no retry/imputation',
                         interpretation=d['statistics'])
    p['logging'] = 'Keep existing SDLOG_PROFILE bits OR16/1024/2048; complete final R03 time/reset/tail chain'
    return p


def require_execution_authority(gate='A'):
    valid_gate(gate)
    if fingerprint(AUTHORIZATION) != AUTHORIZATION_SHA:
        raise PermissionError('RI03 finite user authority changed')
    validate_manifest()
    return dict(approved=True, stage='RI03-A', revision=REVISION, gate=gate,
                authorization_sha256=AUTHORIZATION_SHA, **budget())


def fresh_seeds(gate='A'):
    cfg = valid_gate(gate)
    audit = load_file('_ri03_seed_history', REPO/'research/sta-velocity-control/scripts/check_v04_protocol02.py')
    audit.CONFIG = Path('/__RI03_no_directory_exemption__')
    result = audit.seed_audit(cfg['seeds'])
    file = HERE/'seed_reservations.json'
    allowed = read(file) if file.exists() else {}
    if allowed:
        if set(allowed) != {str(HERE/n) for n in REGISTRATION_NAMES}:
            raise ValueError('Only four exact initial registrations may be exempted')
        validate_manifest()
        if any(fingerprint(path) != sha for path, sha in allowed.items()):
            raise ValueError('Seed reservation changed')
    result['design_registrations'] = [r for r in result['matches'] if r['path'] in allowed]
    result['matches'] = [r for r in result['matches'] if r['path'] not in allowed]
    result['accepted'] = not result['matches'] and not result['invalid_json']
    return result


def prepare():
    if any((HERE/n).exists() for n in (*REGISTRATION_NAMES, 'seed_reservations.json')):
        raise ValueError('No registration overwrite')
    if fingerprint(AUTHORIZATION) != AUTHORIZATION_SHA:
        raise PermissionError('Missing exact RI03 authority')
    audit = fresh_seeds()
    if not audit['accepted']:
        raise ValueError('Seed collision/invalid history: '+str(audit))
    d = design()
    records = dict(zip(REGISTRATION_NAMES, (audit, d, d['jobs'],
        [{k: j[k] for k in ('id', 'gate', 'task', 'seed', 'candidate', 'mode', 'axes')} |
         {'status': 'unattempted'} for j in d['jobs']])))
    for name, data in records.items():
        with (HERE/name).open('x') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2); stream.write('\n')
    with (HERE/'seed_reservations.json').open('x') as stream:
        json.dump({str(HERE/n): fingerprint(HERE/n) for n in REGISTRATION_NAMES}, stream, indent=2); stream.write('\n')


def qualification_binding(gate, source_head, firmware_sha256):
    require_execution_authority(gate)
    return dict(stage='RI03-A', revision=REVISION, gate=gate, source_head=source_head,
                firmware_sha256=firmware_sha256, execution_sha256=fingerprint(HERE/'execution.json'),
                frozen_sha256=fingerprint(HERE/'gates'/gate/'frozen.json'),
                authorization_sha256=AUTHORIZATION_SHA, new_flights=0,
                execution_authorized=True, flight_authorized=True, execution_ready=True, **budget())


def authorization_binding(q, path):
    binding = qualification_binding(q['gate'], q['source_head'], q['firmware_sha256'])
    return dict(approved=True, qualification_sha256=fingerprint(path), **binding)


def archive_qualification(gate, source_head, path):
    valid_gate(gate)
    path = Path(path).resolve()
    if DATA_ROOT/gate not in path.parents:
        raise ValueError('Foreign qualification')
    q = read(path)
    expected = qualification_binding(gate, source_head, q.get('firmware_sha256'))
    expected.update(success=True, clean=True, approved=True)
    if any(not exact(q.get(k), v) for k, v in expected.items()):
        raise ValueError('Qualification identity/authorization mismatch')
    if not isinstance(q.get('firmware_sha256'), str) or len(q['firmware_sha256']) != 64:
        raise ValueError('Missing binary fingerprint')
    for key, minimum in (('cpp_unique_tests', MIN_CPP), ('python_tests', MIN_PYTHON)):
        if type(q.get('counts', {}).get(key)) is not int or q['counts'][key] < minimum:
            raise ValueError('Missing actual nonzero regression counts')
    if not q.get('commands') or any(c.get('exit_code') != 0 for c in q['commands']):
        raise ValueError('Incomplete qualification commands')
    if not REQUIRED_TARGETS.issubset(set(q.get('cpp_test_targets', []))):
        raise ValueError('Required actual test executable missing')
    for target in REQUIRED_TARGETS:
        if not any(c.get('name') == target and c.get('exit_code') == 0 for c in q['commands']):
            raise ValueError('Required test was not executed: ' + target)
    if not q.get('evidence_files'):
        raise ValueError('Missing actual evidence')
    for name, sha in q['evidence_files'].items():
        if path.parent not in Path(name).resolve().parents or fingerprint(name) != sha:
            raise ValueError('Changed/nonlocal qualification evidence')
    if not exact(read(path.parent/'authorization.json'), authorization_binding(q, path)):
        raise ValueError('Qualification authorization receipt mismatch')
    freeze = load_file('_ri03_archive_freeze', HERE/'freeze.py')
    freeze.archive_check(gate, source_head, q['frozen_sha256'])
    return q


def require_qualification(gate, source_head, path):
    require_execution_authority(gate)
    q = archive_qualification(gate, source_head, path)
    if git('rev-parse', 'HEAD') != source_head or git('status', '--porcelain'):
        raise ValueError('Execution requires current qualified clean HEAD')
    if git('branch', '--show-current') != 'research/ista-velocity-regularized':
        raise ValueError('Wrong branch')
    if fingerprint(REPO/'build/px4_sitl_default/bin/px4') != q['firmware_sha256']:
        raise ValueError('Current binary differs from qualified binary')
    load_file('_ri03_launch_freeze', HERE/'freeze.py').check(gate)
    return q


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare()
    else:
        print(json.dumps(load_protocol(), ensure_ascii=False, indent=2))
