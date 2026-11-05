#!/usr/bin/env python3
"""Authorized R03 revision05 B/C/D analysis, retaining completed revision04 A.

Only ideal-nu numerical acceptance is versioned through the sealed numeric05
adapter. All raw/applied protection, safety, clocks, landing and paired-risk
checks retain their frozen implementation. AX02 Nx3 height stays privately
bound. Only this revision's explicitly qualified new runs are admissible.
Old R03 logs cannot be accepted by this entry. Their separate
--historical-diagnostic route remains non-authorizing and preserves all files.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sys
import traceback
import types

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
OLD = HERE.parent/'r03'
REVISION = 'r03_revision05'
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
_repair = load_path('r03_revision05_frozen_height_repair', REPAIR)
# For the real CLI regression, load the actual NEW runner before the inherited
# analyzer. Importing the analyzer first and only then invoking a runner is not
# a runner-first test and previously hid the historical path-order collision.
if __name__ == '__main__' and '--historical-diagnostic' in sys.argv[1:]:
    _order_parser = argparse.ArgumentParser(add_help=False)
    _order_parser.add_argument('--import-order', default='runner-first')
    _order_args, _ = _order_parser.parse_known_args()
    if _order_args.import_order == 'runner-first':
        load_path('r03_revision05_cli_bootstrap_runner', HERE/'runner.py')
_inherited = _repair.load_analyzer('analyzer-first')
_height, HEIGHT_BINDING = _repair.bind_height(_inherited)
targets = _inherited._targets
_numeric = load_path('r03_revision05_numeric_adapter', HERE/'numeric_adapter.py')
_numeric_r02, _components, NUMERIC_BINDING = _numeric.bind(_inherited)
PREARM_SOURCE = HERE.parent/'r03_prearm04/integration.py'
PREARM_SHA256 = '161dd6273e37dc625472c389278df12cfd2153d3f459e0da37fc86c0c2453235'
if digest(PREARM_SOURCE) != PREARM_SHA256:
    raise ValueError('Frozen prearm preparation implementation changed')
_prearm = load_path('r03_revision05_prearm', PREARM_SOURCE)
_reference = load_path('r03_revision05_reference', HERE.parents[1]/'scripts/v04_prearm17.py')
_task_reference = load_path('r03_revision05_reference_task', HERE.parents[1]/'scripts/v04_task04.py')
_heading = load_path('r03_revision05_heading', HERE.parents[1]/'scripts/v04_live_clock09.py')
_cli_clock = load_path('r03_revision05_cli_clock', HERE.parents[1]/'v08/protocol02/cli_clock.py')
_position = load_path('r03_revision05_position_view', HERE.parents[1]/'v08/protocol02/position_log.py')


def require(condition, message):
    if not condition:
        raise ValueError('Prearm evidence: '+message)


def json_lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def integer(value):
    return type(value) is int and value >= 0


def host_number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def recorded_equal(left, right):
    # The original raw ground reference legitimately contains +Inf limits.
    # Preserve those bits/fields rather than silently replacing them by null.
    return json.dumps(left, sort_keys=True, separators=(',', ':'), allow_nan=True) == \
        json.dumps(right, sort_keys=True, separators=(',', ':'), allow_nan=True)


def prearm_evidence(run):
    """Verify recorded preparation; no new timing threshold or inferred speedup.

    Prefixes are decoded once, using the frozen append-only parser. Every byte,
    packet, pending tail and owned-reader identity is accounted for. The final
    prefix is then passed to the original reference/complete-history predicates.
    Actual CLI reads are associated to the original command journal by nested
    host intervals, not by equating host time to simulation time. Warmup can
    legitimately have no owned file, an incomplete header, no attitude yet, or
    a listener without its first timestamp. Later landing may read more than
    once per monitor call, so no invented single-read rule is imposed there.
    """
    run = Path(run)
    rows = json_lines(run/_prearm.RECEIPT)
    commands = json_lines(run/'commands.jsonl')
    samples = json_lines(run/'samples.jsonl')
    prearms = [i for i, row in enumerate(rows) if row.get('phase') == 'prearm']
    require(len(prearms) == 1 and prearms[0] > 0, 'one prepared prearm required')
    pi = prearms[0]
    require(all(row.get('phase') == 'warmup' for row in rows[:pi])
            and all(row.get('phase') != 'warmup' for row in rows[pi+1:]), 'phase order')
    require([row.get('phase') for row in rows if row.get('phase') != 'prearm'] ==
            [row.get('phase') for row in samples], 'missing/reordered monitor receipt')
    # This is the original per-read diagnostic publication/host check, not a
    # replacement for ULog chronology or the independent 500 ms prearm bound.
    clock = _cli_clock.audit_commands(run/'commands.jsonl')
    linked = set()
    prearm_commands = []
    previous_end = None
    for i, row in enumerate(rows):
        require(row.get('error') is None and row.get('failure_latched') is False
                and row.get('execution_authority_granted') is False, 'failed/authorizing receipt')
        require(type(row.get('transport_max_age_us')) is int and row['transport_max_age_us'] == 500000,
                'changed original 500 ms bound')
        start, duration = row.get('host_started'), row.get('host_elapsed_s')
        require(host_number(start) and host_number(duration), 'invalid host interval')
        require(previous_end is None or start >= previous_end, 'overlapping monitor calls')
        previous_end = start+duration
        require(isinstance(row.get('segments'), dict) and
                all(host_number(value) for value in row['segments'].values()), 'invalid measured segments')
        require(isinstance(row.get('actual_cli'), list), 'missing actual CLI observations')
        cli_end = start
        for observed in row['actual_cli']:
            began, elapsed = observed.get('started_monotonic'), observed.get('host_elapsed_s')
            require(observed.get('error') is None and host_number(began) and host_number(elapsed),
                    'failed/invalid observed CLI')
            require(began >= cli_end and began+elapsed <= start+duration, 'CLI not inside actual monitor')
            cli_end = began+elapsed
            matches = []
            for index, command in enumerate(commands):
                cmd = command.get('cmd', [])
                if (len(cmd) == 4 and Path(cmd[0]).name == 'px4-listener'
                        and cmd[1:] == [observed.get('topic'), '-n', '1']
                        and began <= command['host_start_ns']/1e9
                        and command['host_end_ns']/1e9 <= began+elapsed):
                    matches.append((index, command))
            require(len(matches) == 1 and matches[0][0] not in linked, 'missing/ambiguous/reused CLI command')
            index, command = matches[0]; linked.add(index)
            require(command.get('returncode') == 0, 'unsuccessful observed command')
            parsed = _task_reference.scalars(command['stdout'])
            require(recorded_equal(observed.get('timestamp_us'), parsed.get('timestamp'))
                    and recorded_equal(observed.get('receipt'), command.get('clock')),
                    'CLI receipt differs from original output/clock')
            if i == pi:
                prearm_commands.append((observed['topic'], parsed))
    require([name for name, _ in prearm_commands] == ['vehicle_status', 'vehicle_local_position'],
            'original prearm CLI order')
    require(prearm_commands[0][1].get('arming_state') == 1, 'reference was not disarmed')

    live = json.loads((run/'live_log.json').read_text())
    result = json.loads((run/'result.json').read_text())
    archives = [entry for entry in result.get('logs', []) if entry.get('source') == live.get('path')]
    require(len(archives) == 1, 'unique owned main ULog archive')
    archive = Path(archives[0]['archive'])
    require(archive.stat().st_size == archives[0].get('bytes') and digest(archive) == archives[0].get('sha256'),
            'owned ULog archive fingerprint')
    require(type(live.get('transport_max_age_us')) is int and live['transport_max_age_us'] == 500000,
            'live bound changed')
    decoder = _prearm.incremental.Decoder()
    offset, completed, identity, prefix_reads = 0, 0, None, 0
    with archive.open('rb') as stream:
        for i, row in enumerate(rows[:pi+1]):
            raw = row.get('raw_reader')
            require(isinstance(raw, dict) and type(row.get('read_attempted')) is bool, 'raw reader receipt')
            if not row['read_attempted']:
                require(i < pi and identity is None and row.get('preparation_pending') == 'owned_file_not_created'
                        and raw == {} and row.get('reader_path') is None and row.get('reader_inode') is None
                        and row.get('reader_device') is None and row.get('warmup_reads') == 0,
                        'missing warmup consumption')
                continue
            current = (row.get('reader_path'), row.get('reader_inode'), row.get('reader_device'))
            require(current[0] == live['path'] and integer(current[1]) and integer(current[2])
                    and current[1] == live.get('inode'), 'owned reader identity')
            if identity is None: identity = current
            require(current == identity, 'reader identity changed')
            end = raw.get('snapshot_end_bytes')
            require(integer(end) and offset <= end <= archive.stat().st_size, 'prefix boundary/truncation')
            before = decoder.records
            chunk = stream.read(end-offset)
            decoder.feed(chunk)
            expected = dict(new_bytes=end-offset, new_records=decoder.records-before,
                raw_bytes=end, received_bytes=decoder.received_bytes,
                raw_offset=decoder.complete_bytes, complete_bytes=decoder.complete_bytes,
                pending_bytes=len(decoder.pending), total_records=decoder.records)
            require(all(integer(raw.get(k)) and raw[k] == value for k, value in expected.items()),
                    'incremental byte/record/history accounting')
            require(raw.get('error') is None and raw.get('completed') is bool(decoder.header), 'decoder completion/error')
            require(all(host_number(raw.get(k)) for k in ('read_s','decode_s','snapshot_s','host_elapsed_s')),
                    'invalid decoder timing')
            offset = end; prefix_reads += 1
            if decoder.header:
                decoder.snapshot()  # Original framing/subscription/format validation.
                if i < pi: completed += 1
            else:
                require(i < pi and row.get('preparation_pending') == 'incomplete_first_header'
                        and raw.get('preparation_pending') == 'incomplete_first_header', 'incomplete prearm header')
            require(integer(row.get('warmup_reads')) and row['warmup_reads'] == completed,
                    'completed warmup count/history reset')
    require(completed > 0 and rows[pi]['read_attempted'] is True, 'cold prearm forbidden')
    for row in rows[pi+1:]:
        require((row.get('reader_path'), row.get('reader_inode'), row.get('reader_device')) == identity
                and row.get('warmup_reads') == completed, 'post-prearm reader/state identity changed')
        require(type(row.get('read_attempted')) is bool and isinstance(row.get('raw_reader'), dict),
                'post-prearm reader receipt')
        if row['read_attempted']:
            require(row['raw_reader'].get('error') is None and row['raw_reader'].get('completed') is True,
                    'post-prearm reader failure')
    log = _position.PositionLogView(decoder.snapshot())
    p = _reference.reference_row(log)
    reference = _task_reference.freeze_reference(p)
    history = _heading.replay(log, reference)
    require(recorded_equal(reference, json.loads((run/'height_reference.json').read_text())),
            'saved reference differs from actual prefix')
    require(recorded_equal(log.position_log_evidence, live.get('position_evidence')), 'position mirror evidence')
    prearm = rows[pi]
    require(prearm.get('reference_timestamp_us') == p['timestamp']
            and prearm.get('sealed_watermark_us') == history['through_us'], 'reference/watermark mismatch')
    require(set(prearm['segments']) == {'reference_s','history_replay_s'}, 'missing original full prearm checks')
    now = prearm_commands[1][1].get('timestamp')
    require(host_number(now) and 0 <= now-p['timestamp'] <= 500000, 'original stale/future prearm ULog')
    takeoff = [c for c in commands if len(c.get('cmd', [])) >= 2 and
               Path(c['cmd'][0]).name == 'px4-commander' and c['cmd'][1] == 'takeoff']
    require(len(takeoff) == 1 and takeoff[0]['returncode'] == 0 and
            takeoff[0]['host_start_ns']/1e9 >= prearm['host_started']+prearm['host_elapsed_s'],
            'takeoff before completed prepared prearm')
    return dict(valid=True, preparation_source_sha256=PREARM_SHA256, receipt_sha256=digest(run/_prearm.RECEIPT),
                command_sha256=digest(run/'commands.jsonl'), samples_sha256=digest(run/'samples.jsonl'),
                archive_sha256=digest(archive), receipts=len(rows), warmup_completed_reads=completed,
                prefix_reads=prefix_reads, prearm_prefix_bytes=offset,
                reference_timestamp_us=p['timestamp'], sealed_watermark_us=history['through_us'],
                actual_position_cli_timestamp_us=now, transport_age_us=now-p['timestamp'],
                transport_max_age_us=500000, original_clock_audit=clock,
                semantics='Recorded persistent warmup and one source-bound prearm tail; original full predicates unchanged')


def _protocol():
    return load_path('r03_revision05_analyzer_protocol', HERE/'protocol.py')


def validate_job(job):
    if job.get('revision') != REVISION or job.get('gate') not in ('B','C','D'):
        raise ValueError('Only prospective r03_revision05 jobs are admissible')
    return _inherited.validate_job(job)


def _budget():
    return dict(maximum_attempts=9, new_matrix_attempts=27,
                historical_attempts=30, total_maximum_attempts=57)


def exact(left, right):
    """A bool or float cannot impersonate an integer in frozen provenance."""
    return json.dumps(left,sort_keys=True,separators=(',',':'),allow_nan=False) == \
        json.dumps(right,sort_keys=True,separators=(',',':'),allow_nan=False)


def _protocol_identity(protocol, job):
    validate_job(job)
    if (protocol.get('revision') != REVISION or protocol.get('stage') != 'R03-revision05-'+job['gate']
            or protocol.get('gate') != job['gate']
            or any(type(protocol.get(k)) is not int or protocol[k] != v for k,v in _budget().items())):
        raise ValueError('Wrong revision/stage/gate or explicit 9/27/30/57 budget')
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
                    qualification_sha256=digest(qp), historical_budget=_protocol().retained_failure(),
                    retained_a=_protocol().retained_a(),
                    seed_migration=_protocol().seed_migration(),
                    authorization_sha256=digest(_protocol().AUTHORIZATION),
                    execution_authorized=True,flight_authorized=True,execution_ready=True, **_budget())
    for key in ('execution_sha256', 'frozen_sha256', 'historical_budget', 'retained_a', 'seed_migration',
                'execution_authorized','flight_authorized','execution_ready', *_budget()):
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
    preparation = {}
    def checked_provenance(run, p, j):
        binding = provenance(run, p, j)
        preparation.update(prearm_evidence(run))
        return binding
    namespace = dict(_inherited.analyze.__globals__)
    namespace.update(provenance=checked_provenance, height_evidence=_height,
                     check_components=_components, r02=_numeric_r02)
    function = types.FunctionType(_inherited.analyze.__code__, namespace,
                                  'r03_revision05_analyze', _inherited.analyze.__defaults__,
                                  _inherited.analyze.__closure__)
    function.__kwdefaults__ = _inherited.analyze.__kwdefaults__
    result = function(Path(run), protocol, job)
    result['prearm_preparation'] = preparation or {'valid': False, 'reason': 'preparation not validated'}
    result['candidate_numeric_binding'] = NUMERIC_BINDING
    _inherited.save(Path(run)/'r03_metrics.json', result)
    return result


def compare(pid, candidate):
    for item in (pid, candidate):
        if item.get('prearm_preparation', {}).get('valid') is not True:
            raise ValueError('Paired result lacks validated prearm preparation')
        validate_job(item['job'])
        binding = item.get('binding', {})
        if (binding.get('revision') != REVISION or binding.get('stage') != 'R03-revision05-'+item['job']['gate']
                or any(not exact(binding.get(k), v) for k,v in _budget().items())):
            raise ValueError('Paired results are not prospective revision05 evidence')
        if not exact(binding.get('seed_migration'),_protocol().seed_migration()):
            raise ValueError('Paired seed migration binding changed')
        if not exact(binding.get('retained_a'),_protocol().retained_a()):
            raise ValueError('Paired retained A evidence changed')
        if not exact(item.get('candidate_numeric_binding'),NUMERIC_BINDING):
            raise ValueError('Paired numerical component binding changed')
    return _inherited.compare(pid, candidate)


def historical_diagnostic(source, dest, order):
    """Read-only old-run diagnostics, never a new qualification or rejudgment.

