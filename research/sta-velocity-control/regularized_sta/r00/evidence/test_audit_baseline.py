#!/usr/bin/env python3
"""Offline tests of audit helpers, not controller tests or flight acceptance."""
import copy
import unittest

from audit_baseline import GROUPS, INVARIANTS, intervals, parameters


class BaselineAuditTest(unittest.TestCase):
    def configurations(self):
        return {name: dict(INVARIANTS, MPC_VC_MODE=int(mask > 0), MPC_VC_AXES=mask,
                           MPC_VC_L1_X=.5) for mask, name in enumerate(GROUPS)}

    def test_8_12ms_distribution(self):
        value = intervals([1000, 9000, 21000, 29000, 41000])
        self.assertEqual(value['histogram_us'], {'8000': 2, '12000': 2})
        self.assertEqual(value['mean_hz'], 100.)

    def test_duplicate_is_rejected_not_removed(self):
        with self.assertRaisesRegex(ValueError, 'no deduplication'):
            intervals([1000, 9000, 9000, 21000])

    def test_backwards_is_rejected(self):
        with self.assertRaises(ValueError):
            intervals([1000, 9000, 8000])

    def test_insufficient_data_is_rejected(self):
        with self.assertRaises(ValueError):
            intervals([1000])

    def test_eight_configs_keep_common_parameters(self):
        value = parameters(self.configurations())
        self.assertEqual(len(value['configurations']), 8)
        self.assertNotIn('MPC_VC_MODE', value['common_parameters'])

    def test_wrong_mode_or_axes_is_rejected(self):
        for key in ('MPC_VC_MODE', 'MPC_VC_AXES'):
            candidate = self.configurations()
            candidate['xyz'][key] = 2
            with self.assertRaises(ValueError):
                parameters(candidate)

    def test_combination_specific_gain_is_rejected(self):
        candidate = self.configurations()
        candidate['xyz']['MPC_VC_L1_X'] = .6
        with self.assertRaisesRegex(ValueError, 'differ'):
            parameters(candidate)

    def test_common_wrong_inner_mode_is_rejected(self):
        candidate = copy.deepcopy(self.configurations())
        for item in candidate.values():
            item['MC_RTC_MODE'] = 1
        with self.assertRaisesRegex(ValueError, 'invariant'):
            parameters(candidate)


if __name__ == '__main__':
    unittest.main(verbosity=2)
