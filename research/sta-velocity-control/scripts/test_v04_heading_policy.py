import copy
import hashlib
import json
import math
import unittest
from v04_heading_policy import CONFIG, classify, freeze_task_yaw


class HeadingPolicyTest(unittest.TestCase):
    def event(self):
        return dict(phase='TAKEOFF_PREPARATION',armed=True,airborne=True,contact=False,
            command_sent=False,excitation_started=False,primary_constant=True,primary_healthy=True,
            reference_unchanged=True,pv_counters_unchanged=True,controller_ok=True,
            aligned_before=False,aligned_after=True,yaw_aligned=True,mag_fault=False,
            mag_disturbed=False,emergency_reset=False,other_yaw_source=False,filter_fault=False,
            nav_state=17,previous_events=0,heading_before=2,heading_after=3,quat_before=2,quat_after=3,
            delta_rad=.00656,quat_delta_rad=.00656,quat_pair_offset_s=.004,sample_gap_s=.012,
            metadata_age_s=.12,selector_age_s=.58,status_flags_age_s=0.,event_stream_observable=True,event_counter_gaps=0,
            alignment_lag_s=.12,height_m=1.6,missing_samples=0)

    def test_positive_negative_zero_and_exact_cap(self):
        for delta in (0.,.00656,-.00656,math.radians(5),-math.radians(5)):
            e=self.event(); e.update(delta_rad=delta,quat_delta_rad=delta)
            self.assertEqual(classify(e),'expected_first_takeoff_alignment')

    def test_uint8_single_wrap_but_not_skipped_counters(self):
        e=self.event(); e.update(heading_before=255,heading_after=0,quat_before=255,quat_after=0)
        classify(e)
        for k,v in (('heading_after',1),('quat_after',1),('heading_before',-1),('quat_before',1.0)):
            with self.assertRaises(ValueError): classify({**e,k:v})

    def test_all_boolean_prerequisites_mandatory(self):
        e=self.event()
        for k,v in e.items():
            if isinstance(v,bool):
                with self.subTest(k=k),self.assertRaises(ValueError): classify({**e,k:not v})

    def test_later_phase_repeat_and_landing_always_rejected(self):
        for key,value in [('phase','OBSERVATION'),('phase','LANDING'),('nav_state',4),('nav_state',18),('previous_events',1)]:
            with self.assertRaises(ValueError): classify({**self.event(),key:value})

    def test_nonfinite_overlimit_and_wrong_time(self):
        for key in ('delta_rad','quat_delta_rad','quat_pair_offset_s','sample_gap_s','metadata_age_s','selector_age_s','status_flags_age_s','alignment_lag_s','height_m'):
            for value in (math.nan,math.inf,-math.inf):
                with self.subTest(key=key),self.assertRaises(ValueError): classify({**self.event(),key:value})
        for key,value in [('delta_rad',math.radians(5.001)),('sample_gap_s',.041),('sample_gap_s',0),
                          ('metadata_age_s',-.1),('metadata_age_s',.501),('alignment_lag_s',.501),
                          ('alignment_lag_s',-.001),('quat_pair_offset_s',.041),('height_m',.99),('height_m',3.01)]:
            with self.assertRaises(ValueError): classify({**self.event(),key:value})

    def test_wrong_quaternion_or_missing_sequence(self):
        for key,value in [('quat_delta_rad',-.00656),('missing_samples',1),('event_counter_gaps',1),('selector_age_s',1.201),('status_flags_age_s',1.201)]:
            with self.assertRaises(ValueError): classify({**self.event(),key:value})

    def test_missing_data_not_defaulted_valid(self):
        for key in self.event():
            e=self.event(); del e[key]
            with self.subTest(key=key),self.assertRaises((ValueError,KeyError)): classify(e)

    def test_freeze_post_alignment_value_no_double_delta(self):
        before=1.57; delta=.00656; post=before+delta
        result=freeze_task_yaw(post,post,1.,.02,confirmed=True,nav_state=2,already_frozen=False)
        self.assertEqual(result,post); self.assertNotEqual(result,post+delta)
        self.assertAlmostEqual(freeze_task_yaw(math.pi+.001,-math.pi+.001,1.,0,
            confirmed=True,nav_state=2,already_frozen=False),-math.pi+.001)

    def test_refreeze_unconfirmed_unquiet_stale_and_large_step(self):
        defaults=dict(confirmed=True,nav_state=2,already_frozen=False)
        for key,value in [('confirmed',False),('nav_state',4),('already_frozen',True)]:
            with self.assertRaises(ValueError): freeze_task_yaw(1.,1.,1.,0.,**{**defaults,key:value})
        for args in [(1.,1.,.999,0),(1.,1.,1.,.041),(1.,1.,1.,-.001),(1.,1.02,1.,0),(math.nan,1.,1.,0)]:
            with self.assertRaises(ValueError): freeze_task_yaw(*args,**defaults)

    def test_protocol_not_executable_and_numerical_gates_unchanged(self):
        p=json.loads(CONFIG.read_text()); parent=CONFIG.parents[4]/p['parent']['path']
        self.assertEqual(hashlib.sha256(parent.read_bytes()).hexdigest(),p['parent']['sha256'])
        self.assertFalse(p['flight_authorized']); self.assertFalse(p['execution_ready'])
        self.assertEqual(p['authorized_new_attempts'],0); self.assertIsNone(p['proposed_next_batch']['seeds'])
        original=json.loads(parent.read_text())
        for key in ('candidate','pair_gate','bounds','excitation','additional_log_gates'):
            self.assertIn(key,p['parent']['inherit_unchanged']); self.assertIn(key,original)
        self.assertIn('ref_lat',p['reference_policy']['before_arm'])
        self.assertIn('landing',p['reference_policy']['after_exception'])


if __name__=='__main__': unittest.main()
