"""Result-only serialization safeguards; not flight/numerical acceptance tests."""
import math
from pathlib import Path
import tempfile
import unittest

import collect


class CollectionTests(unittest.TestCase):
    def test_type_strict_comparison(self):
        self.assertFalse(collect.exact({'x': 1}, {'x': 1.0}))
        self.assertFalse(collect.exact([1], [True]))
        self.assertTrue(collect.exact([math.inf, 0.1], [math.inf, 0.1]))

    def test_only_known_unlimited_diagnostics_allowed(self):
        value = {'height_task': {'heading': {'latest_position': {'vxy_max': math.inf}}}}
        collect.check_nonfinite(value, diagnostic=True)
        with self.assertRaises(AssertionError):
            collect.check_nonfinite(value)
        for value in ({'rmse': math.inf}, {'height_task': {'unknown': math.inf}}, {'rmse': math.nan}):
            with self.assertRaises(AssertionError):
                collect.check_nonfinite(value, diagnostic=True)

    def test_finite_values_unchanged(self):
        value = {'x': [0.0, -1.25, 7, True, None]}
        self.assertEqual(collect.json_view(value), value)

    def test_nonfinite_are_distinct_explicit_tags(self):
        for value, name in ((math.inf, 'Infinity'), (-math.inf, '-Infinity'), (math.nan, 'NaN')):
            with self.subTest(name=name):
                self.assertEqual(collect.json_view(value), {'nonfinite_float': name})

    def test_original_is_not_mutated(self):
        value = {'limits': [math.inf, 3.5]}
        self.assertEqual(collect.json_view(value)['limits'][1], 3.5)
        self.assertTrue(math.isinf(value['limits'][0]))

    def test_saved_summary_is_strict_json_and_repeatable(self):
        with tempfile.TemporaryDirectory(prefix='ri03-result-test-') as directory:
            path = Path(directory) / 'summary.json'
            value = {'limit': math.inf, 'rmse': 0.03}
            collect.save(path, value)
            raw = path.read_bytes()
            collect.save(path, value)
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(collect.read(path), {'limit': {'nonfinite_float': 'Infinity'}, 'rmse': 0.03})

    def test_changed_result_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(prefix='ri03-result-test-') as directory:
            path = Path(directory) / 'summary.json'
            collect.save(path, {'rmse': 0.1})
            with self.assertRaises(AssertionError):
                collect.save(path, {'rmse': 0.0})
            self.assertEqual(collect.read(path), {'rmse': 0.1})


if __name__ == '__main__':
    unittest.main()
