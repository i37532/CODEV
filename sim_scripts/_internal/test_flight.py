import math
import unittest
from flight import figure8, yaw_sweep, assert_controller


class FlightTests(unittest.TestCase):
    def test_figure8_closed_both_lobes_bounded_and_zero_endpoint_speed(self):
        points = [figure8(i*.01) for i in range(4001)]
        self.assertAlmostEqual(points[0][0], points[-1][0], places=12)
        self.assertAlmostEqual(points[0][1], points[-1][1], places=12)
        self.assertLess(max(abs(x) for x, _ in points), 2.00001)
        self.assertLess(max(abs(y) for _, y in points), 1.00001)
        self.assertGreater(max(x for x, _ in points), 1.99)
        self.assertLess(min(x for x, _ in points), -1.99)
        self.assertLess(math.hypot(*figure8(.001))/.001, 1e-6)
        self.assertLess(math.hypot(*figure8(39.999))/.001, 1e-6)
        max_speed = max(math.hypot(b[0]-a[0], b[1]-a[1])/.01 for a, b in zip(points, points[1:]))
        self.assertLess(max_speed, 1.)

    def test_fault_or_changed_mode_prevents_continuing(self):
        d = dict(effective_mode=1, effective_axes=7, requested_mode=1, requested_axes=7,
                 pending=False, config_pending=False, config_valid=True, fault=0,
                 abort_requested=False, armed=True, output_valid=True, measurement_valid=True, timing_status=0)
        assert_controller(d, 1, 7)
        for key, value in [('fault', 1), ('effective_mode', 0), ('requested_axes', 3),
                           ('timing_status', 2), ('output_valid', False), ('measurement_valid', False), ('pending', True)]:
            with self.assertRaises(RuntimeError):
                assert_controller(dict(d, **{key: value}), 1, 7)

    def test_yaw_sweep_is_smooth_bounded_and_covers_both_directions(self):
        points = [yaw_sweep(i*.01) for i in range(4001)]
        self.assertAlmostEqual(points[0], 0, places=12)
        self.assertAlmostEqual(points[-1], 0, places=12)
        self.assertAlmostEqual(max(points), math.radians(45), places=5)
        self.assertAlmostEqual(min(points), -math.radians(45), places=5)
        self.assertLess(abs(points[1]-points[0])/.01, 1e-6)
        self.assertLess(abs(points[-1]-points[-2])/.01, 1e-6)


if __name__ == '__main__':
    unittest.main()
