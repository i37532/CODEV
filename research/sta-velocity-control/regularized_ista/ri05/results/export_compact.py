#!/usr/bin/env python3
"""Export a small repository receipt, retaining full external evidence hashes."""
import argparse
import hashlib
import json
from pathlib import Path


def reference(path):
    raw = path.read_bytes()
    return dict(path=str(path.resolve()), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    source, dest = args.source.resolve(), args.destination.resolve()
    if dest.exists() or source == dest or dest in source.parents or source in dest.parents:
        raise ValueError('A separate NEW destination is required')
    full = json.loads((source/'summary.json').read_text())
    keys = ('stage', 'milestone_gate', 'gate', 'source_head', 'firmware_sha256', 'status',
            'gate_passed', 'collection_ok', 'counts', 'groups', 'rista_vs_rsta_descriptive_pairs',
            'independent_numeric_pairs', 'parameter_restore_exact', 'remaining_simulators',
            'gate_receipt', 'prior_gate_receipt', 'issues', 'notes')
    compact = {k: full[k] for k in keys}
    compact['runs'] = [{k: v for k, v in row.items() if k not in ('result', 'metrics', 'parameter_restore')}
                       for row in full['runs']]
    qualification = full.get('qualification') or {}
    compact['qualification'] = {k: qualification.get(k) for k in
        ('stage', 'source_head', 'firmware_sha256', 'success', 'clean', 'approved', 'counts',
         'commands', 'model', 'sequence_properties', 'generated_schema', 'not_executed')}
    compact['external_evidence'] = {name: reference(source/name) for name in
        ('summary.json', 'evidence_index.json', 'ulog_index.json', 'SUMMARY_CN.md')}
    compact['exporter'] = reference(Path(__file__))
    compact['scope'] = 'Lossless selection of report fields; full originals remain externally indexed. No acceptance changes or flights.'
    dest.mkdir(parents=True, exist_ok=False)
    with (dest/'summary.json').open('x') as stream:
        json.dump(compact, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    for name in ('ulog_index.json', 'SUMMARY_CN.md'):
        with (dest/name).open('xb') as stream:
            stream.write((source/name).read_bytes())
    print(json.dumps(dict(destination=str(dest), status=compact['status'], counts=compact['counts']), ensure_ascii=False))


if __name__ == '__main__':
    main()
