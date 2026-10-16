#!/usr/bin/env python3
"""Diagnostic-only repair of R03's cross-stage ``task`` import collision.

No old module/global/source is patched. The frozen AX02 height function's AST
changes only by replacing its local ``from task import offsets`` with ``pass``;
an explicitly loaded AX02 Nx3 reference is supplied in PRIVATE function globals.
The full frozen analyzer runs on new sidecar copies, reads original ULogs, and
cannot mint a flight acceptance, gate receipt, or authorization. An old failed
decision remains failed even if this diagnostic completes all checks.
"""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import traceback
import types

import numpy as np

HERE = Path(__file__).resolve().parent
R03 = HERE.parent
REPO = R03.parents[3]
HEIGHT = REPO/'research/sta-velocity-control/axis_ablation/ax02/height.py'
TASK = HEIGHT.with_name('task.py')
PINS = {
    HEIGHT: '2f7393ce4b73339a80902ac805e7d5c79476b67bbe309961195332af92af4f4c',
    TASK: 'be019473a99622ddba7e603059b54e91efa6472b76dec6aa47f4b13f1163768b',
    R03/'analyzer.py': 'c43f2bff38e874eb23618fc126ccf95f20da38f93ad238b67edabc9a64ce6c72',
    R03/'targets.py': 'f89e068d5f996605336c0df51ec3394a3d047d9f380ccda7395f4f7235d69f65',
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def pinned_inputs():
    actual = {str(path): digest(path) for path in PINS}
    if any(actual[str(path)] != expected for path, expected in PINS.items()):
        raise ValueError('Frozen height/task/analyzer/targets source changed')
    return actual


def load_path(name, path):
    """Private module object; no insertion/replacement in sys.modules."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_analyzer(order='runner-first'):
    pinned_inputs()
    if order == 'runner-first':
        runner = load_path('r03_repair01_runner', R03/'runner.py')
        return runner.local_module('analyzer')
    if order == 'analyzer-first':
        return load_path('r03_repair01_analyzer', R03/'analyzer.py')
    raise ValueError('Unknown diagnostic import order')


def checked_offsets(reference, mode, times):
    """Additional fail-closed structural check, never pad a 2-column result."""
    if type(mode) is not int or mode not in (1, 2, 6, 8):
        raise ValueError('R03 height accepts explicit task modes 1/2/6/8 only')
    times = np.asarray(times, dtype=float)
    if times.ndim != 1 or not len(times) or not np.all(np.isfinite(times)):
        raise ValueError('Invalid height offset time vector')
    value = reference(mode, times)
    expected = dict(p=(len(times), 3), v=(len(times), 3), a=(len(times), 3),
                    yaw=(len(times),), yaw_rate=(len(times),))
    if set(value) != set(expected):
        raise ValueError('Unexpected height reference schema')
    for key, shape in expected.items():
        if np.asarray(value[key]).shape != shape or not np.all(np.isfinite(value[key])):
            raise ValueError('Malformed/nonfinite AX02 reference '+key)
    return value


def height_ast():
    """Return original and import-only repaired ASTs, preserving every check."""
    tree = ast.parse(HEIGHT.read_text(), filename=str(HEIGHT))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'height_evidence']
    if len(functions) != 1:
        raise ValueError('Missing unique frozen height function')
    original = functions[0]
    repaired = copy.deepcopy(original)
    imports = [(i, n) for i, n in enumerate(repaired.body) if isinstance(n, ast.ImportFrom)
               and n.module == 'task']
    if len(imports) != 1 or ast.dump(imports[0][1], include_attributes=False) != ast.dump(
            ast.ImportFrom(module='task', names=[ast.alias(name='offsets')], level=0), include_attributes=False):
        raise ValueError('Unexpected frozen height import; refuse broad AST rewriting')
    index, node = imports[0]
    repaired.body[index] = ast.copy_location(ast.Pass(), node)
    # Prove exact equality after restoring precisely the single import node.
    restored = copy.deepcopy(repaired)
    restored.body[index] = copy.deepcopy(original.body[index])
    if ast.dump(original, include_attributes=False) != ast.dump(restored, include_attributes=False):
        raise ValueError('Height semantics changed outside the import binding')
    return original, repaired, index


def bind_height(analyzer):
    """No writes to analyzer globals, original height globals or generic imports."""
    sources = pinned_inputs()
    original_module = load_path('r03_repair01_frozen_height', HEIGHT)
    task_module = load_path('r03_repair01_frozen_task', TASK)
    original, repaired, index = height_ast()
    namespace = dict(original_module.height_evidence.__globals__)
    namespace['__name__'] = 'r03_repair01_private_height'
    namespace['offsets'] = lambda mode, times: checked_offsets(task_module.offsets, mode, times)
    tree = ast.fix_missing_locations(ast.Module(body=[repaired], type_ignores=[]))
    exec(compile(tree, str(HEIGHT), 'exec'), namespace)
    function = namespace['height_evidence']
    if function.__globals__ is original_module.height_evidence.__globals__:
        raise AssertionError('Height globals were not isolated')
    return function, dict(source_sha256=sources, replaced_statement_index=index,
                         only_change='local import replaced by pass; offsets explicitly bound to AX02 Nx3',
                         offsets_source=str(TASK), height_source=str(HEIGHT),
                         numerical_thresholds_changed=False, historical_sources_modified=False)


def diagnostic_payload(value):
    result = dict(value)
    result.update(diagnostic_checks_complete=value.get('accepted') is True,
                  accepted=False, flight_accepted=False, diagnostic_only=True,
                  historical_acceptance_unchanged=True, new_flights=0)
    return result


def diagnostic_analyze(analyzer, height, run, protocol, job):
    """Run unchanged analyzer code with private height/save bindings only."""
    namespace = dict(analyzer.analyze.__globals__)
    original_save = namespace['save']

    def save(path, value):
        original_save(path, diagnostic_payload(value) if Path(path).name == 'r03_metrics.json' else value)

    namespace.update(height_evidence=height, save=save)
    function = types.FunctionType(analyzer.analyze.__code__, namespace,
                                  'r03_repair01_diagnostic_analyze', analyzer.analyze.__defaults__,
                                  analyzer.analyze.__closure__)
    function.__kwdefaults__ = analyzer.analyze.__kwdefaults__
    return diagnostic_payload(function(run, protocol, job))


def snapshot(root):
    root = Path(root)
    return {str(path): digest(path) for path in sorted(root.rglob('*')) if path.is_file()}


def source_snapshot():
    paths = {p for p in R03.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    paths.update(PINS)
    return {str(p): digest(p) for p in sorted(paths)}


def copy_sidecars(source, dest):
    source, dest = Path(source).resolve(), Path(dest).resolve()
    if source == dest or source in dest.parents or dest in source.parents:
        raise ValueError('Fresh independent output required')
    dest.mkdir(parents=True, exist_ok=False)
    for path in source.iterdir():
        if path.is_file() and path.suffix in ('.json', '.jsonl', '.txt', '.log', '.bson'):
            shutil.copyfile(path, dest/path.name)
    return dest


def run_diagnostic(source, dest, order='runner-first'):
    source, dest = Path(source).resolve(), Path(dest).resolve()
    before, code_before = snapshot(source), source_snapshot()
    old = json.loads((source/'r03_metrics.json').read_text())
    if old.get('accepted') is not False:
        raise ValueError('Repair01 is only for the retained failed historical analysis')
    result = dict(diagnostic_only=True, historical_acceptance_unchanged=True,
                  accepted=False, flight_accepted=False, new_flights=0,
                  source_directory=str(source), output_directory=str(dest), import_order=order,
                  original_accepted=old['accepted'], original_error=old.get('error'),
                  input_sha256_before=before, source_sha256_before=code_before)
    dest = copy_sidecars(source, dest)
    try:
        analyzer = load_analyzer(order)
        height, binding = bind_height(analyzer)
        result['binding'] = binding
        job = json.loads((dest/'job.json').read_text())
        protocol = analyzer.replay_protocol(dest, job)
        result['metrics'] = diagnostic_analyze(analyzer, height, dest, protocol, job)
        result['diagnostic_checks_complete'] = result['metrics']['diagnostic_checks_complete']
    except Exception as exc:
        result.update(diagnostic_checks_complete=False, error=str(exc), traceback=traceback.format_exc())
    finally:
        result['input_sha256_after'] = snapshot(source)
        result['source_sha256_after'] = source_snapshot()
        result['source_inputs_unchanged'] = (result['input_sha256_after'] == before
                                              and result['source_sha256_after'] == code_before)
        result['historical_acceptance_unchanged'] = json.loads((source/'r03_metrics.json').read_text()) == old
        # This is not an admission receipt. Never create gate_pass/authorization.
        (dest/'diagnostic_summary.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--import-order', choices=('runner-first', 'analyzer-first'), default='runner-first')
    args = parser.parse_args()
    outcome = run_diagnostic(args.run, args.output, args.import_order)
    print(json.dumps({k:v for k,v in outcome.items() if k not in
                     ('metrics', 'input_sha256_before', 'input_sha256_after', 'source_sha256_before', 'source_sha256_after')}, indent=2))
    raise SystemExit(0 if outcome.get('diagnostic_checks_complete') and outcome.get('source_inputs_unchanged')
                     and outcome.get('historical_acceptance_unchanged') else 1)
