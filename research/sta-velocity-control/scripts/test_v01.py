import unittest
import numpy as np
from analyze_v01 import check_selection


class SelectionLogTest(unittest.TestCase):
    def data(self):
        t=np.arange(1000,7001000,10000,dtype=np.int64)
        d={k:np.zeros(len(t),dtype=np.int64) for k in ('requested_mode','requested_axes','effective_mode','effective_axes','pending','reject')}
        d.update(timestamp=t,timestamp_sample=t.copy(),input_timestamp=t.copy(),publish_seq=np.arange(len(t)),
                 enabled=np.ones(len(t)),armed=np.ones(len(t)),pid_calls=np.ones(len(t)))
        return d

    def test_complete_pid_log(self):
        self.assertEqual(check_selection(self.data(),0,7001000)['n'],700)

    def test_wrong_requested_effective_pending_reject(self):
        for field in ('requested_mode','requested_axes','effective_mode','effective_axes','pending','reject'):
            d=self.data();d[field][100]=1
            with self.subTest(field=field), self.assertRaises(ValueError):check_selection(d,0,7001000)

    def test_missing_sequence_and_bad_time(self):
        for field in ('publish_seq','timestamp','timestamp_sample','input_timestamp'):
            d=self.data();d[field][100]=d[field][99]
            with self.subTest(field=field), self.assertRaises(ValueError):check_selection(d,0,7001000)

    def test_no_flight_or_double_update_rejected(self):
        for field,value in (('armed',0),('pid_calls',2),('pid_calls',0)):
            d=self.data();d[field][:]=value
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):check_selection(d,0,7001000)

    def test_short_log_rejected(self):
        with self.assertRaises(ValueError):check_selection(self.data(),0,100000)

    def test_disabled_does_not_claim_update(self):
        d=self.data();d['enabled'][:20]=0;d['pid_calls'][:20]=0
        self.assertEqual(check_selection(d,0,7001000)['active_pid_samples'],680)
        d['pid_calls'][0]=1
        with self.assertRaises(ValueError):check_selection(d,0,7001000)
