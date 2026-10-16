#!/usr/bin/env python3
"""Read-only historical replay and host benchmark; never changes flight verdicts.

Old and new readers see identical recorded file prefixes and run unchanged
complete-history checks. A separate new reader then follows every recorded
landing poll, including repeated offsets, without synthetic-prefix prewarming.
Warm pipeline time <250 ms is offline host headroom, not the live 500 ms age
limit or total online time (CLI, file writing and scheduling are excluded).
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import struct
import time
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
DATA = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): digest.update(block)
    return digest.hexdigest()


def tree(root):
    return {str(p): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def report_value(value):
    """Lossless nonfinite evidence encoding, never used as monitor input."""
    if isinstance(value, float) and not math.isfinite(value):
        return {'__float64_bits__': struct.pack('>d', value).hex()}
    if isinstance(value, dict):
        return {key: report_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [report_value(item) for item in value]
    return value


def same(a, b):
    return json.dumps(report_value(a), sort_keys=True, allow_nan=False) == json.dumps(report_value(b), sort_keys=True, allow_nan=False)


def benchmark_summary(polls):
    if len(polls) < 2:
        raise ValueError('At least two actual recorded polls required')
    warm = [p['timing']['total_s'] for p in polls[1:]]
    if not all(math.isfinite(t) and t >= 0 for t in warm):
        raise ValueError('Invalid benchmark time')
    return dict(warm_polls=len(warm), warm_max_s=max(warm),
                warm_median_s=statistics.median(warm), offline_headroom_pass=max(warm)<.25)


def exact_topics(a, b):
    raw_a, raw_b = a.raw, b.raw
    assert [(x.name, x.multi_id) for x in raw_a.data_list] == [(x.name, x.multi_id) for x in raw_b.data_list]
    count = 0
    for left, right in zip(raw_a.data_list, raw_b.data_list):
        assert set(left.data) == set(right.data)
        for key in left.data:
            x, y = left.data[key], right.data[key]
            assert x.dtype == y.dtype and x.shape == y.shape and x.tobytes() == y.tobytes(), (left.name, key)
            count += len(x)
    return count


class PrefixPath:
    """Test seam exposing a bounded prefix of an existing immutable file."""
    def __init__(self, real):
        self.real, self.limit = real, 0
    def stat(self):
        stat = self.real.stat()
        return SimpleNamespace(st_size=self.limit, st_ino=stat.st_ino, st_dev=stat.st_dev)
    def open(self, mode):
        assert mode == 'rb'
        return self.real.open(mode)


def outcome(function):
    try:
        return dict(kind='result', value=function())
    except (ValueError, KeyError, IndexError) as error:
        return dict(kind='exception', type=type(error).__name__, value=str(error))


def run(output):
    if output.exists(): raise ValueError('Output already exists; do not overwrite evidence')
    output.mkdir(parents=True)
    # Reproduce the historical runner's actual module resolution.
    load('monitor02_original_runner', HERE.parent/'r03_revision01/runner.py')
    import position_live, monitor, landing
    from v04_live_clock09 import sealed_time
    legacy_root = REPO/'research/sta-velocity-control/v08/protocol02'
    assert all(Path(m.__file__).parent == legacy_root for m in (position_live, monitor, landing))
    inc = load('monitor02_decoder_replay', HERE/'incremental.py')
    roots = [DATA/'R03/A/batch01/run001']+[DATA/f'R03_revision01/A/batch01/run{i:03d}' for i in range(1,8)]
    receipt = dict(success=False, new_flights=0, accepted=False, replay_sha256=sha(Path(__file__)),
        historical_acceptance_unchanged=False, decoder_sha256=sha(HERE/'incremental.py'),
        integration_sha256=sha(HERE/'integration.py'), pyulog_sha256=inc.PYULOG_SHA256,
        benchmark_limit_s=.25, benchmark_scope='Independent reader, every recorded landing poll in order; first cold poll excluded from warm maximum. Host decode + complete position/heading/landing checks, excludes CLI/writes/scheduling; not WCET', runs=[])
    try:
        for folder in roots:
            before = tree(folder)
            record = json.loads((folder/'result.json').read_text())
            ref = json.loads((folder/'height_reference.json').read_text())
            frozen = json.loads((folder/'task_yaw.json').read_text())
            context = json.loads((folder/'landing_context.json').read_text())
            # The sidecar wraps the actual context on some historical revisions.
            if 'context' in context: context = context['context']
            flight = folder/'log001.ulg'
            polls = [json.loads(line) for line in (folder/'landing_pending_poll.jsonl').read_text().splitlines()]
            limits = {int(p['raw_offset']) for p in polls if p.get('raw_offset')}
            size = flight.stat().st_size
            limits.update(int(size*fraction) for fraction in (.10, .25, .5, .75, 1.0))
            old, new = position_live.PositionLiveLog(flight), inc.PositionLiveLog(flight)
            seam = PrefixPath(flight); old.path = new.path = seam
            item = dict(directory=str(folder), original_success=record['success'], prefixes=[], logs=[])
            for limit in sorted(limits):
                seam.limit = limit
                timings, logs, checks = {}, {}, {}
                for label, reader in (('old', old), ('new', new)):
                    start = time.monotonic(); log = reader.read(); decoded = time.monotonic()
                    log.get_dataset('vehicle_local_position'); positioned = time.monotonic()
                    stop = sealed_time(log)
                    task_frozen = frozen if frozen['timestamp'] <= stop else None
                    heading = outcome(lambda: monitor.replay(log, ref, frozen=task_frozen, allow_pending=True))
                    headed = time.monotonic()
                    diagnostic_end = int(log.get_dataset('sta_velocity_ctrl_status').data['timestamp'][-1])
                    land = outcome(lambda: landing.replay(log, context, diagnostic_end))
                    ended = time.monotonic()
                    timings[label] = dict(decode_s=decoded-start, position_s=positioned-decoded,
                        heading_s=headed-positioned, landing_s=ended-headed, total_s=ended-start)
                    logs[label], checks[label] = log, dict(heading=heading, landing=land)
                assert old.offset == new.offset
                fields = exact_topics(logs['old'], logs['new'])
                assert same(logs['old'].position_log_evidence, logs['new'].position_log_evidence)
                assert same(checks['old'], checks['new']), (folder, limit, checks)
                item['prefixes'].append(dict(raw_limit=limit, complete_bytes=new.offset,
                    equal_field_values=fields, checks=report_value(checks['new']), timing=timings,
                    incremental_reader=new.last_timing))
            # Exact complete-stream comparison also includes the startup ULog.
            from pyulog import ULog
            for entry in record['logs']:
                path = Path(entry['archive'])
                assert sha(path) == entry['sha256'] and path.stat().st_size == entry['bytes']
                decoder = inc.Decoder()
                with path.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(65537), b''): decoder.feed(chunk)
                old_log = ULog(str(path), message_name_filter_list=inc.TOPICS)
                new_log = decoder.snapshot()
                count = exact_topics(SimpleNamespace(raw=old_log), SimpleNamespace(raw=new_log))
                assert not decoder.pending
                item['logs'].append(dict(path=str(path), sha256=entry['sha256'], equal_field_values=count,
                    topic_instances=len(new_log.data_list), records=decoder.records))
            # Do not count arbitrary 10/25/50/75% catch-up chunks as live polls.
            # A fresh reader follows every original poll, without deduplicating
            # offsets or discarding slow samples; its first catch-up is cold.
            bench = inc.PositionLiveLog(flight)
            bench_path = PrefixPath(flight); bench.path = bench_path
            item['actual_poll_benchmark'] = []
            for poll in polls:
                if not poll.get('raw_offset'):
                    raise ValueError('Missing original poll offset')
                bench_path.limit = int(poll['raw_offset'])
                start = time.monotonic(); log = bench.read(); decoded = time.monotonic()
                log.get_dataset('vehicle_local_position'); positioned = time.monotonic()
                stop = sealed_time(log)
                task_frozen = frozen if frozen['timestamp'] <= stop else None
                heading = outcome(lambda: monitor.replay(log, ref, frozen=task_frozen, allow_pending=True))
                headed = time.monotonic()
                diagnostic_end = int(log.get_dataset('sta_velocity_ctrl_status').data['timestamp'][-1])
                land = outcome(lambda: landing.replay(log, context, diagnostic_end))
                ended = time.monotonic()
                expected = next(p for p in item['prefixes'] if p['raw_limit'] == bench_path.limit)
                assert same(dict(heading=heading, landing=land), expected['checks'])
                item['actual_poll_benchmark'].append(dict(raw_offset=bench_path.limit,
                    timing=dict(decode_s=decoded-start,position_s=positioned-decoded,
                        heading_s=headed-positioned,landing_s=ended-headed,total_s=ended-start),
                    incremental_reader=dict(bench.last_timing)))
            assert before == tree(folder), 'Historical inputs changed'
            item.update(unchanged_files=len(before), **benchmark_summary(item['actual_poll_benchmark']))
            receipt['runs'].append(item)
            print(json.dumps(dict(run=str(folder), prefixes=len(item['prefixes']), warm_polls=item['warm_polls'], warm_max_s=item['warm_max_s'])), flush=True)
        # Recorded old now must not be replaced by a fictitious faster-time now.
        failed = receipt['runs'][-1]
        point = next(p for p in failed['prefixes'] if p['raw_limit'] == 104232694)
        through = point['checks']['heading']['value']['through_us']
        age = 147876000-through
        assert age == 540000 and not 0 <= age <= 500000
        receipt['retained_failure'] = dict(through_us=through, recorded_now_us=147876000,
            age_us=age, accepted=False, reason='Original 500 ms guard still rejects')
        receipt['historical_acceptance_unchanged'] = True
        receipt['success'] = all(x['offline_headroom_pass'] for x in receipt['runs'])
    except Exception as error:
        receipt['error'] = repr(error)
        raise
    finally:
        with (output/'evidence.json').open('x') as stream:
            json.dump(receipt, stream, indent=2, allow_nan=False)
            stream.write('\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    raise SystemExit(0 if result['success'] else 1)
