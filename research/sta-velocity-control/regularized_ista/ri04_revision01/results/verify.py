"""Offline result tests and immutable prior-archive check; never launches SITL."""
import argparse
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import collect

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]


def archive_rows(index, root):
    """Normalize the two frozen index schemas, not their contents/verdicts."""
    if isinstance(index['files'], list):
        assert index['scope'] == str(root)
        rows, links = index['files'], index['symlinks']
    else:
        assert isinstance(index['files'], dict) and index['root'] == str(root)
        rows = []
        for name, item in index['files'].items():
            path = Path(name)
            assert not path.is_absolute() and '..' not in path.parts
            rows.append(dict(path=str(root/path), **item))
        links = {str(root/name): value for name, value in index['links'].items()}
    assert all(root in Path(row['path']).parents and Path(row['path']).resolve() == Path(row['path']) for row in rows)
    assert all(root in Path(name).parents and '..' not in Path(name).parts for name in links)
    return rows, links


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    assert collect.ROOT in out.parents and not out.exists()
    out.mkdir(parents=True)
    evidence = dict(stage='RI04-REVISION01 result checks', success=False, new_flights=0, commands=[])
    try:
        argv = [sys.executable, '-B', str(HERE/'test_collect.py')]
        start = time.monotonic()
        with (out/'unit.log').open('xb') as stream:
            result = subprocess.run(argv, cwd=REPO, stdout=stream, stderr=subprocess.STDOUT)
        evidence['commands'].append(dict(argv=argv, exit_code=result.returncode,
            wall_s=time.monotonic()-start, log=collect.ref(out/'unit.log')))
        import importlib.util
        spec = importlib.util.spec_from_file_location('_ri04_revision01_result_receipt', HERE.parent/'receipt.py')
        receipt = importlib.util.module_from_spec(spec); spec.loader.exec_module(receipt)
        evidence['tests'] = receipt.unittest_count((out/'unit.log').read_bytes(), 'result checks')
        assert result.returncode == 0 and evidence['tests'] == 15
        for file in HERE.glob('*.py'):
            ast.parse(file.read_text())
        evidence['syntax_files'] = [collect.ref(p) for p in sorted(HERE.glob('*.py'))]
        archives = []
        for stage, reference in (
                ('RI04', HERE.parents[1]/'ri04/results/archive_reference.json'),
                ('RI04_HTE_FIX', HERE.parents[1]/'ri04_hte_fix/verification_summary.json')):
            # Original index itself is an immutable repository-bound artifact.
            root = collect.ROOT.parent/stage
            index = root/'archive_index.json'
            frozen = collect.read(reference)
            if stage == 'RI04':
                assert frozen['sha256'] == collect.digest(index)
            else:
                assert collect.digest(index) == '5e7e1dd566235fb679eed0d749572bbce5e340152057fa1c7e2921ef6e52da8c'
            original = collect.read(index)
            rows, links = archive_rows(original, root)
            for row in rows:
                file = Path(row['path'])
                assert root in file.parents and collect.ref(file) == row
            for name, target in links.items():
                assert root in Path(name).parents and os.readlink(name) == target
            archives.append(dict(stage=stage, index=collect.ref(index), files=len(rows),
                symlinks=len(links), unchanged=True))
        evidence['prior_archives'] = archives
        result = subprocess.run(['git','diff','--check','HEAD'], cwd=REPO, capture_output=True, text=True)
        evidence['commands'].append(dict(argv=['git','diff','--check','HEAD'],exit_code=result.returncode,
            stdout=result.stdout,stderr=result.stderr))
        assert result.returncode == 0
        evidence['success'] = True
    except BaseException as error:
        evidence['error'] = repr(error)
        raise
    finally:
        collect.save(out/'evidence.json', evidence)
    collect.save(HERE/'verification.json', dict(**collect.ref(out/'evidence.json'),
        success=True, tests=evidence['tests'], prior_archives=evidence['prior_archives'],new_flights=0))
    print(json.dumps(dict(success=True,tests=evidence['tests'],prior_archives=evidence['prior_archives'])))


if __name__ == '__main__':
    main()
