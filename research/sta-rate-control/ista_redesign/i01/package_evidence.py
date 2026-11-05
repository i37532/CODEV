#!/usr/bin/env python3
"""Archive I01's explicit final attempt; no newest/best-run selection or flying."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    p = argparse.ArgumentParser(); p.add_argument('--root', type=Path, required=True)
    p.add_argument('--attempt', required=True); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(); root = args.root.resolve(); out = args.output.resolve()
    if root == out or root in out.parents:
        raise ValueError('Index must be outside the indexed evidence root')
    repo = Path(__file__).resolve().parents[4]
    run = root/args.attempt
    e = json.loads((run/'evidence.json').read_text())
    assert e['success'] and e['existing']['success'] and e['i00']['success']
    assert all(digest(repo/path) == sha for path, sha in e['source_hashes'].items())
    assert (run/'scalar/summary.json').read_bytes() == (run/'sanitizer_scalar/summary.json').read_bytes()
    files = sorted(p for p in root.rglob('*') if p.is_file())
    lines = [f'{digest(path)}  {path}\n' for path in files]
    existing_cpp = sum(v['tests'] for k, v in e['existing']['tests'].items() if not k.startswith('python'))
    existing_python = sum(v['tests'] for k, v in e['existing']['tests'].items() if k.startswith('python'))
    evidence = dict(success=True, parent=e['head'], branch=e['branch'], submodules=e['submodules'],
                    final_attempt=str(run), raw_root=str(root), artifacts=len(files),
                    artifact_bytes=sum(p.stat().st_size for p in files),
                    commands=e['commands'], regression_commands=e['existing']['commands'],
                    i00_commands=e['i00']['commands'], source_hashes=e['source_hashes'],
                    firmware_sha256=e['firmware_sha256'],
                    new_cpp=e['tests']['cpp_new'], existing_cpp=existing_cpp, total_cpp=existing_cpp+e['tests']['cpp_new']['tests'],
                    new_python=e['tests']['python_new'], existing_python=existing_python, i00_python=e['i00']['tests'],
                    total_python=e['tests']['python_new']+existing_python+e['i00']['tests'],
                    new_reference=e['scalar']['reference'], new_plant_cases=len(e['scalar']['cases']), new_updates=e['scalar']['updates'],
                    i00_reference_plant_cases=len(e['i00']['scalar']['cases']),
                    matlab_executed=False, matlab_path=e['matlab'], octave_path=e['octave'], flight_executed=False,
                    new_kernel_in_final_firmware=False, index_sha256=hashlib.sha256(''.join(lines).encode()).hexdigest())
    checks = []
    for argv in (['git', 'diff', '--check'], ['git', 'submodule', 'foreach', '--recursive', 'git status --porcelain'],
                 ['g++', '--version'], ['python3', '--version'], ['cmake', '--version'], ['uname', '-a']):
        r = subprocess.run(argv, cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        checks.append(dict(argv=argv, returncode=r.returncode, output=r.stdout))
        assert r.returncode == 0
    evidence['packaging_checks'] = checks
    evidence['packager_sha256'] = digest(Path(__file__))
    paper = Path('/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I00/run01/sources/2406.16094v1.pdf')
    evidence['fixed_paper'] = dict(path=str(paper), sha256=digest(paper), url='https://arxiv.org/pdf/2406.16094v1')
    assert evidence['fixed_paper']['sha256'] == '9aa4a20ef2a0f562cfad897e18cb8db96cf174fd332592bb2887e19ddafdd73b'
    out.mkdir(parents=True, exist_ok=False)
    with (out/'artifacts.sha256').open('x') as stream:
        stream.writelines(lines)
    save(out/'evidence.json', evidence)
    save(out/'scalar_summary.json', e['scalar'])
    print(json.dumps({k: evidence[k] for k in ('total_cpp', 'total_python', 'artifacts', 'artifact_bytes', 'index_sha256')}, indent=2))


if __name__ == '__main__':
    main()
