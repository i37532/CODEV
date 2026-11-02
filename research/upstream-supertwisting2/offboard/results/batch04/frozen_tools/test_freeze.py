"""Offline revision bookkeeping. No simulator/runtime started by these tests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import freeze


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old = self.root/'old'
        (self.old/'runs/O001').mkdir(parents=True)
        self.manifest = self.old/'manifest.json'
        self.manifest.write_text(json.dumps(dict(max_attempts=8,data_root=str(self.old))))
        self.path = self.old/'runs/O001/result.json'
        self.result = dict(id='O001',success=False,independent_replay_passed=False,
            parameter_restore_exact=True,finished_utc='2026-11-02T04:05:28Z',remaining_simulators=[],
            manifest_sha256=freeze.sha256(self.manifest))
        self.save()

    def save(self): self.path.write_text(json.dumps(self.result))

    def test_new_eight_plus_old_one_never_reuses_old_samples(self):
        before = self.path.read_bytes()
        r=freeze.revision_lineage(self.root/'new',self.manifest)
        self.assertEqual((r['previous_attempts'],r['new_max_attempts'],r['cumulative_max_attempts']), (1,8,9))
        self.assertEqual(r['old_unexecuted_jobs_closed'],7)
        self.assertEqual(self.path.read_bytes(),before)

    def test_overlapping_data_roots_rejected(self):
        for path in (self.old,self.old/'new',self.root):
            with self.subTest(path=path),self.assertRaises(ValueError):
                freeze.revision_lineage(path,self.manifest)

    def test_no_extra_prior_attempts_hidden(self):
        (self.old/'runs/O002').mkdir()
        with self.assertRaises(ValueError):freeze.revision_lineage(self.root/'new',self.manifest)

    def test_incomplete_or_accepted_prior_attempt_rejected(self):
        original=dict(self.result)
        for key,value in [('success',True),('independent_replay_passed',True),('parameter_restore_exact',False),
            ('finished_utc',None),('remaining_simulators',[123]),('manifest_sha256','wrong')]:
            self.result=dict(original,**{key:value});self.save()
            with self.subTest(key=key),self.assertRaises(ValueError):
                freeze.revision_lineage(self.root/'new',self.manifest)

    def test_new_policy_needs_lineage_before_runtime_or_source_reads(self):
        with patch.object(freeze.subprocess,'run') as command:
            with self.assertRaises(ValueError):
                freeze.make_manifest(self.root/'new','missing',heading_policy=freeze.POLICY)
            command.assert_not_called()

    def test_old_policy_cannot_hide_new_revision(self):
        with self.assertRaises(ValueError):
            freeze.make_manifest(self.root/'new','missing',previous_manifest=self.manifest)

    def test_unknown_policy_rejected(self):
        with self.assertRaises(ValueError):
            freeze.make_manifest(self.root/'new','missing',heading_policy='allow_all')


class DiagnosticRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ancestor = self.root/'b01'
        self.old = self.root/'b02'
        self.new = self.root/'b03'
        (self.ancestor/'runs/O001').mkdir(parents=True)
        self.first_manifest = self.ancestor/'manifest.json'
        self.first_manifest.write_text(json.dumps(dict(max_attempts=8,data_root=str(self.ancestor))))
        (self.ancestor/'runs/O001/result.json').write_text(json.dumps(dict(id='O001',
            success=False,independent_replay_passed=False,parameter_restore_exact=True,
            finished_utc='closed',remaining_simulators=[],
            manifest_sha256=freeze.sha256(self.first_manifest))))
        (self.old/'runs/O001').mkdir(parents=True)
        (self.old/'runs/O002').mkdir()
        self.manifest = self.old/'manifest.json'
        self.manifest.write_text(json.dumps(dict(max_attempts=8,data_root=str(self.old),
            budget_history=freeze.revision_lineage(self.old,self.first_manifest))))
        self.rows = []
        for index,system,success in ((1,'PID',True),(2,'STA2',False)):
            row=dict(id='O%03d'%index,system=system,task='position',success=success,
                independent_replay_passed=success,task_completed=success,
                parameter_restore_exact=True,finished_utc='closed',remaining_simulators=[],
                manifest_sha256=freeze.sha256(self.manifest))
            if not success:row['error']="ValueError('diagnostic attitude_sta_status must be a mapping')"
            self.rows.append(row)
        self.save()

    def save(self):
        for row in self.rows:
            (self.old/'runs'/row['id']/'result.json').write_text(json.dumps(row))

    def lineage(self):
        return freeze.diagnostic_revision_lineage(self.new,self.manifest)

    def test_three_historical_plus_eight_new_without_importing_success(self):
        before={p:p.read_bytes() for p in self.root.rglob('*.json')}
        result=self.lineage()
        self.assertEqual((result['prior_total_attempts'],result['new_max_attempts'],
                          result['cumulative_max_attempts']),(3,8,11))
        self.assertEqual(result['old_unexecuted_jobs_closed'],6)
        self.assertTrue(result['historical_successes_not_imported'])
        self.assertEqual(len(result['lineage_assets']),5)
        self.assertEqual({p:p.read_bytes() for p in before},before)

    def test_no_overlapping_ancestor_or_predecessor_root(self):
        for root in (self.old,self.ancestor,self.root,self.old/'child',self.ancestor/'child'):
            self.new=root
            with self.subTest(root=root),self.assertRaises(ValueError):self.lineage()

    def test_no_unreported_prior_attempt(self):
        (self.old/'runs/O003').mkdir()
        with self.assertRaises(ValueError):self.lineage()

    def test_ancestor_tampering_rejected(self):
        path=self.ancestor/'runs/O001/result.json'
        path.write_text(path.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'Ancestor'):self.lineage()

    def test_incomplete_or_misidentified_results_rejected(self):
        originals=[dict(r) for r in self.rows]
        for i,key,value in ((0,'task_completed',False),(0,'success',False),
            (0,'independent_replay_passed',False),(1,'success',True),(1,'system','RSTA'),
            (1,'task','velocity'),(1,'parameter_restore_exact',False),(1,'finished_utc',None),
            (1,'remaining_simulators',[9]),(1,'manifest_sha256','wrong')):
            self.rows=[dict(r) for r in originals];self.rows[i][key]=value;self.save()
            with self.subTest(i=i,key=key),self.assertRaises(ValueError):self.lineage()

    def test_other_failure_does_not_inherit_wiring_fix_authority(self):
        self.rows[1]['error']='safety failure';self.save()
        with self.assertRaisesRegex(ValueError,'Unexpected B02'):self.lineage()

    def test_unknown_revision_rejected_before_external_calls(self):
        with patch.object(freeze.subprocess,'run') as command:
            with self.assertRaises(ValueError):
                freeze.make_manifest(self.new,'missing',revision='ignore_failures')
            command.assert_not_called()

    def test_revision_requires_previous_batch_and_explicit_policy(self):
        for kwargs in ({},{'heading_policy':freeze.POLICY},
                       {'previous_manifest':self.manifest}):
            with self.subTest(kwargs=kwargs),patch.object(freeze.subprocess,'run') as command:
                with self.assertRaises(ValueError):
                    freeze.make_manifest(self.new,'missing',revision=freeze.DIAGNOSTIC_REVISION,**kwargs)
                command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
