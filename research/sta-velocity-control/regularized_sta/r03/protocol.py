"""R03 immutable four-gate development design; no simulator side effects.

Clean-source qualification records existing user authority, not a new grant.
Every attempt consumes the fixed 36-job manifest. No resumption/replacement.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
EXTERNAL = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016')
BASE = '080528bd30f4a8b7816f5097d789fc71e56ecefe'
GATES = dict(A=dict(axes=1, task='X', test=1, duration=32, seeds=[71001,71002,71003]),
             B=dict(axes=4, task='Z', test=2, duration=32, seeds=[71011,71012,71013]),
             C=dict(axes=3, task='H', test=6, duration=64, seeds=[71021,71022,71023]),
             D=dict(axes=7, task='V', test=8, duration=64, seeds=[71031,71032,71033]))
SEEDS = [s for gate in GATES.values() for s in gate['seeds']]
AUTHORIZATION = HERE.parent/'AUTHORIZATION_CN.md'
SOURCE = REPO/'research/sta-velocity-control/axis_ablation/ax04/execution.json'
SOURCE_SHA = '308aa5a4e52828585bbf6ee3ec0be339a8081475663ceb759de0aee40167d2d3'


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build():
    if fingerprint(SOURCE) != SOURCE_SHA:
        raise ValueError('Historical fixed-parameter source changed')
    old = read(SOURCE)
    fixed = {**old['fixed_parameters'], 'MPC_VC_EPS_X': .01,
             'MPC_VC_EPS_Y': .01, 'MPC_VC_EPS_Z': .02}
    jobs = []
    for gi, (gate, cfg) in enumerate(GATES.items()):
        for block, seed in enumerate(cfg['seeds']):
            tail = [('ESTA',1), ('RSTA',3)] if (gi*3+block)%2 == 0 else [('RSTA',3), ('ESTA',1)]
            for position, (name, mode) in enumerate([('PID',0), *tail], 1):
                axes = cfg['axes'] if mode else 0
                parameters = {**fixed, 'MPC_VC_MODE': mode, 'MPC_VC_AXES': axes,
                              'MPC_VC_DIV': 1, 'MPC_VCT_TEST': cfg['test']}
                jobs.append(dict(id=f'run{len(jobs)+1:03d}', gate=gate, task=cfg['task'],
                    phase='development', seed=seed, block=block+1, position=position,
                    candidate=name, mode=mode, axes=axes, divisor=1,
                    main_duration_s=cfg['duration'], parameters=parameters))
    return dict(stage='R03', baseline_head=BASE, maximum_attempts=36, attempts_per_gate=9,
        authorization_sha256=fingerprint(AUTHORIZATION), fixed_parameters=fixed, gates=copy.deepcopy(GATES),
        seeds=list(SEEDS), jobs=jobs, parameter_source_sha256=SOURCE_SHA,
        output_root=str(EXTERNAL/'R03'), protocol_overrides=old['protocol_overrides'],
        order='A9 -> B9 -> C9 -> D9; PID first in each block; alternate old/new after PID globally',
        authority='User explicitly authorized R00-R05 continuous execution; bounded by AUTHORIZATION_CN.md',
        stop_rule='First mandatory safety, validity, cleanup or paired-risk failure stops; no retry, replacement, seed change or budget addition',
        random_scope='Twelve distinct IMU-only seeds, three paired blocks per gate; non-IMU noise and host scheduling are not claimed independent',
        comparison='Same per-axis lambda, nu/correction limits and protection; epsilon fixed .01/.01/.02; no tuning',
        source_policy='Each gate has its own production-admission commit and clean rebuilt qualification; all nine jobs within a gate share it')


def design():
    return read(HERE/'execution.json')


def validate_manifest(value=None):
    value = design() if value is None else value
    if json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False) != json.dumps(build(),sort_keys=True,separators=(',',':'),allow_nan=False):
        raise ValueError('Frozen R03 design/order/parameters changed')
    if len(value['jobs']) != 36 or len(set(SEEDS)) != 12:
        raise ValueError('Invalid total budget/seeds')
    if set(SEEDS) & (set(range(41001,41021)) | set(range(52001,52021))):
        raise ValueError('Protected seed conflict')
    return True


def load_protocol(gate):
    if gate not in GATES:
        raise ValueError('Unknown gate; never silently substitute X')
    validate_manifest()
    scripts = REPO/'research/sta-velocity-control/scripts'
    if str(scripts) not in sys.path:
        sys.path.append(str(scripts))
    from v04_protocol10 import load_protocol as inherited
    d, cfg = design(), GATES[gate]
    p = inherited()
    p.update(copy.deepcopy(d['protocol_overrides']))
    p.update(stage='R03-'+gate, gate=gate, gate_config=copy.deepcopy(cfg),
             jobs=[j for j in d['jobs'] if j['gate']==gate], seeds=list(cfg['seeds']),
             maximum_attempts=9, total_maximum_attempts=36, flight_authorized=True,
             execution_ready=True, config_dir=str(HERE/'gates'/gate),
             execution_path=str(HERE/'execution.json'),
             qualification_path=str(EXTERNAL/'R03'/gate/'qualification01/evidence.json'))
    p['artifacts'] = {**p['artifacts'], 'new_run_root': str(EXTERNAL/'R03'/gate/'batch01')}
    p['startup_overrides'] = {**p['startup_overrides'], **d['fixed_parameters']}
    p['candidate'] = {k:v for k,v in d['fixed_parameters'].items()
                      if k.startswith(('MPC_VC_L', 'MPC_VC_NU', 'MPC_VC_A_', 'MPC_VC_EPS_'))}
    p['scope'] = 'Iris SITL R03 '+gate+' fixed-form PID/ESTA/RSTA comparison; all other loops original PID, DIV1'
    p['authorization'] = dict(basis=d['authority'],maximum_attempts=36,this_gate_attempts=9,
        source='Clean per-gate qualification and automatic receipt bind the existing continuous user authority')
    p['status']='R03 gate '+gate+' design; executable only with a clean qualification and all earlier gates accepted/replayed'
    p['not_authorized'] = ['hardware','ISTA','DIV2/4','tuning','V08/V09 changes','replacement flights']
    p['current_turn_not_run'] = ['formal holdout','hardware','ISTA','tuning']
    p['diagnostic_gate'].update(minimum_excitation_samples=3190 if cfg['duration']==32 else 6390,
        minimum_excitation_span_s=cfg['duration']-.04)
    p['pair_gate'].update(maximum_candidate_flights_before_reauthorization=36,candidates=2,
        order=d['order'], window=f"{cfg['duration']}s main and two equal halves; 90s position/yaw",
        calculation='Each ESTA and RSTA versus same-gate same-seed PID; no required superiority')
    p['excitation'] = dict(parameter=cfg['test'], duration_s=cfg['duration'], settle_after_auto_loiter_s=12,
        source='Existing single Navigator/FlightTask plus mc_pos_control guarded task adapter; no external setpoint publisher',
        task=cfg['task'], definition_file=str(HERE/'PROTOCOL_CN.md'))
    p['metrics'].update(primary='Time-weighted consumed per-axis velocity RMSE; J=arithmetic mean of three RMSEs; full main window and halves',
        missing='Stop first mandatory failure; no imputation/retry; require all36 and24 paired checks',
        interpretation='Three-algorithm fixed-form development, three IMU seed blocks per gate; no tuning or general superiority claim')
    return p


def fresh_seeds(gate=None):
    scripts = REPO/'research/sta-velocity-control/scripts'
    if str(scripts) not in sys.path:
        sys.path.append(str(scripts))
    # A private loader instance removes the old directory-wide exemption.
    audit = load_file('r03_seed_history', scripts/'check_v04_protocol02.py')
    audit.CONFIG = Path('/__R03_no_directory_exemption__')
    if gate is not None and gate not in GATES:
        raise ValueError('Unknown seed gate')
    result = audit.seed_audit(SEEDS if gate is None else GATES[gate]['seeds'])
    allowed = read(HERE/'seed_reservations.json') if (HERE/'seed_reservations.json').exists() else {}
    expected_paths={str(HERE/(name+'.json')) for name in
                    ('seed_audit_initial','execution','manifest','outcomes_unattempted')}
    if allowed and set(allowed)!=expected_paths:
        raise ValueError('Only exact current unattempted design reservations are permitted')
    if allowed:
        if read(HERE/'manifest.json')!=build()['jobs']:
            raise ValueError('Wrong reserved manifest')
        outcomes=read(HERE/'outcomes_unattempted.json')
        expected_outcomes=[{k:j[k] for k in ('id','gate','task','seed','candidate','mode','axes')}
                           | {'status':'unattempted'} for j in build()['jobs']]
        if outcomes!=expected_outcomes:
            raise ValueError('Reservation contains attempted or changed outcomes')
    for path, sha in allowed.items():
        if fingerprint(path) != sha:
            raise ValueError('Changed exact unattempted registration '+path)
    result['design_registrations'] = [x for x in result['matches'] if x['path'] in allowed]
    result['matches'] = [x for x in result['matches'] if x['path'] not in allowed]
    result['accepted'] = not result['matches'] and not result['invalid_json']
    result['excluded'] = 'No directory exclusions; exact fingerprinted unattempted design files only'
    return result


def require_previous_gates(gate):
    """A later mask requires exact jobs, six actual pairs and nine raw replays."""
    if gate not in GATES:
        raise ValueError('Unknown gate')
    checked=[]
    for name in list(GATES)[:list(GATES).index(gate)]:
        root=EXTERNAL/'R03'/name
        receipt=read(root/'gate_pass.json')
        # Recompute from immutable source/replay inputs rather than accepting
        # caller-written aggregate booleans, counts or a list of hashes alone.
        verifier=load_file('r03_previous_gate_replay',HERE/'replay.py')
        expected=verifier.verify_complete(name,root)
        if json.dumps(receipt,sort_keys=True,separators=(',',':'),allow_nan=False) != \
                json.dumps(expected,sort_keys=True,separators=(',',':'),allow_nan=False):
            raise ValueError('Previous gate receipt differs from verified raw evidence '+name)
        checked.append(dict(gate=name,receipt_sha256=fingerprint(root/'gate_pass.json')))
    return checked


def require_qualification(gate, source_head, path):
    p = load_protocol(gate)
    qpath = Path(path).resolve()
    if EXTERNAL/'R03'/gate not in qpath.parents:
        raise ValueError('Qualification outside frozen gate evidence root')
    q = read(qpath)
    frozen_path = Path(p['config_dir'])/'frozen.json'
    expected = dict(success=True, clean=True, stage=p['stage'], gate=gate,
        source_head=source_head, new_flights=0,
        execution_sha256=fingerprint(HERE/'execution.json'), frozen_sha256=fingerprint(frozen_path),
        firmware_sha256=fingerprint(REPO/'build/px4_sitl_default/bin/px4'))
    for key,value in expected.items():
        if q.get(key) != value:
            raise ValueError('Qualification mismatch: '+key)
    if source_head != git('rev-parse','HEAD') or git('status','--porcelain'):
        raise ValueError('Not the qualified clean source')
    if git('branch','--show-current') != 'research/sta-velocity-regularized':
        raise ValueError('Wrong research branch')
    if any(type(q['counts'].get(k)) is not int or q['counts'][k]<minimum
           for k,minimum in [('cpp_unique_tests',475),('python_tests',709)]):
        raise ValueError('Incomplete qualification regression counts')
    previous=require_previous_gates(gate)
    if q.get('previous_gates')!=previous:
        raise ValueError('Wrong previous gate qualification binding')
    for file,sha in q.get('evidence_files',{}).items():
        if qpath.parent not in Path(file).resolve().parents or fingerprint(file)!=sha:
            raise ValueError('Offline test evidence changed')
    if not q.get('evidence_files'):
        raise ValueError('No offline test evidence files')
    receipt = read(qpath.parent/'authorization.json')
    required = dict(approved=True, stage=p['stage'], gate=gate, source_head=source_head,
        execution_sha256=expected['execution_sha256'], frozen_sha256=expected['frozen_sha256'],
        firmware_sha256=expected['firmware_sha256'], qualification_sha256=fingerprint(qpath),
        maximum_attempts=9, total_maximum_attempts=36,
        authorization_sha256=fingerprint(AUTHORIZATION))
    for key,value in required.items():
        if receipt.get(key) != value:
            raise ValueError('Authority receipt mismatch: '+key)
    return q


def prepare():
    if (HERE/'execution.json').exists():
        raise ValueError('Refuse to replace existing R03 registration')
    audit = fresh_seeds()
    if not audit['accepted']:
        raise ValueError('Seed history collision/invalid JSON: '+str(audit))
    records = dict(seed_audit_initial=audit, execution=build(), manifest=build()['jobs'],
        outcomes_unattempted=[{k:j[k] for k in ('id','gate','task','seed','candidate','mode','axes')}
                             | {'status':'unattempted'} for j in build()['jobs']])
    for name,value in records.items():
        with (HERE/(name+'.json')).open('x') as stream:
            json.dump(value,stream,indent=2,ensure_ascii=False); stream.write('\n')
    with (HERE/'seed_reservations.json').open('x') as stream:
        json.dump({str(HERE/(n+'.json')):fingerprint(HERE/(n+'.json')) for n in records},stream,indent=2)
        stream.write('\n')


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--gate',choices=GATES,default='A')
    args=parser.parse_args()
    if args.prepare:
        prepare()
    else:
        print(json.dumps(load_protocol(args.gate)['jobs'],indent=2))
