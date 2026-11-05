#!/usr/bin/env python3
import json, statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent

def summarize(rows):
    f=json.loads((HERE/'FROZEN_RA.json').read_text()); gate=f['paired_gate']; violations=[]; checks=[]
    by={(r.get('seed'),r.get('algorithm')):r for r in rows}
    if len(rows)!=len(f['ordered_jobs']): violations.append('attempt_count')
    if any(not r.get('success') for r in rows): violations.extend('invalid:'+str(r.get('seed'))+':'+str(r.get('algorithm')) for r in rows if not r.get('success'))
    commanded={'hover':(0,1),'tracking':(0,1),'roll_only':(0,), 'pitch_only':(1,), 'synchronous':(0,1)}; primary=[]
    for seed in f['paired_seeds']:
        e=by.get((seed,'esta'));p=by.get((seed,'proper_ista'))
        if not e or not p or not e.get('success') or not p.get('success'): violations.append('pair:'+str(seed));continue
        for window,axes in commanded.items():
            for axis,(ev,pv) in enumerate(zip(e['metrics'][window]['rmse'],p['metrics'][window]['rmse'])):
                margin=gate['absolute_margin_commanded_rad_s'] if axis in axes else gate['absolute_margin_uncommanded_rad_s']
                threshold=max(gate['ratio_max_each']*ev,ev+margin);ok=pv<=threshold
                checks.append(dict(seed=seed,window=window,axis=axis,esta=ev,proper=pv,ratio=pv/ev,threshold=threshold,passed=ok))
                if not ok: violations.append(f'{seed}:{window}:{axis}')
                if window=='pitch_only' and axis==1: primary.append(pv/ev)
    median=statistics.median(primary) if len(primary)==gate['required_pairs'] else None
    if median is None or median>gate['median_primary_pitch_ratio_max']: violations.append('primary_pitch_median')
    return dict(success=not violations,subgate='R-A',planned=len(f['ordered_jobs']),attempted=len(rows),accepted=sum(bool(r.get('success')) for r in rows),
                primary_pitch_paired_ratios=primary,primary_pitch_median_ratio=median,checks=checks,violations=violations,rows=rows)
