#!/usr/bin/env python3
"""Offline-only nested height/handoff import repair; never a flight admission.

Both frozen functions keep their complete bodies. The unique local task import
in each is replaced by pass, with an inverse-AST identity proof. Private globals
bind height -> fixed handoff -> fixed AX02 Nx3 offsets, not sys.modules' task or
handoff. No production source, numerical tolerance, old verdict or seed changes.
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

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parents[1]
REPO = RESEARCH.parents[1]
OLD = HERE.parent/'r03_revision05'
RETAINED = HERE.parent/'r03_revision04'
HEIGHT = RESEARCH/'axis_ablation/ax02/height.py'
TASK = HEIGHT.with_name('task.py')
HANDOFF = RESEARCH/'v08/protocol02/handoff.py'
CAPTURE = HANDOFF.with_name('handoff_capture.py')
SCRIPTS = RESEARCH/'scripts'
PINS = {
    HEIGHT: '2f7393ce4b73339a80902ac805e7d5c79476b67bbe309961195332af92af4f4c',
    TASK: 'be019473a99622ddba7e603059b54e91efa6472b76dec6aa47f4b13f1163768b',
    HANDOFF: '7b0074bd9f176e9af08c85ebb5a28af104077cd1adf3e689e7e31ce04594b7bf',
    CAPTURE: '7994a2fbcbfdee497cb9a14a8c7d25887ff7eabdcd267fd8c4f91db2398c78bf',
    SCRIPTS/'v04_triplet16.py': 'ae0fc4b11342f8db1b87ec5732a240b0f59609f982af1a829d1f10a91e55c95b',
    SCRIPTS/'v04_heading_stream.py': '0d23ea43e95968aeb86529ce073aa85d9a99f8a07c006349654d6744adeb0db3',
    SCRIPTS/'v04_task04.py': '32581042abed4c683267bd949fc18f0d72f9a3e8160b4ce05470f717d81c1d91',
    SCRIPTS/'v04_logcheck07.py': 'ebf8ddce4fd87aa3dcc61f51da756f52bef8ae4ddbc3657454266e3992d9e752',
    SCRIPTS/'analyze_v00.py': '4298ee230c4d0d60aeca83ddd0b805ef04f29fa54e09889476c91fb4c82a5051',
    SCRIPTS/'v04_live_clock09.py': '74d7e97d04faeab285691eede9424c02cb26dedb637111dae93d701f707e8a09',
    SCRIPTS/'check_v04_protocol02.py': 'ad890643a84ed359c2c027d6141f8e4909428ded47ac96d4b105de54f23314b4',
    OLD/'analyzer.py': '3cc164cb8108e07a42de5105e8f943bec37d82b5a8163baa74006ff2f745d72c',
    OLD/'runner.py': '4bb6e77cc700f7df91c121aedf9e51744e2fd0709a05cf5a0c4ab52ffb0fb978',
    OLD/'numeric_adapter.py': 'd685f68dd3079b4923210665d7a7c9ae5b50296fa2dcca0c6fd9d0cfd1b3d6b0',
    OLD/'replay.py': 'f99353ebc2698a1538a2fac641bdd95fb729742ef44a1281c7997181493a0f0d',
    RETAINED/'analyzer.py': 'a9e6ecd071859782d883a0301d4db27259d66882e9eba9fbba09d5a99c407f82',
    RETAINED/'replay.py': 'db8c69f4f0d8086ade4a2f92f7a639a519d7036b89b203fe2c36cd3640f97ff3',
}


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def pinned_inputs():
    actual = {str(path): digest(path) for path in PINS}
    if any(actual[str(path)] != expected for path, expected in PINS.items()):
        raise ValueError('Frozen handoff06 dependency changed')
    return actual


def load_path(name, path):
    """A private module object, never replacing a sys.modules entry."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_analyzer(order):
    pinned_inputs()
    if order == 'runner-first':
        runner = load_path('handoff06_original_runner', OLD/'runner.py')
        return runner.local_module('analyzer')
    if order == 'analyzer-first':
        return load_path('handoff06_original_analyzer', OLD/'analyzer.py')
    raise ValueError('Unknown diagnostic import order')


