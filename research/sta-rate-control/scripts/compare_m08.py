#!/usr/bin/env python3
"""Fixed-threshold stage gates and same-binary nine-flight comparison. No tuning."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics


def read(run, name):
    return json.loads((run/name).read_text())


def ratios(references, candidates, windows, limit):
    medians={w:[statistics.median(r['metrics'][w]['rmse'][a] for r in references) for a in range(3)] for w in windows}
    if any(v<=0 for row in medians.values() for v in row): raise ValueError('Undefined ratio')
    values=[{w:[r['metrics'][w]['rmse'][a]/medians[w][a] for a in range(3)] for w in windows} for r in candidates]
    violations=[dict(run=i,window=w,axis='RPY'[a],ratio=v) for i,row in enumerate(values)
                for w,vals in row.items() for a,v in enumerate(vals) if v>limit]
    return dict(success=not violations, medians=medians, ratios=values, violations=violations, limit=limit)


def stage(run, references):
    if len(references)!=3: raise ValueError('Require three historical PID references')
    candidate=read(run,'m04_analysis.json'); protocol=read(run,'m04_protocol.json')
    expected=dict(protocol); expected.pop('integration_milestone',None); expected.pop('integration_version',None)
    expected.pop('frozen_before_ista_flight',None)
    if not candidate['success'] or candidate['mode']!=2 or candidate['axes'] not in (1,3):
        raise ValueError('Expected accepted staged ISTA run')
    refs=[read(p,'m04_analysis.json') for p in references]
    for p,r in zip(references,refs):
        if not r['success'] or r['mode']!=0 or read(p,'m04_protocol.json')!=expected:
            raise ValueError('Historical scene/reference mismatch')
    result=ratios(refs,[candidate],['hover','tracking',*protocol.get('windows',{})],protocol['limits']['rmse_ratio_max'])
    result.update(stage_axes=candidate['axes'],scope='Historical PID stage regression, NOT same-binary three-mode experiment',
                  run=str(run.resolve()),references=[str(p.resolve()) for p in references],
                  input_hashes={str(p/'m04_analysis.json'):hashlib.sha256((p/'m04_analysis.json').read_bytes()).hexdigest()
                                for p in [run,*references]})
    return result


def compare(pid, esta, ista):
    runs=pid+esta+ista
    if any(len(group)!=3 for group in (pid,esta,ista)) or len({p.resolve() for p in runs})!=9:
        raise ValueError('Require nine distinct runs, three per mode')
    summaries=[read(p,'m04_analysis.json') for p in runs]
    protocols=[read(p,'m04_protocol.json') for p in runs]
    if protocols!=[protocols[0]]*9 or protocols[0].get('integration_milestone')!='M08' or protocols[0]['trigger']!=4:
        raise ValueError('Not the same frozen full-axis protocol')
    sources=[read(p,'m04_source_hashes.json') for p in runs]
    if sources!=[sources[0]]*9 or len({s['binary_sha256'] for s in summaries})!=1 or len({s['ulog_sha256'] for s in summaries})!=9:
        raise ValueError('Source/binary mismatch or duplicated logs')
    configs=[read(p,'m04_config.json') for p in runs]
    for i,(s,c) in enumerate(zip(summaries,configs)):
        mode=i//3
        if not s['success'] or s['mode']!=mode or s['axes']!=(7 if mode else 0): raise ValueError('Mode/mask mismatch')
        if (s.get('pid_updates_armed',0)>0)!=(mode==0): raise ValueError('Wrong actual PID execution')
        if any(c.get(k)!=v for k,v in protocols[0]['scenario_parameters'].items()): raise ValueError('Scene drift')
        expected={**configs[0], 'MC_RTC_MODE':mode, 'MC_STA_AXES':7 if mode else 0}
        if mode==2:
            expected['MC_STA_L1_P']=2.0 # documented candidate02, NOT a same-gain claim
        if c!=expected:
            raise ValueError('Configuration drift from documented mode-specific frozen candidates')
    result=ratios(summaries[:3],summaries[3:],['hover','tracking',*protocols[0]['windows']],protocols[0]['limits']['rmse_ratio_max'])
    result.update(scope='Nominal Iris SITL development, not held-out paper or hardware validation',
                  binary_sha256=summaries[0]['binary_sha256'],
                  runs=[dict(path=str(p.resolve()),summary=s) for p,s in zip(runs,summaries)])
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--pid',type=Path,nargs=3,required=True)
    p.add_argument('--esta',type=Path,nargs=3);p.add_argument('--ista',type=Path,nargs=3)
    p.add_argument('--stage',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=stage(args.stage,args.pid) if args.stage else compare(args.pid,args.esta,args.ista)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    if not result['success']:raise SystemExit('M08 fixed RMSE gate failed: '+str(result['violations']))
