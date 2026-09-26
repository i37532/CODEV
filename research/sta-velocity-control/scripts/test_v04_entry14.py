import copy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import numpy as np
from v04_entry14 import check_entry_window, entry_ready, advance_entry
from v04_task04 import EntryGate


class Log:
    def __init__(self, topics): self.topics = topics
    def get_dataset(self, name): return SimpleNamespace(data=self.topics[name])


def fixture():
    t = np.arange(1000000, 4010000, 10000, dtype=np.uint64)
    pos = dict(timestamp=t.copy(), timestamp_sample=t.copy(), z=np.full(len(t), -2.5), vz=np.zeros(len(t)))
    for key in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid'): pos[key] = np.ones(len(t), dtype=bool)
    return Log(dict(vehicle_local_position=pos,
        trajectory_setpoint=dict(timestamp=t.copy(), z=np.full(len(t), -2.5), vz=np.zeros(len(t)), yaw=np.zeros(len(t))),
        vehicle_status=dict(timestamp=t.copy(), arming_state=np.full(len(t), 2), nav_state=np.full(len(t), 4), failsafe=np.zeros(len(t))),
        vehicle_land_detected=dict(timestamp=t.copy(), landed=np.zeros(len(t)), ground_contact=np.zeros(len(t))),
        sta_velocity_ctrl_status={'timestamp':t.copy(), 'p_sp[2]':np.full(len(t), -2.5)})), dict(position=dict(z=0), target_z=-2.5, yaw=0)


class RawEntry14(unittest.TestCase):
    def test_complete_contiguous_window(self):
        u, r = fixture(); self.assertTrue(entry_ready(u, r, 4000000)['ready'])

    def test_future_converged_target_cannot_fix_previous_sample(self):
        u, r = fixture(); u.topics['trajectory_setpoint']['z'][:12] = -2.447
        self.assertFalse(entry_ready(u, r, 4000000)['ready'])
        # CLI looking 112 ms ahead would see convergence, but old raw rows remain mandatory.
        self.assertEqual(u.topics['trajectory_setpoint']['z'][12], -2.5)

    def test_single_bad_sample_between_good_host_polls(self):
        u, r = fixture(); u.topics['trajectory_setpoint']['vz'][155] = .051
        self.assertFalse(entry_ready(u, r, 4000000)['ready'])

    def test_no_prefix_future_match_or_large_gap(self):
        for mutator in [lambda u: u.topics['trajectory_setpoint']['timestamp'].__iadd__(10000),
                        lambda u: u.topics['vehicle_local_position']['timestamp'].__setitem__(150, 2600000)]:
            u, r = fixture(); mutator(u)
            with self.assertRaises(ValueError): entry_ready(u, r, 4000000)
        u, r = fixture()
        with self.assertRaises(ValueError): entry_ready(u, r, 4100000)

    def test_invalid_sample_clocks_never_pending(self):
        for value in [0, 1000000, 5000000]:
            u, r = fixture(); u.topics['vehicle_local_position']['timestamp_sample'][150] = value
            with self.assertRaisesRegex(ValueError, 'sample clock'): entry_ready(u, r, 4000000)

    def test_invalid_state_failsafe_nan_not_pending(self):
        for topic, field, value in [('vehicle_status', 'failsafe', 1), ('vehicle_status', 'nav_state', 18),
            ('vehicle_land_detected', 'landed', 1), ('vehicle_local_position', 'z_valid', 0),
            ('vehicle_local_position', 'z', np.nan), ('trajectory_setpoint', 'z', np.nan)]:
            u, r = fixture(); u.topics[topic][field][100] = value
            with self.assertRaises(ValueError): entry_ready(u, r, 4000000)

    def test_velocity_and_yaw_limits_unchanged(self):
        for topic, field, value in [('vehicle_local_position', 'vz', .2),
            ('trajectory_setpoint', 'vz', .05001), ('trajectory_setpoint', 'yaw', .001001),
            ('sta_velocity_ctrl_status', 'p_sp[2]', -2.449)]:
            u, r = fixture(); u.topics[topic][field][0] = value
            self.assertFalse(entry_ready(u, r, 4000000)['ready'])

    def test_no_source_mutation(self):
        u, r = fixture(); before = copy.deepcopy(u.topics)
        check_entry_window(u, r, 4000000)
        for topic, fields in before.items():
            for name, data in fields.items(): np.testing.assert_array_equal(data, u.topics[topic][name])

    def test_other_topic_duplicate_and_consumed_gap_are_fatal(self):
        for topic in ('trajectory_setpoint', 'vehicle_status', 'vehicle_land_detected', 'sta_velocity_ctrl_status'):
            u, r = fixture(); u.topics[topic]['timestamp'][150] = u.topics[topic]['timestamp'][149]
            with self.assertRaisesRegex(ValueError, 'Nonmonotonic'): entry_ready(u, r, 4000000)
        u, r = fixture()
        for key in u.topics['sta_velocity_ctrl_status']:
            u.topics['sta_velocity_ctrl_status'][key] = u.topics['sta_velocity_ctrl_status'][key][:10]
        with self.assertRaisesRegex(ValueError, 'Missing consumed'): entry_ready(u, r, 4000000)

    def test_runner_adapter_requires_both_gates(self):
        u, r = fixture(); gate = Mock(); reader = Mock(return_value=u)
        gate.update.return_value = False
        self.assertFalse(advance_entry(gate, 4000000, True, {}, reader, r, 4000000)['ready'])
        reader.assert_not_called(); gate.update.return_value = True
        u.topics['trajectory_setpoint']['z'][0] = -2.447
        self.assertFalse(advance_entry(gate, 4000000, True, {}, reader, r, 4000000)['ready'])
        u.topics['trajectory_setpoint']['z'][0] = -2.5
        self.assertTrue(advance_entry(gate, 4000000, True, {}, reader, r, 4000000)['ready'])

    def test_raw_pending_never_extends_original_deadline(self):
        gate = EntryGate(); reader = Mock(); diag = dict(timestamp_sample=4000000, excitation_time=-12)
        with patch('v04_entry14.entry_ready', return_value=dict(ready=False)):
            for t in range(4000000, 14000001, 500000):
                self.assertFalse(advance_entry(gate, t, True, diag, reader, {}, t)['ready'])
            with self.assertRaisesRegex(ValueError, 'gate\\+10s'):
                advance_entry(gate, 14500000, True, diag, reader, {}, 14500000)


if __name__ == '__main__': unittest.main()
