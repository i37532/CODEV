"""R03 immutable four-gate development design; no simulator side effects.

Activate exactly the unchanged 36 jobs previously reserved in revision02.
Retain eight historical attempts; total 44. Clean per-gate qualification is mandatory.
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
REVISION = 'r03_revision03'
DATA_STAGE = 'R03_revision03'
TOTAL_MAXIMUM_ATTEMPTS = 44
HISTORICAL_ATTEMPTS = 8
NEW_MATRIX_ATTEMPTS = 36
EXECUTION_AUTHORIZED = True
PLAN_STATE = 'execution_authorized_pending_clean_qualification'
HISTORY_SPECS = (
    dict(stage='R03', revision='r03', source_head='f0d07dbbfb1695b59a9e4e1653ac447e05c1afd9',
         ledger_sha256='ce05b50487bc7f2ee39fa607df648f7919613ee8b856b9c9b1073bdbdd331fd8',
         journal_sha256='44072e97baa6d9d7dad4c10019a071eee39c5d9e0310ff383e89d5b10f21ebf5',
         attempts=1, accepted=0, failed=1),
    dict(stage='R03_revision01', revision='r03_revision01', source_head='80c27cb37d889e1b0a70de2124048f6c9075f199',
         ledger_sha256='3f07de0cbb5e7d2b1480d8c1bff3598c30623e2b41946670d066a65de342f0f1',
         journal_sha256='8811941c20b2a20dcbcd264d41a9ea332a7d922d86dff9265b75f27f34e1e9fe',
         attempts=7, accepted=6, failed=1))
PROTECTED_SEEDS = set(range(41001,41021)) | set(range(52001,52021)) | {
    51001,51002,51003,51011,51012,51013,
    71001,71002,71003,71011,71012,71013,71021,71022,71023,71031,71032,71033,
    71041,71042,71043,71051,71052,71053,71061,71062,71063,71071,71072,71073}

GATES = dict(A=dict(axes=1, task='X', test=1, duration=32, seeds=[71101,71102,71103]),
             B=dict(axes=4, task='Z', test=2, duration=32, seeds=[71111,71112,71113]),
             C=dict(axes=3, task='H', test=6, duration=64, seeds=[71121,71122,71123]),
             D=dict(axes=7, task='V', test=8, duration=64, seeds=[71131,71132,71133]))
SEEDS = [s for gate in GATES.values() for s in gate['seeds']]
AUTHORIZATION = HERE.parent/'AUTHORIZATION_R03_REVISION03_CN.md'
SOURCE = REPO/'research/sta-velocity-control/axis_ablation/ax04/execution.json'
SOURCE_SHA = '308aa5a4e52828585bbf6ee3ec0be339a8081475663ceb759de0aee40167d2d3'
AUTHORIZATION_SHA = '221d9e432281203f8319712bdcc1438b2c344ac40d5f642c2f9136be7d386aea'
MIGRATION_FROM = HERE.parent/'r03_revision02'
MIGRATION_REGISTRATION_SHA = '3692990eacc53ee6d8871103d9a38337c3b1ae616f24d82bc5a8acda472ba535'
MIGRATION_FILES = {
    'seed_audit_initial.json':'10d96dcbfe7e4984585dc0acb574e7feb472aa7fe7a3bd42b608264f4943ab7e',
    'execution.json':'6705fc12d7e5960dee2e28b64c4ab3f31d88c61c33278381600098999a82ecad',
    'manifest.json':'1d6e9de215e3a049be06bea07446f3057e3263dd86ee2ff05bcb5b11e2e81597',
    'outcomes_unattempted.json':'9c1c80ee22f5ea484748bb510f72e9d3ef932dca3548f86d82c379f0a01975c1'}



def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def exact(left, right):
    return json.dumps(left,sort_keys=True,separators=(',',':'),allow_nan=False) == \
        json.dumps(right,sort_keys=True,separators=(',',':'),allow_nan=False)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def retained_history():
    """Bind both stopped batches, verdicts, journals and exact parameter restoration."""
    batches = []
    for spec in HISTORY_SPECS:
        root = EXTERNAL/spec['stage']
        ledger_path = root/'A/batch01/ledger.json'
        journal = ledger_path.with_name('journal.jsonl')
        if sorted(root.glob('*/batch*')) != [ledger_path.parent]:
            raise ValueError('Historical batch set changed: '+spec['stage'])
        if sorted(root.glob('*/batch*/ledger.json')) != [ledger_path]:
            raise ValueError('Historical ledger set changed: '+spec['stage'])
        if sorted(root.glob('*/batch*/journal.jsonl')) != [journal]:
            raise ValueError('Historical journal set changed: '+spec['stage'])
        if fingerprint(ledger_path) != spec['ledger_sha256']:
            raise ValueError('Retained history ledger changed: '+spec['stage'])
        if fingerprint(journal) != spec['journal_sha256']:
            raise ValueError('Retained history journal changed: '+spec['stage'])
        ledger = read(ledger_path)
        rows = ledger.get('attempts', [])
        old_jobs = read(HERE.parent/spec['revision']/'execution.json')['jobs'][:spec['attempts']]
        if sorted(ledger_path.parent.glob('run[0-9][0-9][0-9]')) != [
                ledger_path.parent/j['id'] for j in old_jobs]:
            raise ValueError('Historical run directory set changed: '+spec['stage'])
        expected_statuses = ['accepted']*spec['accepted'] + ['failed']*spec['failed']
        if (ledger.get('success') is not False or len(rows) != spec['attempts'] or
                [r.get('status') for r in rows] != expected_statuses or
                not exact([r.get('job') for r in rows], old_jobs) or
                ledger.get('source_head') != spec['source_head'] or
                ledger.get('parameter_restore_exact') is not True or
                ledger.get('remaining_simulators') != []):
            raise ValueError('Retained history count/verdict/cleanup changed: '+spec['stage'])
        records = [json.loads(line) for line in journal.read_text().splitlines()]
        expected_events = [event for status in expected_statuses
                           for event in ('attempt','restore',status)] + ['gate_end']
        if [r.get('event') for r in records] != expected_events:
            raise ValueError('Historical journal event order/count changed')
        backup = ledger_path.parent/'original_parameters.bson'
        backup_sha = fingerprint(backup)
        if backup_sha != ledger.get('original_parameter_sha256'):
            raise ValueError('Historical original parameter backup changed')
        files = {str(backup): backup_sha}
        for i, row in enumerate(rows):
            attempt, restore, verdict = records[i*3:i*3+3]
            job, run = old_jobs[i], ledger_path.parent/old_jobs[i]['id']
            if (not exact(attempt.get('job'), job) or attempt.get('attempt') != i+1 or
                    verdict.get('job_id') != job['id']):
                raise ValueError('Historical journal job binding changed')
            required = dict(source_head=spec['source_head'],gate='A',job_id=job['id'],
                            parameter_restore_exact=True,remaining_simulators=[],
                            stopped_before_restore=True,original_parameter_sha256=backup_sha,
                            restored_parameter_sha256=backup_sha,backup_path=str(backup))
            if any(not exact(restore.get(k),v) for k,v in required.items()):
                raise ValueError('Historical per-attempt restore changed')
            receipt_path = run/'parameter_restore.json'
            receipt = read(receipt_path)
            if any(not exact(receipt.get(k),v) for k,v in required.items()):
                raise ValueError('Historical restore receipt changed')
            files[str(receipt_path)] = fingerprint(receipt_path)
            if row['status'] == 'accepted':
                metrics = run/'r03_metrics.json'
                if (fingerprint(metrics) != row.get('metrics_sha256') or
                        read(metrics).get('accepted') is not True or
                        verdict.get('metrics_sha256') != row['metrics_sha256']):
                    raise ValueError('Historical accepted result changed')
                files[str(metrics)] = fingerprint(metrics)
        end = records[-1]
        if (end.get('success') is not False or end.get('attempts') != spec['attempts'] or
                end.get('parameter_restore_exact') is not True or end.get('remaining_simulators') != []):
            raise ValueError('Historical terminal journal changed')
        batches.append(dict(root=str(root),ledger_path=str(ledger_path),
            ledger_sha256=spec['ledger_sha256'],journal_path=str(journal),
            journal_sha256=spec['journal_sha256'],attempts=spec['attempts'],
            accepted=spec['accepted'],failed=spec['failed'],source_head=spec['source_head'],
            run_ids=[j['id'] for j in old_jobs],seeds=[j['seed'] for j in old_jobs],
            evidence_files=files))
    return dict(attempts=8,accepted=6,failed=2,accepted_for_new_matrix=0,batches=batches)


def retained_failure():
    """Compatibility alias; returns ALL eight retained attempts, not only failures."""
    return retained_history()


def seed_migration():
    """Activate one unchanged reservation; no used data or directory exemptions."""
    registration = MIGRATION_FROM/'seed_reservations.json'
    if fingerprint(registration) != MIGRATION_REGISTRATION_SHA:
        raise ValueError('Migration registration SHA changed')
    expected_files = {str(MIGRATION_FROM/name):sha for name,sha in MIGRATION_FILES.items()}
    if not exact(read(registration), expected_files):
        raise ValueError('Migration registration must be the exact four pinned files')
    for path,sha in expected_files.items():
        if fingerprint(path) != sha:
            raise ValueError('Migration source file changed: '+path)
    old = read(MIGRATION_FROM/'execution.json')
    old_jobs = read(MIGRATION_FROM/'manifest.json')
    if (old.get('revision') != 'r03_revision02' or not exact(old.get('jobs'),old_jobs) or
            len(old_jobs) != NEW_MATRIX_ATTEMPTS or
            any(old.get(k) is not False for k in ('execution_authorized','flight_authorized','execution_ready'))):
        raise ValueError('Migration source is not the closed revision02 design')
    outcomes = [{k:j[k] for k in ('id','gate','task','seed','candidate','mode','axes')}
                | {'status':'unattempted'} for j in old_jobs]
    if not exact(read(MIGRATION_FROM/'outcomes_unattempted.json'),outcomes):
        raise ValueError('Migration source outcomes are not all unattempted')
    root = EXTERNAL/'R03_revision02'
    if (list(root.glob('*/batch*')) or list(root.rglob('ledger.json')) or
            list(root.rglob('journal.jsonl'))):
        raise ValueError('Migration source already has flight/budget records')
    if not exact(old['seeds'],SEEDS) or not exact(old['gates'],GATES):
        raise ValueError('Migration seeds/gates changed')
    return dict(from_revision='r03_revision02',to_revision=REVISION,
        source_entry_head='73c2ef5b5544a27cc8dfcaf6dfe7b2d7ceb0950d',
        source_root=str(MIGRATION_FROM),source_external_root=str(root),
        registration_path=str(registration),registration_sha256=MIGRATION_REGISTRATION_SHA,
        # Receipts and earlier-gate ledgers copy this binding. Do not copy all
        # future gate seeds into them: that would falsely mark them consumed.
        # The pinned source files and the exact checks above bind the seed list.
        files=expected_files,seed_count=len(SEEDS),jobs=NEW_MATRIX_ATTEMPTS,
        prior_attempts_in_source=0,additional_budget=0,
        interpretation='Exact unattempted reservation activation, not a second 36-attempt budget')


def require_execution_authority(gate):
    """Bind explicit user authority; the caller must ALSO verify clean qualification."""
    if gate not in GATES:
        raise ValueError('Unknown gate')
    if EXECUTION_AUTHORIZED is not True or fingerprint(AUTHORIZATION) != AUTHORIZATION_SHA:
        raise PermissionError('Explicit revision03 execution authorization missing or changed')
    validate_manifest()
    d=design()
    if any(d.get(k) is not True for k in ('execution_authorized','flight_authorized','execution_ready')):
        raise PermissionError('Exact authorized plan is not enabled')
    return dict(approved=True,gate=gate,revision=REVISION,maximum_attempts=9,
        total_maximum_attempts=TOTAL_MAXIMUM_ATTEMPTS,new_matrix_attempts=NEW_MATRIX_ATTEMPTS,
        historical_attempts=HISTORICAL_ATTEMPTS,authorization_sha256=AUTHORIZATION_SHA,
        historical_budget=retained_history(),seed_migration=seed_migration())


def build():
    if fingerprint(AUTHORIZATION) != AUTHORIZATION_SHA:
        raise PermissionError('Explicit revision03 execution authorization SHA changed')
    migration=seed_migration()
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
                jobs.append(dict(revision=REVISION, id=f'run{len(jobs)+1:03d}', gate=gate, task=cfg['task'],
                    phase='development', seed=seed, block=block+1, position=position,
                    candidate=name, mode=mode, axes=axes, divisor=1,
                    main_duration_s=cfg['duration'], parameters=parameters))
    previous=read(MIGRATION_FROM/'manifest.json')
    if not exact([{**j,'revision':REVISION} for j in previous],jobs):
        raise ValueError('Only exact unchanged revision02 jobs may be activated')
    return dict(stage='R03-revision03', revision=REVISION, baseline_head=BASE,
        revision_entry_head='73c2ef5b5544a27cc8dfcaf6dfe7b2d7ceb0950d',
        status=PLAN_STATE, execution_authorized=True, flight_authorized=True, execution_ready=True,
        maximum_attempts=TOTAL_MAXIMUM_ATTEMPTS, new_matrix_attempts=NEW_MATRIX_ATTEMPTS,
        historical_attempts=HISTORICAL_ATTEMPTS, historical_budget=retained_failure(), attempts_per_gate=9,
        seed_migration=migration,
        authorization_sha256=fingerprint(AUTHORIZATION), fixed_parameters=fixed, gates=copy.deepcopy(GATES),
        seeds=list(SEEDS), jobs=jobs, parameter_source_sha256=SOURCE_SHA,
        output_root=str(EXTERNAL/DATA_STAGE), protocol_overrides=old['protocol_overrides'],
        order='A9 -> B9 -> C9 -> D9; PID first in each block; alternate old/new after PID globally',
        authority='User explicitly authorized the unchanged new36 within total44; retain all8 history; clean gate qualification required; stop first mandatory failure; no automatic R04/R05; bounded by AUTHORIZATION_R03_REVISION03_CN.md',
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
    if set(SEEDS) & PROTECTED_SEEDS:
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
    p.update(stage='R03-revision03-'+gate, gate=gate, gate_config=copy.deepcopy(cfg),
             jobs=[j for j in d['jobs'] if j['gate']==gate], seeds=list(cfg['seeds']),
             revision=REVISION, maximum_attempts=9, total_maximum_attempts=TOTAL_MAXIMUM_ATTEMPTS,
             new_matrix_attempts=NEW_MATRIX_ATTEMPTS, historical_attempts=HISTORICAL_ATTEMPTS,
             historical_budget=retained_history(), seed_migration=seed_migration(), flight_authorized=True,
             execution_authorized=True, execution_ready=True, config_dir=str(HERE/'gates'/gate),
             execution_path=str(HERE/'execution.json'),
             qualification_path=str(EXTERNAL/DATA_STAGE/gate/'qualification01/evidence.json'))
    p['artifacts'] = {**p['artifacts'], 'new_run_root': str(EXTERNAL/DATA_STAGE/gate/'batch01')}
    p['startup_overrides'] = {**p['startup_overrides'], **d['fixed_parameters']}
    p['candidate'] = {k:v for k,v in d['fixed_parameters'].items()
                      if k.startswith(('MPC_VC_L', 'MPC_VC_NU', 'MPC_VC_A_', 'MPC_VC_EPS_'))}
    p['scope'] = 'Iris SITL R03 '+gate+' fixed-form PID/ESTA/RSTA comparison; all other loops original PID, DIV1'
    p['authorization'] = dict(basis=d['authority'],maximum_attempts=TOTAL_MAXIMUM_ATTEMPTS,this_gate_attempts=9,
        source='Explicit user authorization activates unchanged revision02 new36; clean per-gate qualification still mandatory',
        execution_authorized=True)
    p['status']=PLAN_STATE
    p['not_authorized'] = ['automatic R04/R05','hardware','ISTA','DIV2/4','tuning','V08/V09 changes','replacement flights']
    p['current_turn_not_run'] = ['R04','R05','formal holdout','hardware','ISTA','tuning']
    p['diagnostic_gate'].update(minimum_excitation_samples=3190 if cfg['duration']==32 else 6390,
        minimum_excitation_span_s=cfg['duration']-.04)
    p['pair_gate'].update(maximum_candidate_flights_before_reauthorization=TOTAL_MAXIMUM_ATTEMPTS,candidates=2,
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
    migrated=seed_migration()
    migrated_paths=migrated['files']
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
    result['migration_registrations'] = [x for x in result['matches'] if x['path'] in migrated_paths]
    result['seed_migration'] = migrated
    result['design_registrations'] = [x for x in result['matches'] if x['path'] in allowed]
    result['matches'] = [x for x in result['matches'] if x['path'] not in allowed and x['path'] not in migrated_paths]
    result['accepted'] = not result['matches'] and not result['invalid_json']
    result['excluded'] = 'No directory exclusions; four exact prior unattempted reservation SHAs plus four exact current registration SHAs only'
    return result


def require_previous_gates(gate):
    """A later mask requires exact jobs, six actual pairs and nine raw replays."""
    if gate not in GATES:
        raise ValueError('Unknown gate')
    checked=[]
    for name in list(GATES)[:list(GATES).index(gate)]:
        root=EXTERNAL/DATA_STAGE/name
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
    """Validate clean current-gate qualification and the existing execution authority."""
    require_execution_authority(gate)
    p = load_protocol(gate)
    qpath = Path(path).resolve()
    if EXTERNAL/DATA_STAGE/gate not in qpath.parents:
        raise ValueError('Qualification outside frozen gate evidence root')
    q = read(qpath)
    frozen_path = Path(p['config_dir'])/'frozen.json'
    expected = dict(success=True, clean=True, stage=p['stage'], gate=gate, revision=REVISION,
        execution_authorized=True,flight_authorized=True,execution_ready=True,
        maximum_attempts=9,new_matrix_attempts=NEW_MATRIX_ATTEMPTS,
        historical_attempts=HISTORICAL_ATTEMPTS,total_maximum_attempts=TOTAL_MAXIMUM_ATTEMPTS,
        historical_budget=retained_failure(),seed_migration=seed_migration(),
        source_head=source_head, new_flights=0,
        execution_sha256=fingerprint(HERE/'execution.json'), frozen_sha256=fingerprint(frozen_path),
        firmware_sha256=fingerprint(REPO/'build/px4_sitl_default/bin/px4'))
    for key,value in expected.items():
        if not exact(q.get(key), value):
            raise ValueError('Qualification mismatch: '+key)
    if source_head != git('rev-parse','HEAD') or git('status','--porcelain'):
        raise ValueError('Not the qualified clean source')
    if git('branch','--show-current') != 'research/sta-velocity-regularized':
        raise ValueError('Wrong research branch')
    if any(type(q['counts'].get(k)) is not int or q['counts'][k]<minimum
           for k,minimum in [('cpp_unique_tests',475),('python_tests',709)]):
        raise ValueError('Incomplete qualification regression counts')
    previous=require_previous_gates(gate)
    if not exact(q.get('previous_gates'),previous):
        raise ValueError('Wrong previous gate qualification binding')
    for file,sha in q.get('evidence_files',{}).items():
        if qpath.parent not in Path(file).resolve().parents or fingerprint(file)!=sha:
            raise ValueError('Offline test evidence changed')
    if not q.get('evidence_files'):
        raise ValueError('No offline test evidence files')
    receipt = read(qpath.parent/'authorization.json')
    required = dict(approved=True, stage=p['stage'], gate=gate, revision=REVISION, source_head=source_head,
        execution_authorized=True,flight_authorized=True,execution_ready=True,
        new_matrix_attempts=NEW_MATRIX_ATTEMPTS, historical_attempts=HISTORICAL_ATTEMPTS,
        historical_budget=retained_failure(),seed_migration=seed_migration(),
        execution_sha256=expected['execution_sha256'], frozen_sha256=expected['frozen_sha256'],
        firmware_sha256=expected['firmware_sha256'], qualification_sha256=fingerprint(qpath),
        maximum_attempts=9, total_maximum_attempts=TOTAL_MAXIMUM_ATTEMPTS,
        authorization_sha256=fingerprint(AUTHORIZATION))
    for key,value in required.items():
        if not exact(receipt.get(key), value):
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
