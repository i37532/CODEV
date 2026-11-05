"""RI06 finite equal-budget tuning. Formal jobs are registration only."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ENTRY_HEAD = '152e5bc9b31f4b2b373671abfd116288131872d8'
REVISION = 'ri06'
DATA_ROOT = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261025/RI06')
AUTHORIZATION = HERE/'AUTHORIZATION_CN.md'
SOURCE = HERE.parent/'ri00/results/interface.json'
SOURCE_SHA = '37729b3d84309c899dce52803c234ef109f738ac0d1a4e1520a729dd18cbeb81'
OVERRIDES = REPO/'research/sta-velocity-control/axis_ablation/ax04/execution.json'
OVERRIDES_SHA = '308aa5a4e52828585bbf6ee3ec0be339a8081475663ceb759de0aee40167d2d3'
GATES = {
    'TH': dict(task='H', axes=7, test=6, duration=64, phase='training', seeds=[84001,84002]),
    'TV': dict(task='V', axes=7, test=8, duration=64, phase='training', seeds=[84001,84002]),
    'VH': dict(task='H', axes=7, test=6, duration=64, phase='validation', seeds=[84101,84102,84103]),
    'VV': dict(task='V', axes=7, test=8, duration=64, phase='validation', seeds=[84101,84102,84103])}
FORMAL_SEEDS = {'A': list(range(85001,85021)), 'B': list(range(85101,85121))}
SCALES = [.9, 1., 1.1]
ALGORITHMS = [('PID',0),('RSTA',3),('RISTA',4)]
REGISTRATION_NAMES = ('seed_audit_initial.json','execution.json','manifest.json','outcomes_unattempted.json')

def read(path):
    return json.loads(Path(path).read_text())

def fingerprint(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda:stream.read(1048576),b''): h.update(part)
    return h.hexdigest()

def exact(a,b):
    return json.dumps(a,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(b,sort_keys=True,separators=(',',':'),allow_nan=False)

def git(*args):
    return subprocess.check_output(['git',*args],cwd=REPO,text=True).strip()

def load_file(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

PRIOR = load_file('_ri06_prior_protocol',HERE.parent/'ri05/protocol.py')
REQUIRED_TARGETS = PRIOR.REQUIRED_TARGETS
MIN_CPP, MIN_PYTHON = 751, 982

def valid_gate(gate):
    if gate not in GATES: raise ValueError('Only RI06 TH/TV/VH/VV; no formal execution')
    return copy.deepcopy(GATES[gate])

def stage(gate):
    valid_gate(gate); return 'RI06-'+gate

def budget(gate='TH'):
    n=18 if valid_gate(gate)['phase']=='training' else 9
    return dict(maximum_attempts=n,new_matrix_attempts=n,total_maximum_attempts=54,
                historical_attempts=0,required_pairs=n*2//3,required_replays=n,
                n_per_algorithm=n//3,logging_profile=3089)

def fixed_parameters():
    if fingerprint(SOURCE)!=SOURCE_SHA or fingerprint(OVERRIDES)!=OVERRIDES_SHA:
        raise ValueError('Frozen source parameter/threshold fingerprints changed')
    p=read(SOURCE)['full_r03_parameters']
    if len(p)!=127: raise ValueError('Incomplete parameter source')
    return p

def candidate_parameters(algorithm,index,task):
    if algorithm not in dict(ALGORITHMS) or type(index) is not int or index not in range(3) or task not in ('H','V'):
        raise ValueError('Unknown candidate/task; no implicit default')
    p=fixed_parameters(); scale=SCALES[index]
    if algorithm=='PID':
        names=['MPC_XY_VEL_P_ACC','MPC_XY_VEL_I_ACC','MPC_XY_VEL_D_ACC',
               'MPC_Z_VEL_P_ACC','MPC_Z_VEL_I_ACC','MPC_Z_VEL_D_ACC']
    else:
        names=['MPC_VC_L'+str(i)+'_'+axis for axis in 'XYZ' for i in (1,2)]
    if not set(names)<=set(p): raise ValueError('Parameter name conflict/missing source')
    for name in names: p[name]=round(p[name]*scale,12)
    mode=dict(ALGORITHMS)[algorithm]
    p.update(MPC_VC_MODE=mode,MPC_VC_AXES=7 if mode else 0,MPC_VC_DIV=1,MPC_VCT_TEST=6 if task=='H' else 8)
    return p

def templates():
    rows=[]
    for gate,cfg in GATES.items():
        for block,seed in enumerate(cfg['seeds'],1):
            # Rotate the predeclared candidate order without learning from results.
            indices=([1,0,2] if block==1 else [2,1,0]) if cfg['phase']=='training' else [None]
            for index in indices:
                order=ALGORITHMS if (block+(index or 0))%2 else [ALGORITHMS[0],ALGORITHMS[2],ALGORITHMS[1]]
                for position,(algorithm,mode) in enumerate(order,1):
                    rows.append(dict(id=f'run{len(rows)+1:03d}',revision=REVISION,gate=gate,task=cfg['task'],
                        phase=cfg['phase'],role='equal_budget',seed=seed,block=block,position=position,
                        candidate=algorithm,candidate_index=index,mode=mode,axes=7 if mode else 0,
                        divisor=1,main_duration_s=64,
                        parameters=candidate_parameters(algorithm,index,cfg['task']) if index is not None else None))
    return rows

def formal_templates():
    rows=[]
    for group,seeds in FORMAL_SEEDS.items():
        algorithms=ALGORITHMS[1:] if group=='A' else ALGORITHMS
        for block,seed in enumerate(seeds,1):
            # Task and algorithm order rotate by paired block, frozen pre-data.
            tasks=('H','V') if block%2 else ('V','H')
            offset=(block-1)%len(algorithms)
            order=algorithms[offset:]+algorithms[:offset]
            for task in tasks:
                for algorithm,mode in order:
                    rows.append(dict(id=f'{group}{len(rows)+1:03d}',group=group,block=block,seed=seed,
                        task=task,candidate=algorithm,mode=mode,axes=7 if mode else 0,divisor=1,
                        candidate_index=1 if group=='A' else None,status='unattempted',flight_authorized=False))
    return rows

def design():
    return dict(stage='RI06',revision=REVISION,entry_head=ENTRY_HEAD,maximum_attempts=54,
        gates=GATES,jobs=templates(),formal_jobs=formal_templates(),formal_attempts=200,
        formal_execution_authorized=False,fixed_parameters=fixed_parameters(),scales=SCALES,
        epsilon_degrees_of_freedom=0,protocol_overrides=read(OVERRIDES)['protocol_overrides'],
        order='TH18 -> TV18 -> training selection commit -> VH9 -> VV9; PID first in each candidate/block',
        authority='Current RI06 user request only:54 finite attempts; first mandatory failure stops; no retries/push/formal',
        parameter_sources={str(SOURCE):SOURCE_SHA},threshold_sources={str(OVERRIDES):OVERRIDES_SHA},
        score=dict(formula='mean over H/V x 2 seeds of (J / .01 + .10 * mean_axis_correction_TV_per_s)',
            J='arithmetic mean of three time-weighted axis RMSE, m/s',task_weights=[.5,.5],
            failed_penalty='infinity and stop entire batch',tie_tolerance=1e-12,tie_order=[1,0,2],
            eligibility='four accepted complete runs, independent replay, paired development risk',
            validation_reselection=False,no_eligible='stop; no validation/formal freeze',early_stop='mandatory failure only'))

def validate_manifest(value=None):
    d=design()
    if not exact(d,read(HERE/'execution.json') if value is None else value): raise ValueError('Changed exact execution')
    if not exact(d['jobs'],read(HERE/'manifest.json')): raise ValueError('Changed job templates')
    if not exact([{'id':j['id'],'status':'unattempted'} for j in d['jobs']],read(HERE/'outcomes_unattempted.json')):
        raise ValueError('Initial outcomes modified')
    return True

def selected():
    s=read(HERE/'selection.json')
    if s.get('accepted') is not True or set(s.get('indices',{}))!=set(dict(ALGORITHMS)):
        raise ValueError('No eligible committed training selection')
    if any(type(i) is not int or i not in range(3) for i in s['indices'].values()): raise ValueError('Unregistered candidate')
    expected_files={str(DATA_ROOT/g/name) for g in ('TH','TV') for name in ('gate_pass.json','replay01/summary.json','batch01/ledger.json')}
    expected_files.update(str(DATA_ROOT/g/'batch01'/j['id']/'r03_metrics.json') for g in ('TH','TV') for j in jobs(g))
    if set(s.get('input_sha256',{}))!=expected_files: raise ValueError('Incomplete training selection evidence')
    for name,sha in s['input_sha256'].items():
        if fingerprint(name)!=sha: raise ValueError('Training selection input changed')
    chooser=load_file('_ri06_selection_validation',HERE/'choose_candidate.py')
    rows=[read(DATA_ROOT/g/'batch01'/j['id']/'r03_metrics.json') for g in ('TH','TV') for j in jobs(g)]
    computed=chooser.choose(rows)
    if not exact(s['indices'],computed['indices']) or not exact(s['scores'],computed['scores']) or not exact(s['rule'],computed['rule']):
        raise ValueError('Selection differs from frozen scores/ties')
    return s

def jobs(gate):
    cfg=valid_gate(gate); rows=[j for j in templates() if j['gate']==gate]
    if cfg['phase']=='validation':
        indices=selected()['indices']
        for j in rows:
            j['candidate_index']=indices[j['candidate']]
            j['parameters']=candidate_parameters(j['candidate'],j['candidate_index'],j['task'])
    return rows

def load_protocol(gate='TH'):
    cfg=valid_gate(gate); d=design(); js=jobs(gate)
    scripts=REPO/'research/sta-velocity-control/scripts'
    if str(scripts) not in sys.path: sys.path.append(str(scripts))
    from v04_protocol10 import load_protocol as inherited
    p=inherited();p.update(copy.deepcopy(d['protocol_overrides']))
    p.update(stage=stage(gate),revision=REVISION,gate=gate,gate_config=cfg,jobs=js,seeds=cfg['seeds'],**budget(gate),
        execution_authorized=True,flight_authorized=True,execution_ready=True,
        config_dir=str(HERE/'gates'/gate),execution_path=str(HERE/'execution.json'),
        qualification_path=str(DATA_ROOT/gate/'qualification01/evidence.json'),
        post_logger_warmup_us=30000000,simulation_speed=1,status='finite_equal_budget_training_validation',
        scope='XYZ PID/RSTA/RISTA; no new control law/model/limits/epsilon; fixed inner PID')
    p['artifacts']={**p['artifacts'],'new_run_root':str(DATA_ROOT/gate/'batch01')}
    p['startup_overrides']={**p['startup_overrides'],**js[0]['parameters']}
    p['candidate']={k:v for k,v in d['fixed_parameters'].items() if k.startswith(('MPC_VC_L','MPC_VC_NU','MPC_VC_A_','MPC_VC_EPS_'))}
    p['authorization']=dict(basis=d['authority'],maximum_attempts=54,this_gate_attempts=len(js),source=str(AUTHORIZATION))
    p['not_authorized']=['RI07','old R04/R05','formal holdout','hardware','DIV2/4','replacement','push','adaptive extra tuning']
    p['current_turn_not_run']=p['not_authorized']
    p['diagnostic_gate'].update(minimum_excitation_samples=6390,minimum_excitation_span_s=63.96)
    p['pair_gate'].update(maximum_candidate_flights_before_reauthorization=len(js),candidates=2,order=d['order'],
        window='64s main/two32s halves;90s position/yaw',calculation='same candidate index and seed during training; selected PID in validation')
    p['excitation']=dict(parameter=cfg['test'],duration_s=64,settle_after_auto_loiter_s=12,task=cfg['task'],
        source='Unchanged Navigator/FlightTask/task adapter; unique publisher; analytic FF once',definition_file=str(HERE/'PROTOCOL_CN.md'))
    p['metrics'].update(primary=d['score']['J'],missing='first mandatory failure stops; no retry/imputation',interpretation='seen development; not formal inference')
    p['logging']='existing bits OR16/1024/2048; exact final R03/RI05 chain'
    return p

def require_execution_authority(gate='TH'):
    valid_gate(gate);validate_manifest()
    if not AUTHORIZATION.is_file(): raise PermissionError('Missing explicit scoped authority')
    return dict(approved=True,stage=stage(gate),revision=REVISION,gate=gate,
        authorization_sha256=fingerprint(AUTHORIZATION),**budget(gate))

def require_prior_gate(gate):
    valid_gate(gate)
    for prior in list(GATES)[:list(GATES).index(gate)]:
        r=read(DATA_ROOT/prior/'gate_pass.json'); n=budget(prior)['maximum_attempts']
        if not all(r.get(k)==v for k,v in dict(accepted=True,attempts=n,accepted_runs=n,independent_replays=n,paired_checks=n*2//3,missing=0).items()):
            raise PermissionError('Incomplete prior gate '+prior)
        b=load_file('_ri06_prior_bindings',HERE/'tools/bindings.py')
        b.local('replay').verify_complete(Path(r['replay_summary_path']).parent,gate=prior)
    if valid_gate(gate)['phase']=='validation': selected()

def fresh_seeds(gate=None):
    # Exact files only: initial registrations and fully verified earlier gates.
    seeds=sorted(set(s for cfg in GATES.values() for s in cfg['seeds'])|set(sum(FORMAL_SEEDS.values(),[])))
    scanner=load_file('_ri06_seed_scan',REPO/'research/sta-velocity-control/scripts/check_v04_protocol02.py')
    scanner.CONFIG=Path('/__RI06_no_root_exemption__')
    result=scanner.seed_audit(seeds); allowed={}
    registry=HERE/'seed_reservations.json'
    if registry.exists():
        allowed=read(registry);validate_manifest()
        if set(allowed)!={str(HERE/n) for n in REGISTRATION_NAMES}: raise ValueError('Expanded initial seed exemption')
        for path,sha in allowed.items():
            if fingerprint(path)!=sha: raise ValueError('Changed seed reservation')
    if gate is not None:
        freezer=load_file('_ri06_seed_freeze',HERE/'freeze.py')
        earlier=list(GATES)[:list(GATES).index(gate)]
        # Exact committed freeze files are legitimate registrations, never a
        # directory exemption. Every present pending freeze must validate.
        for registered_gate in GATES:
            file=HERE/'gates'/registered_gate/'frozen.json'
            if file.exists():
                if registered_gate not in earlier: freezer.check(registered_gate)
                allowed[str(file)]=fingerprint(file)
        for prior in earlier:
            receipt=read(DATA_ROOT/prior/'gate_pass.json')
            summary=read(receipt['replay_summary_path'])
            allowed.update(summary['original_input_sha256_after']['files'])
            # Replay and qualification are independently validated before here.
            for folder in (Path(receipt['replay_summary_path']).parent,DATA_ROOT/prior/'qualification01'):
                allowed.update({str(f):fingerprint(f) for f in folder.rglob('*') if f.is_file() and not f.is_symlink()})
            for name in ('gate_pass.json',):
                f=DATA_ROOT/prior/name;allowed[str(f)]=fingerprint(f)
        selection=HERE/'selection.json'
        if selection.exists(): selected();allowed[str(selection)]=fingerprint(selection)
    result['registrations']=[m for m in result['matches'] if m['path'] in allowed]
    result['matches']=[m for m in result['matches'] if m['path'] not in allowed]
    result['accepted']=not result['matches'] and not result['invalid_json']
    return result

def prepare():
    if any((HERE/n).exists() for n in (*REGISTRATION_NAMES,'seed_reservations.json')): raise ValueError('No overwrite')
    a=fresh_seeds()
    if not a['accepted']: raise ValueError('Seed collision/invalid history '+str(a))
    d=design()
    for name,data in zip(REGISTRATION_NAMES,(a,d,d['jobs'],[{'id':j['id'],'status':'unattempted'} for j in d['jobs']])):
        with (HERE/name).open('x') as f: json.dump(data,f,indent=2);f.write('\n')
    with (HERE/'seed_reservations.json').open('x') as f:
        json.dump({str(HERE/n):fingerprint(HERE/n) for n in REGISTRATION_NAMES},f,indent=2);f.write('\n')

def qualification_binding(gate,source_head,firmware_sha256):
    require_execution_authority(gate)
    return dict(stage=stage(gate),revision=REVISION,gate=gate,source_head=source_head,firmware_sha256=firmware_sha256,
        execution_sha256=fingerprint(HERE/'execution.json'),frozen_sha256=fingerprint(HERE/'gates'/gate/'frozen.json'),
        authorization_sha256=fingerprint(AUTHORIZATION),new_flights=0,
        execution_authorized=True,flight_authorized=True,execution_ready=True,**budget(gate))

def authorization_binding(q,path):
    return dict(approved=True,qualification_sha256=fingerprint(path),**qualification_binding(q['gate'],q['source_head'],q['firmware_sha256']))

def archive_qualification(gate,source_head,path):
    path=Path(path).resolve();valid_gate(gate)
    if DATA_ROOT/gate not in path.parents: raise ValueError('Foreign qualification')
    q=read(path);expected={**qualification_binding(gate,source_head,q.get('firmware_sha256')), 'success':True,'clean':True,'approved':True}
    if any(not exact(q.get(k),v) for k,v in expected.items()): raise ValueError('Qualification identity differs')
    for name,sha in q['evidence_files'].items():
        if path.parent not in Path(name).resolve().parents or fingerprint(name)!=sha: raise ValueError('Changed/nonlocal leaf evidence')
    receipt=load_file('_ri06_leaf_receipt',HERE/'receipt.py')
    receipt.validate(q,path,REQUIRED_TARGETS,MIN_PYTHON)
    if q['counts']['cpp_unique_tests']<MIN_CPP: raise ValueError('Incomplete actual C++ inventory')
    if not exact(read(path.parent/'authorization.json'),authorization_binding(q,path)): raise ValueError('Wrong authority receipt')
    load_file('_ri06_archive_freeze',HERE/'freeze.py').archive_check(gate,source_head,q['frozen_sha256'])
    return q

def require_qualification(gate,source_head,path):
    require_prior_gate(gate);q=archive_qualification(gate,source_head,path)
    if git('rev-parse','HEAD')!=source_head or git('status','--porcelain') or git('branch','--show-current')!='research/ista-velocity-regularized':
        raise ValueError('Not current clean research source')
    if fingerprint(REPO/'build/px4_sitl_default/bin/px4')!=q['firmware_sha256']: raise ValueError('Unqualified firmware')
    load_file('_ri06_live_freeze',HERE/'freeze.py').check(gate)
    return q

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--gate',choices=GATES,default='TH');a=parser.parse_args()
    if a.prepare: prepare()
    else: print(json.dumps(load_protocol(a.gate),indent=2))
