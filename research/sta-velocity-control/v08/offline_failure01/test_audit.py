import unittest
import numpy as np
from audit import listener_clock, sequence


def command(timestamp=113508000, age='0.008000'):
    return dict(cmd=['/bin/px4-listener', 'sta_velocity_ctrl_status', '-n', '1'],
                returncode=0, stdout=f'TOPIC: sta_velocity_ctrl_status\n timestamp: {timestamp}  ({age} seconds ago)\n')


class ClockAudit(unittest.TestCase):
    def test_cross_read_difference_is_not_publication_age(self):
        r = listener_clock(command(), 'sta_velocity_ctrl_status')
        self.assertEqual(r['printed_age_us'], 8000)
        self.assertEqual(r['timestamp_us'] - 112320000, 1188000)
        self.assertFalse(r['host_delivery_latency_known'])

    def test_exact_limit_and_neighbors(self):
        for value in ('0.999999', '1.000000'):
            listener_clock(command(age=value), 'sta_velocity_ctrl_status')
        with self.assertRaises(ValueError):
            listener_clock(command(age='1.000001'), 'sta_velocity_ctrl_status')

    def test_invalid_or_future_timestamp(self):
        for c in (command(timestamp=0), command(age='-0.000001'),
                  command(age='18446744073709.551616'), command(age='nan'), command(age='inf')):
            with self.assertRaises(ValueError): listener_clock(c, 'sta_velocity_ctrl_status')

    def test_missing_duplicate_or_ambiguous_fields(self):
        for suffix in (' timestamp: 1\n', command()['stdout'], 'TOPIC: different\n'):
            c = command(); c['stdout'] += suffix
            with self.assertRaises(ValueError): listener_clock(c, 'sta_velocity_ctrl_status')
        c = command(); c['stdout'] = c['stdout'].replace('seconds ago', 'unknown')
        with self.assertRaises(ValueError): listener_clock(c, 'sta_velocity_ctrl_status')

    def test_wrong_failed_command(self):
        for key, value in (('returncode', 1), ('cmd', ['/bin/px4-listener','other','-n','1'])):
            c = command(); c[key] = value
            with self.assertRaises(ValueError): listener_clock(c, 'sta_velocity_ctrl_status')

    def test_sequence_wrap_allowed_not_gap_or_repeat(self):
        d = dict(timestamp=np.array([4,8,12]), timestamp_sample=np.array([4,8,12]),
                 publish_seq=np.array([2**32-1,0,1]))
        self.assertEqual(sequence(d, 'publish_seq')['sequence_gaps'], 0)
        for seq in ([1,1,2], [1,3,4], [1,0,1]):
            with self.assertRaises(ValueError): sequence({**d,'publish_seq':np.array(seq)},'publish_seq')

    def test_sample_and_publication_clock_reject(self):
        d = dict(timestamp=np.array([4,8,12]), timestamp_sample=np.array([4,8,12]),
                 publish_seq=np.array([1,2,3]))
        for key, values in [('timestamp',[4,4,12]),('timestamp_sample',[4,3,12]),
                            ('timestamp_sample',[4,9,12])]:
            with self.assertRaises(ValueError): sequence({**d,key:np.array(values)},'publish_seq')


if __name__ == '__main__': unittest.main()
