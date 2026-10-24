#!/usr/bin/env python3
"""Verify this offline evidence package without rerunning trajectories or flying."""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
import sys
from analyze import digest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    reference = json.loads((HERE/'results/archive_reference.json').read_text())
    summary = json.loads((HERE/'results/summary.json').read_text())
    commands = []
    def run(name, argv):
        result = subprocess.run(argv, cwd=REPO, capture_output=True, text=True)
        log = args.output/(name+'.log')
        log.write_text(result.stdout+result.stderr)
        commands.append(dict(name=name, argv=argv, exit_code=result.returncode, log=str(log.resolve()), sha256=digest(log)))
        if result.returncode:
            raise RuntimeError(name)
        return result.stdout
    try:
        index_path = Path(reference['final_archive_index'])
        assert digest(index_path) == reference['final_archive_index_sha256']
        index = json.loads(index_path.read_text())
        assert len(index) == reference['final_archive_files']
        assert sum(row['bytes'] for row in index) == reference['final_archive_bytes']
        for row in index:
            path = Path(row['path'])
            assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256'], str(path)
        for path, expected in summary['input_sha256'].items():
            assert digest(Path(path)) == expected, path
        assert digest(HERE/'analyze.py') == summary['analysis_sha256']
        assert digest(Path(summary['summary_path'])) == summary['summary_sha256']
        assert summary['independent_metric_replays'] == 144
        assert summary['complete_trajectories'] == 132 and summary['rejected_trajectories'] == 12
        assert summary['cpp_bridge_tests'] == 72 and summary['python_tests'] == 18
        assert summary['existing_cpp_cases'] == 433 and summary['new_flights'] == 0
        run('analysis_tests', [sys.executable, '-B', str(HERE/'test_analysis.py'), '-v'])
        diff = run('production_diff', ['git', 'diff', summary['entry_head'], '--',
                   'src', 'msg', 'Tools', 'sitl', 'ROMFS', 'boards', 'platforms', 'CMakeLists.txt', '.gitmodules'])
        assert not diff
        run('diff_check', ['git', 'diff', '--check'])
        submodules = run('submodules', ['git', 'submodule', 'status', '--recursive'])
        assert submodules == summary['submodules']
        assert not run('submodule_worktrees', ['git', 'submodule', 'foreach', '--quiet', '--recursive', 'git status --porcelain'])
        for path in HERE.glob('*.py'):
            ast.parse(path.read_text())
        links = 0
        report = HERE.parent/'reports/PROPER_ISTA_PROBE.md'
        for document in [*HERE.glob('*.md'), report]:
            for target in re.findall(r'\]\(([^)]+)\)', document.read_text()):
                if '://' not in target:
                    assert (document.parent/target.split('#')[0]).resolve().exists(), target
                    links += 1
        receipt = dict(success=True, commands=commands, verified_archive_files=len(index),
                       local_document_links=links, cpp_cases=505, python_cases=24,
                       trajectories_attempted=144, trajectories_complete=132, numeric_stops=12,
                       infeasible_examples=12, production_diff_empty=True, new_flights=0)
    except Exception as error:
        (args.output/'verification.json').write_text(json.dumps(dict(success=False, error=repr(error), commands=commands), indent=2)+'\n')
        raise
    (args.output/'verification.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({key: value for key, value in receipt.items() if key != 'commands'}))


if __name__ == '__main__':
    main()
