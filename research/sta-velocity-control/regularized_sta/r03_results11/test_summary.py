"""Result-only consistency tests. No flight, mutation or acceptance decision."""
import hashlib
import json
import math
from pathlib import Path
import statistics
import unittest

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / 'summary.json').read_text())
GATES = DATA['gate_results']


class ResultConsistency(unittest.TestCase):
    def test_exact_four_gates(self):
        self.assertEqual([g['gate'] for g in GATES], ['A', 'B', 'C', 'D'])
        for gate in GATES:
            self.assertEqual((gate['accepted'], gate['replays'], gate['paired_checks']), (9, 9, 6))
            self.assertEqual(len(gate['runs']), 9)

    def test_distinct_versions_not_one_binary(self):
        self.assertEqual({g['source_head'] for g in GATES[:3]},
                         {'eb25fecbdba9a499132a16ce16f6b847e4a218d3'})
        self.assertEqual(GATES[3]['source_head'], 'b2883d7871f659cf810a0a527979c9c1f119fd41')
        self.assertNotEqual(GATES[0]['firmware_sha256'], GATES[3]['firmware_sha256'])
        self.assertFalse(DATA['formal_significance_claim'])

    def test_paired_seed_blocks(self):
        starts = [71601, 71611, 71621, 71831]
        for gate, start in zip(GATES, starts):
            for algo in ('PID', 'ESTA', 'RSTA'):
                seeds = [r['seed'] for r in gate['runs'] if r['algorithm'] == algo]
                self.assertEqual(sorted(seeds), list(range(start, start + 3)))

    def test_error_decomposition_and_J(self):
        for gate in GATES:
            for row in gate['runs']:
                self.assertAlmostEqual(row['J_m_s'], sum(row['rmse_m_s']) / 3, places=15)
                for rmse, bias, var in zip(row['rmse_m_s'], row['mean_error_m_s'], row['variance']):
                    self.assertTrue(math.isclose(rmse * rmse, bias * bias + var,
                                                 rel_tol=1e-12, abs_tol=1e-15))

    def test_group_means(self):
        for gate in GATES:
            for algo, group in gate['groups'].items():
                rows = [r for r in gate['runs'] if r['algorithm'] == algo]
                self.assertEqual(group['n'], len(rows))
                for key, value in group['means'].items():
                    if isinstance(value, list):
                        expected = [statistics.mean(r[key][i] for r in rows) for i in range(len(value))]
                    else:
                        expected = statistics.mean(r[key] for r in rows)
                    self.assertEqual(value, expected)
                self.assertEqual(group['J_sample_sd'], statistics.stdev(r['J_m_s'] for r in rows))

    def test_pair_differences(self):
        for gate in GATES:
            for pair in gate['paired_differences']:
                rows = {r['algorithm']: r for r in gate['runs'] if r['seed'] == pair['seed']}
                a, b = rows[pair['candidate']], rows['PID']
                self.assertEqual(pair['J_difference'], a['J_m_s'] - b['J_m_s'])
                self.assertEqual(pair['rmse_difference'], [x - y for x, y in zip(a['rmse_m_s'], b['rmse_m_s'])])

    def test_actual_output_and_mode(self):
        for gate in GATES:
            for row in gate['runs']:
                self.assertTrue(all(row['baseline_checks'].values()))
                self.assertEqual(row['lifecycle']['actual_algorithms'],
                                 [{'PID': 0, 'ESTA': 1, 'RSTA': 3}[row['algorithm']]])
                output = row['actual_output']
                self.assertEqual(output['coverage'], output['matched'] / output['denominator'])
                # Retain the original matcher contract; old A/run001 has one
                # unmatched record. This result test adds no new gate.
                self.assertGreaterEqual(output['coverage'], 0.8)
                self.assertLessEqual(output['max_gap_s'], 0.25)
                if gate['gate'] == 'D':
                    self.assertEqual(output['coverage'], 1.0)
                self.assertEqual(row['actual_output']['max_abs_error'], 0.0)
                self.assertEqual(row['position_log']['sequence_gaps'], 0)
                position = row['position_log']
                self.assertEqual(position['raw_overlap_records'] + position['raw_missing_records'],
                                 position['records'])
                self.assertTrue(position['no_interpolation'])
                self.assertTrue(position['no_deduplication'])
                self.assertTrue(position['raw_records_preserved'])

    def test_receipts_and_history_not_reclassified(self):
        for gate in GATES:
            path = HERE / ('gate_' + gate['gate'] + '.json')
            receipt = json.loads(path.read_text())
            self.assertTrue(receipt['success'])
            self.assertEqual(receipt['source_head'], gate['source_head'])
            original = next(p for p in DATA['input_sha256']
                            if p.endswith('/' + gate['gate'] + '/gate_pass.json'))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), DATA['input_sha256'][original])
        last = json.loads((HERE / 'gate_D.json').read_text())
        self.assertEqual((last['retained_attempts'], last['retained_accepted_attempts'],
                          last['retained_invalid_attempts'], last['total_budget']), (88, 78, 8, 97))

    def test_index_shape(self):
        self.assertEqual(len(DATA['input_sha256']), 276)
        for path, digest in DATA['input_sha256'].items():
            self.assertTrue(Path(path).is_absolute())
            self.assertRegex(digest, '^[0-9a-f]{64}$')


if __name__ == '__main__':
    unittest.main(verbosity=2)
