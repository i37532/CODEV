"""D-only continuation after exact equal-publication/advancing-sample reproduction.

Preparation registers nine new D jobs without flight. Execution requires
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
HERE=BASE/'r03_revision11'
EXTERNAL=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016')
DATA_ROOT=EXTERNAL/'R03_revision11'
REVISION='r03_revision11'
ENTRY_HEAD='17b1a4df1e56ec4de872d087983fdd41497b26af'
DRAFT_ONLY=False
AUTHORIZATION=BASE/'AUTHORIZATION_R03_REVISION11_CN.md'
AUTHORIZATION_SHA='d03a505eb59e7b971bfb797b4054643d16cf9704f69fb7b6ed1cb916ed89cbb6'
UPSTREAM_REPLAY_RECEIPT=EXTERNAL/'R03_upstream08/offline_diagnostic_replay01/results_v2_01/summary.json'
UPSTREAM_REPLAY_SHA='88830fc70aa6bc8874603a032ca82ca53e1163d99d23c615b8dc428a0dfc8992'
DIAGNOSTIC_HEAD='1273eed615cf36845c0ad61f23e44a6edcb15089'
TOTAL_MAXIMUM_ATTEMPTS=97
HISTORICAL_ATTEMPTS=88
NEW_MATRIX_ATTEMPTS=9
DATA_STAGE='R03_revision11'
GATES={'D':dict(task='V',axes=7,test=8,duration=64,seeds=(71831,71832,71833),source='r03_revision05')}
PREVIOUS=BASE/'r03_revision09'
PREVIOUS_HEAD='eb25fecbdba9a499132a16ce16f6b847e4a218d3'
PREVIOUS_FIRMWARE='4b62cde850d5612cccb7392acfd7b2040b98e18c61efb2eaa98d3162154f98cc'
PREVIOUS_RECEIPTS={
 'A':'03654f4015a6b2110353749e654eef3108eae2e30970b2dbdff6b86feb9686ad',
 'B':'19be1806782b4af196cff4282c80d9e2167d5a5e5c38f95865353a04a957fdf2',
 'C':'58cebb1f1f2fec1a2ecb76d299954ec281d068e646dd980f72e6386c0c9e29df'}
FAILED_LEDGER_SHA='baed1b94a5d0d75272ab788e9f2ffe6420dbeda446c802748b5fe8b89871808c'
FAILED_JOURNAL_SHA='566af65eb9102e964a4251e1ca1ac39924775587c29fe2eb4b62ef4d87784406'



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
    if gate not in GATES:raise ValueError('Unknown revision11 gate')
    return GATES[gate]
def _activated():
    return (not DRAFT_ONLY and Path(__file__).resolve().parent==HERE
            and isinstance(AUTHORIZATION_SHA,str) and len(AUTHORIZATION_SHA)==64
            and UPSTREAM_REPLAY_RECEIPT is not None and UPSTREAM_REPLAY_SHA is not None)
def _sealed_module(revision):
    path=BASE/revision/'protocol.py'
    committed=subprocess.check_output(['git','show',ENTRY_HEAD+':'+str(path.relative_to(REPO))],cwd=REPO)
    if hashlib.sha256(committed).hexdigest()!=fingerprint(path):raise ValueError('Inherited protocol source changed')
    return load_file('_revision11_readonly_'+revision,path)


def budget(gate=None):
    if gate is not None:valid_gate(gate)
    return dict(maximum_attempts=9,new_matrix_attempts=9,historical_attempts=88,total_maximum_attempts=97,
        prior_attempts=88,retained_accepted_attempts=78,retained_invalid_attempts=8,retained_diagnostic_attempts=2,
        retained_takeoffs=86,required_pairs=6,required_replays=9,n_per_algorithm=3,
        diagnostic_only=False,count_as_R03_acceptance=True,logging_profile=3089)



def retained_history():
    h=_sealed_module('r03_revision10').retained_history()
    root=EXTERNAL/'R03_revision10';batch=root/'D/batch01'
    lp=batch/'ledger.json';jp=batch/'journal.jsonl'
    if sorted(root.glob('*/batch*'))!=[batch]:raise ValueError('Revision10 batch set changed')
    if fingerprint(lp)!=FAILED_LEDGER_SHA or fingerprint(jp)!=FAILED_JOURNAL_SHA:
        raise ValueError('Revision10 stopped ledger/journal changed')
    ledger=read(lp);jobs=read(BASE/'r03_revision10/manifest.json');rows=ledger['attempts']
    if (len(rows)!=6 or not exact([x['job'] for x in rows],jobs[:6])
            or ledger['source_head']!='17b1a4df1e56ec4de872d087983fdd41497b26af'
            or ledger['firmware_sha256']!='7bc426ed0dda36dabd1ee36a80600dbe5730599e30d74cd678562468c74a7b9b'
            or ledger['success'] is not False or ledger['parameter_restore_exact'] is not True
            or ledger['remaining_simulators']!=[] or ledger['unattempted']!=[j['id'] for j in jobs[6:]]):
        raise ValueError('Revision10 count/source/cleanup changed')
    files={str(lp):FAILED_LEDGER_SHA,str(jp):FAILED_JOURNAL_SHA};takeoffs=0
    for index,item in enumerate(rows):
        run=batch/item['job']['id'];result=read(run/'result.json');restore=read(run/'parameter_restore.json')
        accepted=index<5
        if item['status']!=('accepted' if accepted else 'failed') or result['success'] is not accepted:
            raise ValueError('Revision10 historical verdict changed')
        if (restore['parameter_restore_exact'] is not True or restore['remaining_simulators']!=[]
                or restore['stopped_before_restore'] is not True
                or restore['original_parameter_sha256']!=fingerprint(batch/'original_parameters.bson')
                or restore['restored_parameter_sha256']!=restore['original_parameter_sha256']):
            raise ValueError('Revision10 historical parameters changed')
        takeoffs+=sum(e['name']=='takeoff_command' for e in result['events'])
        names=['job.json','result.json','parameter_restore.json','original_parameters.bson',
               'r03_prearm04_timing.jsonl','commands.jsonl']
        if accepted:names.append('r03_metrics.json')
        if accepted and fingerprint(run/'r03_metrics.json')!=item['metrics_sha256']:
            raise ValueError('Revision10 original metrics changed')
        if not accepted and (result.get('error')!="ValueError('Invalid position clock timestamp')"
                or 'landed_disarmed' in [e['name'] for e in result['events']]):
            raise ValueError('Revision10 stopped flight relabelled')
        for entry in result['logs']:
            path=Path(entry['archive'])
            if path.parent!=run or path.stat().st_size!=entry['bytes'] or fingerprint(path)!=entry['sha256']:
                raise ValueError('Revision10 original ULog changed')
            files[str(path)]=entry['sha256']
        files.update({str(run/n):fingerprint(run/n) for n in names})
    if takeoffs!=6:raise ValueError('Revision10 takeoff count changed')
    partial=EXTERNAL/'R03_revision10/D/partial_replay01/summary.json'
    if fingerprint(partial)!='ca86b7145e2d3d65f90748e3618438302529ba7b0f0bc96a9704422be13f2b88':
        raise ValueError('Revision10 partial replay changed')
    files[str(partial)]=fingerprint(partial)
    h['batches'].append(dict(root=str(root/'D'),ledger_path=str(lp),ledger_sha256=FAILED_LEDGER_SHA,
        journal_path=str(jp),journal_sha256=FAILED_JOURNAL_SHA,attempts=6,takeoffs=6,accepted=5,failed=1,
        diagnostic_complete=0,accepted_for_new_matrix=0,source_head=ledger['source_head'],evidence_files=files))
    h.update(attempts=88,takeoffs=86,accepted=78,failed=8,diagnostic_complete=2,accepted_for_new_matrix=0)
    return h


def retained_abc():
    files={};gates=[]
    for gate,sha in PREVIOUS_RECEIPTS.items():
        path=EXTERNAL/'R03_revision09'/gate/'gate_pass.json'
        if fingerprint(path)!=sha:raise ValueError('Retained ABC receipt changed')
        r=read(path)
        if (r['success'] is not True or r['accepted']!=9 or r['independent_replays']!=9 or r['paired_checks']!=6
                or r['source_head']!=PREVIOUS_HEAD or r['firmware_sha256']!=PREVIOUS_FIRMWARE):
            raise ValueError('Retained ABC identity changed')
        files[str(path)]=sha
        gates.append(dict(gate=gate,revision='r03_revision09',source_head=PREVIOUS_HEAD,
                          firmware_sha256=PREVIOUS_FIRMWARE,receipt_sha256=sha))
    return dict(accepted_design_runs=27,gates=gates,files=files,counts_toward_new_matrix=False,
        interpretation='Keep original revision09 ABC; new D uses a separately frozen runner. No same-HEAD36 claim or pooling across tasks')



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
    jobs=[]
    for i,j in enumerate(source_jobs('D')):
        j=copy.deepcopy(j);j.update(revision=REVISION,seed=GATES['D']['seeds'][i//3],phase='development',role='matrix');jobs.append(j)
    source=_sealed_module('r03_revision09').design()
    return dict(stage='R03-revision11',revision=REVISION,status='authorized_pending_new_clean_qualification',
        execution_authorized=_activated(),flight_authorized=_activated(),execution_ready=_activated(),
        **budget(),jobs=jobs,fixed_parameters=source['fixed_parameters'],protocol_overrides=source['protocol_overrides'],
        historical_budget=retained_history(),retained_abc=retained_abc(),entry_head=ENTRY_HEAD,
        parameter_sources={str(BASE/'r03_revision05/manifest.json'):SOURCE_SHA['r03_revision05']},
        diagnostic_replay_required=True,same_source_all36=False,seed_migration=seed_migration(),
        post_logger_warmup_us=30000000,order='D-only original nine-job order; first mandatory failure stops',
        scientific_scope='Original revision09 ABC retained; new D9 at fixed parameters. Position/callback clock policy11 and runner-only changes; no pooled36 or identical-binary claim')



def load_protocol(gate):
    cfg=valid_gate(gate);d=design();p=copy.deepcopy(_sealed_module(cfg['source']).load_protocol(gate))
    p.update(stage='R03-revision11-'+gate,revision=REVISION,gate=gate,role='matrix',
        gate_config={k:copy.deepcopy(v) for k,v in cfg.items() if k!='source'},
        jobs=[j for j in d['jobs'] if j['gate']==gate],seeds=list(cfg['seeds']),**budget(gate),
        historical_budget=d['historical_budget'],retained_abc=d['retained_abc'],
        execution_authorized=d['execution_authorized'],flight_authorized=d['flight_authorized'],
        execution_ready=d['execution_ready'],
        same_source_all36=False,post_logger_warmup_us=30000000,config_dir=str(HERE/'gates'/gate),
        execution_path=str(HERE/'execution.json'),
        qualification_path=str(DATA_ROOT/gate/'qualification01/evidence.json'))
    p['seed_migration']=seed_migration();p.pop('retained_a',None)
    p['artifacts']={**p['artifacts'],'new_run_root':str(DATA_ROOT/gate/'batch01')}
    p['authorization']=dict(basis='Continuous user authorization, frozen finite revision11',maximum_attempts=97,this_gate_attempts=9)
    p['status']=d['status']
    p['scope']='New D-only9; original revision09 ABC kept. Post-logger30s preparation, no tuning or cross-task pooling'
    p['logging']='Inherited1041 OR2048 =3089; original raw gyro coverage and complete protections'
    p['pair_gate'].update(maximum_candidate_flights_before_reauthorization=97,candidates=2,order=d['order'])
    p['excitation']['definition_file']=str(HERE/'PROTOCOL_CN.md')
    p['metrics'].update(missing='First mandatory failure stops; all9 new D required; no retry/imputation',
        interpretation='Original ABC plus new D with runner-only version difference; each task n3; never pool different tasks')
    return p


def validate_manifest(value=None):
    registered=read(HERE/'execution.json') if value is None else value
    if not exact(registered,design()) or not exact(read(HERE/'manifest.json'),design()['jobs']):
        raise ValueError('Registered revision11 design differs')
    return True


def require_execution_authority(gate):
    valid_gate(gate)
    if DRAFT_ONLY or Path(__file__).resolve().parent!=HERE or not AUTHORIZATION_SHA:
        raise PermissionError('External draft never grants execution authority')
    if fingerprint(AUTHORIZATION)!=AUTHORIZATION_SHA:raise PermissionError('New revision11 authority missing/changed')
    validate_manifest();diagnostic_replay_binding()
    if any(design().get(k) is not True for k in ('execution_authorized','flight_authorized','execution_ready')):
        raise PermissionError('Revision10 activation has not been explicitly frozen')
    return dict(approved=True,gate=gate,revision=REVISION,authorization_sha256=AUTHORIZATION_SHA,**budget(gate))


def fresh_seeds(gate=None):
    """Audit all three new seeds; never exempt experiment data directories."""
    selected=[s for cfg in GATES.values() for s in cfg['seeds']] if gate is None else valid_gate(gate)['seeds']
    audit=load_file('_revision11_seed_audit',REPO/'research/sta-velocity-control/scripts/check_v04_protocol02.py')
    audit.CONFIG=Path('/__revision11_no_directory_exemption__');result=audit.seed_audit(selected)
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
    valid_gate(gate);proof=[]
    verifier=load_file('_revision11_original09_replay',PREVIOUS/'replay.py')
    for name,sha in PREVIOUS_RECEIPTS.items():
        root=EXTERNAL/'R03_revision09'/name
        if not (root/'gate_pass.json').is_file():raise ValueError('Missing retained original ABC proof')
        receipt=read(root/'gate_pass.json')
        if fingerprint(root/'gate_pass.json')!=sha or not exact(receipt,verifier.verify_complete(name,root)):
            raise ValueError('Retained original ABC independent evidence changed')
        if receipt['source_head']!=PREVIOUS_HEAD or receipt['firmware_sha256']!=PREVIOUS_FIRMWARE:
            raise ValueError('Retained ABC original source changed')
        proof.append(dict(gate=name,revision='r03_revision09',source_head=PREVIOUS_HEAD,
                          firmware_sha256=PREVIOUS_FIRMWARE,receipt_sha256=sha))
    return proof



def qualification_binding(gate,source_head,firmware_sha256):
    """New root verifier calls with its measured source and binary; no live-BIN lookup."""
    require_execution_authority(gate)
    return dict(stage='R03-revision11-'+gate,revision=REVISION,gate=gate,source_head=source_head,
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
    expected=dict(success=True,clean=True,stage='R03-revision11-'+gate,revision=REVISION,gate=gate,
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
    freeze=load_file('_revision11_archive_freeze',HERE/'freeze.py')
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
    freeze=load_file('_revision11_launch_freeze',HERE/'freeze.py');freeze.check(gate)
    if fingerprint(REPO/'build/px4_sitl_default/bin/px4')!=q['firmware_sha256']:
        raise ValueError('Current binary differs from qualified source')
    return q


def prepare():
    if any((HERE/n).exists() for n in (*REGISTRATION_NAMES,'seed_reservations.json')):
        raise ValueError('Refuse to overwrite existing registration')
    if not _activated() or fingerprint(AUTHORIZATION)!=AUTHORIZATION_SHA:
        raise PermissionError('Finite revision11 authority not frozen')
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
    parser.add_argument('--prepare',action='store_true');parser.add_argument('--gate',choices=GATES,default='D')
    args=parser.parse_args()
    if args.prepare:prepare()
    else:print(json.dumps(load_protocol(args.gate),indent=2))
