"""Collect only RI06 development; freeze200 UNATTEMPTED formal jobs. No flight API."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

_s=importlib.util.spec_from_file_location('_ri06_package_api',Path(__file__).with_name('protocol.py'))
p=importlib.util.module_from_spec(_s);_s.loader.exec_module(p)
stats=p.load_file('_ri06_package_stats',p.HERE/'statistical_plan.py')

def formal_rows(indices):
    if set(indices)!=set(dict(p.ALGORITHMS)):raise ValueError('Incomplete three-way selection')
    rows=p.formal_templates()
    for row in rows:
        index=1 if row['group']=='A' else indices[row['candidate']]
        params=p.candidate_parameters(row['candidate'],index,row['task'])
        row.update(candidate_index=index,parameters=params,
            parameters_sha256=hashlib.sha256(json.dumps(params,sort_keys=True,separators=(',',':')).encode()).hexdigest())
    return rows

def collect():
    p.require_prior_gate('VV')
    binding=p.load_file('_ri06_package_bindings',p.HERE/'tools/bindings.py')
    selected=p.selected();rows=[];inputs={};qualifications={};ledgers={}
    for gate in p.GATES:
        root=p.DATA_ROOT/gate;binding.local('replay').verify_complete(root/'replay01',gate=gate)
        ledger=p.read(root/'batch01/ledger.json');ledgers[gate]=ledger
        qref=p.read(root/'batch01/qualification_reference.json');q=p.read(qref['path']);qualifications[gate]=q
        for path in (root/'gate_pass.json',root/'batch01/ledger.json',root/'replay01/summary.json',Path(qref['path'])):
            inputs[str(path)]=p.fingerprint(path)
        for item in ledger['attempts']:
            run=Path(item['directory']);m=p.read(run/'r03_metrics.json');result=p.read(run/'result.json')
            inputs[str(run/'r03_metrics.json')]=p.fingerprint(run/'r03_metrics.json')
            inputs[str(run/'result.json')]=p.fingerprint(run/'result.json')
            rows.append(dict(job=item['job'],accepted=m['accepted'],J=m['diagnostic']['J'],
                velocity_rmse=m['diagnostic']['error']['rmse'],velocity_mean=m['diagnostic']['error']['mean'],
                velocity_variance=m['diagnostic']['error']['variance'],windows=m['diagnostic']['windows'],
                position_rmse=m['position_rmse'],yaw_rmse=m['yaw_rmse'],height=m['height'],height_task=m['height_task'],
                correction_tv_per_s=m['diagnostic']['correction_tv_per_second'],
                thrust_tv_per_s=m['diagnostic']['normalized_thrust_tv_per_second'],
                constraints=m['diagnostic']['constraint_fraction'],true_updates=m['diagnostic']['actual_updates'],
                spectral_summary=m['spectral_summary'],host_cost=m['host_cost'],lifecycle=m['lifecycle'],
                actual_output=m['actual_output'],rate_actuator=m['rate_actuator'],
                source_head=result['source_head'],firmware_sha256=result['binary_sha256'],
                metrics_path=str(run/'r03_metrics.json'),logs=result['logs']))
    if len(rows)!=54 or not all(r['accepted'] for r in rows):raise ValueError('Not complete54; no formal freeze')
    # A's common baseline requires genuine baseline runs for BOTH tasks and algorithms.
    a=[r for r in rows if r['job']['phase']=='training' and r['job']['candidate_index']==1 and r['job']['mode'] in (3,4)]
    if len(a)!=8:raise ValueError('Common A configuration not actually validated')
    precision={}
    for task in ('H','V'):
        common={}
        for row in a:
            if row['job']['task']==task:
                common.setdefault(row['job']['seed'],{})[row['job']['candidate']]=row['J']
        precision['A/'+task+':RISTA-RSTA']=stats.precision_estimate([b['RISTA']-b['RSTA'] for b in common.values()])
        blocks={}
        for row in rows:
            if row['job']['phase']=='validation' and row['job']['task']==task:
                blocks.setdefault(row['job']['seed'],{})[row['job']['candidate']]=row['J']
        for later,earlier in [('RSTA','PID'),('RISTA','PID'),('RISTA','RSTA')]:
            precision['B/'+task+':'+later+'-'+earlier]=stats.precision_estimate([b[later]-b[earlier] for b in blocks.values()])
    q=qualifications['VV'];f=p.read(p.HERE/'gates/VV/frozen.json')
    package=dict(stage='RI06',accepted=True,planned=54,attempts=54,accepted_runs=54,independent_replays=54,
        paired_checks=36,failed=0,missing=0,selection=selected,rows=rows,input_sha256=inputs,
        development_precision=precision,qualification_counts={g:q['counts'] for g,q in qualifications.items()},
        source_versions={g:dict(source_head=l['source_head'],firmware_sha256=l['firmware_sha256']) for g,l in ledgers.items()},
        formal=dict(executable_source_head=q['source_head'],firmware_sha256=q['firmware_sha256'],
            assets=f['assets'],external_assets=f['external_assets'],submodules=f['submodules'],
            derived_iris_sha256=f['derived_iris_sha256'],jobs=formal_rows(selected['indices']),
            budget=200,A=80,B=120,all_unattempted=True,flight_authorized=False,
            source_limit='Frozen qualified executable version; result commit does not change control/tool code. RI07 needs separate authority and current-source qualification.',
            statistics=dict(bootstrap_replicates=stats.BOOTSTRAP_REPLICATES,bootstrap_seed=stats.BOOTSTRAP_SEED,
                sign_replicates=stats.SIGN_REPLICATES,sign_seed=stats.SIGN_SEED,family_size=8,
                minimum_practical_difference=stats.MIN_PRACTICAL_DIFFERENCE)))
    return package

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    output=args.output.resolve()
    if output.exists():raise ValueError('Fresh result path required')
    result=collect();output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(dict(accepted=result['accepted'],attempts=54,formal_attempts=0,next_budget=200)))
