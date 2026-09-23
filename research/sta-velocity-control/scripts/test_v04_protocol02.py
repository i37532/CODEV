"""Protocol-only regression checks, not flight or control-loop tests."""
import math
import unittest
from check_v04_protocol02 import load, target_altitude


class Protocol02Test(unittest.TestCase):
    def setUp(self):
        self.p, self.old = load()

    def test_design_is_not_flight_authorization(self):
        self.assertFalse(self.p['execution_ready'])
        self.assertFalse(self.p['flight_authorized'])
        self.assertIn('not yet implemented', self.p['implementation_gate']['runner'])

    def test_six_new_attempts_no_old_budget(self):
        budget = self.p['budget']
        self.assertEqual(budget['maximum_new_attempts'], 6)
        self.assertEqual(budget['old_remaining_attempts_reused'], 0)
        self.assertEqual(budget['extra_smoke_or_tuning_attempts'], 0)
        self.assertFalse(budget['automatic_retry'])
        self.assertTrue(budget['stop_on_any_required_failure'])

    def test_paired_pid_first_order(self):
        jobs = self.p['budget']['jobs']
        self.assertEqual([j['id'] for j in jobs], ['run%02d' % i for i in range(1, 7)])
        self.assertEqual([(j['seed'], j['mode'], j['axes']) for j in jobs],
                         [(9201, 0, 0), (9201, 1, 1), (9202, 0, 0),
                          (9202, 1, 1), (9203, 0, 0), (9203, 1, 1)])

    def test_historical_gains_and_limits_unchanged(self):
        self.assertEqual(self.old['candidate'], dict(MPC_VC_L1_X=1, MPC_VC_L2_X=.2,
                                                   MPC_VC_NU_X=.4, MPC_VC_A_X=.8))
        self.assertEqual(self.old['pair_gate']['relative_rmse_limit'], 1.25)
        self.assertEqual(self.old['pair_gate']['absolute_velocity_rmse_allowance_m_s'], [.02, .02, .01])
        self.assertEqual(self.old['bounds']['height_at_hover_entry_error_m'], .5)

    def test_inner_pid_and_default_lifecycle(self):
        for key, expected in dict(MC_RTC_MODE=0, MC_STA_AXES=0, MC_RTC_DIV=1,
                                  MC_RATT_TEST=0, MC_STA_TKO_MGT=0).items():
            self.assertEqual(self.old['startup_overrides'][key], expected)

    def test_height_transform_float32_roundtrip(self):
        for ground, ref in ((.5666, 488.4), (-1.2, 0), (10., 1234.5), (0., -430.)):
            z, alt = target_altitude(ground, ref)
            self.assertAlmostEqual(ground - z, 2.5)
            self.assertLessEqual(abs(-(alt - ref) - z), .02)

    def test_invalid_height_reference_rejected(self):
        for a, b in ((math.nan, 1), (1, math.inf), (0, 1e40), (0, 1e30)):
            with self.assertRaises(ValueError):
                target_altitude(a, b)

    def test_old_failed_height_still_rejected(self):
        lo, hi = self.p['height_task']['entry']['height_m']
        self.assertFalse(lo <= .5666 - (-1.4003) <= hi)
        self.assertEqual([lo, hi], [2., 3.])

    def test_entry_precedes_unchanged_excitation(self):
        entry = self.p['height_task']['entry']
        self.assertEqual(entry['continuous_sim_seconds'], 3)
        self.assertEqual(entry['height_ready_deadline_after_excitation_gate_s'], 10)
        self.assertLess(entry['height_ready_deadline_after_excitation_gate_s'],
                        self.old['excitation']['settle_after_auto_loiter_s'])
        self.assertEqual(self.old['excitation']['duration_s'], 32)
        self.assertGreater(self.p['height_task']['observation_sim_s'], 12 + 32)

    def test_single_navigation_command_and_no_resend(self):
        command = self.p['height_task']['reposition']
        self.assertEqual(command['maximum_sends'], 1)
        self.assertEqual(command['param2'], 1)
        self.assertEqual([command['param5'], command['param6']], ['NaN', 'NaN'])
        self.assertIn('radians', command['param4'])
        self.assertIn('ACK alone does not prove', command['require'])

    def test_first_failure_never_hidden(self):
        gates = self.p['additional_log_gates']
        self.assertEqual(gates['required_zero_fields'], ['first_fail', 'retry_result', 'excitation_fault'])
        self.assertEqual(gates['missing_new_field'], 'reject, never substitute zero')

    def test_observation_and_logger_thresholds_not_relaxed(self):
        self.assertEqual(self.old['data_gate']['maximum_ulog_dropouts'], 0)
        self.assertEqual(self.old['diagnostic_gate']['maximum_gap_s'], .04)
        self.assertEqual(self.old['diagnostic_gate']['output_exact_minimum_coverage'], .8)
        self.assertEqual(self.p['height_task']['observation_accepted_duration_s'], [60, 62])


if __name__ == '__main__':
    unittest.main()
