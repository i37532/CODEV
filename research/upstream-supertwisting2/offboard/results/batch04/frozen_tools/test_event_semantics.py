"""Offline event-generation and full-chain tests; no synthetic flight evidence."""
import copy
import json
from pathlib import Path
import unittest

import numpy as np

import heading_check as h
import runner_contract as rc
from test_heading_check import qualified, full_check
from test_runner_contract import manifest

FORBIDDEN = tuple(k for k in h.FORBIDDEN_EVENTS if k not in h.OLD_WARNING_FIELDS) + (
    'reset_hgt_to_baro','reset_hgt_to_gps','reset_hgt_to_rng','reset_hgt_to_ev')


def cached(times=None):
    times=np.arange(1000000,12000000,1000000,dtype=np.int64) if times is None else np.asarray(times,dtype=np.int64)
    d=dict(timestamp=times,timestamp_sample=np.full(len(times),800000,dtype=np.int64),
           information_event_changes=np.full(len(times),4,dtype=np.int64),
           **{k:np.zeros(len(times),dtype=np.int64) for k in h.STA2_EVENT_FIELDS})
    d['reset_vel_to_gps'][:]=1
    return d


def new_event(d,index,field='gps_checks_passed',sample=None):
    d['information_event_changes'][index:]=(int(d['information_event_changes'][index-1])+1)%2**32
    d['timestamp_sample'][index:]=int(d['timestamp'][index])-100000 if sample is None else sample
    for key in h.STA2_EVENT_FIELDS:d[key][index:]=int(key==field)


def check(d):return h.upstream_event_history(d,3000000,10000000,FORBIDDEN)


def full_fixture(task='position',system='STA2'):
    f=qualified(task,system)
    f['job']['event_semantics_policy']=h.REPUBLICATION_EVENTS
    if system=='STA2':
        end=f['events'][-1]['timestamp_us']
        ev=f['topics']['estimator_event_flags']
        ev.clear();ev.update(cached(np.arange(900000,end+1100000,1000000)))
    return f


