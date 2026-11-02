import unittest
from ros_bridge import check_native_source, forwarded_runner_heartbeat


class ForwardingTests(unittest.TestCase):
    def test_only_known_gcs_heartbeat_is_ignored(self):
        self.assertTrue(forwarded_runner_heartbeat('HEARTBEAT', 255, 190, 6))
        for args in (('HEARTBEAT', 1, 1, 2), ('HEARTBEAT', 255, 191, 6),
                     ('HEARTBEAT', 255, 190, 2), ('LOCAL_POSITION_NED', 255, 190, 6),
                     ('HEARTBEAT', 254, 190, 6)):
            self.assertFalse(forwarded_runner_heartbeat(*args))

    def test_gcs_is_still_not_native_measurement_source(self):
        with self.assertRaises(ValueError):
            check_native_source(255, 190)
        check_native_source(1, 1)


if __name__ == '__main__':
    unittest.main()
