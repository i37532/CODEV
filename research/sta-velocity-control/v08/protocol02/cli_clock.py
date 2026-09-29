"""Per-read publication freshness and separate host receipt bound; no ULog edits."""
import json
import re

TOPICS = {'vehicle_local_position', 'vehicle_attitude', 'sta_rate_ctrl_status', 'sta_velocity_ctrl_status'}
MAX_AGE_US = 1000000
MAX_HOST_NS = 1000000000


def receipt(module, arguments, raw, start_ns, end_ns):
    if module != 'listener' or not arguments or arguments[0] not in TOPICS:
        return None
    if list(arguments[1:]) != ['-n', '1']:
        raise ValueError('Clock guard requires one listener message')
    if not all(isinstance(x, int) and x >= 0 for x in (start_ns, end_ns)) or end_ns < start_ns:
        raise ValueError('Invalid host clock')
    elapsed = end_ns - start_ns
    if elapsed > MAX_HOST_NS:
        raise ValueError('CLI host receipt exceeds one second')
    fields = re.findall(r'^\s*timestamp:.*$', raw, re.M)
    if not fields:  # Original warmup no-publication handling remains in monitor.
        return None
    rows = re.findall(r'^\s*timestamp: ([0-9]+)\s+\(([0-9]+)\.([0-9]{6}) seconds ago\)\s*$', raw, re.M)
    if len(rows) != 1 or len(fields) != 1 or raw.count('TOPIC: ') != 1 or 'TOPIC: '+arguments[0]+'\n' not in raw:
        raise ValueError('Ambiguous/malformed listener clock')
    timestamp, seconds, microseconds = map(int, rows[0])
    age = seconds*1000000 + microseconds
    if timestamp <= 0 or age > MAX_AGE_US:
        raise ValueError('Stale/future diagnostic publication')
    return dict(topic=arguments[0], timestamp_us=timestamp, age_at_print_us=age,
                host_start_ns=start_ns, host_end_ns=end_ns, host_elapsed_ns=elapsed,
                semantics='print-time simulation age and independent host receipt duration; not cross-topic subtraction')


def require_fresh(data):
    r = data.get('_clock')
    if not isinstance(r, dict) or r.get('timestamp_us') != data.get('timestamp'):
        raise RuntimeError('Missing/exchanged diagnostic clock receipt')
    if (not isinstance(r.get('age_at_print_us'), int) or not 0 <= r['age_at_print_us'] <= MAX_AGE_US
            or not isinstance(r.get('host_elapsed_ns'), int) or not 0 <= r['host_elapsed_ns'] <= MAX_HOST_NS
            or r.get('host_end_ns', -1)-r.get('host_start_ns', 0) != r['host_elapsed_ns']):
        raise RuntimeError('Invalid diagnostic freshness/receipt')


def audit_commands(path):
    counts = {name: 0 for name in TOPICS}
    max_age = 0; max_host = 0
    previous_end = None
    for line in path.read_text().splitlines():
        record = json.loads(line)
        start, end = record['host_start_ns'], record['host_end_ns']
        if (not isinstance(start, int) or not isinstance(end, int) or end < start
                or (previous_end is not None and start < previous_end)
                or record['host_elapsed_ns'] != end-start or 'clock_error' in record):
            raise ValueError('Invalid command host chronology')
        previous_end = end
        module = record['cmd'][0].rsplit('/',1)[-1].removeprefix('px4-')
        r = receipt(module, record['cmd'][1:], record['stdout'], start, end) if record['returncode']==0 else None
        if record.get('clock') != r: raise ValueError('Receipt does not match original CLI output')
        if r is not None:
            counts[r['topic']] += 1
            max_age=max(max_age,r['age_at_print_us']);max_host=max(max_host,r['host_elapsed_ns'])
    if not all(counts.values()): raise ValueError('Missing required live receipt coverage')
    return dict(counts=counts,max_print_age_us=max_age,max_receipt_host_ns=max_host,
                raw_time_rules_unchanged=True)
