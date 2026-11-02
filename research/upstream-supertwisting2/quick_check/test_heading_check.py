"""Synthetic tests. These fixtures are never counted as flight evidence."""
import copy
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import analyze
import heading_check as h
import ros_bridge
from test_analyze import ORIGIN, fixture


def qualified(task='position', system='PID', event=True):
    f = fixture(task, system, array_layout=system == 'STA2')
    topics = f['topics']
    p, att = topics['vehicle_local_position'], topics['vehicle_attitude']
    t = p['timestamp']; n = len(t); mask = t >= 13000000
    p.update(heading=np.full(n, ORIGIN['heading']), delta_heading=np.full(n, .003))
    for key in h.REFERENCES:
        p[key] = np.full(n, 1.)
    p['heading_reset_counter'][mask] = int(event)
    att['quat_reset_counter'] = p['heading_reset_counter'].copy()
    for axis, value in enumerate((math.cos(.003/2), 0., 0., math.sin(.003/2))):
        att['delta_q_reset[%d]' % axis] = np.full(n, value)
    topics['vehicle_status']['failure_detector_status'] = np.zeros(4, dtype=int)
    topics['estimator_selector_status'] = dict(timestamp=t.copy(), primary_instance=np.zeros(n, dtype=int),
        instance_changed_count=np.ones(n, dtype=int), **{'healthy[0]': np.ones(n)},
        gyro_fault_detected=np.zeros(n), accel_fault_detected=np.zeros(n))
    topics['estimator_status'] = dict(timestamp=t.copy(), filter_fault_flags=np.zeros(n),
        reset_count_quat=p['heading_reset_counter'].copy())
    topics['estimator_status_flags'] = dict(timestamp=t.copy(), cs_yaw_align=np.ones(n), cs_in_air=np.ones(n),
        cs_mag_aligned_in_flight=mask.astype(int) if event else np.ones(n),
        **{key: np.zeros(n) for key in (*h.FORBIDDEN_FLAGS, 'fs_bad_mag_x')})
    topics['estimator_event_flags'] = dict(timestamp=np.asarray([900000]),
        information_event_changes=np.asarray([4]), warning_event_changes=np.asarray([2]),
        **{key: np.zeros(1) for key in h.FORBIDDEN_EVENTS})
    if system == 'STA2':
        flags=topics['estimator_status_flags']; ev=topics['estimator_event_flags']
        flags['cs_gnss_yaw']=flags.pop('cs_gps_yaw')
        flags['cs_mag']=np.ones(n)
        for key in h.NEW_STATE_FIELDS: flags[key]=np.zeros(n)
        for key in (*h.OLD_WARNING_FIELDS,'warning_event_changes'): ev.pop(key)
        for key in ('reset_hgt_to_baro','reset_hgt_to_gps','reset_hgt_to_rng','reset_hgt_to_ev'): ev[key]=np.zeros(1)
        f['log'].msg_info_dict={'ver_sw':h.STA2_HEAD}
    f['log'].data_list = [SimpleNamespace(name=name, multi_id=0, data=d) for name, d in topics.items()]
    f['job']['heading_reset_policy'] = h.POLICY
    return f


def check(f):
    windows, end = analyze.phase_windows(f['events'], f['job']['task'])
    return h.audit(f['log'], windows[1]['start'], end['landed_disarmed'], windows[1]['end'],
                   min(w['start'] for w in windows if w['phase'] in analyze.SCORED_PHASES), ORIGIN,
                   schema=h.STA2_SCHEMA if f['job']['system']=='STA2' else h.CODEV_SCHEMA)


def full_check(f):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        for name, rows in [('sent.jsonl', f['sent']), ('ros_published.jsonl', f['published'])]:
            (path/name).write_text(''.join(ros_bridge.canonical_json(row)+'\n' for row in rows))
        return analyze.audit_native_log('synthetic.ulg', f['events'], ORIGIN, f['job'], path/'sent.jsonl',
                                        ulog_class=lambda *args, **kw: f['log'])


