"""RI07 exact RI06 formal manifest; authority is separate from frozen outcomes."""
import copy
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
DATA_ROOT = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261026/RI07')
PACKAGE = HERE.parent/'ri06/results/final02/package.json'
PACKAGE_SHA = 'd9351d9a4f76d66274739928b60cf8df6499f03ac21e6198f2e075ae6bd3e842'
ENTRY_HEAD = 'f2728792ed1d03d8e0919043c3bb310eba8e089a'
# RI06 reference identity; RI07 metadata-only rebuilt binary is pinned by qualification.
EXECUTABLE_HEAD = '16113b0ab3a0569755a11282dfc79cfed148f66b'
REVISION = 'ri07'
AUTHORIZATION = HERE/'AUTHORIZATION_CN.md'
GATES = {'FORMAL': dict(phase='formal', axes=7, duration=64)}
_PACKAGE_CACHE = None
_PACKAGE_STAT = None

def load_file(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

PRIOR=load_file('_ri07_prior_protocol',HERE.parent/'ri06/protocol.py')
REQUIRED_TARGETS=PRIOR.REQUIRED_TARGETS
MIN_CPP,MIN_PYTHON=751,1121
read=PRIOR.read
fingerprint=PRIOR.fingerprint
exact=PRIOR.exact
git=PRIOR.git
candidate_parameters=PRIOR.candidate_parameters
selected=PRIOR.selected

def formal():
    global _PACKAGE_CACHE,_PACKAGE_STAT
    s=PACKAGE.stat();identity=(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    if _PACKAGE_CACHE is None or identity!=_PACKAGE_STAT:
        if fingerprint(PACKAGE)!=PACKAGE_SHA:raise ValueError('Changed RI06 formal package')
        _PACKAGE_CACHE=read(PACKAGE)['formal'];_PACKAGE_STAT=identity
    f=_PACKAGE_CACHE
    if f['budget']!=200 or f['A']!=80 or f['B']!=120 or f['executable_source_head']!=EXECUTABLE_HEAD:
        raise ValueError('Changed formal scope')
    return f

def valid_gate(gate):
    if gate!='FORMAL':raise ValueError('Only exact RI07 formal200')
    return copy.deepcopy(GATES[gate])

def stage(gate='FORMAL'):
    valid_gate(gate);return 'RI07-FORMAL'

def budget(gate='FORMAL'):
    valid_gate(gate)
    return dict(maximum_attempts=200,total_maximum_attempts=200,new_matrix_attempts=200,
        historical_attempts=0,required_pairs=80,required_replays=200,logging_profile=3089)

def jobs(gate='FORMAL'):
    valid_gate(gate)
    return [dict(j,revision=REVISION,gate=gate,phase='formal',main_duration_s=64) for j in formal()['jobs']]

def validate_manifest():
    d=read(HERE/'execution.json')
    expected=dict(stage=stage(),revision=REVISION,package_sha256=PACKAGE_SHA,
        executable_source_head=EXECUTABLE_HEAD,jobs=jobs(),budget=budget(),
        order='Exact RI06 final02 sequence; A80 then B120; task and algorithm order unchanged',
        first_failure='Stop entire batch, no retry/replacement/tuning/threshold change',
        ri06_reference_firmware_sha256=formal()['firmware_sha256'],
        firmware_policy='User-authorized metadata-only rebuild at clean RI07 tools commit; one qualified binary for all200')
    if not exact(d,expected):raise ValueError('Changed exact execution manifest')
    return True

def load_protocol(gate='FORMAL'):
    valid_gate(gate);validate_manifest()
    p=PRIOR.load_protocol('VH')
    p.update(stage=stage(),revision=REVISION,gate=gate,gate_config=valid_gate(gate),jobs=jobs(),
        seeds=sorted({j['seed'] for j in jobs()}),**budget(),
        config_dir=str(HERE/'gates/FORMAL'),execution_path=str(HERE/'execution.json'),
        qualification_path=str(DATA_ROOT/'FORMAL/qualification01/evidence.json'),
        status='formal_frozen200',scope='XYZ PID/RSTA/RISTA; frozen RI06 parameters/science; qualified RI07 version-only binary',
        authorization=dict(basis=str(AUTHORIZATION),maximum_attempts=200,this_gate_attempts=200),
        not_authorized=['old R04/R05','V09','axis ablation','hardware','DIV2/4','replacement','push','tuning'])
    p['current_turn_not_run']=p['not_authorized']
    p['artifacts']['new_run_root']=str(DATA_ROOT/'FORMAL/batch01')
    p['startup_overrides'].update(jobs()[0]['parameters'])
    p['metrics'].update(interpretation='Preregistered formal A/B; exact paired20 blocks; no zero imputation')
    p['pair_gate'].update(maximum_candidate_flights_before_reauthorization=200,
        order='Frozen RI06 exact200, including rotated task/algorithm order',
        calculation='B selected PID paired development-risk checks; A has no PID member, no invented comparison')
    p['excitation']['definition_file']=str(HERE.parent/'ri06/PROTOCOL_CN.md')
    return p

def job_protocol(protocol,job):
    if not any(exact(job,j) for j in jobs()):raise ValueError('Foreign formal job')
    p=copy.deepcopy(protocol)
    p['startup_overrides'].update(job['parameters'])
    p['excitation'].update(task=job['task'],parameter=job['parameters']['MPC_VCT_TEST'])
    return p

def require_execution_authority(gate='FORMAL'):
    valid_gate(gate);validate_manifest()
    if not AUTHORIZATION.is_file():raise PermissionError('No explicit RI07 authority')
    return dict(approved=True,stage=stage(),revision=REVISION,gate=gate,**budget())

def scope():
    changes=git('diff','--name-only',ENTRY_HEAD).splitlines()+git('ls-files','--others','--exclude-standard').splitlines()
    allowed=('research/sta-velocity-control/regularized_ista/ri07/',
             'research/sta-velocity-control/regularized_ista/plan/ri07-resume/')
    bad=[s for s in changes if not s.startswith(allowed) and s!='research/sta-velocity-control/reports/RI07.md']
    if bad:raise ValueError('Outside RI07 nonproduction scope: '+repr(bad))
    return changes

def capture():
    scope();f=formal();old=read(HERE.parent/'ri06/gates/VV/frozen.json')
    assets=dict(f['assets']);assets[str(PACKAGE.relative_to(REPO))]=PACKAGE_SHA
    for root in (HERE,HERE.parent/'plan/ri07-resume'):
        for path in root.rglob('*'):
            if path.is_file() and not {'results','gates','__pycache__'}.intersection(path.relative_to(root).parts):
                assets[str(path.relative_to(REPO))]=fingerprint(path)
    for name,expected in f['assets'].items():
        if fingerprint(REPO/name)!=expected:raise ValueError('Frozen RI06 asset changed: '+name)
    for name,expected in f['external_assets'].items():
        if fingerprint(name)!=expected:raise ValueError('Frozen external asset changed: '+name)
    if git('submodule','status','--recursive').splitlines()!=[line.strip() for line in f['submodules']]:
        # git().strip() only strips the leading space on the first line.
        norm=lambda lines:sorted(' '.join(line.split()[:2]) for line in lines)
        if norm(git('submodule','status','--recursive').splitlines())!=norm(f['submodules']):raise ValueError('Submodule mismatch')
    return dict(stage=stage(),revision=REVISION,assets=assets,external_assets=f['external_assets'],
        submodules=f['submodules'],control_parameters=old['control_parameters'],generated_assets=old['generated_assets'],
        derived_iris_sha256=f['derived_iris_sha256'],ri06_reference_firmware_sha256=f['firmware_sha256'],
        executable_source_head=EXECUTABLE_HEAD,jobs=jobs(),budget=budget())

def check():
    f=read(HERE/'gates/FORMAL/frozen.json')
    if not exact(f,capture()):raise ValueError('RI07 assets changed')
    return f

def qualification_binding(source_head,firmware_sha256):
    if re.fullmatch('[0-9a-f]{40}',source_head or '') is None or re.fullmatch('[0-9a-f]{64}',firmware_sha256 or '') is None:
        raise ValueError('Explicit source and firmware identities required')
    return dict(stage=stage(),revision=REVISION,gate='FORMAL',source_head=source_head,
        executable_source_head=source_head,ri06_reference_executable_source=EXECUTABLE_HEAD,firmware_sha256=firmware_sha256,
        execution_sha256=fingerprint(HERE/'execution.json'),frozen_sha256=fingerprint(HERE/'gates/FORMAL/frozen.json'),
        authorization_sha256=fingerprint(AUTHORIZATION),execution_authorized=True,flight_authorized=True,
        execution_ready=True,new_flights=0,**budget())

def archive_qualification(gate,source_head,path):
    valid_gate(gate);path=Path(path).resolve();q=read(path)
    if DATA_ROOT/'FORMAL' not in path.parents:raise ValueError('Foreign qualification')
    expected=dict(qualification_binding(source_head,q.get('firmware_sha256')),success=True,clean=True,approved=True)
    if any(not exact(q.get(k),v) for k,v in expected.items()):raise ValueError('Qualification identity mismatch')
    for name,sha in q['evidence_files'].items():
        if path.parent not in Path(name).resolve().parents or fingerprint(name)!=sha:raise ValueError('Qualification leaf changed')
    if q['counts']['cpp_unique_tests']<MIN_CPP or q['counts']['python_tests']<MIN_PYTHON:
        raise ValueError('Insufficient actual regression')
    load_file('_ri07_qualification_validator',HERE/'qualify.py').validate_receipt(q,path)
    approval=dict(approved=True,qualification_sha256=fingerprint(path),**qualification_binding(source_head,q['firmware_sha256']))
    if not exact(read(path.parent/'authorization.json'),approval):raise ValueError('Authorization differs')
    # All executable/tool bytes must have been committed, not just an asserted SHA.
    frozen=read(HERE/'gates/FORMAL/frozen.json')
    for name,sha in frozen['assets'].items():
        if name.startswith('research/sta-velocity-control/regularized_ista/ri07/'):
            raw=subprocess.check_output(['git','show',source_head+':'+name],cwd=REPO)
            if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Uncommitted qualification tool')
    return q

def require_qualification(gate,source_head,path):
    q=archive_qualification(gate,source_head,path)
    if git('rev-parse','HEAD')!=source_head or git('status','--porcelain') or git('branch','--show-current')!='research/ista-velocity-regularized':
        raise ValueError('Not clean current qualified research source')
    check()
    if fingerprint(REPO/'build/px4_sitl_default/bin/px4')!=q['firmware_sha256']:
        raise ValueError('Qualified RI07 firmware changed')
    return q

def fresh_seeds(gate=None):
    return load_file('_ri07_seed_scan_api',HERE/'seed_scan.py').audit()
