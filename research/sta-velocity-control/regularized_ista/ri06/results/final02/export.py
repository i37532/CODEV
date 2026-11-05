"""Result-only strict JSON encoding; never alters frozen flight/analyzer code."""
import argparse
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('_ri06_original_package', ROOT / 'final_package.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
p = original.p
MARKER = '__px4_float__'
FIELDS = ('vxy_max', 'vz_max', 'hagl_min', 'hagl_max')
PREFIXES = (('height_task', 'heading', 'latest_position'),
            ('height_task', 'handoff', 'source', 'reference'),
            ('height_task', 'reference', 'position'))
ALLOWED = {prefix + (field,) for prefix in PREFIXES for field in FIELDS}


def permitted(path):
    return len(path) >= 3 and path[0] == 'rows' and type(path[1]) is int and path[2:] in ALLOWED


def encode(value, path=(), changes=None):
    changes = [] if changes is None else changes
    if isinstance(value, float) and not math.isfinite(value):
        if value != math.inf or not permitted(path):
            raise ValueError('Unexpected nonfinite value at ' + repr(path))
        changes.append(list(path))
        return {MARKER: '+Infinity'}
    if isinstance(value, dict):
        if MARKER in value:
            raise ValueError('Preexisting reserved marker')
        return {key: encode(item, path + (key,), changes) for key, item in value.items()}
    if isinstance(value, list):
        return [encode(item, path + (i,), changes) for i, item in enumerate(value)]
    return value


def decode(value, path=()):
    if isinstance(value, dict):
        if MARKER in value:
            if value != {MARKER: '+Infinity'} or not permitted(path):
                raise ValueError('Invalid diagnostic marker')
            return math.inf
        return {key: decode(item, path + (key,)) for key, item in value.items()}
    if isinstance(value, list):
        return [decode(item, path + (i,)) for i, item in enumerate(value)]
    return value


def build():
    raw = original.collect()  # Re-verifies all54 independent replays and archived qualifications.
    changes = []
    result = encode(raw, changes=changes)
    if decode(result) != raw or len(changes) != 54 * 12:
        raise ValueError('Unexpected encoding coverage or non-lossless representation')
    extras = {}
    for row in raw['rows']:
        metrics = p.read(row['metrics_path'])
        extras[row['job']['id']] = dict(task_metrics=metrics['task_metrics'],
            limitations=metrics['limitations'],landing=metrics['landing'],
            postland_tail=metrics['postland_tail'])
    # Extras and every science/config field MUST serialize as finite strict JSON.
    json.dumps(extras, allow_nan=False)
    result['supplemental_metrics'] = extras
    partial = ROOT / 'results/final01/package.partial.log'
    result['export_provenance'] = dict(
        original_export_exit_code=1, original_partial_path=str(partial),
        original_partial_sha256=p.fingerprint(partial), original_partial_bytes=partial.stat().st_size,
        encoding='Only positive infinity in12 exact estimator-limit snapshot paths becomes {__px4_float__: +Infinity}; losslessly reversible; never zero/null imputed.',
        changed_paths=changes, encoded_values=len(changes),
        ekf_source='src/modules/ekf2/EKF2.cpp:841-857',
        ekf_source_sha256=p.fingerprint(p.REPO/'src/modules/ekf2/EKF2.cpp'),
        message_comment_caveat='Message comments say zero; actual frozen EKF publisher explicitly converts nonfinite limits to positive infinity.',
        flight_or_acceptance_changes=False, source_metrics_unchanged=True, new_flights=0)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Fresh output required; no overwrite')
    result = build()
    serialized = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(serialized)
    print(json.dumps(dict(accepted=result['accepted'],attempts=result['attempts'],
        formal_attempts=0, next_budget=200,encoded_diagnostic_values=result['export_provenance']['encoded_values'])))