class HeadingTests(unittest.TestCase):
    def test_upstream_pinned_version_and_explicit_schema(self):
        f=qualified(system='STA2');self.assertFalse(check(f)['warning_event_counter_available'])
        f['log'].msg_info_dict['ver_sw']='unverified'
        with self.assertRaisesRegex(ValueError,'firmware version'):check(f)

    def test_upstream_missing_fields_never_reconstructed_as_false(self):
        for name,key in [('estimator_status_flags','cs_gnss_yaw'),('estimator_status_flags','cs_mag'),
            ('estimator_status_flags','cs_gnss_yaw_fault'),('estimator_event_flags','yaw_aligned_to_imu_gps'),
            ('estimator_event_flags','information_event_changes')]:
            f=qualified(system='STA2');del f['topics'][name][key]
            with self.subTest(key=key),self.assertRaises(ValueError):check(f)

    def test_upstream_fault_or_navigation_loss_rejected(self):
        for key in (*h.NEW_STATE_FIELDS,'cs_gnss_yaw','cs_mag'):
            f=qualified(system='STA2');f['topics']['estimator_status_flags'][key][200]=0 if key=='cs_mag' else 1
            with self.subTest(key=key),self.assertRaises(ValueError):check(f)

    def test_upstream_emergency_yaw_event_rejected(self):
        f=qualified(system='STA2');d=f['topics']['estimator_event_flags']
        for key in d:d[key]=np.repeat(d[key],2)
        d['timestamp'][1]=14000000;d['information_event_changes'][1]+=1;d['yaw_aligned_to_imu_gps'][1]=1
        with self.assertRaisesRegex(ValueError,'yaw_aligned_to_imu_gps'):check(f)

    def test_mixed_schema_cannot_hide_missing_legacy_warning_counter(self):
        f=qualified();del f['topics']['estimator_event_flags']['warning_event_changes']
        with self.assertRaisesRegex(ValueError,'warning_event_changes'):check(f)
        f=qualified(system='STA2');f['topics']['estimator_event_flags']['warning_event_changes']=np.zeros(1)
        with self.assertRaisesRegex(ValueError,'mixed'):check(f)

    def test_single_alignment_all_systems_and_tasks_complete_chain(self):
        for system in ('PID', 'STA2', 'RSTA', 'RISTA'):
            for task in ('position', 'velocity'):
                with self.subTest(system=system, task=task):
                    result = full_check(qualified(task, system))
                    self.assertTrue(result['accepted'])
                    self.assertEqual(result['heading_evidence']['event_count'], 1)

    def test_missing_policy_preserves_old_rejection(self):
        f = qualified(); del f['job']['heading_reset_policy']
        with self.assertRaisesRegex(ValueError, 'Native estimator reset: heading_reset_counter'):
            full_check(f)

    def test_unknown_policy_is_not_a_bypass(self):
        for policy in ('allow_all', '', None, 5):
            f = qualified(); f['job']['heading_reset_policy'] = policy
            with self.subTest(policy=policy), self.assertRaisesRegex(ValueError, 'Unknown heading'):
                full_check(f)

    def test_no_reset_is_valid_and_metrics_equal_to_old(self):
        f = qualified(event=False)
        new = full_check(f); f['job'].pop('heading_reset_policy')
        old = full_check(f)
        new.pop('heading_evidence')
        self.assertEqual(old, new)

    def test_inputs_are_not_mutated(self):
        f = qualified(); before = copy.deepcopy(f['topics'])
        check(f)
        for name, d in before.items():
            for key, v in d.items():
                np.testing.assert_array_equal(v, f['topics'][name][key])

    def test_positive_negative_zero_and_exact_delta_cap(self):
        for delta in (0., -.003, .003, -h.DELTA_MAX_RAD, h.DELTA_MAX_RAD):
            f = qualified(); f['topics']['vehicle_local_position']['delta_heading'][:] = delta
            att = f['topics']['vehicle_attitude']
            att['delta_q_reset[0]'][:] = math.cos(delta/2); att['delta_q_reset[3]'][:] = math.sin(delta/2)
            with self.subTest(delta=delta):
                self.assertEqual(check(f)['classification'], 'expected_first_takeoff_alignment')

    def test_nonfinite_and_over_cap_delta(self):
        for delta in (np.nan, np.inf, -np.inf, np.nextafter(h.DELTA_MAX_RAD, np.inf), -h.DELTA_MAX_RAD-1e-9):
            f = qualified(); f['topics']['vehicle_local_position']['delta_heading'][:] = delta
            with self.subTest(delta=delta), self.assertRaises(ValueError): check(f)

    def test_counter_wrap_once_is_not_multiple_events(self):
        f = qualified()
        for name, key in [('vehicle_local_position','heading_reset_counter'),
                          ('vehicle_attitude','quat_reset_counter'), ('estimator_status','reset_count_quat')]:
            f['topics'][name][key] = (f['topics'][name][key]+255) % 256
        self.assertEqual(check(f)['event_count'], 1)

    def test_counter_jump_fraction_nan_and_negative_rejected(self):
        for name, key in [('vehicle_local_position','heading_reset_counter'),
                          ('vehicle_attitude','quat_reset_counter'), ('estimator_status','reset_count_quat')]:
            for bad in (2., .5, np.nan, -1., 256.):
                f = qualified(); d=f['topics'][name]; d[key]=d[key].astype(float); d[key][d['timestamp']>=13000000]=bad
                with self.subTest(name=name,bad=bad), self.assertRaises(ValueError): check(f)

    def test_second_reset_including_landing_tail_rejected(self):
        for name, key in [('vehicle_local_position','heading_reset_counter'),
                          ('vehicle_attitude','quat_reset_counter'), ('estimator_status','reset_count_quat')]:
            for when in (14000000, 23000000, 64000000):
                f = qualified(); d=f['topics'][name]; d[key][d['timestamp']>=when] += 1
                with self.subTest(name=name,when=when), self.assertRaises(ValueError): check(f)

    def test_each_missing_or_unpaired_counter_or_flag(self):
        for name, key in [('vehicle_local_position','heading_reset_counter'),
                          ('vehicle_attitude','quat_reset_counter'), ('estimator_status','reset_count_quat'),
                          ('estimator_status_flags','cs_mag_aligned_in_flight')]:
            f=qualified(); f['topics'][name][key][:]=0
            with self.subTest(name=name), self.assertRaisesRegex(ValueError,'unpaired'): check(f)

    def test_every_metadata_topic_required_and_duplicate_rejected(self):
        for name in h.TOPICS:
            for duplicate in (False, True):
                f=qualified(); rows=f['log'].data_list
                f['log'].data_list = rows+[next(r for r in rows if r.name==name)] if duplicate else [r for r in rows if r.name!=name]
                with self.subTest(name=name,duplicate=duplicate), self.assertRaisesRegex(ValueError,'topic'): check(f)

    def test_required_fields_never_default_to_zero(self):
        for name,key in [('vehicle_local_position','delta_heading'),('vehicle_attitude','delta_q_reset[2]'),
            ('estimator_selector_status','healthy[0]'),('estimator_status','reset_count_quat'),
            ('estimator_status_flags','cs_mag_field_disturbed'),('estimator_event_flags','warning_event_changes')]:
            f=qualified();del f['topics'][name][key]
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'missing field'):check(f)

    def test_actual_selected_instance_bound_not_zero_fallback(self):
        f=qualified(); selector=f['topics']['estimator_selector_status']; selector['primary_instance'][:]=2
        selector['healthy[2]']=selector.pop('healthy[0]')
        for row in f['log'].data_list:
            if row.name in h.TOPICS[1:]: row.multi_id=2
        self.assertEqual(check(f)['primary_instance'], 2)
        f['log'].data_list[-1].multi_id=0
        with self.assertRaisesRegex(ValueError,'instance 2'): check(f)

    def test_primary_switch_away_and_back_or_changed_counter(self):
        for key in ('primary_instance','instance_changed_count'):
            f=qualified(); f['topics']['estimator_selector_status'][key][200]+=1
            with self.subTest(key=key), self.assertRaisesRegex(ValueError,'changed'): check(f)

    def test_primary_fault_unhealthy_and_filter_fault(self):
        for name,key,bad in [('estimator_selector_status','healthy[0]',0),
            ('estimator_selector_status','gyro_fault_detected',1),('estimator_selector_status','accel_fault_detected',1),
            ('estimator_status','filter_fault_flags',1),('estimator_status_flags','cs_yaw_align',0),
            *[('estimator_status_flags',k,1) for k in (*h.FORBIDDEN_FLAGS,'fs_bad_mag_x')]]:
            f=qualified(); f['topics'][name][key][200]=bad
            with self.subTest(key=key), self.assertRaises(ValueError): check(f)

    def test_position_velocity_reference_changes_never_exempted(self):
        for key in (*h.PV_COUNTERS,*h.REFERENCES):
            f=qualified(); f['topics']['vehicle_local_position'][key][200:]+=1
            with self.subTest(key=key), self.assertRaises(ValueError): check(f)

    def test_reset_on_either_phase_boundary_is_rejected(self):
        for when in (3000000, 19000000, 22000000, 64000000):
            f=qualified()
            for name,key in [('vehicle_local_position','heading_reset_counter'),('vehicle_attitude','quat_reset_counter'),
                             ('estimator_status','reset_count_quat'),('estimator_status_flags','cs_mag_aligned_in_flight')]:
                d=f['topics'][name];d[key][:]=(d['timestamp']>=when)
            with self.subTest(when=when), self.assertRaises(ValueError): check(f)

    def test_alignment_leading_decimated_position_is_allowed(self):
        f=qualified(); p=f['topics']['vehicle_local_position']
        p['timestamp']+=8000; p['timestamp_sample']+=8000
        self.assertEqual(check(f)['event_count'],1)

    def test_disjoint_reset_intervals_rejected(self):
        for name,key in [('vehicle_attitude','quat_reset_counter'),('estimator_status','reset_count_quat')]:
            f=qualified();d=f['topics'][name];d[key][:]=(d['timestamp']>=13400000)
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'disjoint'):check(f)

    def test_pairing_offset_preserves_open_old_closed_new_interval(self):
        for delay,valid in ((139999,True),(140000,False),(140001,False)):
            f=qualified();d=f['topics']['vehicle_attitude']
            d['timestamp']+=delay;d['timestamp_sample']+=delay
            with self.subTest(delay=delay):
                if valid:self.assertEqual(check(f)['event_count'],1)
                else:
                    with self.assertRaisesRegex(ValueError,'disjoint'):check(f)

    def test_exact_and_late_alignment_confirmation(self):
        f=qualified();d=f['topics']['estimator_status_flags'];d['cs_mag_aligned_in_flight'][:]=(d['timestamp']>=13500000)
        self.assertEqual(check(f)['event_count'],1)
        d['cs_mag_aligned_in_flight'][:]=(d['timestamp']>=13600000)
        with self.assertRaisesRegex(ValueError,'confirmation'):check(f)

    def test_missing_interval_boundaries_and_periodic_gap(self):
        for name in ('vehicle_local_position','vehicle_attitude',*h.TOPICS[:3]):
            for mode in ('left','right','gap'):
                f=qualified();d=f['topics'][name];t=d['timestamp']
                keep=t>4000000 if mode=='left' else t<60000000 if mode=='right' else ((t<12000000)|(t>14000000))
                for key in d: d[key]=d[key][keep]
                with self.subTest(name=name,mode=mode),self.assertRaises(ValueError):check(f)

    def test_duplicate_reversed_publication_and_position_sample_clock(self):
        for name in ('vehicle_local_position','vehicle_attitude',*h.TOPICS[:3]):
            for offset in (0,-1):
                f=qualified();d=f['topics'][name];d['timestamp'][100]=d['timestamp'][99]+offset
                with self.subTest(name=name,offset=offset),self.assertRaises(ValueError):check(f)

    def test_identical_attitude_sample_allowed_but_reset_ambiguity_rejected(self):
        f=qualified();d=f['topics']['vehicle_attitude'];d['timestamp_sample'][100]=d['timestamp_sample'][99]
        self.assertEqual(check(f)['event_count'],1)
        d['quat_reset_counter'][100]=1
        with self.assertRaisesRegex(ValueError,'ambiguous same-sample'):check(f)

    def test_sample_clock_backwards_or_ahead_publication(self):
        for name in ('vehicle_local_position','vehicle_attitude'):
            for value in (0, 1, 999999999):
                f=qualified();f['topics'][name]['timestamp_sample'][100]=value
                with self.subTest(name=name,value=value),self.assertRaises(ValueError):check(f)

    def test_quaternion_delta_mismatch_and_norm(self):
        for value in (np.nan,.05,2.):
            f=qualified();f['topics']['vehicle_attitude']['delta_q_reset[3]'][:]=value
            with self.subTest(value=value),self.assertRaises(ValueError):check(f)

    def test_preparation_height_boundaries(self):
        for height in (1.,3.,.999999,3.000001):
            f=qualified();p=f['topics']['vehicle_local_position'];p['z'][p['timestamp']==13000000]=-height
            with self.subTest(height=height):
                if 1<=height<=3:self.assertEqual(check(f)['event_count'],1)
                else:
                    with self.assertRaisesRegex(ValueError,'height'):check(f)

    def test_airborne_mode_and_takeoff_evidence_required(self):
        for name,key,bad in [('vehicle_status','nav_state',4),('vehicle_status','arming_state',1),
            ('vehicle_land_detected','landed',1),('vehicle_land_detected','ground_contact',1),
            ('vehicle_land_detected','maybe_landed',1),('takeoff_status','takeoff_state',4),
            ('estimator_status_flags','cs_in_air',0)]:
            f=qualified();f['topics'][name][key][:]=bad
            with self.subTest(key=key),self.assertRaises(ValueError):check(f)

    def test_quiet_yaw_not_compensated_or_recaptured(self):
        f=qualified();p=f['topics']['vehicle_local_position'];p['heading'][:]=ORIGIN['heading']+.02
        with self.assertRaisesRegex(ValueError,'quiet'):check(f)
        p['heading'][:]=ORIGIN['heading']+2*math.pi
        self.assertFalse(check(f)['target_yaw_changed'])

    def test_old_event_snapshot_not_required_to_heartbeat(self):
        f=qualified();f['topics']['estimator_event_flags']['reset_vel_to_gps'][0]=1
        self.assertEqual(check(f)['event_count'],1)

    def test_new_forbidden_event_and_counter_gap_rejected(self):
        for key in (*h.FORBIDDEN_EVENTS,'information_event_changes','warning_event_changes'):
            f=qualified();d=f['topics']['estimator_event_flags']
            for k in d:d[k]=np.repeat(d[k],2)
            d['timestamp'][1]=14000000
            d[key][1]+=2 if key.endswith('changes') else 1
            with self.subTest(key=key),self.assertRaises(ValueError):check(f)

    def test_event_snapshot_must_precede_flight(self):
        f=qualified();f['topics']['estimator_event_flags']['timestamp'][0]=14000000
        with self.assertRaisesRegex(ValueError,'preceding'):check(f)

    def test_event_counter_single_wrap_not_gap(self):
        f=qualified();d=f['topics']['estimator_event_flags']
        for key in d:d[key]=np.repeat(d[key],2)
        d['timestamp'][1]=14000000
        d['information_event_changes']=np.asarray([2**32-1,0],dtype=np.int64)
        self.assertEqual(check(f)['event_count'],1)

    def test_exact_start_and_end_boundary_records_kept(self):
        d={'timestamp':np.asarray([1,10,20,30])}
        np.testing.assert_array_equal(h.interval(d,10,20),[0,1,2])
        np.testing.assert_array_equal(h.interval(d,11,21),[1,2,3])

    def test_native_gap_limit_unchanged_at_half_second(self):
        for gap,valid in ((500000,True),(500001,False)):
            d={'timestamp':np.asarray([1,1+gap,1+2*gap])}
            with self.subTest(gap=gap):
                if valid:self.assertEqual(len(h.interval(d,2,1+gap,500000)),2)
                else:
                    with self.assertRaisesRegex(ValueError,'gapped'):h.interval(d,2,1+gap,500000)

    def test_ground_flag_clear_is_not_a_reset(self):
        f=qualified();when=f['events'][-1]['timestamp_us']-200000
        d=f['topics']['estimator_status_flags'];mask=d['timestamp']>=when
        d['cs_mag_aligned_in_flight'][mask]=0;d['cs_in_air'][mask]=0
        f['topics']['vehicle_land_detected']['timestamp'][-1]=when
        self.assertEqual(check(f)['ground_flag_clear_us'],[when])

    def test_airborne_flag_clear_or_landing_reset_is_not_excused(self):
        f=qualified();d=f['topics']['estimator_status_flags'];d['cs_mag_aligned_in_flight'][d['timestamp']>=30000000]=0
        with self.assertRaises(ValueError):check(f)
        f=qualified();when=f['events'][-1]['timestamp_us']-200000
        d=f['topics']['estimator_status_flags'];mask=d['timestamp']>=when
        d['cs_mag_aligned_in_flight'][mask]=0;d['cs_in_air'][mask]=0
        f['topics']['vehicle_land_detected']['timestamp'][-1]=when
        p=f['topics']['vehicle_local_position'];p['heading_reset_counter'][p['timestamp']>=when]+=1
        with self.assertRaises(ValueError):check(f)

    def test_dropout_corruption_and_fault_rejected(self):
        for attr,value in [('dropouts',[1]),('file_corruption',True)]:
            f=qualified();setattr(f['log'],attr,value)
            with self.subTest(attr=attr),self.assertRaises(ValueError):check(f)
        for key in ('failsafe','failure_detector_status'):
            f=qualified();f['topics']['vehicle_status'][key][1]=1
            with self.subTest(key=key),self.assertRaises(ValueError):check(f)


if __name__ == '__main__':
    unittest.main()
