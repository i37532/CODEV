import tempfile
from pathlib import Path
import unittest
from prestart_audit import capacity, sha, verify_assets, GIB, MIB


class PrestartTests(unittest.TestCase):
    def test_full_200_requires_51_0625_gib(self):
        self.assertEqual(capacity(0, 200)['required_bytes'], 54827941888)

    def test_one_byte_short_rejected(self):
        self.assertFalse(capacity(54827941887, 200)['passed'])

    def test_exact_boundary_accepted(self):
        self.assertTrue(capacity(54827941888, 200)['passed'])

    def test_no_runs_still_requires_reserve(self):
        self.assertFalse(capacity(12*GIB-1, 0)['passed'])
        self.assertTrue(capacity(12*GIB, 0)['passed'])

    def test_remaining_budget_formula(self):
        self.assertEqual(capacity(0, 120)['required_bytes'], 12*GIB+120*200*MIB)

    def test_invalid_inputs(self):
        for free, remaining in [(-1, 0), (True, 1), (0, -1), (0, 201), (0, 1.5)]:
            with self.assertRaises(ValueError):
                capacity(free, remaining)

    def test_matching_and_changed_asset(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'fixture'
            p.write_bytes(b'fixture')
            self.assertTrue(verify_assets({'fixture': sha(p)}, d)['passed'])
            self.assertFalse(verify_assets({'fixture': 'bad-sha'}, d)['passed'])

    def test_missing_asset_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(verify_assets({'missing': 'bad-sha'}, d)['passed'])


if __name__ == '__main__':
    unittest.main()
