#!/usr/bin/env python3
"""One command replays one immutable job and derives its metrics."""
import argparse
import json
from pathlib import Path
from batch_m10 import execute

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--job',type=Path,required=True)
    p.add_argument('--plugins',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--speed',type=float,default=5);a=p.parse_args()
    if a.output.exists():raise RuntimeError('Replay output must be new')
    rows=execute(a.output.resolve(),[json.loads(a.job.read_text())],a.plugins.resolve(),a.speed)
    raise SystemExit(0 if all(r['success'] for r in rows) else 1)
