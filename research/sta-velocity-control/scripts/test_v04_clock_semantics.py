"""Offline audit counterexamples. Existing production and flight checks stay unchanged."""
import unittest
from types import SimpleNamespace
import numpy as np
from audit_v04_clock_semantics import describe,tied_candidates
from v04_heading_stream import data,index,span
from analyze_v00 import previous_indices
from analyze_v03 import exact_output_match
from v04_logcheck07 import event_data


class ClockSemanticsAuditTest(unittest.TestCase):
    def test_equal_publish_distinct_forward_samples(self):
        v=describe([100,100,104],[96,100,104])
        self.assertEqual(v['equal_publish'],1);self.assertEqual(v['equal_sample'],0)
        self.assertEqual(v['same_publish_different_forward_sample'],1)
        self.assertEqual(v['max_age_us'],4)

    def test_duplicate_and_backward_samples_are_distinct_findings(self):
        v=describe([100,104,108],[100,100,96])
        self.assertEqual(v['equal_sample'],1);self.assertEqual(v['backward_sample'],1)

    def test_backward_publish_even_with_forward_sample(self):
        v=describe([104,103],[96,100]);self.assertEqual(v['backward_publish'],1)

    def test_gap_and_age_are_not_concealed(self):
        v=describe([100,200],[96,160])
        self.assertEqual(v['max_sample_gap_us'],64);self.assertEqual(v['max_age_us'],40)
        self.assertEqual(describe([100],[104])['future_sample_count'],1)

    def test_invalid_clock_rejected_without_rounding(self):
        for values in ([],[0],[float('nan')],[1.1],[True],[2**63]):
            with self.subTest(values=values),self.assertRaises(ValueError):describe(values)
        with self.assertRaises(ValueError):describe([100,104],[100])

    def test_old_strict_sampled_accessor_still_rejects_equal_publish(self):
        d={'timestamp':np.array([100,100]),'timestamp_sample':np.array([96,100])}
        log=SimpleNamespace(get_dataset=lambda *a:SimpleNamespace(data=d))
        with self.assertRaisesRegex(ValueError,'nonmonotonic'):data(log,'vehicle_attitude')
        with self.assertRaisesRegex(ValueError,'cannot weaken'):event_data(log,'vehicle_attitude')

    def test_no_sort_or_deduplication(self):
        p=np.array([100,100,104]);s=np.array([96,100,104]);before=(p.copy(),s.copy())
        describe(p,s);self.assertEqual(tied_candidates(p,100),[0,1])
        np.testing.assert_array_equal(p,before[0]);np.testing.assert_array_equal(s,before[1])

    def test_nearest_previous_is_not_unique_consumption_proof(self):
        p=np.array([100,100,104]);chosen,_=previous_indices(p,np.array([100]))
        self.assertEqual(chosen.tolist(),[1]);self.assertEqual(tied_candidates(p,100),[0,1])
        self.assertEqual(tied_candidates(p,99),[])
        with self.assertRaises(ValueError):tied_candidates([100,96],100)

    def test_boundary_span_can_hide_first_same_time_reset(self):
        d={'timestamp':np.array([100,100,104]),'quat_reset_counter':np.array([2,3,3])}
        self.assertEqual(index(d,100),1)
        self.assertEqual(span(d,100,104).tolist(),[1,2])
        self.assertEqual(np.diff(d['quat_reset_counter']).tolist(),[1,0])
        self.assertEqual(np.diff(d['quat_reset_counter'][span(d,100,104)]).tolist(),[0])

    def test_intersection_can_hide_nonmatching_second_output(self):
        d={'timestamp':np.array([100,200]),'link':np.array([100,200]),'value':np.array([0.,0.])}
        output={'timestamp':np.array([100,100,200]),'value':np.array([0.,1.,0.])}
        r=exact_output_match(d,output,'link',[('value','value')],100,201)
        self.assertEqual(r['coverage'],1);self.assertEqual(r['max_abs_error'],0)
        # This reproduces a limitation, not approval to reuse this join for duplicate keys.
        self.assertEqual(tied_candidates(output['timestamp'],100),[0,1])

    def test_publish_weight_zero_does_not_mean_sample_zero_duration(self):
        publish=np.array([100,100,104]);sample=np.array([96,100,104])
        self.assertEqual(np.diff(publish).tolist(),[0,4])
        self.assertEqual(np.diff(sample).tolist(),[4,4])

    def test_single_and_publish_only_topics_no_fabricated_sample_clock(self):
        self.assertIsNone(describe([100])['max_publish_gap_us'])
        self.assertNotIn('equal_sample',describe([100,100]))


if __name__=='__main__':unittest.main()
