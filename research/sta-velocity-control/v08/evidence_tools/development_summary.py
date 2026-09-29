"""Read complete frozen development batches; no retuning or formal inference."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def summarize(batches):
    groups={};sources=[]
    for batch in batches:
        ledger=json.loads((batch/'ledger.json').read_text())
        if not ledger['success'] or len(ledger['attempts'])!=ledger['planned']:
            raise ValueError('Complete qualified development batch required')
        sources.append(dict(path=str(batch),source_head=ledger['source_head'],ledger_sha256=digest(batch/'ledger.json')))
        for item in ledger['attempts']:
            path=Path(item['directory'])/'xyz_metrics.json'
            if item['status']!='accepted' or digest(path)!=item['metrics_sha256']:raise ValueError('Changed/failed development evidence')
            m=json.loads(path.read_text());j=item['job']
            if j['phase'] not in ('validation','pilot'):raise ValueError('Do not estimate new precision from training/formal data')
            scene=j.get('scene',j['task']);key=(scene,j['seed'],j['mode'])
            if key in groups:raise ValueError('Repeated development job')
            groups[key]=m
    result=dict(sources=sources,scenes={},formal_attempts=0,interpretation='Development only; no reselection or confirmatory inference')
    for scene in sorted({k[0] for k in groups}):
        seeds=sorted({k[1] for k in groups if k[0]==scene})
        if len(seeds)!=3 or any((scene,s,m) not in groups for s in seeds for m in (0,1)):
            raise ValueError('Need exact three independent complete development pairs')
        summary=dict(seeds=seeds,algorithms={},differences_m_s=[])
        for mode in (0,1):
            rows=[groups[(scene,s,mode)] for s in seeds]
            xyz=np.array([m['diagnostic']['error']['rmse'] for m in rows])
            tv=np.array([m['spectral_summary']['correction_tv_per_second'] for m in rows])
            # cadence.py converts q.*_ns to microseconds, despite retaining
            # raw column names as dictionary keys. Label the report correctly.
            cost={name:{q:float(np.mean([m['diagnostic']['cadence']['host_cost'][name]['update'][q] for m in rows]))
                        for q in ('median','p95','p99','max')} for name in ('path_ns','module_ns')}
            summary['algorithms'][str(mode)]=dict(accepted=3,attempted=3,xyz_rmse_mean_m_s=xyz.mean(axis=0).tolist(),
                xy_rmse_mean_m_s=float(xyz[:,:2].mean()),xy_correction_tv_per_second=float(tv[:,:2].mean()),
                position_rmse_mean_m=np.mean([m['position_rmse'] for m in rows],axis=0).tolist(),
                yaw_rmse_mean_rad=float(np.mean([m['yaw_rmse'] for m in rows])),
                host_cost_us_mean_of_run_quantiles=cost,
                host_cost_window='full observation, about90s; not pooled quantiles, not board CPU/WCET')
        for seed in seeds:
            a,b=(groups[(scene,seed,m)] for m in (0,1))
            summary['differences_m_s'].append(float(np.mean(b['diagnostic']['error']['rmse'][:2])-np.mean(a['diagnostic']['error']['rmse'][:2])))
        x=np.array(summary['differences_m_s']);sd=float(np.std(x,ddof=1))
        summary.update(paired_mean_difference_m_s=float(x.mean()),paired_sd_m_s=sd,
            approximate_n20_95_halfwidth_m_s=float(2.093*sd/np.sqrt(20)),
            precision_caveat='Only3 development pairs, imperfect IID; approximate t projection, not a power guarantee or stopping rule')
        result['scenes'][scene]=summary
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('batches',nargs='+',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();result=summarize(args.batches)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))
