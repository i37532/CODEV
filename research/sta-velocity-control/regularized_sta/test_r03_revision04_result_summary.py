"""Temporary synthetic files only; no flight, real ledger mutation or gate creation."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

PATH=Path(__file__).with_name('r03_revision04_result_summary.py')
SPEC=importlib.util.spec_from_file_location('_r03_result_summary_test',PATH)
s=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(s)


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='r03-summary-test-')
        self.root=Path(self.temp.name)
        self.api=types.SimpleNamespace(REPO=self.root/'repo',EXTERNAL=self.root/'data',
            DATA_STAGE='R03_revision04',REVISION='r03_revision04',GATES={'A':{}},
            validate_manifest=lambda:True)
        self.jobs=[dict(id=f'run{i+1:03d}',gate='A',revision='r03_revision04',
            candidate=('PID','ESTA','RSTA')[i%3],mode=(0,1,3)[i%3],axes=0 if i%3==0 else 1,
            seed=101+i//3,main_duration_s=32) for i in range(9)]
        self.api.design=lambda:dict(jobs=copy.deepcopy(self.jobs))
        self.gate=self.api.EXTERNAL/self.api.DATA_STAGE/'A'
        self.batch=self.gate/'batch01'
        self.proof=types.SimpleNamespace(verify_complete=Mock(side_effect=AssertionError('Do not verify without receipt')))

    def tearDown(self):
        self.temp.cleanup()

    def save(self,path,data):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(data))

    def seed(self,n=3,failed=False):
        ledger=dict(stage='R03-revision04-A',gate='A',revision='r03_revision04',planned=9,total_budget=51,
            source_head='a'*40,firmware_sha256='b'*64,success=False,parameter_restore_exact=True,
            remaining_simulators=[],attempts=[],pairs=[])
        for i,job in enumerate(self.jobs[:n]):
            run=self.batch/job['id']; run.mkdir(parents=True)
            result=dict(success=not(failed and i==n-1),source_head='a'*40,binary_sha256='b'*64,
                events=[dict(name=x) for x in ('ready','takeoff_command','hover_start','landed_disarmed')],logs=[])
            self.save(run/'result.json',result)
            d=dict(error=dict(rmse=[.1,.2,.3]),J=.2,seconds=32)
            for stem in ('correction','acceleration','normalized_thrust'):
                d[stem+'_tv']=[1.,2.,3.];d[stem+'_tv_per_second']=[1/32,2/32,3/32]
            m=dict(accepted=True,job=job,diagnostic=d,
                binding=dict(revision='r03_revision04',gate='A',source_head='a'*40,firmware_sha256='b'*64))
            self.save(run/'r03_metrics.json',m)
            ledger['attempts'].append(dict(attempt=i+1,job=job,directory=str(run),
                status='failed' if failed and i==n-1 else 'accepted',metrics_sha256=s.digest(run/'r03_metrics.json')))
        self.save(self.batch/'ledger.json',ledger)
        return ledger

    def summary(self):
        return s.gate_summary(self.api,self.proof,'A')

    def change_metrics(self,mutation):
        path=self.batch/'run001/r03_metrics.json';m=s.read(path);mutation(m);self.save(path,m)
        ledger=s.read(self.batch/'ledger.json');ledger['attempts'][0]['metrics_sha256']=s.digest(path)
        self.save(self.batch/'ledger.json',ledger)

    def test_absent_ledger_counts_are_unknown_not_zero_or_pass(self):
        d=self.summary();self.assertEqual(d['status'],'pending');self.assertEqual(d['planned'],9)
        for k in ('attempted','accepted_recorded','failed','unattempted','takeoff_commands'):
            self.assertIsNone(d[k])
        self.assertIsNone(d['algorithms']);self.proof.verify_complete.assert_not_called()

    def test_partial_accepted_runs_have_per_algorithm_means_but_no_gate_pass(self):
        self.seed();d=self.summary();self.assertEqual(d['attempted'],3);self.assertEqual(d['accepted_recorded'],3)
        self.assertEqual(d['accepted_metrics_verified'],3);self.assertEqual(d['unattempted'],6)
        self.assertEqual(d['takeoff_commands'],3);self.assertEqual(d['airborne_task_reached'],3)
        self.assertEqual(d['status'],'pending');self.assertFalse(d['gate_passed'])
        for a in s.ALGORITHMS:
            self.assertEqual(d['algorithms'][a]['n'],1);self.assertEqual(d['algorithms'][a]['J_m_s'],.2)
            self.assertEqual(d['algorithms'][a]['correction_tv_per_second'],[1/32,2/32,3/32])

    def test_failed_attempt_preserved_and_excluded_not_zero_imputed(self):
        self.seed(failed=True);d=self.summary();self.assertEqual(d['failed'],1)
        self.assertEqual(d['accepted_metrics_verified'],2);self.assertEqual(d['status'],'stopped_failed')
        self.assertEqual(d['algorithms']['RSTA']['n'],0);self.assertNotIn('J_m_s',d['algorithms']['RSTA'])
        self.assertEqual(d['rows'][2]['status'],'failed')

    def test_missing_result_remains_unknown(self):
        self.seed();(self.batch/'run001/result.json').unlink()
        d=self.summary();self.assertEqual(d['missing_results'],1);self.assertIsNone(d['takeoff_commands'])
        self.assertFalse(d['rows'][0]['metrics_verified'])

    def test_takeoff_command_is_not_physical_airborne_proof(self):
        self.seed(1);p=self.batch/'run001/result.json';v=s.read(p)
        v['events']=[dict(name='ready'),dict(name='takeoff_command')];self.save(p,v)
        d=self.summary();self.assertEqual(d['takeoff_commands'],1);self.assertEqual(d['airborne_task_reached'],0)

    def test_missing_or_modified_metrics_excluded(self):
        self.seed();(self.batch/'run001/r03_metrics.json').unlink()
        path=self.batch/'run002/r03_metrics.json';path.write_text(path.read_text()+' ')
        d=self.summary();self.assertEqual(d['missing_metrics'],1);self.assertEqual(d['accepted_metrics_verified'],1)
        self.assertEqual(d['accepted_recorded'],3);self.assertFalse(d['gate_passed'])

    def test_foreign_source_job_or_binding_cannot_enter_means(self):
        self.seed(1)
        for mutation in (lambda d:d['job'].update(seed=9),lambda d:d['binding'].update(revision='r03'),
                         lambda d:d['binding'].update(source_head='c'*40)):
            original=s.read(self.batch/'run001/r03_metrics.json')
            self.change_metrics(mutation);self.assertEqual(self.summary()['accepted_metrics_verified'],0)
            self.save(self.batch/'run001/r03_metrics.json',original)

    def test_invalid_j_window_tv_or_nonfinite_metric_not_silently_averaged(self):
        self.seed(1)
        for mutation in (lambda d:d['diagnostic'].update(J=0),lambda d:d['diagnostic'].update(seconds=64),
                         lambda d:d['diagnostic'].update(correction_tv_per_second=[1,2,3]),
                         lambda d:d['diagnostic']['error'].update(rmse=[float('nan'),.2,.3]),
                         lambda d:d['diagnostic']['error'].update(rmse=[True,.2,.3])):
            original=s.read(self.batch/'run001/r03_metrics.json')
            self.change_metrics(mutation);self.assertEqual(self.summary()['accepted_metrics_verified'],0)
            self.save(self.batch/'run001/r03_metrics.json',original)

    def test_completed_ledger_without_gate_receipt_is_still_pending(self):
        ledger=self.seed(9);ledger['success']=True;self.save(self.batch/'ledger.json',ledger)
        d=self.summary();self.assertEqual(d['status'],'pending');self.proof.verify_complete.assert_not_called()

    def test_pass_requires_original_receipt_and_matching_full_readonly_proof(self):
        self.seed(9);receipt=dict(success=True,accepted=9,independent_replays=9,paired_checks=6)
        self.save(self.gate/'gate_pass.json',receipt)
        self.proof.verify_complete=Mock(return_value=receipt)
        d=self.summary();self.assertTrue(d['gate_passed']);self.assertEqual(d['status'],'passed')
        self.proof.verify_complete.assert_called_once_with('A',self.gate)

    def test_receipt_alone_or_mismatched_recomputed_proof_never_passes(self):
        self.seed(9);self.save(self.gate/'gate_pass.json',dict(success=True))
        self.proof.verify_complete=Mock(side_effect=ValueError('raw input mismatch'))
        self.assertEqual(self.summary()['status'],'evidence_error')
        self.proof.verify_complete=Mock(return_value=dict(success=True,accepted=9,independent_replays=9,paired_checks=6))
        self.assertFalse(self.summary()['gate_passed'])

    def test_reordered_job_and_orphan_directory_rejected(self):
        ledger=self.seed();ledger['attempts'][0]['job']=copy.deepcopy(self.jobs[1])
        self.save(self.batch/'ledger.json',ledger);self.assertEqual(self.summary()['status'],'evidence_error')
        ledger['attempts'][0]['job']=self.jobs[0];self.save(self.batch/'ledger.json',ledger)
        (self.batch/'run009').mkdir();self.assertEqual(self.summary()['status'],'evidence_error')

    def test_replay_counts_are_recorded_not_automatic_pass(self):
        self.seed();self.save(self.gate/'replay01/summary.json',dict(revision='r03_revision04',gate='A',replayed=3))
        d=self.summary();self.assertEqual(d['independent_replays_recorded'],3);self.assertFalse(d['gate_passed'])

    def test_wrong_replay_filename_never_counts_as_actual_summary(self):
        self.seed();self.save(self.gate/'replay01/evidence.json',dict(revision='r03_revision04',gate='A',replayed=3))
        d=self.summary();self.assertIsNone(d['replay']);self.assertIsNone(d['independent_replays_recorded'])

    def test_replayed_is_bounded_integer_count_not_list_bool_or_float(self):
        self.seed()
        for count in ([],[1,2,3],True,3.0,-1,4,None):
            self.save(self.gate/'replay01/summary.json',dict(revision='r03_revision04',gate='A',replayed=count))
            with self.subTest(count=count):
                d=self.summary();self.assertEqual(d['status'],'evidence_error');self.assertFalse(d['gate_passed'])

    def test_ledger_change_during_read_invalidates_snapshot(self):
        self.seed();original=s.digest;counter=[0]
        def digest(path):
            if Path(path)==self.batch/'ledger.json':
                counter[0]+=1
                if counter[0]>=3:return 'f'*64
            return original(path)
        with patch.object(s,'digest',side_effect=digest):
            d=self.summary();self.assertEqual(d['status'],'changed_during_read');self.assertFalse(d['gate_passed'])

    def test_output_only_fresh_summary_location_and_never_overwrites(self):
        dest=self.api.EXTERNAL/'R03_revision04_summaries/test01'
        s.write_fresh(dest,{'new_flights':0},self.api)
        self.assertEqual(s.read(dest/'summary.json'),{'new_flights':0})
        with self.assertRaises(FileExistsError):s.write_fresh(dest,{},self.api)
        for bad in (self.batch/'summary01',self.api.REPO/'output',self.api.EXTERNAL/'R03_revision03/out'):
            with self.subTest(path=bad),self.assertRaises(ValueError):s.write_fresh(bad,{},self.api)

    def test_overall_missing_gate_stays_unverified_and_history_not_pooled(self):
        d=s.summarize(api=self.api,proof=self.proof)
        self.assertFalse(d['all_four_gates_verified']);self.assertFalse(d['historical']['pooled_into_new_results'])
        self.assertIn('not PID-axis',d['definitions']['pid_calls'])


if __name__ == '__main__':
    unittest.main()
