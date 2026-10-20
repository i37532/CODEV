"""Offline receipt tests, never a source of flight authorization."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('revision06_diagnostic_receipt_tests', Path(__file__).with_name('verify.py'))
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class DiagnosticReceipts(unittest.TestCase):
    def setUp(self):
        self.source = Path('/fixture/old/D/run028')
        self.binding = {'adapter_sha256': 'a'*64, 'complete_direct_symbol_binding': True}
        self.record = dict(diagnostic_checks_complete=True, source_inputs_unchanged=True,
            historical_acceptance_unchanged=True, accepted=False, flight_accepted=False,
            execution_authority_granted=False, original_accepted=False, new_flights=0,
            source_directory=str(self.source), handoff_dependency_binding=copy.deepcopy(self.binding))
        self.metrics = dict(accepted=False, flight_accepted=False, diagnostic_only=True,
            new_flights=0, execution_authority_granted=False, diagnostic_checks_complete=True,
            handoff_dependency_binding=copy.deepcopy(self.binding))

    def check(self, original=False):
        v.validate_handoff_diagnostic(self.record, self.metrics, self.source, original, self.binding)

    def test_failed_old_run_remains_nonaccepted(self):
        self.check()

    def test_retained_pass_is_diagnostic_not_new_acceptance(self):
        self.record['original_accepted'] = True
        self.check(True)
        self.assertIs(self.metrics['accepted'], False)

    def test_false_or_missing_complete_checks_rejected(self):
        for key in ('diagnostic_checks_complete', 'source_inputs_unchanged', 'historical_acceptance_unchanged'):
            with self.subTest(key=key):
                saved = self.record.pop(key)
                with self.assertRaises(ValueError): self.check()
                self.record[key] = False
                with self.assertRaises(ValueError): self.check()
                self.record[key] = saved

    def test_summary_cannot_grant_authority(self):
        for key in ('accepted', 'flight_accepted', 'execution_authority_granted'):
            with self.subTest(key=key):
                self.record[key] = True
                with self.assertRaises(ValueError): self.check()
                self.record[key] = False

    def test_metric_cannot_grant_authority(self):
        for key in ('accepted', 'flight_accepted', 'execution_authority_granted'):
            with self.subTest(key=key):
                self.metrics[key] = True
                with self.assertRaises(ValueError): self.check()
                self.metrics[key] = False

    def test_metric_incomplete_or_not_diagnostic_rejected(self):
        for key in ('diagnostic_only', 'diagnostic_checks_complete'):
            with self.subTest(key=key):
                self.metrics[key] = False
                with self.assertRaises(ValueError): self.check()
                self.metrics[key] = True

    def test_zero_flight_requires_integer_not_boolean_or_float(self):
        for target in (self.record, self.metrics):
            for wrong in (False, 0.0, 1, None):
                with self.subTest(wrong=wrong):
                    target['new_flights'] = wrong
                    with self.assertRaises(ValueError): self.check()
            target['new_flights'] = 0

    def test_original_verdict_cannot_be_reclassified(self):
        for value in (True, 0, None):
            self.record['original_accepted'] = value
            with self.assertRaises(ValueError): self.check()

    def test_wrong_original_source_rejected(self):
        self.record['source_directory'] = '/fixture/another/run028'
        with self.assertRaises(ValueError): self.check()

    def test_missing_changed_or_old_component_binding_rejected(self):
        for target in (self.record, self.metrics):
            for wrong in (None, {}, {'adapter_sha256': 'b'*64}, {**self.binding, 'complete_direct_symbol_binding': 1}):
                target['handoff_dependency_binding'] = wrong
                with self.assertRaises(ValueError): self.check()
            target['handoff_dependency_binding'] = copy.deepcopy(self.binding)

    def test_metric_comparison_keeps_types_nan_and_list_order(self):
        self.assertTrue(v.diagnostic_metrics_equal({'a': float('nan'), 'b': [1, 2]}, {'b': [1, 2], 'a': float('nan')}))
        self.assertFalse(v.diagnostic_metrics_equal({'a': 1}, {'a': 1.0}))
        self.assertFalse(v.diagnostic_metrics_equal({'a': [1, 2]}, {'a': [2, 1]}))
        self.assertFalse(v.diagnostic_metrics_equal({'a': float('nan')}, {'a': None}))


if __name__ == '__main__':
    unittest.main(verbosity=2)