Original R03 import-repair evidence retains its old diagnostic route. For
revision04, use its ORIGINAL provenance/prearm checks and the new scientific
numeric component in private globals. Both accepted and failed old runs keep
their original files/verdicts; every output here has accepted=false.
Copied historical authorization sidecars are provenance, not new permission.
"""
    source, dest = Path(source).resolve(), Path(dest).resolve()
    if order == 'runner-first':
        # Reproduce the NEW real runner's import chain, not just a clean import.
        load_path('r03_revision05_diagnostic_runner', HERE/'runner.py')
    elif order != 'analyzer-first':
        raise ValueError('Unknown historical import order')
    job = json.loads((source/'job.json').read_text())
    if job.get('revision') != 'r03_revision04':
        result = _repair.run_diagnostic(source, dest, order)
        result.update(prearm04_receipt_applicable=False, new_prearm_acceptance=False)
        return result
    original_source = HERE.parent/'r03_revision04/analyzer.py'
    if digest(original_source) != 'a9e6ecd071859782d883a0301d4db27259d66882e9eba9fbba09d5a99c407f82':
        raise ValueError('Frozen revision04 analysis changed')
    original = load_path('r03_revision05_historical_revision04', original_source)
    protocol = original.replay_protocol(source, job)
    original.provenance(source, protocol, job)  # Preserve original source/restore/authority binding.
    before = _repair.snapshot(source)
    old = json.loads((source/'r03_metrics.json').read_text())
    code_paths = {*_numeric.PINS, *_repair.PINS, REPAIR, PREARM_SOURCE,
                  Path(__file__).resolve(), HERE/'numeric_adapter.py', original_source}
    code_before = {str(path):digest(path) for path in sorted(code_paths)}
    result = dict(diagnostic_only=True, accepted=False, flight_accepted=False, new_flights=0,
                  execution_authority_granted=False, historical_acceptance_unchanged=True,
                  source_directory=str(source), output_directory=str(dest), import_order=order,
                  original_accepted=old.get('accepted'), original_error=old.get('error'),
                  prearm04_receipt_applicable=True, new_prearm_acceptance=False,
                  input_sha256_before=before, source_sha256_before=code_before)
    dest = _repair.copy_sidecars(source, dest)
    try:
        preparation = {}
        def old_provenance(run, p, j):
            binding = original.provenance(run, p, j)
            preparation.update(original.prearm_evidence(run))
            return binding
        def diagnostic_save(path, value):
            _inherited.save(path, _repair.diagnostic_payload(value)
                            if Path(path).name == 'r03_metrics.json' else value)
        function = _numeric.clone(_inherited.analyze, provenance=old_provenance,
          height_evidence=_height, check_components=_components, r02=_numeric_r02, save=diagnostic_save)
        raw = function(dest, protocol, job)
        metrics = _repair.diagnostic_payload(raw)
        metrics['prearm_preparation'] = preparation or {'valid':False,'reason':'preparation not validated'}
        metrics['candidate_numeric_binding'] = NUMERIC_BINDING
        _inherited.save(dest/'r03_metrics.json', metrics)  # Already non-authorizing; do not rewrap twice.
        result.update(metrics=metrics, diagnostic_checks_complete=raw.get('accepted') is True,
                      candidate_numeric_binding=NUMERIC_BINDING)
    except Exception as error:
        result.update(diagnostic_checks_complete=False,error=str(error),traceback=traceback.format_exc())
    finally:
        result['input_sha256_after'] = _repair.snapshot(source)
        result['source_sha256_after'] = {str(path):digest(path) for path in sorted(code_paths)}
        result['source_inputs_unchanged'] = (before == result['input_sha256_after']
                                              and code_before == result['source_sha256_after'])
        result['historical_acceptance_unchanged'] = json.loads((source/'r03_metrics.json').read_text()) == old
        _inherited.save(dest/'diagnostic_summary.json', result)
    return result


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
