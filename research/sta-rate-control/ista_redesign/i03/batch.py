#!/usr/bin/env python3
"""Run exactly the frozen I03 jobs once, then decode and pair them."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from analyze import analyze, summarize
from design import HERE, REPO, build_jobs, load_frozen
from batch_m10 import execute


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=REPO, text=True).strip():
        raise RuntimeError('I03 formal experiment requires clean source')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    frozen_path = HERE/'FROZEN.json'
    tracked = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--', str(frozen_path.relative_to(REPO))], cwd=REPO, text=True).strip()
    if tracked != head:
        raise RuntimeError('Run only on the commit that froze I03 protocol/source')
    frozen, jobs = build_jobs(head)
    _, _, plugins = load_frozen()
    root = args.output.resolve()
    execute(root, jobs, plugins, frozen['simulation_speed_requested'])
    rows = []
    for number, job in enumerate(jobs):
        label = f"{number:04d}_{job['group']}_m{job['mode']}_{job['scene']}_s{job['seed']}"
        rows.append(analyze(root/label))
    summary = summarize(rows)
    summary.update(source_head=head, frozen_sha256=hashlib.sha256(frozen_path.read_bytes()).hexdigest(),
                   jobs_sha256=hashlib.sha256((root/'jobs.json').read_bytes()).hexdigest(), rows=rows)
    (root/'i03_summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({k: summary[k] for k in ('planned', 'attempted', 'accepted', 'selected_common_protection', 'stop_future_flight')}, indent=2))


if __name__ == '__main__':
    main()
