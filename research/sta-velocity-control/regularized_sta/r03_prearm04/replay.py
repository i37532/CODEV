#!/usr/bin/env python3
"""Offline prearm preparation replay; no flight or historical reclassification.

Method frozen before execution:
* All 15 original main ULogs are scanned once in physical record order. Each
  of the 435 recorded warmup position times selects the end of the last
  vehicle_local_position_log message at/before that time. These are SYNTHETIC
  growing prefixes, NOT the unrecorded historical writer/read byte cutoffs.
  Readers receive every original byte from zero through that boundary: no
  topic-wise file reconstruction, sorting, deduplication or invented samples.
* At every warmup prefix, plus duplicate/partial-header/partial-body/completed
  tail probes and final EOF, compare the new reader with frozen monitor02's
  incremental reader: all selected raw field bits, complete position mirror,
  original reference_row and sealed_time, or the same rejection type/text.
* Exactly three fixed points per log (first warmup, last warmup, EOF) also
  compare the earlier full-pyulog reader independently: 45 cold parses, not
  435 independent full parses. All 15 complete archived logs must agree.
* Retain all 14 saved original prearm ages and the failed run007 unknown age.
  Neither final archives nor this synthetic growth schedule can reconstruct
  its missing online read cutoff/reference/watermark or reverse its failure.
* Report cold/warm/final host timing separately, with no new timing pass
  threshold. This is byte/behavioral equivalence, not online latency, WCET,
  transport availability or flight acceptance. Inputs are SHA checked before
  and after; outputs are new and fail closed on attempted overwrite.
"""
import argparse
import bisect
import hashlib
import importlib.util
import json
import mmap
from pathlib import Path
import re
import statistics
import struct
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
DATA = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016')
RUNS = [DATA/'R03/A/batch01/run001'] + [DATA/f'R03_revision01/A/batch01/run{i:03d}' for i in range(1, 8)] + [DATA/f'R03_revision03/A/batch01/run{i:03d}' for i in range(1, 8)]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


utils = load('prearm04_replay_frozen_utilities', HERE.parent/'r03_monitor02/replay.py')


def scan_anchors(path):
    """Framing-only one-pass index; decode only the checked anchor timestamp.

    The existing decoder still performs full record validation independently.
    A minimal schema check prevents assuming timestamp is first for any topic.
    """
    times, ends, records, formats, subscriptions = [], [], [], {}, {}
    with Path(path).open('rb') as stream:
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as raw:
            if len(raw) < 16 or raw[:7] != b'ULog\x01\x12\x35' or raw[7] not in (0, 1):
                raise ValueError('Unsupported ULog framing header')
            offset = 16
            while offset < len(raw):
                if offset+3 > len(raw):
                    raise ValueError('Incomplete archived record header')
                size, kind = struct.unpack_from('<HB', raw, offset)
                end = offset+3+size
                if not 0 < size <= 10000 or end > len(raw):
                    raise ValueError('Incomplete/invalid archived record body')
                body = offset+3
                if kind == ord('F'):
                    name, schema = raw[body:end].decode().split(':', 1)
                    if name in formats:
                        raise ValueError('Repeated format')
                    formats[name] = schema
                elif kind == ord('A'):
                    if size < 4:
                        raise ValueError('Malformed subscription')
                    multi, ident = struct.unpack_from('<BH', raw, body)
                    name = raw[body+3:end].decode()
                    if ident in subscriptions or name not in formats:
                        raise ValueError('Invalid subscription identity/schema')
                    subscriptions[ident] = (name, multi)
                    if name == 'vehicle_local_position_log' and formats[name].split(';')[0] != 'uint64_t timestamp':
                        raise ValueError('Anchor timestamp is not the first uint64 field')
                elif kind == ord('D'):
                    if size < 2:
                        raise ValueError('Malformed data record')
                    ident = struct.unpack_from('<H', raw, body)[0]
                    if ident not in subscriptions:
                        raise ValueError('Unknown data subscription')
                    if subscriptions[ident] == ('vehicle_local_position_log', 0):
                        if size < 10:
                            raise ValueError('Short anchor timestamp')
                        stamp = struct.unpack_from('<Q', raw, body+2)[0]
                        if times and stamp <= times[-1]:
                            raise ValueError('Anchor publication is not strictly increasing')
                        times.append(stamp); ends.append(end)
                records.append((offset, end))
                offset = end
            total = len(raw)
    if not times:
        raise ValueError('No position-log timestamp anchors')
    return dict(times=times, ends=ends, records=records, bytes=total)


def select_limits(index, stamps):
    if not stamps or any(b < a for a, b in zip(stamps, stamps[1:])):
        raise ValueError('Warmup times missing/decreasing')
    result = []
    for stamp in stamps:
        i = bisect.bisect_right(index['times'], stamp)-1
        if i < 0:
            raise ValueError('No causal anchor for recorded warmup time')
        result.append(dict(raw_limit=index['ends'][i], anchor_us=index['times'][i], requested_warmup_us=stamp))
    return result


