from pathlib import Path
import unittest
import numpy as np
from test_v04_triplet15 import TripletLog
from v04_triplet16 import triplet_data
from v04_heading_stream import data as strict_data


class TripletUseWindow16(unittest.TestCase):
    def test_unique_unchanged(self):
        u=TripletLog([1, 2, 3, 4, 5]); d,e=triplet_data(u, 3, 5)
        self.assertIs(d,u.d); self.assertEqual(e['checked_rows'],3)

    def test_superseded_ambiguous_preparation_is_retained_not_resolved(self):
        u=TripletLog([1,2,2,3,4,5]); u.d['current.valid'][2]=False
        d,e=triplet_data(u,3,5)
        self.assertIs(d,u.d); self.assertEqual(len(d['timestamp']),6)
        self.assertEqual(e['unresolved_outside_groups'][0]['reason'],'superseded before entry')

    def test_ambiguous_predecessor_before_start_rejected(self):
        u=TripletLog([1,2,2,4,5]); u.d['current.valid'][2]=False
        with self.assertRaisesRegex(ValueError,'Ambiguous'): triplet_data(u,3,5)

    def test_equal_time_entry_middle_end_groups_rejected(self):
        for when in (3,4,5):
            u=TripletLog(sorted([1,2,3,4,5,when,6]))
            ids=np.flatnonzero(u.d['timestamp']==when);u.d['next.valid'][ids[-1]]=True
            with self.assertRaisesRegex(ValueError,'Ambiguous'): triplet_data(u,3,5)

    def test_identical_boundary_groups_not_deduplicated(self):
        u=TripletLog([1,2,3,3,4,5,5,6]);d,e=triplet_data(u,3,5)
        self.assertIs(d,u.d); self.assertEqual(e['checked_rows'],5)
        self.assertEqual(e['unresolved_outside_groups'],[])

    def test_post_window_ambiguity_disclosed(self):
        u=TripletLog([1,2,3,4,5,6,6]);u.d['current.alt'][-1]=1
        d,e=triplet_data(u,3,5)
        self.assertEqual(e['unresolved_outside_groups'][0]['reason'],'after closing boundary')
        self.assertEqual(len(d['timestamp']),7)

    def test_no_predecessor_or_invalid_window(self):
        for a,b in [(0,2),(2,2),(3,2),(np.nan,3),(1,np.inf),(1,3)]:
            with self.assertRaises(ValueError): triplet_data(TripletLog([2,3,4]),a,b)

    def test_global_reversal_and_misalignment_even_outside_window(self):
        for times in ([2,1,3,4,5],[1,2,3,4,6,5],[0,1,2,3],[]):
            with self.assertRaises(ValueError): triplet_data(TripletLog(times),3,4)
        u=TripletLog([1,2,3,4]);u.d['next.valid']=np.zeros(3)
        with self.assertRaises(ValueError):triplet_data(u,3,4)

    def test_unrepresentable_clock(self):
        u=TripletLog([1,2,3,2**63+5])
        with self.assertRaises(ValueError):triplet_data(u,2,3)

    def test_all_fields_nan_payload_signed_zero_previous_and_next(self):
        for field in ['current.alt','current.lat','next.valid','previous.timestamp']:
            u=TripletLog([1,2,3,3,4,5]);u.d['previous.timestamp']=np.zeros(6,dtype=np.uint64)
            if field=='current.alt':u.d[field][3]=-0.0
            elif field=='current.lat':u.d[field].view(np.uint64)[3]=np.uint64(0x7ff8000000000001)
            else:u.d[field][3]=1
            with self.assertRaisesRegex(ValueError,'Ambiguous'):triplet_data(u,3,5)

    def test_other_topic_policy_unchanged(self):
        u=TripletLog([1,2,2,3,4]);u.d['current.valid'][2]=False
        triplet_data(u,3,4)
        for topic in ['trajectory_setpoint','vehicle_local_position','sta_velocity_ctrl_status']:
            with self.assertRaises(ValueError):strict_data(u,topic)

    def test_complete_chain_only_window_reader_and_evidence_change(self):
        root=Path(__file__).resolve().parent
        original=(root/'analyze_v04_handoff15.py').read_text()
        expected=original.replace('from v04_triplet15 import triplet_data','from v04_triplet16 import triplet_data').replace(
            'trip = triplet_data(u)',"trip, publication_window = triplet_data(u, events['handoff_ready'], events['hover_end'])").replace(
            'observation_triplets=last-first+1)','observation_triplets=last-first+1, publication_window=publication_window)')
        self.assertEqual((root/'analyze_v04_handoff16.py').read_text(),expected)
        self.assertEqual((root/'analyze_v04_height16.py').read_text(),(root/'analyze_v04_height15.py').read_text().replace(
            'from analyze_v04_handoff15 import check_handoff','from analyze_v04_handoff16 import check_handoff'))


if __name__=='__main__':unittest.main()
