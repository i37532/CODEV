"""Independent, bounded upstream diagnosis: history52 + PID/ESTA2; no R03 acceptance.

Read-only by default. --prepare registers an exact unused paired IMU seed only
after a complete historical audit. Neither this module nor preparation flies.
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
REVISION = 'r03_upstream08'
STAGE = 'R03-upstream08-diagnostic'
DATA_ROOT = EXTERNAL/'R03_upstream08/diagnostic01'
AUTHORIZATION = HERE.parent/'AUTHORIZATION_R03_UPSTREAM08_CN.md'
AUTHORIZATION_SHA = '21cb637e8b27830e23608b97674e865b106e52a6aa45aa92ed49e82e4440751c'
OLD = HERE.parent/'r03_revision06'
OLD_PROTOCOL_SHA = '3116bb563132feae4b0189033bc7107cce25a257e4be70fc9513268a29752d04'
OLD_MANIFEST_SHA = '59b04946ae250a0d10216a6baa3fd754608a63bb0e3db59d7956f6dbd647daa3'
SEEDS = [71591]
REGISTRATION_NAMES = ('seed_audit_initial.json', 'execution.json', 'manifest.json', 'outcomes_unattempted.json')
HISTORY06 = EXTERNAL/'R03_revision06/D/batch01'
HISTORY06_SHA = {'ledger.json': 'e3d6af1187b1d02e3f365134704cf66cab07c2e17924766494608512761bf8f5',
                 'journal.jsonl': '4d52273c9116d32377779e18310400a5d11eb3be606aec37b4b6bc0302957d20'}


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def exact(a, b):
    return json.dumps(a, sort_keys=True, separators=(',', ':'), allow_nan=False) == json.dumps(b, sort_keys=True, separators=(',', ':'), allow_nan=False)


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def old_protocol():
    if fingerprint(OLD/'protocol.py') != OLD_PROTOCOL_SHA or fingerprint(OLD/'manifest.json') != OLD_MANIFEST_SHA:
        raise ValueError('Frozen revision06 source changed')
    return load_file('_up08_readonly_old_protocol', OLD/'protocol.py')


def budget():
    return dict(maximum_attempts=2, historical_attempts=52, total_maximum_attempts=54,
                new_matrix_attempts=0, diagnostic_attempts=2,
                diagnostic_only=True, count_as_R03_acceptance=False,
                logging_profile_before=1041, logging_profile_after=3089, added_logging_mask=2048)


def retained_history():
    """Keep all nine real batches, including stopped06 and its six unattempted jobs."""
    old = old_protocol(); history = old.retained_history()
    for name, expected in HISTORY06_SHA.items():
        if fingerprint(HISTORY06/name) != expected:
            raise ValueError('Stopped revision06 history changed: '+name)
    if sorted((EXTERNAL/'R03_revision06').glob('*/batch*')) != [HISTORY06]:
        raise ValueError('Additional revision06 batch')
    ledger = read(HISTORY06/'ledger.json'); journal = [json.loads(x) for x in (HISTORY06/'journal.jsonl').read_text().splitlines()]
    jobs = read(OLD/'manifest.json')[:3]; rows = ledger['attempts']
    statuses = ['accepted', 'accepted', 'failed']
    source = 'ae61c29f6ed37e67a64ff29f952a45554e11096b'
    if (ledger.get('source_head') != source or ledger.get('success') is not False
            or ledger.get('parameter_restore_exact') is not True or ledger.get('remaining_simulators') != []
            or not exact([r['job'] for r in rows], jobs) or [r['status'] for r in rows] != statuses
            or ledger.get('unattempted') != ['run%03d' % n for n in range(31,37)]
            or sorted(HISTORY06.glob('run[0-9][0-9][0-9]')) != [HISTORY06/j['id'] for j in jobs]):
        raise ValueError('Stopped revision06 verdict/count/source/cleanup changed')
    if [r['event'] for r in journal] != [event for status in statuses for event in ('attempt','restore',status)] + ['gate_end']:
        raise ValueError('Stopped revision06 journal order changed')
    backup = HISTORY06/'original_parameters.bson'; backup_sha = fingerprint(backup)
    if ledger.get('original_parameter_sha256') != backup_sha:
        raise ValueError('Stopped revision06 backup changed')
    files = {str(backup): backup_sha}; takeoffs = 0
    for i, (job, status) in enumerate(zip(jobs, statuses)):
        run = HISTORY06/job['id']; attempt, restore, verdict = journal[i*3:i*3+3]
        required = dict(source_head=source,gate='D',job_id=job['id'],parameter_restore_exact=True,
                        remaining_simulators=[],stopped_before_restore=True,
                        original_parameter_sha256=backup_sha,restored_parameter_sha256=backup_sha,backup_path=str(backup))
        if (not exact(attempt['job'],job) or attempt['attempt'] != i+1 or verdict['job_id'] != job['id']
                or any(not exact(restore.get(k),v) for k,v in required.items())
                or any(not exact(read(run/'parameter_restore.json').get(k),v) for k,v in required.items())):
            raise ValueError('Stopped revision06 attempt/restore changed')
        result = read(run/'result.json'); takeoffs += int(any(x['name']=='takeoff_command' for x in result['events']))
        if result.get('source_head') != source or result.get('success') is not (status=='accepted'):
            raise ValueError('Stopped revision06 flight result changed')
        for name in ('parameter_restore.json','result.json'):
            files[str(run/name)] = fingerprint(run/name)
        if status == 'accepted':
            metrics = run/'r03_metrics.json'
            if (read(metrics).get('accepted') is not True or fingerprint(metrics) != rows[i]['metrics_sha256']
                    or verdict['metrics_sha256'] != fingerprint(metrics)):
                raise ValueError('Stopped revision06 accepted metrics changed')
            files[str(metrics)] = fingerprint(metrics)
        elif (run/'r03_metrics.json').exists():
            raise ValueError('Failed revision06 run acquired analysis/acceptance')
    end = journal[-1]
    if (takeoffs != 3 or end.get('success') is not False or end.get('attempts') != 3
            or end.get('parameter_restore_exact') is not True or end.get('remaining_simulators') != []):
        raise ValueError('Stopped revision06 terminal evidence changed')
    history['batches'].append(dict(root=str(EXTERNAL/'R03_revision06'),ledger_path=str(HISTORY06/'ledger.json'),
        ledger_sha256=HISTORY06_SHA['ledger.json'],journal_path=str(HISTORY06/'journal.jsonl'),
        journal_sha256=HISTORY06_SHA['journal.jsonl'],attempts=3,accepted=2,failed=1,takeoffs=3,
        source_head=source,run_ids=[j['id'] for j in jobs],evidence_files=files))
    history.update(attempts=52,accepted=46,failed=6,takeoffs=51,accepted_for_new_matrix=0)
    return history


def retained_abc():
    return old_protocol().retained_abc()


def build():
    if fingerprint(AUTHORIZATION) != AUTHORIZATION_SHA:
        raise PermissionError('Exact finite upstream diagnostic authority not finalized')
    old = old_protocol(); original = old.design(); jobs=[]
    for index, mode in enumerate((0,1),1):
        previous=next(j for j in original['jobs'] if j['mode']==mode)
        jobs.append({**copy.deepcopy(previous),'revision':REVISION,'id':'diag%03d'%index,
                     'phase':'diagnostic','seed':SEEDS[0],'block':1,'position':index})
    return dict(stage=STAGE,revision=REVISION,status='authorized_pending_clean_diagnostic_qualification',
        **budget(),execution_authorized=True,flight_authorized=True,execution_ready=True,
        historical_budget=retained_history(),retained_abc=retained_abc(),
        fixed_parameters=original['fixed_parameters'],protocol_overrides=original['protocol_overrides'],
        jobs=jobs,seeds=list(SEEDS),parameter_source_sha256=original['parameter_source_sha256'],
        previous_execution_sha256=fingerprint(OLD/'execution.json'),
        authorization_sha256=AUTHORIZATION_SHA,output_root=str(DATA_ROOT),
        order='Exactly PID then legacy ESTA on one paired fresh IMU seed; stop first mandatory failure',
        stop_rule='No retry/resume/replacement/automatic expansion; diagnostic events never count as R03 acceptance',
        interpretation='Two bounded diagnostics, not proof of rare-fault elimination or algorithm causality')


def design():
    return read(HERE/'execution.json')


def validate_manifest(value=None):
    d=design() if value is None else value
    if not exact(d,build()):
        raise ValueError('Frozen diagnostic protocol differs')
    if len(SEEDS)!=1 or type(SEEDS[0]) is not int or SEEDS[0]<=0:
        raise ValueError('Exactly one positive integer paired seed')
    return True


def load_protocol():
    validate_manifest(); d=design(); p=old_protocol().load_protocol('D')
    p.update(stage=STAGE,revision=REVISION,jobs=copy.deepcopy(d['jobs']),seeds=list(SEEDS),
        **budget(),historical_budget=retained_history(),retained_abc=retained_abc(),
        execution_authorized=True,flight_authorized=True,execution_ready=True,
        config_dir=str(HERE),execution_path=str(HERE/'execution.json'),
        qualification_path=str(DATA_ROOT/'qualification01/evidence.json'))
    p.pop('seed_migration',None)
    p['artifacts']={**p['artifacts'],'new_run_root':str(DATA_ROOT/'batch01')}
    p['scope']='Iris SITL two upstream diagnostics only, PID then legacy XYZ ESTA, original D TEST8; not R03 acceptance'
    p['authorization']=dict(maximum_attempts=2,cumulative_attempt_cap=54,basis=AUTHORIZATION_SHA)
    p['status']=d['status'];p['not_authorized']=['R03 acceptance','replacement','resume','third diagnostic','R04','R05','hardware','ISTA','tuning']
    p['current_turn_not_run']=['R03 matrix','R04','R05','hardware','tuning']
    p['logging']='Preserve1041 OR2048 =3089; raw sensor_gyro0/1/2 interval0 only'
    p['pair_gate'].update(maximum_candidate_flights_before_reauthorization=54,candidates=1,order=d['order'])
    p['metrics'].update(missing='At most two diagnostics; first mandatory failure stops; no imputation/retry or R03 acceptance',
                        interpretation='One paired IMU seed, PID and legacy ESTA; descriptive root-cause diagnosis only, not proof of rare-fault elimination')
    p['excitation']['definition_file']=str(HERE/'PROTOCOL_CN.md')
    return p


def fresh_seeds():
    audit=load_file('_up08_seed_scan',REPO/'research/sta-velocity-control/scripts/check_v04_protocol02.py')
    audit.CONFIG=Path('/__up08_no_directory_exemption__')
    result=audit.seed_audit(SEEDS)
    allowed=read(HERE/'seed_reservations.json') if (HERE/'seed_reservations.json').exists() else {}
    if allowed:
        if set(allowed)!={str(HERE/n) for n in REGISTRATION_NAMES}:
            raise ValueError('Only four exact current registration files may be exempt')
        if not exact(read(HERE/'manifest.json'),build()['jobs']):
            raise ValueError('Reserved manifest changed')
        expected=[{k:j[k] for k in ('id','gate','task','seed','candidate','mode','axes')}|{'status':'unattempted'} for j in build()['jobs']]
        if not exact(read(HERE/'outcomes_unattempted.json'),expected):
            raise ValueError('Reserved outcomes changed')
    for path,digest in allowed.items():
        if fingerprint(path)!=digest: raise ValueError('Registration SHA changed')
    result['design_registrations']=[x for x in result['matches'] if x['path'] in allowed]
    result['matches']=[x for x in result['matches'] if x['path'] not in allowed]
    result['accepted']=not result['matches'] and not result['invalid_json']
    result['excluded']='Four exact current unattempted registration SHAs only; no old or directory exemptions'
    return result


def require_execution_authority():
    validate_manifest()
    if fingerprint(AUTHORIZATION)!=AUTHORIZATION_SHA:
        raise PermissionError('Upstream diagnostic authority changed')
    return dict(approved=True,revision=REVISION,stage=STAGE,authorization_sha256=AUTHORIZATION_SHA,**budget())


def qualification_binding(source_head):
    require_execution_authority()
    return dict(stage=STAGE,revision=REVISION,gate='D',source_head=source_head,new_flights=0,
        execution_authorized=True,flight_authorized=True,execution_ready=True,**budget(),
        historical_budget=retained_history(),retained_abc=retained_abc(),authorization_sha256=AUTHORIZATION_SHA,
        execution_sha256=fingerprint(HERE/'execution.json'),frozen_sha256=fingerprint(HERE/'frozen.json'),
        firmware_sha256=fingerprint(REPO/'build/px4_sitl_default/bin/px4'))


def authorization_binding(q, path):
    return dict(approved=True,qualification_sha256=fingerprint(path),
                **{k:q[k] for k in qualification_binding(q['source_head'])})


def require_qualification(source_head,path):
    path=Path(path).resolve()
    if DATA_ROOT not in path.parents: raise ValueError('Diagnostic qualification outside exact evidence root')
    load_file('_up08_freeze_check',HERE/'freeze.py').check()
    q=read(path);expected=qualification_binding(source_head)
    if q.get('success') is not True or q.get('clean') is not True or any(not exact(q.get(k),v) for k,v in expected.items()):
        raise ValueError('Wrong clean diagnostic qualification/source/profile/budget')
    if git('rev-parse','HEAD')!=source_head or git('status','--porcelain') or git('branch','--show-current')!='research/sta-velocity-regularized':
        raise ValueError('Not the current qualified clean research source')
    if any(type(q.get('counts',{}).get(k)) is not int or q['counts'][k]<minimum
           for k,minimum in (('cpp_unique_tests',525),('python_tests',800))):
        raise ValueError('Missing actual required qualification tests')
    if not {'functional-VehicleIMU','functional-EKF2SelectorTiming','functional-EstimatorDiagnosticTopics'} <= set(q.get('cpp_test_targets',[])):
        raise ValueError('Missing actual upstream diagnostic test targets')
    if not q.get('evidence_files'):
        raise ValueError('Missing offline evidence')
    for name,digest in q['evidence_files'].items():
        if path.parent not in Path(name).resolve().parents or fingerprint(name)!=digest:
            raise ValueError('Offline qualification evidence changed')
    receipt=read(path.parent/'authorization.json')
    if any(not exact(receipt.get(k),v) for k,v in authorization_binding(q,path).items()):
        raise ValueError('Wrong diagnostic authorization receipt')
    return q


def prepare():
    if any((HERE/n).exists() for n in (*REGISTRATION_NAMES,'seed_reservations.json')):
        raise ValueError('Refuse overwrite existing diagnostic registration')
    audit=fresh_seeds()
    if not audit['accepted']: raise ValueError('Seed collision or invalid historical JSON')
    d=build()
    records={'seed_audit_initial.json':audit,'execution.json':d,'manifest.json':d['jobs'],
        'outcomes_unattempted.json':[{k:j[k] for k in ('id','gate','task','seed','candidate','mode','axes')}|{'status':'unattempted'} for j in d['jobs']]}
    for name,value in records.items():
        with (HERE/name).open('x') as f: json.dump(value,f,indent=2);f.write('\n')
    with (HERE/'seed_reservations.json').open('x') as f:
        json.dump({str(HERE/n):fingerprint(HERE/n) for n in REGISTRATION_NAMES},f,indent=2);f.write('\n')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prepare',action='store_true');args=parser.parse_args()
    if args.prepare:prepare()
    else:print(json.dumps(load_protocol(),indent=2))
