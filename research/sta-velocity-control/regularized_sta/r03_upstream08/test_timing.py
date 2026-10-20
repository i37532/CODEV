"""Negative/boundary checks for additional diagnostic gyro coverage."""
import copy
import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec = importlib.util.spec_from_file_location('_timing_test', Path(__file__).with_name('timing.py'))
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


def rows():
    clock = np.arange(100000, 168001, 4000, dtype=np.uint64)
    return dict(timestamp=clock.copy(), timestamp_sample=clock.copy(),
        device_id=np.full(len(clock), 123, dtype=np.uint32),
        samples=np.ones(len(clock), dtype=np.uint8),
        error_count=np.zeros(len(clock), dtype=np.uint64),
        x=np.zeros(len(clock)), y=np.zeros(len(clock)), z=np.zeros(len(clock)))


class Timing(unittest.TestCase):
    def test_complete_nominal_and_inputs_unchanged(self):
        d=rows(); before=copy.deepcopy(d); v=t.gyro_evidence(d,112000,152000)
        self.assertEqual(v['observed_median_rate_hz'],250)
        self.assertEqual(v['max_age_us'],0)
        for key in d: np.testing.assert_array_equal(d[key],before[key])

    def test_publication_tie_is_not_deduplicated(self):
        d=rows(); d['timestamp'][4]=d['timestamp'][5]
        v=t.gyro_evidence(d,112000,152000)
        self.assertEqual(v['publication_ties'],1)

    def test_sample_tie_rejected(self):
        d=rows(); d['timestamp_sample'][4]=d['timestamp_sample'][3]
        with self.assertRaises(ValueError):t.gyro_evidence(d,112000,152000)

    def test_backwards_publication_rejected(self):
        d=rows(); d['timestamp'][4]=100000
        with self.assertRaises(ValueError):t.gyro_evidence(d,112000,152000)

    def test_future_sample_rejected(self):
        d=rows(); d['timestamp_sample'][4]+=1
        with self.assertRaises(ValueError):t.gyro_evidence(d,112000,152000)

    def test_twelve_ms_exact_age_and_plus_one(self):
        for age,valid in ((12000,True),(12001,False)):
            d=rows(); d['timestamp']+=age
            if valid:self.assertEqual(t.gyro_evidence(d,116000,148000)['max_age_us'],age)
            else:
                with self.assertRaises(ValueError):t.gyro_evidence(d,116000,148000)

    def test_missing_start_or_end_or_seal_rejected(self):
        for start,end in ((99000,152000),(112000,180000),(112000,168000)):
            with self.subTest(start=start,end=end),self.assertRaises(ValueError):t.gyro_evidence(rows(),start,end)

    def test_sparse_one_hz_rejected(self):
        d=rows();d['timestamp']*=250;d['timestamp_sample']*=250
        with self.assertRaises(ValueError):t.gyro_evidence(d,112000*250,152000*250)

    def test_device_and_error_change_rejected(self):
        for key in ('device_id','error_count'):
            d=rows();d[key][5]+=1
            with self.subTest(key=key),self.assertRaises(ValueError):t.gyro_evidence(d,112000,152000)

    def test_invalid_samples_or_values_rejected(self):
        for key,val in (('device_id',0),('samples',0),('x',np.nan),('y',np.inf)):
            d=rows();d[key][5]=val
            with self.subTest(key=key),self.assertRaises(ValueError):t.gyro_evidence(d,112000,152000)

    def test_row_lengths_and_clock_types_rejected(self):
        d=rows();d['x']=d['x'][:-1]
        with self.assertRaises(ValueError):t.gyro_evidence(d,112000,152000)
        d=rows();d['timestamp']=d['timestamp'].astype(float)
        with self.assertRaises(ValueError):t.gyro_evidence(d,112000,152000)

    def test_trace_records_old_24ms_symptom_without_passing(self):
        d=rows();d['timestamp']+=24000
        v=t.trace_summary(d,124000,176000)
        self.assertEqual(v['max_age_us'],24000)
        self.assertGreater(v['age_over_existing_12ms'],0)
        self.assertNotIn('accepted',v)

    def test_whole_log_rejects_wrong_profile_and_dropout(self):
        class Log:
            dropouts=[];file_corruption=False;initial_parameters={'SDLOG_PROFILE':1041}
        with self.assertRaises(ValueError):t.inspect_log(Log(),112000,152000)
        Log.initial_parameters={'SDLOG_PROFILE':3089};Log.dropouts=[1]
        with self.assertRaises(ValueError):t.inspect_log(Log(),112000,152000)


if __name__=='__main__':unittest.main(verbosity=2)
