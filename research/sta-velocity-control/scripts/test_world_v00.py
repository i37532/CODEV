import copy
import os
from pathlib import Path
import unittest
from world_v00 import process_record, validate_world, ENV_KEYS


class WorldTest(unittest.TestCase):
    def setUp(self):
        self.world = Path('/repo/sitl/worlds/empty_grey.world')
        self.master = 'http://127.0.0.1:11345'
        self.record = dict(pid=124, sid=123, comm='gzserver',
                           argv=['gzserver', str(self.world)],
                           environment={'PX4_SITL_WORLD': str(self.world), 'GAZEBO_MASTER_URI': self.master})

    def check(self, records, pid=123, sid=123):
        return validate_world(records, pid, sid, self.world, self.master)

    def test_actual_world_without_console_world(self):
        self.assertEqual(self.check([self.record]), self.record)

    def test_correct_environment_cannot_hide_wrong_argv(self):
        self.record['argv'][1] = '/repo/other.world'
        with self.assertRaises(RuntimeError):
            self.check([self.record])

    def test_unrelated_session_rejected(self):
        self.record['sid'] = 999
        with self.assertRaises(RuntimeError):
            self.check([self.record])

    def test_missing_or_multiple_servers_rejected(self):
        for records in ([], [self.record, copy.deepcopy(self.record)]):
            with self.subTest(records=records), self.assertRaises(RuntimeError):
                self.check(records)

    def test_launcher_session_leader_required(self):
        for pid, sid in ((123, 999), (0, 0)):
            with self.subTest(pid=pid), self.assertRaises(RuntimeError):
                self.check([self.record], pid, sid)

    def test_missing_wrong_or_relative_world_argv(self):
        for args in (['gzserver'], ['gzserver', 'empty_grey.world'],
                     ['gzserver', str(self.world), '/other.world']):
            self.record['argv'] = args
            with self.subTest(argv=args), self.assertRaises(RuntimeError):
                self.check([self.record])

    def test_wrong_environment_or_master_rejected(self):
        for key in ENV_KEYS:
            for value in (None, 'incorrect'):
                record = copy.deepcopy(self.record)
                if value is None:
                    del record['environment'][key]
                else:
                    record['environment'][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                    self.check([record])

    def test_wrong_process_name_rejected(self):
        self.record['comm'] = 'python3'
        with self.assertRaises(RuntimeError):
            self.check([self.record])

    def test_live_proc_reader_without_simulator(self):
        record = process_record(os.getpid())
        self.assertEqual(record['sid'], os.getsid(0))
        self.assertTrue(record['argv'])
        self.assertLessEqual(set(record['environment']), set(ENV_KEYS))


if __name__ == '__main__':
    unittest.main()
