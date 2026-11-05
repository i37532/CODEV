#!/usr/bin/env python3
"""Offline-only R03 revision02 analysis preparation, with isolated AX02 Nx3 height.

The inherited numerical, safety, clock, landing and paired-risk code is frozen.
Only the private height import binding and explicitly authorized revision/budget
provenance differ. New flight acceptance is hard-disabled in this revision.
Old R03 logs cannot be accepted by this entry. Their separate
--historical-diagnostic route remains non-authorizing and preserves all files.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import types

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
OLD = HERE.parent/'r03'
REVISION = 'r03_revision02'
REPAIR = OLD/'repair01/adapter.py'
REPAIR_SHA256 = 'be4baf146c3c0991968b30db853e51fb3812fe6723e80d5adcbec50053155e55'


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def load_path(name, path):
    """No generic module names or shared module-global overrides."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if digest(REPAIR) != REPAIR_SHA256:
    raise ValueError('Frozen height repair implementation changed')
_repair = load_path('r03_revision02_frozen_height_repair', REPAIR)
# For the real CLI regression, load the actual NEW runner before the inherited
# analyzer. Importing the analyzer first and only then invoking a runner is not
# a runner-first test and previously hid the historical path-order collision.
if __name__ == '__main__' and '--historical-diagnostic' in sys.argv[1:]:
    _order_parser = argparse.ArgumentParser(add_help=False)
    _order_parser.add_argument('--import-order', default='runner-first')
    _order_args, _ = _order_parser.parse_known_args()
    if _order_args.import_order == 'runner-first':
        load_path('r03_revision02_cli_bootstrap_runner', HERE/'runner.py')
_inherited = _repair.load_analyzer('analyzer-first')
_height, HEIGHT_BINDING = _repair.bind_height(_inherited)
targets = _inherited._targets


def _protocol():
    return load_path('r03_revision02_analyzer_protocol', HERE/'protocol.py')


def validate_job(job):
    if job.get('revision') != REVISION:
        raise ValueError('Only prospective r03_revision02 jobs are admissible')
    return _inherited.validate_job(job)


def _budget():
    return dict(maximum_attempts=9, new_matrix_attempts=36,
                historical_attempts=8, total_maximum_attempts=44)


def exact(left, right):
    """A bool or float cannot impersonate an integer in frozen provenance."""
    return json.dumps(left,sort_keys=True,separators=(',',':'),allow_nan=False) == \
        json.dumps(right,sort_keys=True,separators=(',',':'),allow_nan=False)


def _protocol_identity(protocol, job):
    validate_job(job)
    if (protocol.get('revision') != REVISION or protocol.get('stage') != 'R03-revision02-'+job['gate']
            or protocol.get('gate') != job['gate']
            or any(type(protocol.get(k)) is not int or protocol[k] != v for k,v in _budget().items())):
        raise ValueError('Wrong revision/stage/gate or explicit 9/36/8/44 budget')
    if not any(exact(job, candidate) for candidate in protocol.get('jobs', [])):
        raise ValueError('Job outside prospective frozen manifest')
    frozen = _protocol().load_protocol(job['gate'])
    excluded = {'qualification_path', 'startup_overrides'}
    if not exact({k:v for k,v in protocol.items() if k not in excluded}, {k:v for k,v in frozen.items() if k not in excluded}):
        raise ValueError('Actual protocol differs from prospective frozen gate')
    if not exact(protocol['startup_overrides'], {**frozen['startup_overrides'], **job['parameters']}):
        raise ValueError('Wrong prospective per-job parameter overlay')
    actual_path = Path(protocol['qualification_path']).resolve()
    gate_root = Path(frozen['qualification_path']).resolve().parent.parent
    if gate_root not in actual_path.parents:
        raise ValueError('Prospective qualification outside frozen gate root')
    return frozen


def _archive_scope(run, protocol, job):
    """Before any output write, refuse legacy evidence disguised as a new run."""
    validate_job(job)
    run = Path(run).resolve()
    record = json.loads((run/'result.json').read_text())
    expected = (Path(protocol['artifacts']['new_run_root'])/job['id']).resolve()
    files = record.get('logs', [])
    if (not files or len({entry['archive'] for entry in files}) != len(files)
            or any(Path(entry['archive']).resolve().parent != expected
                   or Path(entry['archive']).suffix != '.ulg' for entry in files)):
        raise ValueError('Raw ULogs are not from the exact prospective job directory')
    return record


