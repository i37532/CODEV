#!/usr/bin/env python3
import json,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
def summarize(rows):
 f=json.loads((HERE/'FROZEN_RC.json').read_text());g=f['paired_gate'];by={(r.get('divisor'),r.get('seed'),r.get('algorithm')):r for r in rows};v=[];checks=[];medians={}
 if len(rows)!=f['planned_attempts']:v.append('attempt_count')
 for r in rows:
  if not r.get('success'):v.append('invalid:'+str(r.get('divisor'))+':'+str(r.get('seed'))+':'+str(r.get('algorithm')))
 for div in f['divisors']:
  pair=[]
  for seed in f['paired_seeds']:
   e=by.get((div,seed,'esta'));p=by.get((div,seed,'proper_ista'))
   if not e or not p or not e.get('success') or not p.get('success'):v.append(f'pair:{div}:{seed}');continue
   rr=[]
   for w in ('yaw_only','synchronous_low','synchronous_repeat'):
    for a,(ev,pv) in enumerate(zip(e['metrics'][w]['rmse'],p['metrics'][w]['rmse'])):
     th=max(g['ratio_max_each']*ev,ev+g['absolute_margin_rad_s']);ok=pv<=th;rr.append(pv/ev);checks.append(dict(div=div,seed=seed,window=w,axis=a,esta=ev,proper=pv,ratio=pv/ev,threshold=th,passed=ok))
     if not ok:v.append(f'{div}:{seed}:{w}:{a}')
   pair.append(sum(rr)/len(rr))
  med=statistics.median(pair) if len(pair)==3 else None;medians[str(div)]=dict(pair_ratios=pair,median_ratio=med)
  if med is None or med>g['median_ratio_max_each_div']:v.append('median:'+str(div))
 return dict(success=not v,subgate='R-C',planned=f['planned_attempts'],attempted=len(rows),accepted=sum(bool(r.get('success')) for r in rows),by_divisor=medians,checks=checks,violations=v,rows=rows)