def function_ast(path, name):
    nodes = [node for node in ast.parse(Path(path).read_text()).body
             if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(nodes) != 1:
        raise ValueError('Missing unique frozen function '+name)
    return nodes[0]


def import_only_ast(path, name):
    """Remove exactly one specified local import, then prove inverse identity."""
    original = function_ast(path, name)
    revised = copy.deepcopy(original)
    wanted = ast.dump(ast.parse('from task import offsets').body[0], include_attributes=False)
    positions = []
    for node in ast.walk(revised):
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                for index, child in enumerate(value):
                    if isinstance(child, ast.ImportFrom) and child.module == 'task':
                        if ast.dump(child, include_attributes=False) != wanted:
                            raise ValueError('Unexpected task import shape')
                        positions.append((node, field, index, child))
    if len(positions) != 1:
        raise ValueError('Expected exactly one local task import')
    node, field, index, statement = positions[0]
    marker = ast.copy_location(ast.Pass(), statement)
    getattr(node, field)[index] = marker
    # Source contains no pass statements in either frozen function. Replacing
    # this one marker back must recreate the entire original AST exactly.
    class Inverse(ast.NodeTransformer):
        count = 0
        def visit_Pass(self, current):
            self.count += 1
            return copy.deepcopy(statement)
    inverse = Inverse()
    restored = inverse.visit(copy.deepcopy(revised))
    if inverse.count != 1 or ast.dump(restored, include_attributes=False) != ast.dump(original, include_attributes=False):
        raise ValueError('Import repair changed another frozen AST node')
    return original, revised


def compile_function(node, path, namespace):
    private = dict(namespace)
    private['__name__'] = 'handoff06_private_'+node.name
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(path), 'exec'), private)
    return private[node.name]


def checked_offsets(reference, mode, times):
    if type(mode) is not int or mode not in (1, 2, 6, 8):
        raise ValueError('Handoff06 requires task modes 1/2/6/8')
    t = np.asarray(times, dtype=float)
    if t.ndim != 1 or not len(t) or not np.all(np.isfinite(t)):
        raise ValueError('Invalid reference time vector')
    value = reference(mode, t)
    expected = dict(p=(len(t), 3), v=(len(t), 3), a=(len(t), 3), yaw=(len(t),), yaw_rate=(len(t),))
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError('Unexpected reference schema')
    for key, shape in expected.items():
        if np.asarray(value[key]).shape != shape or not np.all(np.isfinite(value[key])):
            raise ValueError('Malformed/nonfinite AX02 reference '+key)
    return value


def attest(function, path, name=None):
    if not isinstance(function, types.FunctionType) or Path(function.__code__.co_filename).resolve() != Path(path).resolve():
        raise ValueError('Unexpected direct dependency source '+str(name or path))
    if name and function.__name__ != name:
        raise ValueError('Unexpected dependency symbol '+name)
    return function


def bind_height(analyzer=None):
    """Bind every direct project symbol by explicit path, with no generic imports.

Unique historical v04 helpers retain their frozen implementations. The two
ambiguous stage names (task, handoff) and handoff_capture are never resolved via
the process cache. This is not a rewrite of unrelated legacy helper internals.
"""
    sources = pinned_inputs()
    modules = {name: load_path('handoff06_'+name, SCRIPTS/(name+'.py')) for name in
               ('v04_triplet16', 'v04_heading_stream', 'v04_task04', 'v04_logcheck07')}
    capture = load_path('handoff06_capture', CAPTURE)
    # Even capture's unique imported v04 symbols must come from their frozen
    # source paths; a poisoned generic helper fails closed rather than passing.
    for name, file in [('data', 'v04_heading_stream'), ('index', 'v04_heading_stream'),
                       ('row', 'v04_heading_stream'), ('replay', 'v04_live_clock09'),
                       ('scalars', 'v04_task04'), ('target_altitude', 'check_v04_protocol02')]:
        attest(getattr(capture, name), SCRIPTS/(file+'.py'), name)
    reference = compile_function(function_ast(TASK, 'offsets'), TASK, {'np': np})
    offsets = lambda mode, times: checked_offsets(reference, mode, times)
    def symbol(module, name):
        return attest(getattr(modules[module], name), SCRIPTS/(module+'.py'), name)
    handoff_globals = dict(json=json, np=np, offsets=offsets,
        triplet_data=symbol('v04_triplet16', 'triplet_data'),
        data=symbol('v04_heading_stream', 'data'), index=symbol('v04_heading_stream', 'index'),
        row=symbol('v04_heading_stream', 'row'), accepted_ack=symbol('v04_task04', 'accepted_ack'),
        event_data=symbol('v04_logcheck07', 'event_data'),
        receiver_target=symbol('v04_logcheck07', 'receiver_target'),
        validate_receiver_profile=symbol('v04_logcheck07', 'validate_receiver_profile'))
    for name in ('capture', 'matches_target', 'decode_current'):
        handoff_globals[name] = attest(getattr(capture, name), CAPTURE, name)
    _, handoff_ast = import_only_ast(HANDOFF, 'check_handoff')
    handoff = compile_function(handoff_ast, HANDOFF, handoff_globals)
    previous = compile_function(function_ast(SCRIPTS/'analyze_v00.py', 'previous_indices'),
                                SCRIPTS/'analyze_v00.py', {'np': np})
    height_globals = dict(json=json, np=np, offsets=offsets, check_handoff=handoff,
        previous_indices=previous, replay=symbol('v04_heading_stream', 'replay'),
        REFERENCE=modules['v04_task04'].REFERENCE)
    _, height_ast = import_only_ast(HEIGHT, 'height_evidence')
    height = compile_function(height_ast, HEIGHT, height_globals)
    return height, dict(source_sha256=sources, offsets_source=str(TASK), handoff_source=str(HANDOFF),
        height_source=str(HEIGHT), complete_direct_symbol_binding=True,
        only_change='Two local task imports replaced by pass; explicit private height -> handoff -> AX02 offsets',
        inverse_ast_identity=True, shared_globals_modified=False,
        numerical_thresholds_changed=False, historical_sources_modified=False,
        authority='offline diagnostic only; no qualification, flight or gate receipt')


