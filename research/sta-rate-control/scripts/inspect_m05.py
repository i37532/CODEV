#!/usr/bin/env python3
"""Single-run development diagnosis against three PID runs, not six-run acceptance."""
import argparse
import json
from pathlib import Path
import statistics
import numpy as np
from pyulog import ULog
from analyze_m03 import vector
from analyze_m00 import plain


def inspect(run, pid):
    summary=json.loads((run/'m04_analysis.json').read_text())
    baselines=[json.loads((p/'m04_analysis.json').read_text()) for p in pid]
    result=json.loads((run/'result.json').read_text())
    item=next(v for v in result['logs'] if v['sha256']==summary['ulog_sha256'])
    data=ULog(item['archive']).get_dataset('sta_rate_ctrl_status').data
    metrics=json.loads((run/'metrics.json').read_text())
    elapsed=(data['timestamp_sample'].astype(float)-metrics['hover_start_us'])*1e-6
    diagnostic={}
    for name,lo,hi in [('early_hover',0,15),('combined_tracking',15,51),('late_hover',51,60)]:
        mask=(elapsed>=lo)&(elapsed<hi)
        diagnostic[name]=dict(samples=int(np.sum(mask)),
            rmse=np.sqrt(np.mean(vector(data,'s')[mask].astype(float)**2,axis=0)),
            mean_error=np.mean(vector(data,'s')[mask].astype(float),axis=0),
            mean_nu=np.mean(vector(data,'nu')[mask].astype(float),axis=0),
            min_nu=np.min(vector(data,'nu')[mask],axis=0),max_nu=np.max(vector(data,'nu')[mask],axis=0))
    ratios={w:[summary['metrics'][w]['rmse'][a]/statistics.median(p['metrics'][w]['rmse'][a] for p in baselines)
               for a in range(3)] for w in summary['metrics']}
    violations=[dict(window=w,axis='RPY'[a],ratio=v) for w,values in ratios.items() for a,v in enumerate(values) if v>1.25]
    return dict(scope='Single development run only; not three-repeat acceptance', run=str(run),
                ratios=ratios,violations=violations,segments=diagnostic)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--pid',type=Path,nargs=3,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    with args.output.open('x') as f: json.dump(inspect(args.run,args.pid),f,indent=2,default=plain);f.write('\n')
