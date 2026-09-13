#!/usr/bin/env python3
"""Offline monitor/sequence negative checks, no simulator launch."""
import unittest
from run_m03 import Checks, check_abort
from analyze_m03 import sequence_stats
from pathlib import Path


class M03Scripts(unittest.TestCase):
    def test_warmup_grace_cannot_allow_takeoff_without_diagnostics(self):
        checks = Checks()
        checks.monitor('warmup', None, lambda name: {}, Path('/not-written'), {'position': {}})
        with self.assertRaises(RuntimeError):
            checks.monitor('warmup', None, lambda name: {}, Path('/not-written'), {'position': {'timestamp': 31e6}})

    def test_abort_fault_missing_and_stale(self):
        valid = dict(timestamp=1000, effective_mode=0, effective_axes=0, fault=0, abort_requested=False)
        check_abort(valid, 2000)
        for key, value in [('fault', 8), ('abort_requested', True), ('effective_mode', 1),
                           ('timestamp', float('nan')), ('timestamp', -2000000)]:
            with self.assertRaises(RuntimeError):
                check_abort(dict(valid, **{key: value}), 2000)
        with self.assertRaises(RuntimeError):
            check_abort({}, 2000)

    def test_invalid_active_pid_aborts(self):
        valid = dict(timestamp=1000, effective_mode=0, effective_axes=0, fault=0, abort_requested=False,
                     armed=True, updated=True, timing_status=0, measurement_valid=True, output_valid=True)
        check_abort(valid, 2000)
        for key, value in [('timing_status', 4), ('measurement_valid', False), ('output_valid', False)]:
            with self.assertRaises(RuntimeError):
                check_abort(dict(valid, **{key: value}), 2000)

    def test_sequence_loss_wrap_empty(self):
        self.assertEqual(sequence_stats([1, 2, 5], [1000, 2000, 3000])['missing'], 2)
        self.assertEqual(sequence_stats([0xffffffff, 0, 1], [1000, 2000, 3000])['missing'], 0)
        for seq, times in [([], []), ([1], [1]), ([1, 1], [1, 2]), ([2, 1], [1, 2]), ([1, 2], [2, 1])]:
            with self.assertRaises(ValueError):
                sequence_stats(seq, times)

    def test_param_parse_and_profile_bits(self):
        self.assertEqual(Checks.get_param(lambda *args: 'x SDLOG_PROFILE [626,1139] : 131', 'SDLOG_PROFILE'), 131)
        for original in (131, 147, 257):
            self.assertEqual((original | 16) & original, original)


if __name__ == '__main__':
    unittest.main()