def boundary_probes(index, limit):
    starts = [row[0] for row in index['records']]
    i = bisect.bisect_left(starts, limit)
    if i == len(starts) or starts[i] != limit:
        raise ValueError('Warmup limit is not a complete physical boundary')
    end = index['records'][i][1]
    if end <= limit+3:
        raise ValueError('Tail probe record has no body')
    return [('repeat', limit), ('partial_header', limit+1), ('partial_body', end-1), ('complete_tail_record', end)]


def cli_field(row, name):
    match = re.search(r'^\s*'+re.escape(name)+r':\s+(\d+)', row['stdout'], re.M)
    if not match:
        raise ValueError('Missing original CLI '+name)
    return int(match[1])


def historical_prearm(folder):
    rows = [json.loads(line) for line in (folder/'commands.jsonl').read_text().splitlines()]
    takeoffs = [i for i, row in enumerate(rows) if 'takeoff' in row['cmd']]
    stop = takeoffs[0] if takeoffs else len(rows)
    i = max(i for i, row in enumerate(rows[:stop]) if row['cmd'][1:] == ['vehicle_local_position', '-n', '1'])
    if rows[i-1]['cmd'][1:] != ['vehicle_status', '-n', '1']:
        raise ValueError('Original prearm CLI ordering changed')
    current = cli_field(rows[i], 'timestamp')
    ref = folder/'height_reference.json'
    if ref.exists():
        stamp = json.loads(ref.read_text())['position']['timestamp']
        age = current-stamp
        if not 0 <= age <= 500000:
            raise ValueError('Saved original prearm reference did not pass unchanged rule')
    else:
        stamp = age = None
    return dict(original_cli_us=current, original_saved_reference_us=stamp,
                original_age_us=age, original_exact_writer_cutoff_bytes=None,
                unknown_cutoff_not_inferred=True)


def compare_views(a, b, reference_row, sealed_time):
    count = utils.exact_topics(a, b)
    def validate(log):
        pos = log.get_dataset('vehicle_local_position').data
        # Include full mirror field bytes rather than just last row/counters.
        mirror = {k: dict(dtype=str(v.dtype), shape=list(v.shape), sha256=hashlib.sha256(v.tobytes()).hexdigest()) for k, v in pos.items()}
        return dict(mirror=mirror, evidence=log.position_log_evidence)
    checks = {}
    for name, function in [('position', validate), ('reference', reference_row), ('sealed', sealed_time)]:
        left, right = utils.outcome(lambda: function(a)), utils.outcome(lambda: function(b))
        if not utils.same(left, right):
            raise AssertionError('Different complete-history '+name+' result/rejection')
        checks[name] = utils.report_value(right)
    return dict(equal_field_values=count, checks=checks)


def summary(values):
    return dict(n=len(values), min_s=min(values), median_s=statistics.median(values), max_s=max(values)) if values else dict(n=0)


