#!/usr/bin/env python3
import json,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
def summarize(rows):
 f=json.loads((HERE/'FROZEN_RB.json').read_text());g=f['paired_gate'];by={(r.get('seed'),r.get('algorithm')):r for r in rows};v=[];checks=[];pair_ratios=[]
 if len(rows)!=6:v.append('attempt_count')
 for r in rows:
  if not r.get('success'):v.append('invalid:'+str(r.get('seed'))+':'+str(r.get('algorithm')))
 for seed in f['paired_seeds']:
  e=by.get((seed,'esta'));p=by.get((seed,'proper_ista'))
  if not e or not p or not e.get('success') or not p.get('success'):v.append('pair:'+str(seed));continue
  ratios=[]
  for w in ('yaw_only','synchronous_low','synchronous_repeat'):
   for a,(ev,pv) in enumerate(zip(e['metrics'][w]['rmse'],p['metrics'][w]['rmse'])):
    th=max(g['ratio_max_each']*ev,ev+g['absolute_margin_rad_s']);ok=pv<=th;ratios.append(pv/ev);checks.append(dict(seed=seed,window=w,axis=a,esta=ev,proper=pv,ratio=pv/ev,threshold=th,passed=ok))
    if not ok:v.append(f'{seed}:{w}:{a}')
  pair_ratios.append(sum(ratios)/len(ratios))
 med=statistics.median(pair_ratios) if len(pair_ratios)==3 else None
 if med is None or med>g['median_three_axis_ratio_max']:v.append('median_three_axis')
 return dict(success=not v,subgate='R-B',planned=6,attempted=len(rows),accepted=sum(bool(r.get('success')) for r in rows),pair_ratios=pair_ratios,median_three_axis_ratio=med,checks=checks,violations=v,rows=rows)
