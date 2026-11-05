"""Isolated complete-chain diagnostic replay; never changes frozen flight verdicts."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import numpy as np
from pyulog import ULog
from audit_v04_diagnostic11 import sha
from v04_triplet16 import triplet_data
from analyze_v04_height16 import height_evidence


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('batch', type=Path)
    parser.add_argument('--protocol-dir', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(args.protocol_dir.resolve()))
    import common
    import analyze
    analyze.height_evidence = height_evidence
    rows = []
    for src in sorted(args.batch.glob('run[0-9][0-9]')):
        dst = out / src.name; dst.mkdir()
        original_path = src / ('v04_' + args.protocol_dir.name + '_metrics.json')
        original_sha = sha(original_path); original = json.loads(original_path.read_text())
        for path in src.iterdir():
            if path.is_file() and path.suffix in ('.json', '.jsonl', '.txt', '.log'): shutil.copyfile(path, dst / path.name)
        protocol = common.load_protocol(); job = json.loads((dst / 'job.json').read_text()); protocol['startup_overrides'].update(job['parameters'])
        candidate = analyze.analyze(dst, protocol, job)
        result = json.loads((src / 'result.json').read_text()); entry = max(result['logs'], key=lambda x:x['bytes'])
        assert sha(entry['archive']) == entry['sha256']
        u = ULog(entry['archive'], message_name_filter_list=['position_setpoint_triplet'])
        events = {e['name']:e['timestamp_us'] for e in result['events']}
        d, window = triplet_data(u, events['handoff_ready'], events['hover_end']); repeats = np.flatnonzero(np.diff(d['timestamp'].astype(np.int64)) == 0) + 1
        rows.append(dict(run=src.name, original_accepted=original['accepted'], original_error=original.get('error'),
            diagnostic_candidate_accepted=candidate['accepted'], candidate_error=candidate.get('error'),
            publication_window=window, all_rows_retained=len(d['timestamp']), equal_timestamp_rows=[int(d['timestamp'][i]) for i in repeats],
            sha256=entry['sha256'], not_a_formal_reacceptance=True))
        assert sha(original_path) == original_sha and sha(entry['archive']) == entry['sha256']
    (out / 'replay.json').write_text(json.dumps(rows, indent=2) + '\n')
    files = sorted(p for p in out.rglob('*') if p.is_file())
    (out / 'artifacts.sha256').write_text(''.join(f'{sha(p)}  {p}\n' for p in files))
    print(json.dumps(rows, indent=2))


if __name__ == '__main__': main()
