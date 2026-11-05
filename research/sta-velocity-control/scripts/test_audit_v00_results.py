import unittest
from audit_v00_results import saturation_summary, perf_counts


class ResultsAuditTest(unittest.TestCase):
    def test_valid_bit_alone_not_saturation(self):
        r = saturation_summary([1, 1], [True, True])
        self.assertEqual(r['raw_nonzero_fraction'], 1)
        self.assertEqual(r['saturation_fraction_among_valid'], 0)

    def test_all_motor_axis_and_thrust_flags(self):
        for bit in range(1, 11):
            r = saturation_summary([1 | (1 << bit)], [True])
            self.assertEqual(r['saturation_fraction_among_valid'], 1)
            self.assertEqual(r['rate_direction_saturation_fraction_among_valid'], int(3 <= bit <= 8))

    def test_invalid_feedback_not_zero_saturation_claim(self):
        r = saturation_summary([1, 8], [False, True])
        self.assertEqual(r['feedback_valid_fraction'], 0)
        self.assertIsNone(r['saturation_fraction_among_valid'])

    def test_bad_shapes_rejected(self):
        for bits, valid in (([], []), ([1], [True, False])):
            with self.assertRaises(ValueError):
                saturation_summary(bits, valid)

    def test_actual_perf_name_and_count_delta(self):
        r = perf_counts('mc_pos_control: cycle time: 4087 events\nmc_pos_control: cycle time: 10127 events', 60.4)
        self.assertEqual(r['approximate_hz'], 100)

    def test_invalid_perf_rejected(self):
        for text in ('', 'mc_pos_control: cycle: 1 events',
                     'mc_pos_control: cycle time: 2 events\nmc_pos_control: cycle time: 1 events'):
            with self.assertRaises(ValueError):
                perf_counts(text, 60)


if __name__ == '__main__':
    unittest.main()