class EventHistoryTests(unittest.TestCase):
    def test_real_sta2_periodic_fixture(self):
        fixture=json.loads((Path(__file__).parent/'results/event_fix01/sta2_event_fixture.json').read_text())
        self.assertEqual(fixture['ver_sw'],h.STA2_HEAD)
        data={k:np.asarray(v) for k,v in fixture['event_data'].items()}
        r=h.upstream_event_history(data,*fixture['flight_window_us'],FORBIDDEN)
        self.assertEqual(r['repeated_publications_in_window'],68)
        self.assertEqual(r['new_event_publications_us'],[])
        self.assertEqual(r['counter_at_predecessor'],5)

    def test_old_forbidden_payload_is_not_new_event_no_deduplication(self):
        d=cached();before=copy.deepcopy(d);r=check(d)
        self.assertTrue(r['all_rows_retained'])
        self.assertEqual(r['repeated_publications_in_window'],8)
        for k in d:np.testing.assert_array_equal(d[k],before[k])

    def test_benign_new_event_and_its_republications(self):
        d=cached();new_event(d,4)
        self.assertEqual(check(d)['new_event_publications_us'],[5000000])

    def test_every_new_forbidden_flag_rejected(self):
        for field in FORBIDDEN:
            d=cached();new_event(d,4,field)
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,field):check(d)

    def test_same_flag_true_again_with_advanced_counter_is_new_event(self):
        d=cached();new_event(d,4,'reset_vel_to_gps')
        with self.assertRaisesRegex(ValueError,'reset_vel_to_gps'):check(d)

    def test_every_changed_cached_payload_field_rejected(self):
        for field in h.STA2_EVENT_FIELDS:
            d=cached();d[field][4]=1-d[field][4]
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'cached event'):check(d)

    def test_counter_jump_reverse_invalid_fraction_and_wrap_jump(self):
        for value in (6,3,-1,2**32,float('nan'),float('inf'),4.5):
            d=cached();d['information_event_changes']=d['information_event_changes'].astype(float)
            d['information_event_changes'][4:]=value
            with self.subTest(value=value),self.assertRaises(ValueError):check(d)
        d=cached();d['information_event_changes'][:4]=2**32-1;d['information_event_changes'][4:]=1
        with self.assertRaisesRegex(ValueError,'jump'):check(d)

    def test_single_uint32_wrap_with_benign_event_is_valid(self):
        d=cached();d['information_event_changes'][:]=2**32-1;new_event(d,4)
        self.assertEqual(check(d)['new_event_publications_us'],[5000000])

    def test_unknown_missing_fields_or_nonbinary_payload_rejected(self):
        for field in (*h.STA2_EVENT_FIELDS,'timestamp_sample','information_event_changes'):
            d=cached();del d[field]
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'schema'):check(d)
        d=cached();d['unknown_event']=np.zeros(len(d['timestamp']))
        with self.assertRaisesRegex(ValueError,'schema'):check(d)
        for value in (-1,2,.5,float('nan'),float('inf')):
            d=cached();d['gps_checks_passed']=d['gps_checks_passed'].astype(float);d['gps_checks_passed'][4]=value
            with self.subTest(value=value),self.assertRaises(ValueError):check(d)

    def test_sample_change_without_event_and_event_without_sample_advance(self):
        d=cached();d['timestamp_sample'][4:]+=1
        with self.assertRaisesRegex(ValueError,'changed sample'):check(d)
        d=cached();new_event(d,4,sample=800000)
        with self.assertRaisesRegex(ValueError,'advancing sample'):check(d)

    def test_sample_negative_zero_future_reverse_fraction_nan(self):
        for value in (-1,0,99999999,1,800000.5,float('nan')):
            d=cached();d['timestamp_sample']=d['timestamp_sample'].astype(float);d['timestamp_sample'][4]=value
            with self.subTest(value=value),self.assertRaises(ValueError):check(d)

    def test_publication_duplicate_reverse_zero_fraction_nan(self):
        for value in (0,4000000,3999999,4000000.5,float('nan')):
            d=cached();d['timestamp']=d['timestamp'].astype(float);d['timestamp'][4]=value
            with self.subTest(value=value),self.assertRaises(ValueError):check(d)

    def test_missing_predecessor_or_successor_rejected(self):
        for keep in (lambda t:t>=3000000,lambda t:t<10000000):
            d=cached();mask=keep(d['timestamp']);d={k:v[mask] for k,v in d.items()}
            with self.assertRaisesRegex(ValueError,'boundaries'):check(d)

    def test_missing_periodic_record_and_over_limit_gap_rejected(self):
        d=cached();d={k:np.delete(v,4) for k,v in d.items()}
        with self.assertRaisesRegex(ValueError,'gapped'):check(d)
        for gap,valid in ((1500000,True),(1500001,False)):
            d=cached([1000000,2000000,3000000,4000000,4000000+gap,6500000,7500000,8500000,9500000,10500000])
            with self.subTest(gap=gap):
                if valid:check(d)
                else:
                    with self.assertRaisesRegex(ValueError,'gapped'):check(d)

    def test_both_closed_boundaries_and_delayed_successor_reject_new_reset(self):
        for t,sample in ((3000000,2900000),(10000000,9900000),(11000000,10000000)):
            d=cached();index=int(np.flatnonzero(d['timestamp']==t)[0]);new_event(d,index,'reset_vel_to_gps',sample)
            with self.subTest(t=t,sample=sample),self.assertRaisesRegex(ValueError,'reset_vel_to_gps'):check(d)

    def test_pre_window_new_event_then_cached_and_strictly_post_window_event(self):
        d=cached();new_event(d,1,'reset_vel_to_gps',1900000);check(d)
        d=cached();new_event(d,10,'reset_vel_to_gps',10000001);check(d)

    def test_counter_gap_before_left_boundary_is_not_hidden_by_cache(self):
        d=cached();d['information_event_changes'][1:]+=2
        with self.assertRaisesRegex(ValueError,'jump'):check(d)

    def test_new_counter_with_empty_payload_rejected(self):
        d=cached();new_event(d,4)
        for k in h.STA2_EVENT_FIELDS:d[k][4:]=0
        with self.assertRaisesRegex(ValueError,'empty payload'):check(d)


