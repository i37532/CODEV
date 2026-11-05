"""Offline reference and actual immutable failed-ULog fixture regressions."""
import copy
import hashlib
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture as f


class Continuity(unittest.TestCase):
    def check(self, old=.5, new=.7, a=-4., ff=.3, nu=-4.):
        answer = f.continuous_mapping(old, new, a, ff, nu, 4., 6.)
        self.assertLess(abs(answer['continuity_residual']), 1e-14)
        self.assertFalse(answer['actually_executed'])
        self.assertFalse(answer['flight_accepted'])
        return answer

    def test_recorded_boundary_is_feasible(self):
        value = self.check(new=.7190654277801514, a=-4.071424961090088, ff=0.)
        self.assertAlmostEqual(value['nu_after'], .22799693972455515, places=13)
        self.assertTrue(value['nu_bound_ok'] and value['correction_bound_ok'])

    def test_identity(self):
        value = self.check(new=.5)
        self.assertAlmostEqual(value['delta'], 0., places=14)

    def test_nonzero_feedforward_exactly_once(self):
        one, two = self.check(ff=.3), self.check(ff=.6)
        self.assertAlmostEqual(two['delta']-one['delta'], (.5/.7-1)*.3, places=14)

    def test_positive_correction_and_ned_sign(self):
        value = self.check(a=2., nu=1.)
        self.assertLess(value['normalized_vertical_before'], 0.)
        self.assertGreater(value['delta'], 0.)

    def test_smaller_hover_reverses_shift(self):
        self.assertLess(self.check(new=.4)['delta'], 0.)

    def test_state_bound_rejected_not_clipped(self):
        value = self.check(nu=4.)
        self.assertFalse(value['nu_bound_ok'])
        self.assertGreater(value['nu_after'], 4.)

    def test_new_output_bound_rejected_not_clipped(self):
        value = self.check(new=.1, a=-4., nu=0.)
        self.assertFalse(value['correction_bound_ok'])
        self.assertLess(value['correction_after'], -6.)

    def test_old_output_bound(self):
        self.assertFalse(self.check(a=-7.)['correction_bound_ok'])

    def test_nonfinite_rejected_all_inputs(self):
        for index in range(7):
            for bad in (math.nan, math.inf, -math.inf):
                args = [.5, .7, -4., 0., -4., 4., 6.]
                args[index] = bad
                with self.subTest(index=index, value=bad), self.assertRaises(ValueError):
                    f.continuous_mapping(*args)

    def test_domain_rejected(self):
        for index, bad in ((0,.09), (0,.91), (1,0), (1,.91), (5,0), (6,-1)):
            args = [.5, .7, -4., 0., -4., 4., 6.]; args[index] = bad
            with self.subTest(index=index), self.assertRaises(ValueError):
                f.continuous_mapping(*args)

    def test_boundary_hover_domain(self):
        self.check(old=.1, new=.9, a=0, nu=0)
        self.check(old=.9, new=.1, a=0, nu=0)

    def test_next_frame_changes_not_claimed_continuous(self):
        value = self.check()
        changed = (value['correction_after']+.3+.5-9.80665)*.7/9.80665
        self.assertGreater(abs(changed-value['normalized_vertical_before']), .01)


class RecordedFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = f.extract()
        cls.old, cls.helper_sha = f.historical_helpers()

    def test_header_exactly_matches_raw_floats(self):
        self.assertEqual((f.HERE/'recorded_hte_fixture.hpp').read_text(), f.render_header(self.data['values']))

    def test_raw_log_sha_and_original_failed_verdict(self):
        self.assertEqual({x['name']: x['sha256'] for x in self.data['raw_logs']}, f.RAW)
        self.assertFalse(self.data['original_result']['success'])
        self.assertTrue(self.data['original_failure_preserved'])
        self.assertFalse(self.data['flight_authorized'])
        self.assertEqual(self.data['new_budget'], 0)

    def test_read_only_archive_fingerprints(self):
        self.assertEqual(self.data['input_fingerprints_before'], self.data['input_fingerprints_after'])
        self.assertEqual(self.data['input_fingerprints_after'], self.old.snapshot(f.RUN))

    def test_414_independent_solutions_actual_samples(self):
        rows = self.data['candidates']
        self.assertEqual(len(rows), 414)
        self.assertEqual({round(x['reference']['h'], 3) for x in rows}, {.008, .012})
        self.assertLess(max(max(x['absolute_error'].values()) for x in rows), 2e-6)
        self.assertLess(max(abs(x['reference']['root_residual']) for x in rows), 1e-14)

    def test_state_limit_does_not_relabel_strict(self):
        row = self.data['candidates'][-1]
        self.assertEqual(row['flags'], 8)
        self.assertEqual(row['strict_axes'], 0)
        self.assertEqual(row['commit_axes'], 4)
        self.assertFalse(row['cache_valid'])
        self.assertEqual(row['nu_applied'], -4)
        self.assertLess(row['recorded']['nu_candidate'], -4)
        self.assertEqual(row['correction_applied'], row['recorded']['correction'])

    def test_seed_inverse_and_last_identity(self):
        seed = self.data['seed']
        self.assertEqual(seed['sample'], 38924000)
        self.assertLess(abs(seed['recorded_nu']-seed['solved_nu']), 2e-6)
        self.assertEqual(self.data['values']['LastSample'], 43064000)
        self.assertEqual(self.data['values']['FailureSample'], 43076000)

    def test_failure_retry_not_used_as_candidate(self):
        fault = self.data['boundary_rows'][-1]['status']
        self.assertEqual((fault['first_fail'], fault['sta_fault'], fault['pid_calls'], fault['retry_result']), (56,10,2,2))
        self.assertLess(max(x['sample'] for x in self.data['candidates']), fault['timestamp_sample'])

    def test_historical_source_objects_not_working_source(self):
        for item in self.data['historical_sources'].values():
            self.assertEqual(item['source'], f.SOURCE)
            self.assertIn('git object', item['provenance'])
        self.assertEqual(self.data['historical_helper_sha256'], self.helper_sha)

    def test_malformed_raw_fingerprint_is_rejected(self):
        changed = dict(f.RAW); changed['06_07_48.ulg'] = '0'*64
        with patch.object(f, 'RAW', changed), self.assertRaisesRegex(ValueError, 'ULog changed'):
            f.extract()

    def test_exact_join_rejects_missing_and_duplicates(self):
        data = {'timestamp_sample': [1,2], 'publish_seq': [1,2]}
        for wrong in ({'timestamp_sample':[1], 'publish_seq':[1]},
                      {'timestamp_sample':[1,1], 'publish_seq':[1,1]}):
            with self.assertRaises(ValueError):
                self.old.exact_join(data, wrong)


if __name__ == '__main__':
    unittest.main(verbosity=2)
