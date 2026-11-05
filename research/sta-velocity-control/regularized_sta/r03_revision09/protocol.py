"""A new full A/B/C/D 36-run matrix with exact source and finite budget.

Preparation registers the complete manifest without flight. Execution requires
the new clean-source qualification and independent preceding-gate replay.
Old UP08 diagnostic qualification never authorizes the revised matrix.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

REPO=Path('/home/yr/Desktop/Codev-autopilot')
BASE=REPO/'research/sta-velocity-control/regularized_sta'
HERE=BASE/'r03_revision09'
EXTERNAL=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016')
DATA_ROOT=EXTERNAL/'R03_revision09'
REVISION='r03_revision09'
ENTRY_HEAD='73bfcb06c5ef99e54af3f13b07840f2bcc1579fb'
DRAFT_ONLY=False
AUTHORIZATION=BASE/'AUTHORIZATION_R03_REVISION09_CN.md'
AUTHORIZATION_SHA='7eb4268388ecd841f179cd66b79d8a610db511d82015d4cddacbf88651ea66d7'
UPSTREAM_REPLAY_RECEIPT=EXTERNAL/'R03_upstream08/offline_diagnostic_replay01/results_v2_01/summary.json'
UPSTREAM_REPLAY_SHA='88830fc70aa6bc8874603a032ca82ca53e1163d99d23c615b8dc428a0dfc8992'
DIAGNOSTIC_HEAD='1273eed615cf36845c0ad61f23e44a6edcb15089'
TOTAL_MAXIMUM_ATTEMPTS=90
HISTORICAL_ATTEMPTS=54
NEW_MATRIX_ATTEMPTS=36
DATA_STAGE='R03_revision09'
GATES={
    'A':dict(task='X',axes=1,test=1,duration=32,seeds=(71601,71602,71603),source='r03_revision04'),
    'B':dict(task='Z',axes=4,test=2,duration=32,seeds=(71611,71612,71613),source='r03_revision05'),
    'C':dict(task='H',axes=3,test=6,duration=64,seeds=(71621,71622,71623),source='r03_revision05'),
    'D':dict(task='V',axes=7,test=8,duration=64,seeds=(71631,71632,71633),source='r03_revision05')}
SOURCE_SHA={
    'r03_revision04':'f3a4634448d96ec79de201a51bec36b09f11bc4cfbceb09396c8c3acd827b7ad',
    'r03_revision05':'78d0d6ba0f9460b64d5fcfc7874c838ed591e6612894eab2ea1e347f00db411f'}
REGISTRATION_NAMES=('seed_audit_initial.json','execution.json','manifest.json','outcomes_unattempted.json')
UPSTREAM=BASE/'r03_upstream08'
DIAGNOSTICS=EXTERNAL/'R03_upstream08/diagnostic01/batch01'
DIAGNOSTIC_SHA={
    'ledger.json':'fa288fc575afdd43d4fe6968302a678b481d6dbd63b3f89068a5afc163e192d8',
    'journal.jsonl':'7d80547f35a45a7854d2a55dd3341a8a4df16ca2af772e4f2832262771cee906',
    'original_parameters.bson':'06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc',
    'diag001/result.json':'149db907baed7759d1ea6e541f4dcaac4a4e9a4b4082406b8bc7c1456b71dd45',
    'diag001/parameter_restore.json':'3805277b1018e95503e27a69a04c20151942d047ade36566055ecd6109c5eacd',
    'diag001/diagnostic_metrics.json':'749d4fb3dff5bfc83ecaa4cd124f1e4fa69173941e610ccf57a166929f7622bf',
    'diag002/result.json':'a01a4b59eb7360400be203c9b41602500b4061360ef2512071efc1c2c03c9c52',
    'diag002/parameter_restore.json':'949067cfd41dd5baca178cac0dbb204063c0ba8a7de9adda396ff485c7150eb5',
    'diag002/diagnostic_metrics.json':'14747fe2476bc5374d31110e75745c7049e9fd21fa1ac74eeb16d0f6d9f6e60b',
    'diag002/diagnostic_pair.json':'2bf91948f8bcbf5364d3133f0b9cb013e74d89a63c4b4b8111cd0503d0f93e28'}
MIN_CPP=541
MIN_PYTHON=1258


def read(path):return json.loads(Path(path).read_text())
def fingerprint(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def exact(a,b):return json.dumps(a,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(b,sort_keys=True,separators=(',',':'),allow_nan=False)
def git(*args):return subprocess.check_output(['git',*args],cwd=REPO,text=True).strip()
def load_file(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def valid_gate(gate):
    if gate not in GATES:raise ValueError('Unknown revision09 gate')
    return GATES[gate]
def _activated():
    return (not DRAFT_ONLY and Path(__file__).resolve().parent==HERE
            and isinstance(AUTHORIZATION_SHA,str) and len(AUTHORIZATION_SHA)==64
            and UPSTREAM_REPLAY_RECEIPT is not None and UPSTREAM_REPLAY_SHA is not None)
def _sealed_module(revision):
    path=BASE/revision/'protocol.py'
    committed=subprocess.check_output(['git','show',ENTRY_HEAD+':'+str(path.relative_to(REPO))],cwd=REPO)
    if hashlib.sha256(committed).hexdigest()!=fingerprint(path):raise ValueError('Inherited protocol source changed')
    return load_file('_revision09_readonly_'+revision,path)


def budget(gate=None):
    """Global36 or one gate9; prior_attempts includes completed NEW previous gates."""
    if gate is not None:valid_gate(gate)
    return dict(maximum_attempts=36 if gate is None else 9,new_matrix_attempts=36,
        historical_attempts=54,total_maximum_attempts=90,
        prior_attempts=54 if gate is None else 54+9*list(GATES).index(gate),
        retained_accepted_attempts=46,retained_invalid_attempts=6,retained_diagnostic_attempts=2,
        retained_takeoffs=53,required_pairs=24 if gate is None else 6,
        required_replays=36 if gate is None else 9,n_per_algorithm=3,
        diagnostic_only=False,count_as_R03_acceptance=True,logging_profile=3089)


def retained_history():
    """52 old attempts plus two completed diagnostics; diagnostics are not failures."""
    upstream=_sealed_module('r03_upstream08');h=upstream.retained_history()
    if not exact({k:h[k] for k in ('attempts','takeoffs','accepted','failed')},
                 dict(attempts=52,takeoffs=51,accepted=46,failed=6)):
        raise ValueError('Original history counts changed')
    if sorted((EXTERNAL/'R03_upstream08').glob('diagnostic*/batch*'))!=[DIAGNOSTICS]:
        raise ValueError('Extra upstream diagnostic batch')
    for name,sha in DIAGNOSTIC_SHA.items():
        if fingerprint(DIAGNOSTICS/name)!=sha:raise ValueError('Diagnostic original changed '+name)
    ledger=read(DIAGNOSTICS/'ledger.json');journal=[json.loads(x) for x in (DIAGNOSTICS/'journal.jsonl').read_text().splitlines()]
    jobs=upstream.design()['jobs'];rows=ledger['attempts']
    if (not exact([x['job'] for x in rows],jobs) or [x['status'] for x in rows]!=['diagnostic_complete']*2
            or ledger.get('success') is not True or ledger.get('parameter_restore_exact') is not True
            or ledger.get('remaining_simulators')!=[] or ledger.get('unattempted')!=[]
            or ledger.get('accepted_for_R03')!=0 or ledger.get('r03_gate_pass') is not False
            or ledger.get('source_head')!=DIAGNOSTIC_HEAD):
        raise ValueError('Diagnostic original outcome changed')
    if [x['event'] for x in journal]!=['attempt','restore','diagnostic_complete']*2+['diagnostic_end']:
        raise ValueError('Diagnostic journal sequence changed')
    takeoffs=0
    for i,job in enumerate(jobs):
        run=DIAGNOSTICS/job['id'];result=read(run/'result.json');m=read(run/'diagnostic_metrics.json');restore=read(run/'parameter_restore.json')
        if (result.get('success') is not True or result.get('source_head')!=DIAGNOSTIC_HEAD
                or m.get('diagnostic_checks_complete') is not True or m.get('scientific_checks_complete') is not True
                or m.get('accepted') is not False or m.get('flight_accepted') is not False
                or m.get('accepted_for_R03')!=0 or not exact(m['job'],job)
                or rows[i]['metrics_sha256']!=fingerprint(run/'diagnostic_metrics.json')
                or restore.get('parameter_restore_exact') is not True
                or restore.get('remaining_simulators')!=[] or restore.get('stopped_before_restore') is not True
                or restore.get('original_parameter_sha256')!=DIAGNOSTIC_SHA['original_parameters.bson']
                or restore.get('restored_parameter_sha256')!=DIAGNOSTIC_SHA['original_parameters.bson']):
            raise ValueError('Diagnostic run/restore changed')
        takeoffs+=sum(e['name']=='takeoff_command' for e in result['events'])
    pair=read(DIAGNOSTICS/'diag002/diagnostic_pair.json')
    if takeoffs!=2 or pair.get('development_risk_passed') is not True or pair.get('accepted') is not False:
        raise ValueError('Diagnostic takeoff/pair record changed')
    h['batches'].append(dict(root=str(DIAGNOSTICS.parent),ledger_path=str(DIAGNOSTICS/'ledger.json'),
        ledger_sha256=DIAGNOSTIC_SHA['ledger.json'],journal_path=str(DIAGNOSTICS/'journal.jsonl'),
        journal_sha256=DIAGNOSTIC_SHA['journal.jsonl'],attempts=2,takeoffs=2,accepted=0,failed=0,
        diagnostic_complete=2,accepted_for_new_matrix=0,source_head=DIAGNOSTIC_HEAD,
        evidence_files={str(DIAGNOSTICS/n):sha for n,sha in DIAGNOSTIC_SHA.items()}))
    h.update(attempts=54,takeoffs=53,accepted=46,failed=6,diagnostic_complete=2,accepted_for_new_matrix=0)
    return h


def retained_abc():
    out=_sealed_module('r03_upstream08').retained_abc()
    out['counts_toward_new_matrix']=False
    out['interpretation']='Historical gates retained unchanged; all four new gates must independently complete9.'
    return out


def diagnostic_replay_binding():
    if UPSTREAM_REPLAY_RECEIPT is None or UPSTREAM_REPLAY_SHA is None:
        raise PermissionError('Completed diagnostic independent replay has not yet been bound')
    path=Path(UPSTREAM_REPLAY_RECEIPT).resolve()
    if EXTERNAL/'R03_upstream08' not in path.parents or fingerprint(path)!=UPSTREAM_REPLAY_SHA:
        raise ValueError('Wrong diagnostic replay proof')
    receipt=read(path)
    if (receipt.get('success') is not True or receipt.get('diagnostic_only') is not True
            or receipt.get('accepted_for_R03')!=0 or receipt.get('new_flights')!=0
            or receipt.get('source_inputs_unchanged') is not True):
        raise ValueError('Incomplete or relabelled diagnostic replay')
    return dict(path=str(path),sha256=UPSTREAM_REPLAY_SHA,diagnostic_only=True,
                accepted_for_R03=0,new_flights=0,source_head=DIAGNOSTIC_HEAD)


def retained_failure():
    return retained_history()


def seed_migration():
    return dict(kind='none',to_revision=REVISION,files={},seed_count=0,jobs=0,
        additional_budget=0,interpretation='Fresh seeds only; no prior registration exemptions')


def source_jobs(gate):
    cfg=valid_gate(gate);path=BASE/cfg['source']/'manifest.json'
    if fingerprint(path)!=SOURCE_SHA[cfg['source']]:raise ValueError('Historical manifest changed')
    rows=[j for j in read(path) if j['gate']==gate]
    if len(rows)!=9:raise ValueError('Historical gate is not nine jobs')
    return rows


def design():
    """Reconstruct the exact registered36 in memory; no filesystem mutation."""
    seeds=[s for cfg in GATES.values() for s in cfg['seeds']]
    if len(seeds)!=12 or len(set(seeds))!=12 or any(type(s) is not int or s<=0 for s in seeds):
        raise ValueError('Exactly twelve distinct positive integral seed candidates')
    jobs=[]
    for gate,cfg in GATES.items():
        old=source_jobs(gate)
        for i,previous in enumerate(old):
            j=copy.deepcopy(previous)
            j.update(revision=REVISION,seed=cfg['seeds'][i//3],phase='development',role='matrix')
            if len(j['parameters'])!=127:raise ValueError('Incomplete scientific parameters')
            jobs.append(j)
    if len(jobs)!=36 or len({j['id'] for j in jobs})!=36:
        raise ValueError('Exactly36 globally distinct jobs required')
    source=_sealed_module('r03_revision04').design()
    active=_activated()
    return dict(stage='R03-revision09',revision=REVISION,
        status='authorized_pending_new_clean_qualification' if active else 'draft_not_registered',
        execution_authorized=active,flight_authorized=active,execution_ready=active,
        **budget(),jobs=jobs,fixed_parameters=source['fixed_parameters'],
        protocol_overrides=source['protocol_overrides'],historical_budget=retained_history(),
        retained_abc=retained_abc(),entry_head=ENTRY_HEAD,
        parameter_sources={str(BASE/r/'manifest.json'):sha for r,sha in SOURCE_SHA.items()},
        diagnostic_replay_required=True,same_source_all36=True,seed_migration=seed_migration(),
        order='Each gate original nine-job order; A then B then C then D; first required failure stops',
        scientific_scope='All four gates newly repeated at n=3 per algorithm; no historical sample pooling')


def load_protocol(gate):
    cfg=valid_gate(gate);d=design();p=copy.deepcopy(_sealed_module(cfg['source']).load_protocol(gate))
    p.update(stage='R03-revision09-'+gate,revision=REVISION,gate=gate,role='matrix',
        gate_config={k:copy.deepcopy(v) for k,v in cfg.items() if k!='source'},
        jobs=[j for j in d['jobs'] if j['gate']==gate],seeds=list(cfg['seeds']),**budget(gate),
        historical_budget=d['historical_budget'],retained_abc=d['retained_abc'],
        execution_authorized=d['execution_authorized'],flight_authorized=d['flight_authorized'],
        execution_ready=d['execution_ready'],
        same_source_all36=True,config_dir=str(HERE/'gates'/gate),
        execution_path=str(HERE/'execution.json'),
        qualification_path=str(DATA_ROOT/gate/'qualification01/evidence.json'))
    p['seed_migration']=seed_migration();p.pop('retained_a',None)
    p['artifacts']={**p['artifacts'],'new_run_root':str(DATA_ROOT/gate/'batch01')}
    p['authorization']=dict(basis='Continuous user authorization, frozen finite revision09',maximum_attempts=90,this_gate_attempts=9)
    p['status']=d['status']
    p['scope']='New full36 final-firmware Iris SITL development matrix; no tuning or historical pooling'
    p['logging']='Inherited1041 OR2048 =3089; original raw gyro coverage and complete protections'
    p['pair_gate'].update(maximum_candidate_flights_before_reauthorization=90,candidates=2,order=d['order'])
    p['excitation']['definition_file']=str(HERE/'PROTOCOL_CN.md')
    p['metrics'].update(missing='First mandatory failure stops; all36 required; no retry/imputation/history pooling',
        interpretation='Same final source, each gate three paired IMU blocks; different tasks not pooled')
    return p


def validate_manifest(value=None):
    registered=read(HERE/'execution.json') if value is None else value
    if not exact(registered,design()) or not exact(read(HERE/'manifest.json'),design()['jobs']):
        raise ValueError('Registered revision09 design differs')
    return True


def require_execution_authority(gate):
    valid_gate(gate)
    if DRAFT_ONLY or Path(__file__).resolve().parent!=HERE or not AUTHORIZATION_SHA:
        raise PermissionError('External draft never grants execution authority')
    if fingerprint(AUTHORIZATION)!=AUTHORIZATION_SHA:raise PermissionError('New revision09 authority missing/changed')
    validate_manifest();diagnostic_replay_binding()
    if any(design().get(k) is not True for k in ('execution_authorized','flight_authorized','execution_ready')):
        raise PermissionError('Revision09 activation has not been explicitly frozen')
    return dict(approved=True,gate=gate,revision=REVISION,authorization_sha256=AUTHORIZATION_SHA,**budget(gate))


def fresh_seeds(gate=None):
    """Initial full12 audit, then CURRENT gate3 only; never exempt data directories."""
    selected=[s for cfg in GATES.values() for s in cfg['seeds']] if gate is None else valid_gate(gate)['seeds']
    audit=load_file('_revision09_seed_audit',REPO/'research/sta-velocity-control/scripts/check_v04_protocol02.py')
    audit.CONFIG=Path('/__revision09_no_directory_exemption__');result=audit.seed_audit(selected)
    reservation=HERE/'seed_reservations.json';allowed=read(reservation) if reservation.exists() else {}
    if allowed:
        if set(allowed)!={str(HERE/n) for n in REGISTRATION_NAMES}:raise ValueError('Unexpected registration exemption')
        validate_manifest()
        expected=[{k:j[k] for k in ('id','gate','task','seed','candidate','mode','axes')}|{'status':'unattempted'} for j in design()['jobs']]
        if not exact(read(HERE/'outcomes_unattempted.json'),expected):raise ValueError('Changed unattempted registration')
        for path,sha in allowed.items():
            if fingerprint(path)!=sha:raise ValueError('Registration SHA changed')
    result['design_registrations']=[x for x in result['matches'] if x['path'] in allowed]
    result['matches']=[x for x in result['matches'] if x['path'] not in allowed]
    result['accepted']=not result['matches'] and not result['invalid_json']
    result['scope']='Current gate only after initial audit; four exact registration SHAs only'
    return result


def require_previous_gates(gate,source_head=None,firmware_sha256=None):
    """Only NEW revision09 gates qualify; retained old ABC are never prerequisites."""
    valid_gate(gate);proof=[]
    source_head=git('rev-parse','HEAD') if source_head is None else source_head
    for name in list(GATES)[:list(GATES).index(gate)]:
        root=DATA_ROOT/name
        if not (root/'gate_pass.json').is_file():raise ValueError('Previous new gate receipt missing: '+name)
        receipt=read(root/'gate_pass.json')
        verifier=load_file('_revision09_previous_replay',HERE/'replay.py')
        expected=verifier.verify_complete(name,root)
        if not exact(receipt,expected) or receipt.get('source_head')!=source_head:
            raise ValueError('Previous new gate incomplete or from another source')
        if firmware_sha256 is not None and receipt.get('firmware_sha256')!=firmware_sha256:
            raise ValueError('Previous new gate used another firmware')
        proof.append(dict(gate=name,revision=REVISION,source_head=source_head,
                          firmware_sha256=receipt.get('firmware_sha256'),
                          receipt_sha256=fingerprint(root/'gate_pass.json')))
    return proof


def qualification_binding(gate,source_head,firmware_sha256):
    """New root verifier calls with its measured source and binary; no live-BIN lookup."""
    require_execution_authority(gate)
    return dict(stage='R03-revision09-'+gate,revision=REVISION,gate=gate,source_head=source_head,
        firmware_sha256=firmware_sha256,new_flights=0,execution_authorized=True,
        flight_authorized=True,execution_ready=True,**budget(gate),
        historical_budget=retained_history(),retained_abc=retained_abc(),seed_migration=seed_migration(),
        diagnostic_replay=diagnostic_replay_binding(),previous_gates=require_previous_gates(gate,source_head,firmware_sha256),
        authorization_sha256=AUTHORIZATION_SHA,execution_sha256=fingerprint(HERE/'execution.json'),
        frozen_sha256=fingerprint(HERE/'gates'/gate/'frozen.json'))


def authorization_binding(q,path):
    """Receipt projection from a NEW qualified record; no old qualification remap."""
    keys=('stage','revision','gate','source_head','firmware_sha256','new_flights',
          'execution_authorized','flight_authorized','execution_ready','historical_budget',
          'retained_abc','seed_migration','diagnostic_replay','previous_gates','authorization_sha256',
          'execution_sha256','frozen_sha256',*budget(q['gate']))
    return dict(approved=True,qualification_sha256=fingerprint(path),**{k:q[k] for k in keys})


def archive_qualification(gate,source_head,path):
    """Read-only historical proof; NOT current HEAD/BIN and NOT launch permission.