class EventIntegrationTests(unittest.TestCase):
    def test_all_four_systems_both_task_shapes_complete_chain(self):
        for system in ('PID','STA2','RSTA','RISTA'):
            for task in ('position','velocity'):
                with self.subTest(system=system,task=task):self.assertTrue(full_check(full_fixture(task,system))['accepted'])

    def test_main_three_systems_exact_legacy_outputs(self):
        for system in ('PID','RSTA','RISTA'):
            f=qualified(system=system);before=full_check(f);f['job']['event_semantics_policy']=h.REPUBLICATION_EVENTS
            self.assertEqual(full_check(f),before)

    def test_old_policy_keeps_old_sta2_rejection(self):
        f=full_fixture();f['job'].pop('event_semantics_policy')
        with self.assertRaisesRegex(ValueError,'unexpected reset_vel_to_gps'):full_check(f)

    def test_main_event_only_no_heartbeat_and_forbidden_new_event_still_rejected(self):
        f=full_fixture(system='PID');full_check(f)
        d=f['topics']['estimator_event_flags']
        for k in d:d[k]=np.repeat(d[k],2)
        d['timestamp'][1]=14000000;d['information_event_changes'][1]+=1;d['reset_vel_to_gps'][1]=1
        with self.assertRaisesRegex(ValueError,'reset_vel_to_gps'):full_check(f)

    def test_unpinned_version_unknown_policy_and_missing_heading_policy_rejected(self):
        f=full_fixture();f['log'].msg_info_dict['ver_sw']='other'
        with self.assertRaisesRegex(ValueError,'firmware version'):full_check(f)
        for policy in ('unknown',None,False):
            f=full_fixture();f['job']['event_semantics_policy']=policy
            with self.subTest(policy=policy),self.assertRaisesRegex(ValueError,'event semantics'):full_check(f)
        f=full_fixture();f['job'].pop('heading_reset_policy')
        with self.assertRaisesRegex(ValueError,'complete heading'):full_check(f)

    def test_full_chain_downstream_stale_final_receipt_not_excused(self):
        f=full_fixture();f['events'][-1]['land_timestamp_us']-=600001
        with self.assertRaisesRegex(ValueError,'Stale final state'):full_check(f)

    def test_inflight_reset_counter_even_without_flag_still_rejected(self):
        for key in h.PV_COUNTERS:
            f=full_fixture();d=f['topics']['vehicle_local_position'];d[key][d['timestamp']>=30000000]+=1
            with self.subTest(key=key),self.assertRaises(ValueError):full_check(f)

    def test_missing_periodic_topic_sample_clock_and_primary_switch_rejected(self):
        for name,key in (('estimator_event_flags','timestamp_sample'),('vehicle_local_position','timestamp_sample')):
            f=full_fixture();del f['topics'][name][key]
            with self.subTest(name=name),self.assertRaises(ValueError):full_check(f)
        f=full_fixture();f['topics']['estimator_selector_status']['primary_instance'][200]=1
        with self.assertRaises(ValueError):full_check(f)

    def test_new_policy_requires_uniform_explicit_manifest_declaration(self):
        m=manifest();m['jobs'][1]['event_semantics_policy']=h.REPUBLICATION_EVENTS
        with self.assertRaisesRegex(ValueError,'event semantics'):rc.validate_manifest(m,'O001')
        m['event_semantics_policy']=h.REPUBLICATION_EVENTS
        with self.assertRaisesRegex(ValueError,'complete heading'):rc.validate_manifest(m,'O001')
        m['heading_reset_policy']=h.POLICY
        for j in m['jobs']:j['heading_reset_policy']=h.POLICY
        with self.assertRaisesRegex(ValueError,'event semantics'):rc.validate_manifest(m,'O001')
        for j in m['jobs']:j['event_semantics_policy']=h.REPUBLICATION_EVENTS
        self.assertEqual(rc.validate_manifest(m,'O001')['id'],'O001')
        m['event_semantics_policy']='unknown'
        with self.assertRaisesRegex(ValueError,'Unknown event'):rc.validate_manifest(m,'O001')


if __name__=='__main__':unittest.main()