def clone(function, **overrides):
    namespace = dict(function.__globals__)
    namespace.update(overrides)
    result = types.FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def diagnostic_payload(value):
    result = dict(value)
    result.update(diagnostic_checks_complete=value.get('accepted') is True, accepted=False,
        flight_accepted=False, diagnostic_only=True, historical_acceptance_unchanged=True,
        new_flights=0, execution_authority_granted=False)
    return result


def diagnostic_analyze(analyzer, height, run, protocol, job, binding, *, source, original=None):
    """Unchanged full R03 checks, retaining revision05 provenance/prearm/numeric."""
    original = analyzer if original is None else original
    preparation = {}
    copied = {}
    def provenance(r, p, j):
        if Path(r).resolve() != Path(run).resolve():
            raise ValueError('Unexpected diagnostic input directory')
        copied.update(copied_input_binding(source, r))
        # The old signed/qualified sidecar is read ONLY in its original archive.
        # Other inputs consumed in the output sandbox must be exact copies.
        result = original.provenance(Path(source), p, j)
        preparation.update(original.prearm_evidence(Path(source)))
        return result
    def save(path, value):
        analyzer._inherited.save(path, diagnostic_payload(value) if Path(path).name == 'r03_metrics.json' else value)
    function = clone(analyzer._inherited.analyze, provenance=provenance, height_evidence=height,
        check_components=analyzer._components, r02=analyzer._numeric_r02, save=save)
    raw = function(run, protocol, job)
    result = diagnostic_payload(raw)
    result['prearm_preparation'] = preparation or dict(valid=False, reason='preparation not validated')
    result['candidate_numeric_binding'] = analyzer.NUMERIC_BINDING
    result['handoff_dependency_binding'] = binding
    result['copied_input_sha256'] = copied
    analyzer._inherited.save(Path(run)/'r03_metrics.json', result)
    return result


def source_snapshot():
    paths = set(PINS)
    for root in (HERE, OLD, RETAINED, HERE.parent/'r03', HERE.parent/'r02', HERE.parent/'r03_numeric05', HERE.parent/'r03_prearm04'):
        paths.update(root.rglob('*.py'))
    return {str(path): digest(path) for path in sorted(paths)}


FORBIDDEN_COPIES = {'gate_pass.json', 'authorization.json', 'r03_metrics.json'}
SIDECAR_SUFFIXES = ('.json', '.jsonl', '.txt', '.log', '.bson')


def copy_sidecars(source, dest):
    source, dest = Path(source).resolve(), Path(dest).resolve()
    if (source == dest or source in dest.parents or dest in source.parents or dest.exists()
            or any(part.startswith('batch') for part in dest.parts)):
        raise ValueError('Fresh independent diagnostic directory required')
    dest.mkdir(parents=True, exist_ok=False)
    # Old receipts are provenance only. A diagnostic must never manufacture a
    # reusable success/authorization artifact, including by copying one.
    for path in source.iterdir():
        if path.is_file() and path.name not in FORBIDDEN_COPIES and path.suffix in SIDECAR_SUFFIXES:
            shutil.copyfile(path, dest/path.name)
    return dest


