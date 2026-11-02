"""B04 frozen qualification/lineage tests. No ROS, simulator or flight."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import freeze
import test_freeze as old_tests


class FinalLineageTests(unittest.TestCase):
    def setUp(self):
        self.base = old_tests.DiagnosticRevisionTests()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.old = self.base.new
        self.new = self.base.root / 'b04'
        self.old.mkdir()
        self.manifest = self.old / 'manifest.json'
        self.history = freeze.diagnostic_revision_lineage(self.old, self.base.manifest)
        self.manifest.write_text(json.dumps(dict(max_attempts=8, data_root=str(self.old),
            revision=freeze.DIAGNOSTIC_REVISION, budget_history=self.history)))
        self.rows = []
        for original in self.base.rows:
            row = dict(original, task_completed=True, manifest_sha256=freeze.sha256(self.manifest))
            row.pop('error', None)
            if not row['success']:
                row['analysis_error'] = "ValueError('Heading evidence: unexpected reset_vel_to_gps')"
            directory = self.old / 'runs' / row['id']
            directory.mkdir(parents=True)
            log = directory / 'synthetic-not-a-flight.ulg'
            log.write_bytes(b'not a ULog; lineage hash fixture only')
            row['logs'] = [dict(archive=str(log), sha256=freeze.sha256(log))]
            self.rows.append(row)
        self.save()

    def save(self):
        for row in self.rows:
            (self.old / 'runs' / row['id'] / 'result.json').write_text(json.dumps(row))

    def lineage(self):
        return freeze.final_capture_lineage(self.new, self.manifest)

    def test_five_old_plus_eight_new_closes_six_without_reuse(self):
        original = {p: p.read_bytes() for p in self.base.root.rglob('*') if p.is_file()}
        result = self.lineage()
        self.assertEqual((result['prior_total_attempts'], result['new_max_attempts'],
                          result['cumulative_max_attempts']), (5, 8, 13))
        self.assertEqual(result['old_unexecuted_jobs_closed'], 6)
        self.assertTrue(result['historical_successes_not_imported'])
        self.assertEqual({p: p.read_bytes() for p in original}, original)

    def test_all_three_old_roots_and_parent_overlap_rejected(self):
        for path in (self.old, self.base.old, self.base.ancestor, self.base.root, self.old / 'child'):
            self.new = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.lineage()

    def test_extra_attempt_or_incomplete_native_task_rejected(self):
        self.rows[1]['task_completed'] = False; self.save()
        with self.assertRaises(ValueError): self.lineage()
        self.rows[1]['task_completed'] = True; self.save()
        (self.old / 'runs/O003').mkdir()
        with self.assertRaisesRegex(ValueError, 'Exactly two'): self.lineage()

    def test_wrong_failure_cannot_authorize_general_retry(self):
        self.rows[1]['analysis_error'] = 'safety failure'; self.save()
        with self.assertRaisesRegex(ValueError, 'Unexpected B03'): self.lineage()

    def test_wrong_restore_accepted_identity_and_fingerprint_rejected(self):
        originals = copy.deepcopy(self.rows)
        for index, key, value in ((0, 'success', False), (0, 'independent_replay_passed', False),
                (1, 'parameter_restore_exact', False), (1, 'system', 'RSTA'), (1, 'task', 'velocity'),
                (1, 'finished_utc', None), (1, 'remaining_simulators', [1]), (1, 'manifest_sha256', 'bad'),
                (1, 'logs', [])):
            self.rows = copy.deepcopy(originals); self.rows[index][key] = value; self.save()
            with self.subTest(key=key), self.assertRaises(ValueError): self.lineage()

    def test_ulog_and_ancestor_result_tampering_rejected(self):
        log = Path(self.rows[1]['logs'][0]['archive'])
        raw = log.read_bytes(); log.write_bytes(raw + b'x')
        with self.assertRaisesRegex(ValueError, 'ULog'): self.lineage()
        log.write_bytes(raw)
        first = self.base.ancestor / 'runs/O001/result.json'
        first.write_text(first.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'Ancestor'): self.lineage()

    def test_wrong_revision_and_fake_ancestor_count_rejected(self):
        old = json.loads(self.manifest.read_text())
        for change in ('revision', 'count'):
            value = copy.deepcopy(old)
            if change == 'revision': value['revision'] = 'anything'
            else: value['budget_history']['prior_total_attempts'] = 1
            self.manifest.write_text(json.dumps(value))
            with self.subTest(change=change), self.assertRaises(ValueError): self.lineage()

    def test_new_revision_requires_explicit_predecessor_and_heading_policy(self):
        for kwargs in ({}, {'heading_policy': freeze.POLICY}, {'previous_manifest': self.manifest}):
            with patch.object(freeze.subprocess, 'run') as external:
                with self.assertRaises(ValueError):
                    freeze.make_manifest(self.new, 'missing', revision=freeze.FINAL_CAPTURE_REVISION, **kwargs)
                external.assert_not_called()


class CombinedQualificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'qualification.json'
        self.original = json.loads((freeze.HERE / 'results/landing_fix01/validation01.json').read_text())
        # Synthetic qualification fixture: no flight and no new acceptance.
        self.original['source_sha256'] = {str(p.resolve()): freeze.sha256(p) for p in freeze.HERE.glob('*.py')}
        self.evidence = copy.deepcopy(self.original)

    def check(self):
        self.path.write_text(json.dumps(self.evidence))
        return freeze.final_capture_qualification(self.path)

    def test_complete_three_suites_and_history_are_bound_to_current_sources(self):
        evidence = self.check()
        self.assertEqual(evidence['total_tests'], 411)
        self.assertIn(str(freeze.HERE / 'freeze.py'), evidence['assets'])
        self.assertEqual(len(self.evidence['history']['protected_sha256']), 209)

    def test_missing_tool_or_changed_source_is_not_qualified(self):
        self.evidence['source_sha256'].pop(str(freeze.HERE / 'freeze.py'))
        with self.assertRaisesRegex(ValueError, 'complete tool set'): self.check()
        self.evidence = copy.deepcopy(self.original)
        self.evidence['source_sha256'][str(freeze.HERE / 'run.py')] = 'changed'
        with self.assertRaisesRegex(ValueError, 'Qualified source changed'): self.check()

    def test_failed_missing_wrong_or_duplicate_test_suites_rejected(self):
        for mutate in (lambda e: e['test_commands'].pop(),
                       lambda e: e['test_commands'][0].update(exit_code=1),
                       lambda e: e['test_commands'][0].update(log_sha256='changed'),
                       lambda e: e['test_commands'][0]['argv'].__setitem__(6, '/tmp/irrelevant'),
                       lambda e: e['test_commands'].__setitem__(1, copy.deepcopy(e['test_commands'][0]))):
            self.evidence = copy.deepcopy(self.original); mutate(self.evidence)
            with self.assertRaises(ValueError): self.check()

    def test_tail_bypass_changed_threshold_or_reclassification_rejected(self):
        for key, value in (('full_diagnostic_chain_passed', False), ('deterministic_analysis_replay', False),
                           ('historical_acceptance_changed', True), ('flight_accepted', True),
                           ('actual_new_flights', 1), ('unchanged_max_gap_us', 1000000), ('negative_probes', [])):
            self.evidence = copy.deepcopy(self.original); self.evidence['tail_probe'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.check()

    def test_history_evidence_missing_or_fingerprint_changed_rejected(self):
        self.evidence['history']['ulog_count'] = 8
        with self.assertRaises(ValueError): self.check()
        self.evidence = copy.deepcopy(self.original)
        key = next(iter(self.evidence['history']['protected_sha256']))
        self.evidence['history']['protected_sha256'][key] = 'changed'
        with self.assertRaisesRegex(ValueError, 'Historical evidence changed'): self.check()

    def test_zero_skips_failures_or_appended_test_run_not_accepted(self):
        log = Path(self.temp.name) / 'offline.log'
        for text in ('Ran 0 tests in 0.1s\n\nOK\n', 'Ran 2 tests in 0.1s\n\nOK (skipped=1)\n',
                     'Ran 2 tests in 0.1s\nFAILED (failures=1)\n',
                     'Ran 1 test in 0.1s\nOK\nRan 2 tests in 0.1s\nOK\n'):
            log.write_text(text)
            with self.assertRaises(ValueError): freeze.offline_test_count(log)
        log.write_text('Ran 2 tests in 0.1s\n\nOK\n')
        self.assertEqual(freeze.offline_test_count(log), 2)


if __name__ == '__main__':
    unittest.main()
