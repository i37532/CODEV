"""Fixed equal-budget rule. Never chooses from validation or holdout data."""
import argparse
import json
from pathlib import Path
import numpy as np
from common import jobs,candidates,fingerprint

def score(metrics):
    if not metrics.get('accepted'): return 1000000.
    r=np.asarray(metrics['diagnostic']['error']['rmse'],dtype=float)
    tv=np.asarray(metrics['spectral_summary']['correction_tv_per_second'],dtype=float)
    if r.shape!=(3,) or tv.shape!=(3,) or not np.all(np.isfinite(np.r_[r,tv])) or np.any(np.r_[r,tv]<0):
        raise ValueError('Invalid selection metrics')
    return float(np.mean(r[:2])/.02+.1*np.mean(tv[:2]))

def select(rows):
    expected=jobs()
    if len(rows)!=24 or [x['job'] for x in rows]!=expected:
        raise ValueError('Need exact complete frozen training list, not validation')
    if not all(x.get('accepted') for x in rows): raise ValueError('Failure/incomplete budget; no selection')
    values={}
    for name in candidates():
        subset=[x for x in rows if x['job']['candidate']==name]
        if len(subset)!=4: raise ValueError('Unequal candidate budget')
        values[name]=float(np.mean([score(x) for x in subset]))
    selected={}
    for mode,prefix in [('0','pid'),('1','esta')]:
        names=[prefix+str(i) for i in range(3)]; best=min(values[n] for n in names)
        selected[mode]=next(n for n in names if values[n]<=best+1e-12)
    return dict(selected=selected,scores=values,criterion='XY RMSE/.02 + .1*XY correction TV/s; equal four-run mean',
                parameters={mode:candidates()[name] for mode,name in selected.items()},
                validation_jobs=jobs('validation',selected))

def main():
    p=argparse.ArgumentParser(); p.add_argument('batch',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); ledger=json.loads((a.batch/'ledger.json').read_text())
    if not ledger.get('success') or len(ledger['attempts'])!=24: raise ValueError('Training not complete')
    rows=[]
    for item in ledger['attempts']:
        f=Path(item['directory'])/'xyz_metrics.json'
        if item['status']!='accepted' or fingerprint(f)!=item['metrics_sha256']:raise ValueError('Training fingerprint/status')
        rows.append(json.loads(f.read_text()))
    result=select(rows);result['training_source']=ledger['source_head'];result['ledger_sha256']=fingerprint(a.batch/'ledger.json')
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
