#!/usr/bin/env python3
"""Package completed I00 evidence; never run flight or alter historical inputs."""
import argparse
import json
import platform
from pathlib import Path
import shutil
import subprocess

from audit import digest, write_json


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    folder = Path(__file__).resolve().parent
    repo = folder.parents[3]
    raw = a.run.resolve()
    checks = []

    def check(name, argv):
        r = subprocess.run(argv, cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        checks.append(dict(name=name, argv=argv, returncode=r.returncode, output=r.stdout))
        if r.returncode:
            raise RuntimeError(name+' failed: '+r.stdout)
        return r.stdout

    check('production_unchanged', ['git', 'diff', '--exit-code', 'd45383a419908db1620e51c9a1a0f03b932f00fc', '--',
          'src', 'msg', 'boards', 'ROMFS', 'Tools', 'sitl', 'sim_scripts'])
    check('diff_check', ['git', 'diff', '--check'])
    check('compiler', ['g++', '--version'])
    check('python', ['python3', '--version'])
    check('submodules', ['git', 'submodule', 'status', '--recursive'])
    scalar = json.loads((raw/'attempt01/scalar/summary.json').read_text())
    verification = json.loads((raw/'attempt01/evidence.json').read_text())
    regression = json.loads((raw/'regression/evidence.json').read_text())
    logs = json.loads((raw/'historical02/summary.json').read_text())
    if not all(x['success'] for x in (scalar, verification, regression, logs)):
        raise AssertionError('Not all required checks passed')
    for case in scalar['cases']:
        if digest(case['raw_path']) != case['raw_sha256']:
            raise AssertionError('Scalar raw fingerprint mismatch')
    for name, data in (('scalar_summary.json', scalar), ('historical_summary.json', logs), ('regression.json', regression)):
        write_json(out/name, data)
    # Keep the compact command record, not a second copy of all scalar cases.
    verification.pop('scalar')
    write_json(out/'verification.json', verification)
    inputs = [Path('/home/yr/Downloads/MATLAB-ISTA/BBSTA.pdf'), raw/'sources/2406.16094v1.pdf']
    inputs += [Path('/home/yr/Downloads/MATLAB-ISTA/email_to_author/code')/name for name in
               ('ISTA.m', 'ESTA.m', 'fig6_fig7_comparison.m')]
    inputs += [Path('/home/yr/Desktop/codev doc/plan')/name for name in
               ('STA_MILESTONES_CN.md', 'STA_MILESTONE_STATUS_CN.md', 'ISTA_REDESIGN_TODO_CN.md', 'ISTA_REDESIGN_PROMPTS_CN.md')]
    inputs += [repo/'research/sta-rate-control/reports'/f'{name}.md' for name in
               ('M07', 'M08', 'M09', 'M10', 'ISTA_OPT01', 'ISTA_OPT02')]
    inputs += sorted(x for x in folder.rglob('*') if x.is_file() and out not in x.parents and '__pycache__' not in x.parts)
    inputs += sorted((repo/'src/modules/mc_rate_control/StaRateControl').glob('*.cpp'))
    inputs += sorted((repo/'src/modules/mc_rate_control/StaRateControl').glob('*.hpp'))
    write_json(out/'sources.json', {str(x): digest(x) for x in inputs})
    evidence = dict(success=True, scope='I00 offline only', base_head=regression['head'], checks=checks,
                    external_root=str(raw), production_updates=scalar['production_updates'],
                    cpp_tests=sum(x['tests'] for k,x in regression['tests'].items() if not k.startswith('python')),
                    existing_python_tests=sum(x['tests'] for k,x in regression['tests'].items() if k.startswith('python')),
                    new_python_tests=verification['tests'], scalar_cases=len(scalar['cases']), historical_runs=len(logs['runs']),
                    matlab_executable=shutil.which('matlab'), octave_executable=shutil.which('octave'),
                    host=platform.platform(), flights=0, proper_ista_implemented=False)
    files = sorted(x for x in raw.rglob('*') if x.is_file() and not x.is_symlink() and '__pycache__' not in x.parts)
    with (out/'artifacts.sha256').open('x') as stream:
        for file in files:
            stream.write(digest(file)+'  '+str(file)+'\n')
    evidence['external_files'] = len(files)
    evidence['external_bytes'] = sum(x.stat().st_size for x in files)
    evidence['artifacts_sha256'] = digest(out/'artifacts.sha256')
    write_json(out/'evidence.json', evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