def copied_input_binding(source, dest):
    """Before analysis writes, prove exact provenance for every copied sidecar."""
    source, dest = Path(source).resolve(), Path(dest).resolve()
    if source == dest or source in dest.parents or dest in source.parents:
        raise ValueError('Independent diagnostic input copy required')
    expected = {path.name:digest(path) for path in source.iterdir()
        if path.is_file() and path.name not in FORBIDDEN_COPIES and path.suffix in SIDECAR_SUFFIXES}
    actual = {path.name:digest(path) for path in dest.iterdir() if path.is_file()}
    if not expected or expected != actual or any(path.is_dir() for path in dest.iterdir()):
        raise ValueError('Diagnostic sidecar copy differs from the original archive')
    return expected


def original_analysis(analyzer, job, source):
    """Keep the actual historical revision/job/provenance, never relabel A as05."""
    if job.get('revision') == 'r03_revision05':
        return analyzer
    if job.get('revision') != 'r03_revision04' or job.get('gate') != 'A':
        raise ValueError('Only retained revision04 A and original revision05 inputs are supported')
    proof = analyzer._protocol().retained_a()
    expected = Path(proof['root']).resolve()/'batch01'/job['id']
    if Path(source).resolve() != expected:
        raise ValueError('Not the original retained A archive')
    return load_path('handoff06_retained_a_original_analyzer', RETAINED/'analyzer.py')


def run_diagnostic(source, dest, order):
    source, dest = Path(source).resolve(), Path(dest).resolve()
    analyzer = load_analyzer(order)
    replay = load_path('handoff06_raw_input_snapshot', OLD/'replay.py')
    before, code_before = replay.raw_snapshot(source), source_snapshot()
    old = json.loads((source/'r03_metrics.json').read_text())
    job = json.loads((source/'job.json').read_text())
    if type(old.get('accepted')) is not bool:
        raise ValueError('Original recorded boolean verdict required')
    original = original_analysis(analyzer, job, source)
    protocol = original.replay_protocol(source, job)
    original._archive_scope(source, protocol, job)
    height, binding = bind_height(analyzer)
    dest = copy_sidecars(source, dest)
    result = dict(diagnostic_only=True, accepted=False, flight_accepted=False, new_flights=0,
        execution_authority_granted=False, historical_acceptance_unchanged=True,
        source_directory=str(source), output_directory=str(dest), import_order=order,
        original_accepted=old['accepted'], original_error=old.get('error'), binding=binding,
        original_revision=job['revision'], original_gate=job['gate'], original_job=job,
        input_sha256_before=before, source_sha256_before=code_before)
    try:
        result['metrics'] = diagnostic_analyze(analyzer, height, dest, protocol, job, binding, source=source, original=original)
        result['diagnostic_checks_complete'] = result['metrics']['diagnostic_checks_complete']
    except Exception as error:
        result.update(diagnostic_checks_complete=False, error=str(error), traceback=traceback.format_exc())
    finally:
        result['input_sha256_after'] = replay.raw_snapshot(source)
        result['source_sha256_after'] = source_snapshot()
        result['source_inputs_unchanged'] = (result['input_sha256_after'] == before and result['source_sha256_after'] == code_before)
        result['historical_acceptance_unchanged'] = json.loads((source/'r03_metrics.json').read_text()) == old
        result['output_sha256'] = {str(path): digest(path) for path in sorted(dest.rglob('*')) if path.is_file()}
        analyzer._inherited.save(dest/'diagnostic_summary.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--import-order', choices=('runner-first', 'analyzer-first'), required=True)
    args = parser.parse_args()
    value = run_diagnostic(args.run, args.output, args.import_order)
    print(json.dumps({k:v for k,v in value.items() if k not in ('metrics', 'input_sha256_before',
        'input_sha256_after', 'source_sha256_before', 'source_sha256_after')}, indent=2))
    raise SystemExit(0 if value.get('diagnostic_checks_complete') is True
        and value.get('source_inputs_unchanged') is True and value.get('historical_acceptance_unchanged') is True else 1)
