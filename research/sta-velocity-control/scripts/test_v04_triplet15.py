from types import SimpleNamespace
from pathlib import Path
import unittest
import numpy as np
from v04_triplet15 import triplet_data
from v04_heading_stream import data as strict_data


class TripletLog:
    def __init__(self, times):
        self.d = dict(timestamp=np.array(times, dtype=np.uint64), **{
            'current.valid': np.ones(len(times), dtype=bool),
            'current.lat': np.full(len(times), np.nan, dtype=np.float64),
            'current.alt': np.zeros(len(times), dtype=np.float32),
            'next.valid': np.zeros(len(times), dtype=bool)})
    def get_dataset(self, name, instance=0): return SimpleNamespace(data=self.d)


class TripletPublication15(unittest.TestCase):
    def test_only_triplet_policy_binding_changes_in_complete_chain(self):
        root = Path(__file__).resolve().parent
        original = (root / 'analyze_v04_handoff09.py').read_text()
        expected = original.replace('import json', 'from v04_triplet15 import triplet_data\nimport json').replace(
            "trip = data(u, 'position_setpoint_triplet')", 'trip = triplet_data(u)')
        self.assertEqual((root / 'analyze_v04_handoff15.py').read_text(), expected)
        original = (root / 'analyze_v04_height_protocol09.py').read_text()
        self.assertEqual((root / 'analyze_v04_height15.py').read_text(), original.replace(
            'from analyze_v04_handoff09 import check_handoff', 'from analyze_v04_handoff15 import check_handoff'))

    def test_increasing_unchanged(self):
        u = TripletLog([1, 2, 3]); self.assertIs(triplet_data(u), u.d)

    def test_equal_identical_keeps_all_rows_and_original_strict_rejects(self):
        u = TripletLog([1, 2, 2, 3]); d = triplet_data(u)
        self.assertIs(d, u.d); self.assertEqual(len(d['timestamp']), 4)
        with self.assertRaises(ValueError): strict_data(u, 'position_setpoint_triplet')

    def test_changed_current_or_next_even_outside_observation_rejected(self):
        for key, value in [('current.valid', False), ('current.alt', .001), ('next.valid', True)]:
            u = TripletLog([1, 2, 2, 3]); u.d[key][2] = value
            with self.assertRaisesRegex(ValueError, 'Ambiguous'): triplet_data(u)

    def test_reversal_empty_zero_and_misaligned_rejected(self):
        for times in [[], [0, 1], [1, 3, 2]]:
            with self.assertRaises(ValueError): triplet_data(TripletLog(times))
        u = TripletLog([1, 2, 3]); u.d['next.valid'] = np.zeros(2)
        with self.assertRaises(ValueError): triplet_data(u)

    def test_nan_payload_and_signed_zero_are_not_hidden(self):
        u = TripletLog([1, 2, 2, 3]); u.d['current.alt'][2] = -0.0
        with self.assertRaisesRegex(ValueError, 'Ambiguous'): triplet_data(u)
        u = TripletLog([1, 2, 2, 3]); u.d['current.lat'].view(np.uint64)[2] = np.uint64(0x7ff8000000000001)
        with self.assertRaisesRegex(ValueError, 'Ambiguous'): triplet_data(u)

    def test_boundary_group_not_discarded_and_other_topics_stay_strict(self):
        u = TripletLog([1, 2, 2, 3]); d = triplet_data(u)
        self.assertEqual(np.flatnonzero(d['timestamp'] == 2).tolist(), [1, 2])
        for topic in ['trajectory_setpoint', 'vehicle_local_position', 'sta_velocity_ctrl_status']:
            with self.assertRaises(ValueError): strict_data(u, topic)


if __name__ == '__main__': unittest.main()
