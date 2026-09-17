#!/usr/bin/env python3
"""Reanalyze completed M09 data, retaining the original JSON/NPZ unchanged."""
import argparse
import contextlib
import hashlib
import json
from pathlib import Path
from analyze_m09 import main as analyze


def main():
    p=argparse.ArgumentParser();p.add_argument('series',type=Path);a=p.parse_args();rows=[]
    for label in ('pid','esta','ista'):
        for div in (1,2,4):
            run=a.series/f'{label}_div{div}'
            if (run/'m09_analysis_v2.json').exists():raise RuntimeError('Refusing to overwrite refined results')
            with (run/'m09_analysis_v2.log').open('w') as stream,contextlib.redirect_stdout(stream):
                rows.append(analyze(run,'_v2'))
            print('REANALYZED',run.name,flush=True)
    for r in rows:
        ref=next(x for x in rows if x['mode']==r['mode'] and x['div']==1)
        pid=next(x for x in rows if x['mode']==0 and x['div']==r['div'])
        r['tracking_ratio_own_n1']=[a/b for a,b in zip(r['rmse_tracking'],ref['rmse_tracking'])]
        r['tracking_ratio_same_div_pid']=[a/b for a,b in zip(r['rmse_tracking'],pid['rmse_tracking'])]
    source=Path(__file__).with_name('analyze_m09.py')
    result=dict(success=True,analysis_version=2,reason='Odd-length one-sided PSD normalization correction; no firmware change',
                analyzer_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),runs=rows)
    (a.series/'refined_analysis.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
