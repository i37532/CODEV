"""RI05 C=A/XY then D=B/XYZ protocol; eighteen finite attempts, no retry."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ENTRY_HEAD = 'bbc5396c272666bd20f526a54113e9698e87c16b'
REVISION = 'ri05'
DATA_ROOT = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI05')
AUTHORIZATION = HERE / 'AUTHORIZATION_CN.md'
AUTHORIZATION_SHA = 'eeb236e5f89a700515c9f7049aaab1b376b32d894f6eca5da6f241926f167d69'
GATES = {
    'C': dict(task='H', axes=3, test=6, duration=64, seeds=[83001, 83002, 83003], milestone_gate='A'),
    'D': dict(task='V', axes=7, test=8, duration=64, seeds=[83101, 83102, 83103], milestone_gate='B')}
# Internal C/D retain the exact R03 H/V task identities; milestone A/B are not R03 X/Z.

REGISTRATION_NAMES = ('seed_audit_initial.json', 'execution.json', 'manifest.json', 'outcomes_unattempted.json')
SOURCE = HERE.parent / 'ri00/results/interface.json'
SOURCE_SHA = '37729b3d84309c899dce52803c234ef109f738ac0d1a4e1520a729dd18cbeb81'
OVERRIDES = REPO / 'research/sta-velocity-control/axis_ablation/ax04/execution.json'
OVERRIDES_SHA = '308aa5a4e52828585bbf6ee3ec0be339a8081475663ceb759de0aee40167d2d3'
MIN_CPP = 711
MIN_PYTHON = 904
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
        raise ValueError('RI05 admits only C=A/XY and D=B/XYZ')
    return copy.deepcopy(GATES[gate])


def budget(gate='C'):
    valid_gate(gate)
    return dict(maximum_attempts=9, new_matrix_attempts=9, total_maximum_attempts=18,
                historical_attempts=0, required_pairs=6, required_replays=9,
                n_per_algorithm=3, logging_profile=3089)


def design():
    if fingerprint(SOURCE) != SOURCE_SHA or fingerprint(OVERRIDES) != OVERRIDES_SHA:
        raise ValueError('Frozen parameter/threshold source changed')
    fixed = read(SOURCE)['full_r03_parameters']
    if len(fixed) != 127:
        raise ValueError('Incomplete parameter source')
    jobs = []
    for gate, cfg in GATES.items():
        for block, seed in enumerate(cfg['seeds']):
            order = [('RSTA', 3), ('RISTA', 4)] if block % 2 == 0 else [('RISTA', 4), ('RSTA', 3)]
            for position, (candidate, mode) in enumerate([('PID', 0), *order], 1):
                axes = cfg['axes'] if mode else 0
                parameters = {**fixed, 'MPC_VC_MODE': mode, 'MPC_VC_AXES': axes,
                              'MPC_VC_DIV': 1, 'MPC_VCT_TEST': cfg['test']}
                jobs.append(dict(id=f'run{len(jobs)+1:03d}', revision=REVISION, gate=gate,
                    task=cfg['task'], phase='development', role='matrix', seed=seed, block=block+1,
                    position=position, candidate=candidate, mode=mode, axes=axes,
                    divisor=1, main_duration_s=cfg['duration'], parameters=parameters))
    return dict(stage='RI05', revision=REVISION, entry_head=ENTRY_HEAD,
                maximum_attempts=18, gates=GATES, n_per_algorithm_per_gate=3,
                status='authorized_pending_per_gate_clean_qualification',
                execution_authorized=True, flight_authorized=True, execution_ready=True,
                fixed_parameters=fixed, jobs=jobs, protocol_overrides=read(OVERRIDES)['protocol_overrides'],
                parameter_sources={str(SOURCE): SOURCE_SHA}, threshold_source={str(OVERRIDES): OVERRIDES_SHA},
                authority='Only current user RI05 request: C=A/XY then D=B/XYZ; no old continuous or push authority',
                order='Each seed PID first; RSTA/RISTA, RISTA/RSTA, RSTA/RISTA; first mandatory failure stops all RI05',
                post_logger_warmup_us=30000000, simulation_speed=1,
                statistics='Paired development n=3 per gate, only IMU explicitly seeded; no superiority requirement')


def jobs(gate):
    valid_gate(gate)
    return [j for j in design()['jobs'] if j['gate'] == gate]


def stage(gate):
    valid_gate(gate)
    return 'RI05-' + gate


def require_prior_gate(gate):
    """D requires a complete actual C receipt, archive and independent replays.

    This is execution qualification only; it never changes the static design
    or rewrites archived C assets when D receives a later source commit.
    """
    valid_gate(gate)
    if gate == 'C':
        return None
    receipt_path = DATA_ROOT/'C/gate_pass.json'
    receipt = read(receipt_path)
    expected = dict(stage=stage('C'), revision=REVISION, gate='C', accepted=True,
        planned=9, attempts=9, accepted_runs=9, independent_replays=9, paired_checks=6,
        missing=0, parameter_restore_exact=True, new_flights_by_replay=0)
    if any(not exact(receipt.get(k), v) for k, v in expected.items()):
        raise PermissionError('RI05 D cannot open before complete RI05 C 9/9/6')
    replay_path = Path(receipt['replay_summary_path'])
    if replay_path.parent.parent != DATA_ROOT/'C' or fingerprint(replay_path) != receipt['replay_summary_sha256']:
        raise PermissionError('C independent replay evidence changed')
    # Import scoped dependencies exactly as the CLI does; never reuse old R03 authority.
    bindings = load_file('_ri05_prior_bindings', HERE/'tools/bindings.py')
    replay = bindings.local('replay')
    replay.verify_complete(replay_path.parent, gate='C')
    ledger = read(DATA_ROOT/'C/batch01/ledger.json')
    if (fingerprint(DATA_ROOT/'C/batch01/ledger.json') != receipt['ledger_sha256']
            or ledger['source_head'] != receipt['source_head']
            or ledger['firmware_sha256'] != receipt['firmware_sha256']):
        raise PermissionError('C gate source or ledger binding differs')
    return receipt


def validate_manifest(value=None):
    expected = design()
    if not exact(expected, read(HERE/'execution.json') if value is None else value):
        raise ValueError('RI05 execution changed')
    if not exact(read(HERE/'manifest.json'), expected['jobs']):
        raise ValueError('RI05 manifest changed')
    outcomes = [{k: j[k] for k in ('id', 'gate', 'task', 'seed', 'candidate', 'mode', 'axes')} |
                {'status': 'unattempted'} for j in expected['jobs']]
    if not exact(outcomes, read(HERE/'outcomes_unattempted.json')):
        raise ValueError('Initial registration must remain unattempted')
    return True


def load_protocol(gate='C'):
    cfg = valid_gate(gate)
    scripts = REPO/'research/sta-velocity-control/scripts'
    if str(scripts) not in sys.path:
        sys.path.append(str(scripts))
    from v04_protocol10 import load_protocol as inherited
    d = design()
    p = inherited()
    p.update(copy.deepcopy(d['protocol_overrides']))
    p.update(stage=stage(gate), revision=REVISION, gate=gate, gate_config=cfg,
             jobs=jobs(gate), seeds=cfg['seeds'], **budget(gate),
             execution_authorized=True, flight_authorized=True, execution_ready=True,
             config_dir=str(HERE/'gates'/gate), execution_path=str(HERE/'execution.json'),
             qualification_path=str(DATA_ROOT/gate/'qualification01/evidence.json'),
             post_logger_warmup_us=30000000, simulation_speed=1,
             status=d['status'], scope='Iris SITL C=A/XY then D=B/XYZ: PID/RSTA/RISTA; rate PID; no tuning')
    p['artifacts'] = {**p['artifacts'], 'new_run_root': str(DATA_ROOT/gate/'batch01')}
    # Safe pre-job representation; the runner still merges and verifies every
    # complete frozen job before writing BSON. Never inherit run029 MODE3/AXES7.
    p['startup_overrides'] = {**p['startup_overrides'], **jobs(gate)[0]['parameters']}
    p['candidate'] = {k: v for k, v in d['fixed_parameters'].items()
                      if k.startswith(('MPC_VC_L', 'MPC_VC_NU', 'MPC_VC_A_', 'MPC_VC_EPS_'))}
    p['authorization'] = dict(basis=d['authority'], maximum_attempts=9, this_gate_attempts=9,
                              execution_authorized=True, source=str(AUTHORIZATION))
    p['not_authorized'] = ['RI06', 'old R04/R05', 'hardware', 'DIV2/4', 'tuning', 'push',
                            'replacement flights', 'MODE4 axes2/5/6', 'new ESTA statistics', 'D before complete C']
    p['current_turn_not_run'] = ['RI06', 'old R04/R05', 'formal holdout', 'hardware', 'tuning', 'push']
    p['diagnostic_gate'].update(minimum_excitation_samples=6390, minimum_excitation_span_s=63.96)
    p['pair_gate'].update(maximum_candidate_flights_before_reauthorization=9, candidates=2,
                          order=d['order'], window='64s main and two32s halves;90s position/yaw',
                          calculation='RSTA and RISTA separately versus same-seed PID; six pairs, no superiority requirement')
    p['excitation'] = dict(parameter=cfg['test'], duration_s=64, settle_after_auto_loiter_s=12, task=cfg['task'],
                           source='Original Navigator/FlightTask plus existing task adapter; one publisher; task analytic acceleration FF once, no additional external derivative FF',
                           definition_file=str(HERE/'PROTOCOL_CN.md'))
    p['metrics'].update(primary='Time-weighted consumed per-axis velocity RMSE; J=arithmetic mean;64s main/two32s halves',
                         missing='First mandatory failure stops; require nine accepted/nine independent replays/six pairs; no retry/imputation',
                         interpretation=d['statistics'])
    p['logging'] = 'Keep existing SDLOG_PROFILE bits OR16/1024/2048; complete final R03 time/reset/tail chain'
    return p


def require_execution_authority(gate='C'):
    valid_gate(gate)
    if fingerprint(AUTHORIZATION) != AUTHORIZATION_SHA:
        raise PermissionError('RI05 finite user authority changed')
    validate_manifest()
    return dict(approved=True, stage=stage(gate), revision=REVISION, gate=gate,
                authorization_sha256=AUTHORIZATION_SHA, **budget(gate))


def fresh_seeds(gate='C'):
    selected = [seed for cfg in GATES.values() for seed in cfg['seeds']] if gate is None else valid_gate(gate)['seeds']
    audit = load_file('_ri05_seed_history', REPO/'research/sta-velocity-control/scripts/check_v04_protocol02.py')
    audit.CONFIG = Path('/__RI05_no_directory_exemption__')
    result = audit.seed_audit(selected)
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
        raise PermissionError('Missing exact RI05 authority')
    audit = fresh_seeds(None)
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
    return dict(stage=stage(gate), revision=REVISION, gate=gate, source_head=source_head,
                firmware_sha256=firmware_sha256, execution_sha256=fingerprint(HERE/'execution.json'),
                frozen_sha256=fingerprint(HERE/'gates'/gate/'frozen.json'),
                authorization_sha256=AUTHORIZATION_SHA, new_flights=0,
                execution_authorized=True, flight_authorized=True, execution_ready=True, **budget(gate))


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
    receipt = load_file('_ri05_leaf_receipt', HERE/'receipt.py')
    receipt.validate(q, path, REQUIRED_TARGETS, MIN_PYTHON)
    if not exact(read(path.parent/'authorization.json'), authorization_binding(q, path)):
        raise ValueError('Qualification authorization receipt mismatch')
    freeze = load_file('_ri05_archive_freeze', HERE/'freeze.py')
    freeze.archive_check(gate, source_head, q['frozen_sha256'])
    return q


def require_qualification(gate, source_head, path):
    require_execution_authority(gate)
    require_prior_gate(gate)
    q = archive_qualification(gate, source_head, path)
    if git('rev-parse', 'HEAD') != source_head or git('status', '--porcelain'):
        raise ValueError('Execution requires current qualified clean HEAD')
    if git('branch', '--show-current') != 'research/ista-velocity-regularized':
        raise ValueError('Wrong branch')
    if fingerprint(REPO/'build/px4_sitl_default/bin/px4') != q['firmware_sha256']:
        raise ValueError('Current binary differs from qualified binary')
    load_file('_ri05_launch_freeze', HERE/'freeze.py').check(gate)
    return q


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--gate', choices=GATES, default='C')
    args = parser.parse_args()
    if args.prepare:
        prepare()
    else:
        print(json.dumps(load_protocol(args.gate), ensure_ascii=False, indent=2))
