import unittest
import numpy as np
import analyze_response as r


class ResponseTests(unittest.TestCase):
    def fixture(self):
        t=np.arange(-.1,10.1,.1)
        h=np.clip(t,0,2.5)
        return t,h,np.where((t>0)&(t<2.5),1.,0.)

    def test_linear_response(self):
        t,h,v=self.fixture();m=r.response_metrics(t,h,v,2.5,9.9)
        self.assertAlmostEqual(m['rise_10_90_s'],2.)
        self.assertAlmostEqual(m['crossings']['t90']['first_sample_s'],2.3)
        self.assertAlmostEqual(m['settling_5pct']['first_sample_s'],2.4)
        self.assertEqual(m['overshoot_m'],0)

    def test_nonuniform_crossing_bracket_no_interpolation(self):
        self.assertEqual(r.crossing(np.array([0,.1,.4]),np.array([0,.2,.5]),.3),
            {'first_sample_s':.4,'bracket_s':[.1,.4]})

    def test_threshold_not_reached(self):
        self.assertIsNone(r.crossing(np.array([0,1,2]),np.array([0,.1,.2]),.3))

    def test_initially_above_threshold_not_crossing(self):
        self.assertIsNone(r.crossing(np.array([0,1,2]),np.ones(3),.3))

    def test_settling_must_follow_last_exit(self):
        t=np.arange(8.);h=np.array([0,2.5,2.5,2.8,2.5,2.5,2.5,2.5])
        self.assertEqual(r.settling(t,h,2.5,.05,8)['first_sample_s'],4)

    def test_short_tail_is_not_settling(self):
        self.assertIsNone(r.settling(np.arange(4.),np.array([0,0,0,2.5]),2.5,.05,4))

    def test_overshoot(self):
        t,h,v=self.fixture();h[30]=2.75
        m=r.response_metrics(t,h,v,2.5,9.9)
        self.assertAlmostEqual(m['overshoot_percent'],10)

    def test_landing_excluded(self):
        t,h,v=self.fixture();h[t>=8]=5
        self.assertEqual(r.response_metrics(t,h,v,2.5,8)['overshoot_m'],0)

    def test_nan_rejected(self):
        t,h,v=self.fixture();h[20]=np.nan
        with self.assertRaises(ValueError):r.response_metrics(t,h,v,2.5,9.9)

    def test_bad_clock_rejected(self):
        t,h,v=self.fixture();t[5]=t[4]
        with self.assertRaises(ValueError):r.response_metrics(t,h,v,2.5,9.9)

    def test_missing_window_rejected(self):
        t,h,v=self.fixture()
        with self.assertRaises(ValueError):r.response_metrics(t,h,v,2.5,11)

    def test_gap_rejected(self):
        t,h,v=self.fixture();keep=(t<1)|(t>2)
        with self.assertRaises(ValueError):r.response_metrics(t[keep],h[keep],v[keep],2.5,9.9)

    def test_missing_native_command(self):
        with self.assertRaises(ValueError):r.native_command({'command':[400],'timestamp':[123]},22)

    def test_ambiguous_native_command(self):
        with self.assertRaises(ValueError):r.native_command({'command':[22,22],'timestamp':[123,124]},22)

    def test_exact_native_command(self):
        self.assertEqual(r.native_command({'command':[22,400],'timestamp':[123,124]},22),123)


if __name__=='__main__':unittest.main()
