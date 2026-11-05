"""Isolated deterministic reanalysis; no simulation and no evidence rewrites."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def compare_metrics(original,replayed):
    if original==replayed:return dict(bytes_identical=True,counts_order_only=False)
    a=json.loads(original);b=json.loads(replayed)
    ac=a['cli_receipts']['counts'];bc=b['cli_receipts']['counts']
    if set(ac)!=set(bc):raise ValueError('CLI count keys changed')
    # audit_commands constructs this one dictionary from a Python set, whose
    # iteration order differs across interpreter hash seeds. Nothing numerical
    # is normalized; retain the original and replay bytes as separate evidence.
    b['cli_receipts']['counts']={k:bc[k] for k in ac}
    if (json.dumps(b,indent=2)+'\n').encode()!=original:raise ValueError('Replay metric content changed')
    return dict(bytes_identical=False,counts_order_only=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('batch',type=Path)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    ledger=json.loads((args.batch/'ledger.json').read_text())
    evidence=dict(success=False,flights_run=0,commands=[],ledger_sha256=digest(args.batch/'ledger.json'))
    try:
        for item in ledger['attempts']:
            if item['status']!='accepted':continue
            run=Path(item['directory']);target=args.output/run.name
            if digest(run/'xyz_metrics.json')!=item['metrics_sha256']:raise ValueError('Original metrics changed')
            argv=[sys.executable,str(args.protocol/'analyze.py'),str(run),'--output',str(target)]
            with (args.output/(run.name+'.log')).open('x') as stream:
                completed=subprocess.run(argv,stdout=stream,stderr=subprocess.STDOUT,env=os.environ.copy())
            record=dict(attempt=item['attempt'],argv=argv,exit_code=completed.returncode)
            evidence['commands'].append(record)
            if completed.returncode:raise ValueError('Replay rejected '+run.name)
            record['metrics_comparison']=compare_metrics((run/'xyz_metrics.json').read_bytes(),(target/'xyz_metrics.json').read_bytes())
            record['metrics_values_identical']=True
            print(json.dumps(record),flush=True)
        evidence['success']=True
    finally:
        (args.output/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')

if __name__=='__main__':main()
