#!/usr/bin/env python3
"""Run the immutable I04 jobs once; failures stay in the denominator."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from analyze import summarize
from design import HERE, REPO, build_jobs, load_frozen


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=REPO, text=True).strip():
        raise RuntimeError('I04 formal runs require a clean worktree')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    frozen_path = HERE/'FROZEN.json'
    tracked = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--', str(frozen_path.relative_to(REPO))],
                                      cwd=REPO, text=True).strip()
    if tracked != head:
        raise RuntimeError('Run only on the commit that froze I04 protocol/source')
    frozen, jobs = build_jobs(head)
    _, _, plugins = load_frozen()
    root = args.output.resolve(); root.mkdir(parents=True, exist_ok=False)
    (root/'jobs.json').write_text(json.dumps(jobs, indent=2)+'\n')
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith(tuple(f'M{i:02d}_' for i in range(11))): env.pop(key)
    env['PYTHONPATH'] = str(REPO/'.px4-python')+':/home/yr/Desktop/codev doc/experiments/M00-20260912/python'
    env['PATH'] = str(REPO/'.px4-python/bin')+':'+env['PATH']
    env.update(M10_PLUGINS=str(plugins), M10_SPEED=str(frozen['simulation_speed_requested']),
               PYTHONDONTWRITEBYTECODE='1')
    rows = []
    runtime_anchor = None
    for number, job in enumerate(jobs):
        label = f"{number:04d}_{job['group']}_m{job['mode']}_{job['scene']}_s{job['seed']}"
        run = root/label; jobfile = root/(label+'.job.json')
        jobfile.write_text(json.dumps(job, indent=2)+'\n'); env['M10_JOB'] = str(jobfile)
        commands = []; started = time.time(); print('START', number+1, '/', len(jobs), label, flush=True)
        for name, argv in [('flight', [sys.executable, str(HERE/'run.py'), '--output', str(run)]),
                           ('analysis', [sys.executable, str(HERE/'analyze.py'), str(run)])]:
            with (root/(label+'.'+name+'.log')).open('x') as stream:
                completed = subprocess.run(argv, cwd=REPO, env=env, stdout=stream, stderr=subprocess.STDOUT)
            commands.append(dict(name=name, command=argv, returncode=completed.returncode))
            if name == 'flight' and not (run/'result.json').exists(): break
        analysis = run/'i04_analysis.json'
        row = json.loads(analysis.read_text()) if analysis.exists() else dict(
            success=False, algorithm=job['algorithm'], seed=job['seed'], failure_class='infrastructure',
            error='No I04 analysis generated')
        current_anchor = (row.get('source_head'), row.get('binary_sha256'))
        if runtime_anchor is None and all(current_anchor):
            runtime_anchor = current_anchor
        elif runtime_anchor is not None and current_anchor != runtime_anchor:
            row.update(success=False, failure_class='infrastructure',
                       error='Source/binary changed inside frozen I04 batch')
        record = dict(job=job, commands=commands, wall_seconds=time.time()-started,
                      success=row.get('success', False), halt=row.get('failure_class') in ('infrastructure', 'analysis_or_data_quality'))
        (root/(label+'.execution.json')).write_text(json.dumps(record, indent=2)+'\n')
        rows.append(row)
        (root/'progress.json').write_text(json.dumps(dict(planned=len(jobs), attempted=len(rows), rows=rows), indent=2)+'\n')
        print('END', label, 'success=', row.get('success'), 'wall=', round(record['wall_seconds'], 1), flush=True)
        if record['halt']:
            raise RuntimeError('Infrastructure/data-quality halt; retained '+label)
    summary = summarize(rows)
    summary.update(source_head=head, frozen_sha256=hashlib.sha256(frozen_path.read_bytes()).hexdigest(),
                   jobs_sha256=hashlib.sha256((root/'jobs.json').read_bytes()).hexdigest(),
                   binary_sha256=runtime_anchor[1] if runtime_anchor else None)
    (root/'i04_summary.json').write_text(json.dumps(summary, indent=2, default=lambda x: x.item() if hasattr(x, 'item') else x)+'\n')
    print(json.dumps({k: summary[k] for k in ('planned', 'attempted', 'accepted', 'success', 'violations')}, indent=2))
    raise SystemExit(0 if summary['success'] else 1)


if __name__ == '__main__': main()
