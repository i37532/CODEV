"""Independent receipt replay. Original prearm byte/boundary audit is additional."""
import hashlib
import json
import math
from pathlib import Path


def replay_rows(rows, samples, monitors):
    # Do not call the online state machine to prove its own output.
    warm = [s for s in samples if s.get('phase') == 'warmup']
    before = [r for r in monitors if r.get('phase') == 'warmup']
    if not rows or len(rows) != len(warm) or len(rows) != len(before):
        raise ValueError('Post-logger warmup receipt/sample count')
    first = previous = None
    for i, (row, sample, monitor) in enumerate(zip(rows, warm, before)):
        now = sample['position'].get('timestamp')
        if (type(now) not in (int, float) or not math.isfinite(now) or not 0 < now < 2**53
                or int(now) != now or (previous is not None and now <= previous)):
            raise ValueError('Post-logger warmup sample clock')
        previous = now
        raw = monitor.get('raw_reader', {})
        reads = monitor.get('warmup_reads')
        if type(reads) is not int or reads < 0 or monitor.get('failure_latched') is not False:
            raise ValueError('Post-logger preparation counter/failure')
        usable = (reads >= 1 and monitor.get('reader_path') is not None
                  and raw.get('completed') is True)
        if first is not None and not usable:
            raise ValueError('Post-logger prepared reader lost')
        if usable and first is None: first = int(now)
        elapsed = None if first is None else int(now)-first
        ready = elapsed is not None and elapsed >= 30000000
        expected = dict(timestamp_us=int(now), first_prepared_sample_us=first, elapsed_us=elapsed,
            minimum_us=30000000, ready=ready, prepared=usable, execution_authority_granted=False,
            warmup_reads=reads, reader_path=monitor.get('reader_path'))
        # JSON strict typing rejects True/1 and int/float substitutions.
        if json.dumps(row, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
            raise ValueError('Post-logger warmup receipt differs from independent clock/read history')
        if ready is not (i == len(rows)-1):
            raise ValueError('Post-logger premature/missing/continued ready')
    return dict(valid=True, first_prepared_sample_us=first, ready_sample_us=int(previous),
                elapsed_us=int(previous)-first, minimum_us=30000000, samples=len(rows))


def check(run):
    run = Path(run)
    names = ('r03_warmup10.jsonl', 'samples.jsonl', 'r03_prearm04_timing.jsonl')
    data = [[json.loads(line) for line in (run/name).read_text().splitlines()] for name in names]
    result = replay_rows(*data)
    result['sha256'] = {name: hashlib.sha256((run/name).read_bytes()).hexdigest() for name in names}
    return result