freeze.archive_check(gate, source_head, frozen_sha256) must verify committed
asset blobs at source_head, external asset SHA and original frozen structure.
It must not merely call the current-working-tree freeze.check().
"""
    valid_gate(gate);path=Path(path).resolve()
    if DRAFT_ONLY or Path(__file__).resolve().parent!=HERE:raise PermissionError('Draft has no historical qualifications')
    if DATA_ROOT/gate not in path.parents:raise ValueError('Foreign qualification root')
    q=read(path)
    expected=dict(success=True,clean=True,stage='R03-revision09-'+gate,revision=REVISION,gate=gate,
        source_head=source_head,new_flights=0,execution_authorized=True,flight_authorized=True,
        execution_ready=True,**budget(gate),historical_budget=retained_history(),retained_abc=retained_abc(),seed_migration=seed_migration(),
        diagnostic_replay=diagnostic_replay_binding(),authorization_sha256=AUTHORIZATION_SHA,
        execution_sha256=fingerprint(HERE/'execution.json'),
        frozen_sha256=fingerprint(HERE/'gates'/gate/'frozen.json'))
    if any(not exact(q.get(k),v) for k,v in expected.items()):raise ValueError('Archived qualification identity changed')
    if (not isinstance(q.get('firmware_sha256'),str) or len(q['firmware_sha256'])!=64
            or any(type(q.get('counts',{}).get(k)) is not int or q['counts'][k]<n
                   for k,n in [('cpp_unique_tests',MIN_CPP),('python_tests',MIN_PYTHON)])):
        raise ValueError('Missing qualified binary/actual regression counts')
    if not {'functional-VehicleIMU','functional-EKF2SelectorTiming','functional-EstimatorDiagnosticTopics'}<=set(q.get('cpp_test_targets',[])):
        raise ValueError('Missing actual upstream regression targets')
    if not q.get('evidence_files'):raise ValueError('Missing qualification evidence')
    for name,sha in q['evidence_files'].items():
        if path.parent not in Path(name).resolve().parents or fingerprint(name)!=sha:raise ValueError('Changed qualification evidence')
    if not exact(read(path.parent/'authorization.json'),authorization_binding(q,path)):
        raise ValueError('Wrong new qualification receipt')
    freeze=load_file('_revision09_archive_freeze',HERE/'freeze.py')
    freeze.archive_check(gate,source_head,q['frozen_sha256'])
    if not exact(q.get('previous_gates'),require_previous_gates(gate,source_head,q['firmware_sha256'])):
        raise ValueError('Archived previous-gate source/proof differs')
    return q


def require_qualification(gate,source_head,path):
    """Launch-only current-source guard, on top of archival evidence validation."""
    require_execution_authority(gate);q=archive_qualification(gate,source_head,path)
    if (git('rev-parse','HEAD')!=source_head or git('status','--porcelain')
            or git('branch','--show-current')!='research/sta-velocity-regularized'):
        raise ValueError('Not the currently qualified clean source')
    freeze=load_file('_revision09_launch_freeze',HERE/'freeze.py');freeze.check(gate)
    if fingerprint(REPO/'build/px4_sitl_default/bin/px4')!=q['firmware_sha256']:
        raise ValueError('Current binary differs from qualified source')
    return q


def prepare():
    if any((HERE/n).exists() for n in (*REGISTRATION_NAMES,'seed_reservations.json')):
        raise ValueError('Refuse to overwrite existing registration')
    if not _activated() or fingerprint(AUTHORIZATION)!=AUTHORIZATION_SHA:
        raise PermissionError('Finite revision09 authority not frozen')
    diagnostic_replay_binding();audit=fresh_seeds()
    if not audit['accepted']:raise ValueError('Seed collision or invalid JSON: '+str(audit))
    d=design()
    records={'seed_audit_initial.json':audit,'execution.json':d,'manifest.json':d['jobs'],
        'outcomes_unattempted.json':[{k:j[k] for k in ('id','gate','task','seed','candidate','mode','axes')}|{'status':'unattempted'} for j in d['jobs']]}
    for name,value in records.items():
        with (HERE/name).open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    with (HERE/'seed_reservations.json').open('x') as f:
        json.dump({str(HERE/n):fingerprint(HERE/n) for n in REGISTRATION_NAMES},f,indent=2);f.write('\n')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true');parser.add_argument('--gate',choices=GATES,default='A')
    args=parser.parse_args()
    if args.prepare:prepare()
    else:print(json.dumps(load_protocol(args.gate),indent=2))
