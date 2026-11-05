"""Isolated replay, preserving flight completion versus final acceptance distinction."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    p=argparse.ArgumentParser(); p.add_argument('--batch',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--protocol',choices=['sl_protocol01','sl_protocol02','protocol03'],required=True)
    a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=False)
    evidence=dict(success=False,protocol=a.protocol,commands=[])
    try:
        for item in json.loads((a.batch/'ledger.json').read_text())['attempts']:
            source=Path(item['directory']); target=a.output/source.name
            cmd=[sys.executable,str(Path(__file__).resolve().parents[1]/a.protocol/'analyze.py'),str(source),'--output',str(target)]
            with (a.output/(source.name+'.log')).open('x') as f:
                r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=120)
            result=json.loads((target/'xyz_metrics.json').read_text())
            accepted=item['status']=='accepted'
            row=dict(run=source.name,argv=cmd,exit_code=r.returncode,expected_accepted=accepted,
                     actual_accepted=result['accepted'],flight_completed=json.loads((source/'result.json').read_text())['success'])
            if (source/'xyz_metrics.json').exists():
                row['identical_metrics']=result==json.loads((source/'xyz_metrics.json').read_text())
            evidence['commands'].append(row)
            if r.returncode!=(0 if accepted else 1) or result['accepted']!=accepted or not row.get('identical_metrics',True):
                raise ValueError('Replay differs from original acceptance/metrics')
            print(source.name,r.returncode,flush=True)
        evidence['success']=True
    finally:
        (a.output/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')


if __name__=='__main__': main()
