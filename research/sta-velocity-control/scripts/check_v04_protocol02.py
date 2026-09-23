#!/usr/bin/env python3
"""Read-only design audit. No flight runner, parameter writes or simulator launch."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / 'research/sta-velocity-control/v04/protocol02'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load():
    protocol = json.loads((CONFIG / 'protocol.json').read_text())
    old_path = REPO / protocol['inherit']['path']
    if sha(old_path) != protocol['inherit']['sha256']:
        raise ValueError('Historical protocol fingerprint changed')
    old = json.loads(old_path.read_text())
    return protocol, {key: old[key] for key in protocol['inherit']['unchanged_fields']}


def target_altitude(ground_z, ref_alt):
    """Pinned FlightTaskAuto conversion z = -(alt - ref_alt), float32 command."""
    import math
    if not all(math.isfinite(x) for x in (ground_z, ref_alt)):
        raise ValueError('Invalid coordinate reference')
    target_z = ground_z - 2.5
    try:
        command_alt = struct.unpack('<f', struct.pack('<f', ref_alt - target_z))[0]
    except OverflowError as exc:
        raise ValueError('Altitude overflow') from exc
    if not math.isfinite(command_alt) or abs(-(command_alt - ref_alt) - target_z) > .02:
        raise ValueError('Unrepresentable target altitude')
    return target_z, command_alt


def seed_audit(seeds):
    """Structured JSON registry audit; doesn't claim every RNG is independently seeded."""
    roots = [REPO / 'research', Path('/home/yr/Desktop/codev doc/experiments'),
             Path('/home/yr/Desktop/codev doc/plan')]
    paths = subprocess.check_output(['rg', '--files', '-g', '*.json', *map(str, roots)], text=True).splitlines()
    matches, invalid, exceptions = [], [], []
    manifest = hashlib.sha256()
    count = 0

    def numbers(value):
        if isinstance(value, int) and not isinstance(value, bool):
            return {value}
        if isinstance(value, str) and value.isdigit():
            return {int(value)}
        if isinstance(value, list):
            return set().union(*(numbers(item) for item in value))
        return set()

    def walk(value, path, field=''):
        if isinstance(value, dict):
            for key, item in value.items():
                found = set(seeds) & numbers(item) if 'seed' in key.lower() else set()
                if found:
                    matches.append(dict(path=path, field=field + key, seeds=sorted(found)))
                walk(item, path, field + key + '.')
        elif isinstance(value, list):
            for i, item in enumerate(value):
                walk(item, path, field + str(i) + '.')

    for name in sorted(paths):
        path = Path(name)
        if CONFIG in path.parents:
            continue  # only this NEW registration; old V04 is deliberately included
        raw = path.read_bytes()
        fingerprint = hashlib.sha256(raw).hexdigest()
        manifest.update((name + '\0' + fingerprint + '\n').encode())
        if name == '/home/yr/Desktop/codev doc/experiments/M06-20260916/c02_regression_roll_diagnostic.json' and raw == b'':
            exceptions.append(dict(path=name, bytes=0, sha256=fingerprint,
                                   reason='Previously audited empty diagnostic, not a seed registry; unchanged'))
            continue
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            invalid.append(name)
            continue
        count += 1
        walk(data, name)
    return dict(seeds=seeds, files_parsed=count, matches=matches, invalid_json=invalid,
                exceptions=exceptions, scan_manifest_sha256=manifest.hexdigest(),
                roots=list(map(str, roots)), excluded=str(CONFIG),
                scope='Structured seed/seed-list keys in JSON, plus separate source text audit; recheck before flight',
                accepted=not matches and not invalid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-seeds', action='store_true')
    args = parser.parse_args()
    p, inherited = load()
    result = dict(stage=p['stage'], execution_ready=p['execution_ready'],
                  flight_authorized=p['flight_authorized'], planned=p['budget']['jobs'],
                  inherited_fields=list(inherited), protocol_sha256=sha(CONFIG / 'protocol.json'))
    if args.audit_seeds:
        result['seed_audit'] = seed_audit(p['budget']['seeds'])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.audit_seeds and not result['seed_audit']['accepted']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
