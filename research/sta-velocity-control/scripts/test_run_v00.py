"""No simulator: parsing, PID gate, matching and metric contract checks."""
import unittest
import numpy as np
from run_v00 import parse_params, check_parameters, encode_bson, check_inner
from capture_v00 import persisted_bson
from analyze_v00 import previous_indices, stats


class RunnerTest(unittest.TestCase):
    def test_parameter_parser(self):
        self.assertEqual(parse_params(' x MC_RTC_MODE [5,9] : 0\n MPC_XY_P [9] : 0.9500'),
                         {'MC_RTC_MODE': 0., 'MPC_XY_P': .95})

    def test_missing_or_wrong_parameters_rejected(self):
        for values in ({}, {'MC_RTC_MODE': 2}, {'MC_RTC_MODE': float('nan')}):
            with self.assertRaises(RuntimeError):
                check_parameters(values, {'MC_RTC_MODE': 0})

    def test_parameter_display_rounding(self):
        check_parameters({'MPC_XY_P': .95}, {'MPC_XY_P': .949999988})

    def test_bson_roundtrip(self):
        values = {'MC_RTC_MODE': 0, 'MPC_XY_P': .95}
        self.assertEqual(persisted_bson(encode_bson(values, {'MC_RTC_MODE':'Int32','MPC_XY_P':'Float'})),values)

    def test_pid_gate_and_reject_each_bad_field(self):
        d = dict(requested_mode=0, requested_axes=0, effective_mode=0, effective_axes=0,
                 div_req=1,div_eff=1,fault=0,abort_requested=0,termination=0)
        check_inner(d)
        for name in d:
            with self.subTest(field=name), self.assertRaises(RuntimeError):
                check_inner({**d, name:99})

    def test_armed_measurement_gate(self):
        d = dict(requested_mode=0, requested_axes=0, effective_mode=0,effective_axes=0,
                 div_req=1,div_eff=1,fault=0,abort_requested=0,termination=0,
                 armed=True,rate_enabled=True,measurement_valid=True,output_valid=True,timing_status=0)
        check_inner(d)
        for name in ('measurement_valid','output_valid'):
            with self.assertRaises(RuntimeError):
                check_inner({**d,name:False})
        with self.assertRaises(RuntimeError):
            check_inner({**d,'timing_status':4})

    def test_preceding_not_future_match(self):
        i, age = previous_indices(np.array([10,20,30]), np.array([19,21,30]), 10)
        np.testing.assert_array_equal(i,[0,1,2])
        np.testing.assert_array_equal(age,[9,1,0])

    def test_absent_or_stale_match_rejected(self):
        for t in (np.array([9]), np.array([100])):
            with self.assertRaises(ValueError):
                previous_indices(np.array([10,20,30]), t, 10)

    def test_weighted_rmse_decomposition(self):
        result=stats(np.array([1.,3.]),np.array([3.,1.]))
        self.assertAlmostEqual(result['mean'],1.5)
        self.assertAlmostEqual(result['rmse']**2,3.)
        self.assertAlmostEqual(result['mean']**2+result['std']**2,result['rmse']**2)

    def test_invalid_metric_rejected(self):
        for x in ([],[float('nan')],[float('inf')]):
            with self.assertRaises(ValueError):
                stats(x)


if __name__ == '__main__':
    unittest.main()