def run(output):
    if output.exists():
        raise ValueError('Refuse overwrite of replay evidence')
    output.mkdir(parents=True)
    load('prearm04_replay_runner_binding', HERE.parent/'r03_revision03/runner.py')
    import position_live
    from v04_prearm17 import reference_row
    from v04_live_clock09 import sealed_time
    if Path(position_live.__file__).resolve() != REPO/'research/sta-velocity-control/v08/protocol02/position_live.py':
        raise ValueError('Unexpected frozen independent reader')
    integration = load('prearm04_replay_owned_reader', HERE/'integration.py')
    inc = integration.incremental
    inputs = {str(path): utils.sha(path) for folder in RUNS for path in folder.rglob('*') if path.is_file()}
    for path in [Path(__file__), HERE/'integration.py', HERE.parent/'r03_monitor02/incremental.py', HERE.parent/'r03_monitor02/replay.py', Path(position_live.__file__)]:
        inputs[str(path)] = utils.sha(path)
    evidence = dict(success=False, new_flights=0, flight_accepted=False,
                    historical_acceptance_unchanged=False, synthetic_growth_not_original_writer=True,
                    method=__doc__, inputs_sha256_before=inputs, runs=[])
    try:
        for folder in RUNS:
            result = json.loads((folder/'result.json').read_text())
            main = next(x for x in result['logs'] if Path(x['archive']).name == 'log001.ulg')
            path = folder/'log001.ulg'
            if utils.sha(path) != main['sha256'] or path.stat().st_size != main['bytes']:
                raise ValueError('Main archive fingerprint changed')
            samples = [json.loads(line) for line in (folder/'samples.jsonl').read_text().splitlines()]
            stamps = [int(s['position']['timestamp']) for s in samples if s['phase'] == 'warmup']
            if len(stamps) != 29:
                raise ValueError('Unexpected historical warmup budget')
            scan_begin = time.monotonic(); index = scan_anchors(path); scan_s = time.monotonic()-scan_begin
            limits = select_limits(index, stamps)
            calls = [('warmup', row['raw_limit'], row) for row in limits]
            calls += [(name, limit, {}) for name, limit in boundary_probes(index, limits[-1]['raw_limit'])]
            calls += [('final_archive', index['bytes'], {})]
            seam = utils.PrefixPath(path)
            old, new = inc.PositionLiveLog(path), integration.OwnedWarmReader(path)
            old.path = new.path = seam
            item = dict(folder=str(folder), source_head=result['source_head'], original_success=result['success'],
                        original_error=result.get('error'), main_archive=main,
                        original_prearm=historical_prearm(folder), scanner_seconds=scan_s,
                        anchor_count=len(index['times']), record_count=len(index['records']),
                        all_prefixes_synthetic=True, prefixes=[], independent_cold_checks=[])
            evidence['runs'].append(item)
            for number, (label, limit, anchor) in enumerate(calls):
                seam.limit = limit
                begin = time.monotonic(); left = old.read(); old_s = time.monotonic()-begin
                begin = time.monotonic(); right = new.consume(allow_incomplete=True); new_s = time.monotonic()-begin
                if right is None:
                    raise ValueError('Historical warmup prefix unexpectedly lacks header')
                begin = time.monotonic(); compared = compare_views(left, right, reference_row, sealed_time)
                validation_s = time.monotonic()-begin
                if old.offset != new.offset or new.last_size != limit or new.decoder.received_bytes != limit:
                    raise AssertionError('Incremental offsets differ')
                row = dict(kind=label, raw_limit=limit, complete_bytes=new.offset,
                           pending_bytes=len(new.decoder.pending), anchor=anchor,
                           old_read_s=old_s, new_read_s=new_s, validation_s=validation_s,
                           new_reader_timing=dict(new.last_timing), **compared)
                item['prefixes'].append(row)
                if number in (0, len(limits)-1, len(calls)-1):
                    cold = position_live.PositionLiveLog(path); cold.path = seam
                    begin = time.monotonic(); independent = cold.read(); cold_s = time.monotonic()-begin
                    check = compare_views(independent, right, reference_row, sealed_time)
                    if cold.offset != new.offset:
                        raise AssertionError('Independent complete record boundary differs')
                    item['independent_cold_checks'].append(dict(prefix_index=number, kind=label,
                        raw_limit=limit, cold_parse_s=cold_s, **check))
            if new.decoder.pending or new.offset != index['bytes']:
                raise AssertionError('Final archive incomplete')
            warm = [row for row in item['prefixes'] if row['kind'] == 'warmup']
            item['timing'] = dict(first_warmup_cold_s=warm[0]['new_read_s'],
                remaining_28_warmup_reads=summary([row['new_read_s'] for row in warm[1:]]),
                final_large_archive_catchup_s=item['prefixes'][-1]['new_read_s'],
                independent_full_parse=summary([row['cold_parse_s'] for row in item['independent_cold_checks']]),
                online_latency_acceptance_claimed=False)
            print(json.dumps(dict(run=str(folder), warmup_prefixes=len(warm),
                independent_cold_checks=len(item['independent_cold_checks']),
                original_age_us=item['original_prearm']['original_age_us'], timing=item['timing'])), flush=True)
        known = [r['original_prearm']['original_age_us'] for r in evidence['runs'] if r['original_prearm']['original_age_us'] is not None]
        if len(known) != 14 or evidence['runs'][-1]['original_prearm']['original_age_us'] is not None:
            raise AssertionError('Historical known/unknown age coverage changed')
        evidence.update(success=True, historical_acceptance_unchanged=True,
            totals=dict(logs=15, warmup_prefixes=435,
                all_incremental_prefixes=sum(len(r['prefixes']) for r in evidence['runs']),
                independent_cold_checks=45, final_archives_equal=15,
                saved_original_ages=14, unknown_original_ages=1),
            retained_last_failure=dict(error="RuntimeError('Stale prearm ULog')", accepted=False,
                exact_online_age_us=None, exact_online_cutoff_bytes=None,
                final_archive_must_not_replace_missing_prefix=True))
    except BaseException as exc:
        evidence['error'] = repr(exc)
        raise
    finally:
        after = {path: utils.sha(Path(path)) for path in inputs}
        evidence['inputs_sha256_after'] = after
        evidence['inputs_unchanged'] = after == inputs
        evidence['success'] = evidence['success'] and evidence['inputs_unchanged']
        with (output/'evidence.json').open('x') as stream:
            json.dump(evidence, stream, indent=2, allow_nan=False); stream.write('\n')
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps(dict(success=result['success'], totals=result.get('totals'), inputs_unchanged=result['inputs_unchanged'], new_flights=0)), flush=True)
    raise SystemExit(0 if result['success'] else 1)
