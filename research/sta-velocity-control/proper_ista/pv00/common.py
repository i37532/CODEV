"""Offline-only evidence helpers; no flight, parameter or production-write API."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
OLD = REPO / 'research/sta-velocity-control/proper_ista_probe'
ROOT = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-PROPER-20261028/PV00')
HISTORY = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-PROPER-20261024/PROBE/attempt02')
CADENCE = REPO / 'research/sta-velocity-control/regularized_ista/ri00/results/cadence.json'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


probe = module('pv00_old_probe', OLD / 'probe.py')
analysis = module('pv00_old_analysis', OLD / 'analyze.py')
sha = probe.sha
save = probe.save


def fresh(path):
    path = Path(path).resolve()
    if path == REPO or REPO in path.parents:
        raise ValueError('external output required')
    path.mkdir(parents=True, exist_ok=False)
    return path


def command(out, name, argv):
    if (out / (name + '.log')).exists() or (out / (name + '.command.json')).exists():
        raise FileExistsError('command evidence already exists: ' + name)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run(list(map(str, argv)), cwd=REPO, env=env, capture_output=True, text=True)
    log = out / (name + '.log')
    log.write_text(result.stdout + result.stderr)
    receipt = dict(argv=list(map(str, argv)), cwd=str(REPO), exit_code=result.returncode,
                   log=str(log), sha256=sha(log))
    save(out / (name + '.command.json'), receipt)
    if result.returncode:
        raise RuntimeError(f'{name} exit {result.returncode}; evidence retained at {out}')
    return result.stdout


def fingerprint(paths):
    return {str(p): dict(bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(paths) if p.is_file()}


def identity(out):
    paths = [REPO / 'research/sta-velocity-control/README_CN.md',
             REPO / 'research/sta-velocity-control/regularized_ista/README_CN.md',
             REPO / 'research/sta-velocity-control/regularized_ista/USAGE_CN.md',
             REPO / 'build/px4_sitl_default/bin/px4',
             REPO / 'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016']
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    paths += list((REPO / 'research/sta-velocity-control/regularized_ista/ri06/results/plots01').rglob('*'))
    paths += list((HERE.parent / 'plan/v1').glob('*.md'))
    paths += list(OLD.rglob('*'))
    paths += [p for pattern in ('*.cpp', '*.hpp') for p in probe.RATE.glob(pattern)]
    paths += [p for pattern in ('*.cpp', '*.hpp') for p in probe.VELOCITY.glob(pattern)]
    result = dict(head=command(out, 'head', ['git', 'rev-parse', 'HEAD']).strip(),
                  branch=command(out, 'branch', ['git', 'branch', '--show-current']).strip(),
                  worktree=command(out, 'worktree', ['git', 'status', '--short']),
                  submodules=command(out, 'submodules', ['git', 'submodule', 'status', '--recursive']),
                  submodule_dirty=command(out, 'submodule_dirty', ['git', 'submodule', 'foreach', '--quiet', '--recursive', 'git status --porcelain']),
                  production_diff=command(out, 'production_diff', ['git', 'diff', 'HEAD', '--', *probe.PRODUCTION_PATHS]),
                  input_files=fingerprint(paths))
    assert result['branch'] == 'research/proper-ista-velocity'
    assert result['head'] == '8079e17177e3edb597d8da1597081a82cbd6747a'
    assert not result['production_diff'] and not result['submodule_dirty']
    assert len(result['submodules'].splitlines()) == 33
    assert all(line.startswith(' ') for line in result['submodules'].splitlines())
    return result
