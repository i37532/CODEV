#!/usr/bin/env python3
"""Record real post-run test/collection/audit/plot commands. Never launches SITL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[5]
STAGE=HERE.parents[1]
DATA=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261026/RI07/FORMAL')


def main(output):
    output.mkdir(parents=True,exist_ok=False)
    gate=json.loads((DATA/'gate_pass.json').read_text())
    if gate.get('accepted') is not True:raise ValueError('Completed replay gate required')
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    env['PYTHONPATH']=':'.join([str(REPO/'.px4-python'),str(REPO/'research/sta-velocity-control/scripts'),
        '/home/yr/Desktop/codev doc/experiments/M00-20260912/python',
        '/home/yr/Desktop/codev doc/experiments/M10-20260917/plot_dependencies01/python'])
    commands=[
        [sys.executable,'-B','-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v'],
        [sys.executable,'-B','-m','unittest','discover','-s',str(STAGE),'-p','test_*.py','-v'],
        [sys.executable,'-B',str(HERE/'collect.py'),'--replay',str(DATA/'replay03'),'--output',str(HERE/'package.json')],
        [sys.executable,'-B',str(HERE/'audit.py'),'--package',str(HERE/'package.json'),'--output',str(HERE/'audit.json')],
        [sys.executable,'-B',str(HERE/'plots.py'),'--package',str(HERE/'package.json'),'--output',str(HERE/'figures')]]
    receipts=[]
    for index,command in enumerate(commands,1):
        path=output/(f'{index:02d}.log');start=time.monotonic()
        with path.open('xb') as stream:
            completed=subprocess.run(command,cwd=REPO,env=env,stdout=stream,stderr=subprocess.STDOUT)
        receipt=dict(argv=command,cwd=str(REPO),exit_code=completed.returncode,elapsed_s=time.monotonic()-start,
                     log=str(path),log_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        receipts.append(receipt)
        # This is a generated execution journal, not a rewritten scientific input.
        (output/'commands.json').write_text(json.dumps(receipts,indent=2)+'\n')
        print(json.dumps(dict(command=index,exit_code=completed.returncode,log=str(path))),flush=True)
        if completed.returncode:return completed.returncode
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();raise SystemExit(main(args.output))
