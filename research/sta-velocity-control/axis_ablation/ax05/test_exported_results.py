"""Verify committed summaries against the original frozen external evidence."""
import unittest
from pathlib import Path
import numpy as np
from audit_results import read, digest

RESULTS = Path(__file__).resolve().parent / 'results'
BASE = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-AXIS-ABLATION-20261008/AX05')


class ExportTest(unittest.TestCase):
    def test_registered_summary_unchanged(self):
        original = read(BASE / 'summary.json')
        self.assertEqual(read(RESULTS / 'summary.json'), {k:v for k,v in original.items() if k != 'rows'})
        self.assertEqual(original['bootstrap']['repetitions'], 200000)
        self.assertEqual(original['randomization']['repetitions'], 100000)

    def test_every_row_and_window(self):
        rows = read(RESULTS / 'metrics.json'); original = read(BASE / 'summary.json')['rows']
        self.assertEqual(len(rows), 320)
        for r, old in zip(rows, original):
            self.assertEqual(r['id'], old['id'])
            self.assertEqual(r['rmse_m_s'], old['rmse_m_s'])
            self.assertEqual(r['J'], float(np.mean(old['rmse_m_s'])))
            self.assertEqual(r['cadence'], old['secondary']['diagnostic']['cadence'])
            self.assertEqual(r['metrics_sha256'], digest(r['metrics_path']))

    def test_artifact_and_source_fingerprints(self):
        for name, sha in read(RESULTS / 'files.json').items():
            self.assertEqual(digest(RESULTS / name), sha, name)
        for path, entry in read(RESULTS / 'evidence_index.json')['inputs'].items():
            self.assertEqual(digest(path), entry['sha256'], path)

    def test_all_raw_log_receipts(self):
        rows = read(RESULTS / 'ulog_index.json'); original = read(BASE / 'audit01/evidence.json')['ulogs']
        self.assertEqual(len(rows), 640)
        self.assertEqual(len({r['archive'] for r in rows}), 640)
        for r, old in zip(rows, original):
            self.assertEqual(r, {k:old[k] for k in r})
            self.assertFalse(r['corruption']); self.assertEqual(r['dropouts'], 0)

    def test_spectra_replayed_without_changes(self):
        for i in range(1, 321):
            name = f'run{i:03d}/spectra.json'
            self.assertEqual(digest(BASE/'formal01'/name), digest(BASE/'replay01'/name), name)

    def test_actual_modes_and_states(self):
        rows = read(RESULTS/'actual_states.json')
        self.assertEqual(rows, read(BASE/'audit01/evidence.json')['runs'])
        for r in rows:
            v=r['actual']['task_values']; mask=v['active_axes'][0]
            self.assertEqual(v['pid_axes'], [7 ^ mask])
            self.assertEqual(v['inner_mode'], [0]);self.assertEqual(v['inner_divisor'], [1])
            self.assertTrue(r['actual']['takeoff_confirmed'])


if __name__ == '__main__': unittest.main()
