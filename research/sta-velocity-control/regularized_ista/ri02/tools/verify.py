#!/usr/bin/env python3
"""RI02 offline tooling evidence. No simulation/process-launch entry imported."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from dependencies import HERE, OLD, REPO, check_pins, digest

HISTORY = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--with-history', action='store_true')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=':'.join(map(str, (
        REPO / '.px4-python', REPO / 'research/sta-velocity-control/scripts',
        Path('/home/yr/Desktop/codev doc/experiments/M00-20260912/python')))))
    evidence = dict(stage='RI02-tools', success=False, new_flights=0, new_seeds=0,
                    dependency_sha256=check_pins(), commands=[], python_tests=0, historical_replays=0)
    inputs = {str(p.relative_to(REPO)): digest(p) for p in HERE.glob('*.py')}
    evidence['source_sha256_before'] = inputs

    def execute(name, command):
        began = time.monotonic()
        log = output / (name + '.log')
        with log.open('xb') as stream:
            done = subprocess.run(command, cwd=REPO, env=env, stdout=stream, stderr=subprocess.STDOUT)
        text = log.read_text(errors='replace')
        count = re.findall(r'Ran (\d+) tests? in', text)
        return dict(name=name, argv=list(map(str, command)), cwd=str(REPO), returncode=done.returncode,
                    elapsed_s=time.monotonic() - began, log=str(log), log_sha256=digest(log),
                    tests=sum(map(int, count)))

    try:
        test_files = [HERE / 'test_tools.py']
        for directory in ('r03_position11', 'r03_warmup10', 'r03_monitor02', 'r03_prearm04'):
            test_files.extend(sorted((OLD / directory).glob('test_*.py')))
        for path in test_files:
            result = execute(path.parent.name + '_' + path.stem, [sys.executable, '-B', str(path)])
            evidence['commands'].append(result)
            evidence['python_tests'] += result['tests']
            print(result['name'], result['returncode'], result['tests'], flush=True)
            if result['returncode'] or not result['tests']:
                raise ValueError('Actual nonzero test required: ' + str(path))
        if args.with_history:
            jobs = []
            for gate, revision, first in (('A', '09', 1), ('B', '09', 10), ('C', '09', 19), ('D', '11', 28)):
                for index in range(first, first + 9):
                    name = f'replay_{gate}_{index:03d}'
                    source = HISTORY / f'R03_revision{revision}' / gate / 'batch01' / f'run{index:03d}'
                    jobs.append((name, [sys.executable, '-B', str(HERE / 'replay.py'), str(source), '--output', str(output / name)]))
            # Two read-only decoders in parallel; no flight or historical write.
            with ThreadPoolExecutor(max_workers=2) as pool:
                for result in pool.map(lambda item: execute(*item), jobs):
                    evidence['commands'].append(result)
                    if result['returncode'] == 0:
                        evidence['historical_replays'] += 1
                    print(result['name'], result['returncode'], flush=True)
            failure = execute('original_failure_exact_prefix', [sys.executable, '-B', str(OLD / 'r03_position11/audit.py'), '--output', str(output / 'historical_failure_audit.json')])
            evidence['commands'].append(failure)
            if failure['returncode'] or evidence['historical_replays'] != 36:
                raise ValueError('Incomplete historical accepted/failed-log audit')
        evidence['source_sha256_before'] = inputs
        evidence['source_sha256_after'] = {str(p.relative_to(REPO)): digest(p) for p in HERE.glob('*.py')}
        evidence['inputs_unchanged'] = evidence['source_sha256_before'] == evidence['source_sha256_after']
        evidence['success'] = evidence['inputs_unchanged'] and all(c['returncode'] == 0 for c in evidence['commands'])
    except BaseException as error:
        evidence['error'] = repr(error)
    evidence['source_sha256_after'] = {str(p.relative_to(REPO)): digest(p) for p in HERE.glob('*.py')}
    evidence['inputs_unchanged'] = inputs == evidence['source_sha256_after']
    evidence['success'] = evidence['success'] and evidence['inputs_unchanged']
    (output / 'evidence.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: v for k, v in evidence.items() if k not in ('commands', 'source_sha256_before', 'source_sha256_after')}, indent=2))
    return 0 if evidence['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
