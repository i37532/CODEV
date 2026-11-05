"""Offline-only event and receiver-representation checks; no tolerance widening."""
import copy
import hashlib
import json
import numbers
from pathlib import Path
import shlex
import numpy as np

REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO/'research/sta-velocity-control/v04/logcheck07'
EVENT_TOPICS = ('vehicle_command', 'vehicle_command_ack')
NUMERIC_FLAGS = ('-O2', '-fno-signed-zeros', '-fno-trapping-math', '-freciprocal-math', '-fno-math-errno')


def event_data(log, name):
    """Keep recorded row order and every event; never sort, deduplicate or interpolate.

    Different command IDs may share a timestamp. Same-ID simultaneous events are
    ambiguous/repeated and rejected. Target command uniqueness is checked separately.
    This accessor is NOT allowed for sampled control/estimator topics.
    """
    if name not in EVENT_TOPICS:
        raise ValueError('Event accessor cannot weaken sampled topic '+name)
    d = log.get_dataset(name).data
    t = np.asarray(d['timestamp']); ids = np.asarray(d['command'])
    if t.ndim != 1 or not len(t) or any(np.asarray(v).shape != t.shape for v in d.values()):
        raise ValueError('Empty/malformed event topic '+name)
    if not np.all(np.isfinite(t)) or np.any(t <= 0) or any(int(v) != v or int(v) >= 2**63 for v in t):
        raise ValueError('Invalid event timestamp '+name)
    if not np.all(np.isfinite(ids)) or any(int(v) != v or not 0 <= v <= 65535 for v in ids):
        raise ValueError('Invalid command ID')
    ts = t.astype(np.int64)
    if np.any(np.diff(ts) < 0):
        raise ValueError('Backward event timestamp '+name)
    seen = set(); last = None
    for stamp, command in zip(ts, ids):
        if stamp != last: seen.clear(); last = stamp
        if int(command) in seen: raise ValueError('Duplicate/ambiguous same-time event '+name)
        seen.add(int(command))
    return d


def validate_receiver_profile():
    """Fail closed on a changed receiver/toolchain; never fit the reference to ULog."""
    p = json.loads((CONFIG/'receiver_profile.json').read_text())
    if hashlib.sha256((REPO/p['source']).read_bytes()).hexdigest() != p['source_sha256']:
        raise ValueError('Receiver source changed; re-audit required')
    database = json.loads((REPO/'build/px4_sitl_default/compile_commands.json').read_text())
    commands = [d for d in database if Path(d['file']).resolve() == (REPO/p['source']).resolve()]
    if len(commands) != 1: raise ValueError('Missing/ambiguous receiver build command')
    if hashlib.sha256(commands[0]['command'].encode()).hexdigest() != p['compile_command_sha256']:
        raise ValueError('Receiver build command changed; re-audit required')
    words = shlex.split(commands[0]['command']); compiler = Path(words[0]).resolve()
    if str(compiler) != p['compiler'] or hashlib.sha256(compiler.read_bytes()).hexdigest() != p['compiler_sha256']:
        raise ValueError('Receiver compiler changed; re-audit required')
    flags = [w for w in words if w.startswith('-O') or w in NUMERIC_FLAGS[1:]]
    forbidden = ('-ffast-math', '-funsafe-math-optimizations', '-fno-reciprocal-math', '-Ofast')
    if flags != list(NUMERIC_FLAGS) or flags != p['numeric_flags'] or any(w in words for w in forbidden):
        raise ValueError('Receiver numerical flags changed; re-audit required')
    if p['scale_hex'] != float(1e-7).hex() or p['operation'] != 'binary64(int32) * binary64(1e-7)':
        raise ValueError('Unsupported receiver mapping')
    return p


def receiver_coordinate(value, axis):
    """Pinned compiled receiver mapping. Not an epsilon/ULP acceptance band."""
    if axis not in ('lat', 'lon'): raise ValueError('Unknown coordinate axis')
    limit = 900000000 if axis == 'lat' else 1800000000
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Integral) or not -limit <= value <= limit:
        raise ValueError('Invalid integer coordinate or ignore sentinel')
    return float(value) * float.fromhex('0x1.ad7f29abcaf48p-24')


def receiver_target(source):
    """Keep original source/projection record intact; derive a separate expected target."""
    out = copy.deepcopy(source)
    out['lat'] = receiver_coordinate(source['wire']['x'], 'lat')
    out['lon'] = receiver_coordinate(source['wire']['y'], 'lon')
    return out