def provenance(run, protocol, job):
    """Version-specific authority, exact restoration and immutable source binding."""
    run = Path(run)
    _protocol_identity(protocol, job)
    _protocol().require_execution_authority(job['gate'])
    record = _archive_scope(run, protocol, job)
    if not exact(json.loads((run/'run_protocol.json').read_text()), protocol):
        raise ValueError('Saved actual protocol differs from prospective binding')
    config, execution, qp = map(Path, (protocol['config_dir'], protocol['execution_path'], protocol['qualification_path']))
    reference = json.loads((run/'qualification_reference.json').read_text())
    if Path(reference.get('path','')).resolve() != qp.resolve() or reference.get('sha256') != digest(qp):
        raise ValueError('Explicit prospective qualification sidecar differs')
    approval = json.loads((run/'authorization.json').read_text())
    qualified = json.loads(qp.read_text())
    if (qualified.get('success') is not True or qualified.get('clean') is not True
            or qualified.get('revision') != REVISION or qualified.get('stage') != protocol['stage']
            or qualified.get('gate') != job['gate'] or type(qualified.get('new_flights')) is not int
            or qualified['new_flights'] != 0):
        raise ValueError('Not a clean prospective offline qualification')
    if any(type(qualified.get(k)) is not int or type(approval.get(k)) is not int for k in _budget()):
        raise ValueError('Prospective budget counts must be integers, not bool/float')
    expected = dict(revision=REVISION, stage=protocol['stage'], gate=job['gate'],
                    source_head=qualified['source_head'], execution_sha256=digest(execution),
                    frozen_sha256=digest(config/'frozen.json'), firmware_sha256=qualified['firmware_sha256'],
                    qualification_sha256=digest(qp), historical_budget=_protocol().retained_failure(), **_budget())
    for key in ('execution_sha256', 'frozen_sha256', 'historical_budget', *_budget()):
        if not exact(qualified.get(key), expected[key]):
            raise ValueError('Prospective qualification input changed: '+key)
    if approval.get('approved') is not True or any(not exact(approval.get(k), v) for k,v in expected.items()):
        raise ValueError('Wrong prospective qualification/authorization/budget binding')
    if (record.get('source_head') != expected['source_head'] or record.get('binary_sha256') != expected['firmware_sha256']
            or record.get('scenario_sha256') != expected['execution_sha256'] or record.get('scenario_path') != str(execution)
            or not exact(json.loads((run/'job.json').read_text()), job)):
        raise ValueError('Wrong prospective source/binary/scenario/job provenance')
    restored = json.loads((run/'parameter_restore.json').read_text())
    if (restored.get('parameter_restore_exact') is not True or restored.get('remaining_simulators')
            or restored.get('stopped_before_restore') is not True or restored.get('source_head') != record['source_head']
            or restored.get('gate') != job['gate'] or restored.get('job_id') != job['id']
            or restored.get('original_parameter_sha256') != digest(run/'original_parameters.bson')
            or restored.get('restored_parameter_sha256') != restored['original_parameter_sha256']):
        raise ValueError('Missing exact prospective parameter restore/shutdown evidence')
    return expected


def replay_protocol(run, job):
    saved = json.loads((Path(run)/'run_protocol.json').read_text())
    _protocol_identity(saved, job)
    reference = json.loads((Path(run)/'qualification_reference.json').read_text())
    if (Path(reference.get('path','')).resolve() != Path(saved['qualification_path']).resolve()
            or reference.get('sha256') != digest(Path(saved['qualification_path']))):
        raise ValueError('Prospective replay qualification sidecar mismatch')
    return saved


def analyze(run, protocol, job):
    # No writes to legacy data even if a caller invokes this API by mistake.
    _protocol_identity(protocol, job)
    _protocol().require_execution_authority(job['gate'])
    _archive_scope(run, protocol, job)
    namespace = dict(_inherited.analyze.__globals__)
    namespace.update(provenance=provenance, height_evidence=_height)
    function = types.FunctionType(_inherited.analyze.__code__, namespace,
                                  'r03_revision02_analyze', _inherited.analyze.__defaults__,
                                  _inherited.analyze.__closure__)
    function.__kwdefaults__ = _inherited.analyze.__kwdefaults__
    return function(Path(run), protocol, job)


def compare(pid, candidate):
    for item in (pid, candidate):
        validate_job(item['job'])
        binding = item.get('binding', {})
        if (binding.get('revision') != REVISION or binding.get('stage') != 'R03-revision02-'+item['job']['gate']
                or any(not exact(binding.get(k), v) for k,v in _budget().items())):
            raise ValueError('Paired results are not prospective revision02 evidence')
    return _inherited.compare(pid, candidate)


def historical_diagnostic(source, dest, order):
    """Same old run, no new sample: retain diagnostic-only / accepted=false."""
    if order == 'runner-first':
        # Reproduce the NEW real runner's import chain, not just a clean import.
        load_path('r03_revision02_diagnostic_runner', HERE/'runner.py')
    elif order != 'analyzer-first':
        raise ValueError('Unknown historical import order')
    return _repair.run_diagnostic(source, dest, order)


def replay_new(source, dest):
    source, dest = Path(source).resolve(), Path(dest).resolve()
    job = json.loads((source/'job.json').read_text())
    protocol = replay_protocol(source, job)
    _protocol().require_execution_authority(job['gate'])
    _archive_scope(source, protocol, job)
    _repair.copy_sidecars(source, dest)
    return analyze(dest, protocol, job)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--historical-diagnostic', action='store_true')
    parser.add_argument('--import-order', choices=('runner-first','analyzer-first'), default='runner-first')
    args = parser.parse_args()
    if args.historical_diagnostic:
        result = historical_diagnostic(args.run, args.output, args.import_order)
        print(json.dumps({k:v for k,v in result.items() if k not in ('metrics','input_sha256_before',
              'input_sha256_after','source_sha256_before','source_sha256_after')}, indent=2))
        ok = (result.get('diagnostic_checks_complete') is True and result.get('source_inputs_unchanged') is True
              and result.get('historical_acceptance_unchanged') is True and result.get('accepted') is False
              and result.get('flight_accepted') is False)
    else:
        result = replay_new(args.run, args.output)
        print(json.dumps(result, indent=2)); ok = result.get('accepted') is True
    raise SystemExit(0 if ok else 1)
