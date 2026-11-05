"""Isolated replay of accepted training attempts; never changes original evidence."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from audit import digest, PROTOCOL


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('batch', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    ledger = json.loads((args.batch / 'ledger.json').read_text())
    evidence = dict(success=False, flights_run=0, commands=[], ledger_sha256=digest(args.batch/'ledger.json'))
    try:
        for item in ledger['attempts']:
            if item['status'] != 'accepted':
                continue
            run = Path(item['directory'])
            if digest(run/'xyz_metrics.json') != item['metrics_sha256']:
                raise ValueError('Original metrics changed')
            out = args.output/run.name
            argv = [sys.executable, str(PROTOCOL/'analyze.py'), str(run), '--output', str(out)]
            with (args.output/(run.name+'.log')).open('x') as stream:
                completed = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, env=os.environ.copy())
            record = dict(attempt=item['attempt'], argv=argv, exit_code=completed.returncode)
            evidence['commands'].append(record)
            if completed.returncode != 0:
                raise ValueError('Replay rejected: '+run.name)
            record['metrics_identical'] = (out/'xyz_metrics.json').read_bytes() == (run/'xyz_metrics.json').read_bytes()
            if not record['metrics_identical']:
                raise ValueError('Replay metrics changed: '+run.name)
            print(json.dumps(record), flush=True)
        evidence['success'] = True
    finally:
        (args.output/'evidence.json').write_text(json.dumps(evidence, indent=2)+'\n')


if __name__ == '__main__': main()
