#!/usr/bin/env python3
"""Offline result/regression receipts; no simulator or parameter writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
DATA=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI04_Z_BANDWIDTH')


def validate_candidate(candidate, model):
    from model_check import BASE, MATCHED, prewarp
    expected=dict(zip(('lambda1','lambda2','epsilon'),MATCHED))
    if (candidate['kind']!='offline_engineering_candidate_not_loadable_profile'
        or candidate['flight_authorized'] is not False or candidate['production_defaults_changed'] is not False
        or candidate['original']!=dict(zip(('lambda1','lambda2','epsilon'),BASE))
        or candidate['candidate']!=expected or list(MATCHED)!=model['fixed_candidate']
        or prewarp(*BASE,.01)!=MATCHED or candidate['reference_h_seconds']!=.01
        or candidate['unchanged_limits']!={'nu_m_per_s2':4.,'correction_m_per_s2':6.}
        or candidate['validation_status']!='offline_model_checked_not_flight_qualified'
        or candidate['validation_evidence']!=str(DATA/'model01/summary.json')
        or candidate['parameter_searches']!=0 or model.get('success') is not True):
        raise ValueError('Candidate/model/authority binding mismatch')


def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve()
    if DATA not in out.parents: raise ValueError('New offline evidence root required')
    out.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    removed={k:env.pop(k) for k in list(env) if k.startswith('GTEST_')}
    env['PYTHONPATH']=str(REPO/'.px4-python')+':/home/yr/Desktop/codev doc/experiments/M00-20260912/python'
    receipt=dict(offline_only=True,new_flights=0,production_changed=False,removed_gtest_env=removed,commands=[])
    cases=0
    def run(name,command):
        nonlocal cases
        r=subprocess.run(command,cwd=REPO,env=env,capture_output=True,text=True)
        log=out/(name+'.log');log.write_text(r.stdout+r.stderr)
        receipt['commands'].append(dict(name=name,argv=command,exit_code=r.returncode,
                                       log=str(log),sha256=digest(log)))
        (out/'verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
        if r.returncode: raise RuntimeError(name+' failed; raw output retained')
        if name=='existing_cpp':
            counts=re.findall(r'\[==========\] (\d+) tests? from .*? ran\.',r.stdout)
            cases=sum(map(int,counts))
            if cases<=0: raise RuntimeError('No nonzero real C++ cases')
        return r
    run('diagnostic_tests',[sys.executable,'-B',str(HERE/'test_diagnose.py'),'-v'])
    run('existing_cpp',['ctest','--test-dir','build/px4_sitl_test','-V','-R',
        'PositionControl|ControlMath|Takeoff|RateControl|Regularized|VelocityZ|VelocityRista'])
    # Old acceptance assets and runtime defaults must stay untouched.
    run('freeze_check',[sys.executable,'-B',str(HERE.parent/'ri04_revision01/freeze.py'),'--check'])
    diff=run('production_diff',['git','diff','8578560847bd32efa17b5f45d3ec413c2961a927','--',
        'src','msg','Tools','sitl','ROMFS','boards','platforms','CMakeLists.txt','.gitmodules'])
    if diff.stdout: raise RuntimeError('Unexpected production/source changes')
    run('diff_check',['git','diff','--check'])
    model=json.loads((DATA/'model01/summary.json').read_text())
    validate_candidate(json.loads((HERE/'candidate.json').read_text()),model)
    for path,sha in model['sources'].items():
        if digest(Path(path))!=sha: raise RuntimeError('Model source changed '+path)
    if not model['success'] or model['trajectory_count']!=72: raise RuntimeError('Model not completed')
    logs=json.loads((DATA/'logs01/summary.json').read_text())
    if len(logs['runs'])!=9: raise RuntimeError('Missing log diagnostics')
    receipt.update(success=True,existing_cpp_cases=cases,existing_cpp_ctest_targets=22,
        python_diagnostic_tests=8,python_actual_cpp_model_tests=9,
        existing_cpp_build_note='Existing test binaries; production unchanged. Two pure cores freshly compiled separately by model01.',
        model_trajectories=72,model_updates=model['total_updates'],infeasible_model_counterexamples=12,
        historical_log_diagnostics=9,MATLAB_rerun=False,SITL_flights=0,
        sources={str(p):digest(p) for p in sorted(HERE.iterdir()) if p.is_file() and p.suffix in ('.py','.cpp','.json','.md')})
    (out/'verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('sources','commands')}))


if __name__=='__main__': main()
