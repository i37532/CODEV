#!/usr/bin/env python3
"""Small temporary-fixture summary contract tests; no real experiments are read.

Proof doubles model the existing verifier's success/failure interface. These tests
do not replace that verifier's independent numerical, ULog or full-history tests.
"""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('_revision06_summary_test',
                                           Path(__file__).with_name('r03_revision06_result_summary.py'))
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def read(path):
    return json.loads(path.read_text())


class Api:
    def __init__(self, root, old=False):
        self.REVISION = 'r03_revision04' if old else 'r03_revision05'
        self.DATA_STAGE = 'R03_revision04' if old else 'R03_revision05'
        self.EXTERNAL, self.REPO = root/'data', root/'repo'
        self.GATES = ('A', 'B', 'C', 'D') if old else ('B', 'C', 'D')
        self.TOTAL_MAXIMUM_ATTEMPTS = 51 if old else 57
        self.HISTORICAL_ATTEMPTS = 15 if old else 30
        self.NEW_MATRIX_ATTEMPTS = 36 if old else 27
        self.history = dict(attempts=15, takeoffs=14, accepted=12, failed=3) if old else \
            dict(attempts=30, takeoffs=29, accepted=26, failed=4)
        self.retained = {}
        self.previous_error = None
        self.protocols = {}
        for gate in self.GATES:
            offset = ord(gate)-ord('A')
            jobs = []
            for i in range(9):
                mode = (0, 1, 3)[i % 3]
                jobs.append(dict(id=f'run{offset*9+i+1:03d}', revision=self.REVISION,
                    gate=gate, candidate=('PID', 'ESTA', 'RSTA')[i % 3],
                    mode=mode, axes=0 if mode == 0 else {'A':1, 'B':4, 'C':3, 'D':7}[gate],
                    seed=800000+offset*100+i//3, main_duration_s=32,
                    parameters={'fixed':1}))
            self.protocols[gate] = dict(jobs=jobs, stage='R03-revision'+('04' if old else '05')+'-'+gate)

    def load_protocol(self, gate):
        return copy.deepcopy(self.protocols[gate])

    def retained_failure(self):
        return copy.deepcopy(self.history)

    def retained_a(self):
        return copy.deepcopy(self.retained)

    def seed_migration(self):
        return dict(kind='none', seed_count=0)

    def require_previous_gates(self, gate):
        if self.previous_error:
            raise ValueError(self.previous_error)
        return [dict(gate=g, receipt_sha256='f'*64) for g in ('A','B','C')[:ord(gate)-ord('A')]]


class Api06(Api):
    def __init__(self,root):
        super().__init__(root)
        self.REVISION='r03_revision06';self.DATA_STAGE='R03_revision06';self.GATES=('D',)
        self.TOTAL_MAXIMUM_ATTEMPTS=58;self.HISTORICAL_ATTEMPTS=49;self.NEW_MATRIX_ATTEMPTS=9
        self.history=dict(attempts=49,takeoffs=48,accepted=44,failed=5)
        self.protocols={'D':self.protocols['D']}
        self.protocols['D']['stage']='R03-revision06-D'
        for job in self.protocols['D']['jobs']:job['revision']=self.REVISION
    def retained_abc(self):return copy.deepcopy(self.retained)


class Proof:
    def __init__(self, api):
        self.api, self.receipts, self.calls = api, {}, []
        self.failure = None

    def source_metrics(self, item, ledger):
        metrics = read(Path(item['directory'])/'r03_metrics.json')
        m.require(metrics['binding']['source_head'] == ledger['source_head'] and
                  metrics['binding']['firmware_sha256'] == ledger['firmware_sha256'],
                  'Fixture metric source mismatch')
        return metrics

    def verify_complete(self, gate, root):
        self.calls.append((gate, str(root)))
        if self.failure:
            raise ValueError(self.failure)
        return copy.deepcopy(self.receipts[gate])


def fixture(api, proof, gate='B', count=9, failure=False, complete=True):
    root = api.EXTERNAL/api.DATA_STAGE/gate
    batch = root/'batch01'
    batch.mkdir(parents=True)
    source, firmware = ('a' if api.REVISION.endswith('04') else 'b')*40, 'c'*64
    p = api.load_protocol(gate)
    backup = batch/'original_parameters.bson'
    backup.write_bytes(b'original full BSON fixture')
    original = m.digest(backup)
    ledger = dict(revision=api.REVISION, gate=gate, stage=p['stage'], planned=9,
        source_head=source, firmware_sha256=firmware,
        total_budget=api.TOTAL_MAXIMUM_ATTEMPTS, new_planned=api.NEW_MATRIX_ATTEMPTS,
        retained_attempts=api.HISTORICAL_ATTEMPTS,
        retained_invalid_attempts=api.history['failed'], retained_accepted_attempts=api.history['accepted'],
        prior_attempts=api.HISTORICAL_ATTEMPTS+9*list(api.GATES).index(gate),
        historical_budget=api.retained_failure(), seed_migration=api.seed_migration(),
        original_parameter_sha256=original, parameter_restore_exact=True,
        remaining_simulators=[], attempts=[], pairs=[], success=complete)
    ledger.update(m.retained_bindings(api))
    qdir = root/'qualification01'
    qdir.mkdir()
    command = qdir/'command.log'
    command.write_text('synthetic fixture only\n')
    q = dict(success=True, clean=True, source_head=source, gate=gate, revision=api.REVISION,
        stage=p['stage'], firmware_sha256=firmware, execution_authorized=True,
        flight_authorized=True, execution_ready=True, maximum_attempts=9,
        total_maximum_attempts=api.TOTAL_MAXIMUM_ATTEMPTS,
        new_matrix_attempts=api.NEW_MATRIX_ATTEMPTS, historical_attempts=api.HISTORICAL_ATTEMPTS,
        new_flights=0, execution_sha256='d'*64, frozen_sha256='e'*64,
        historical_budget=api.retained_failure(), seed_migration=api.seed_migration(),
        counts=dict(cpp_unique_tests=488, python_tests=1430), evidence_files={str(command):m.digest(command)})
    q.update(m.retained_bindings(api))
    if api.REVISION in ('r03_revision05','r03_revision06'):
        q['previous_gates'] = api.require_previous_gates(gate)
    save(qdir/'evidence.json', q)
    qref = dict(path=str(qdir/'evidence.json'), sha256=m.digest(qdir/'evidence.json'))
    authority = {**q, 'approved':True, 'qualification_sha256':qref['sha256']}
    save(qdir/'authorization.json', authority)
    save(batch/'qualification_reference.json', qref)
    save(batch/'qualification.json', q)
    (batch/'journal.jsonl').write_text('{"event":"fixture"}\n')
    for i, job in enumerate(p['jobs'][:count]):
        run = batch/job['id']
        run.mkdir()
        logs = []
        for name, payload in (('startup.ulg', b'startup-'+bytes([i])), ('main.ulg', b'main-'+bytes([i]))):
            path = run/name
            path.write_bytes(payload)
            logs.append(dict(archive=str(path), source='/volatile/'+name, bytes=len(payload), sha256=m.digest(path)))
        failed = failure and i == count-1
        result = dict(source_head=source, binary_sha256=firmware, success=not failed,
            error='fixture mandatory failure' if failed else None, logs=logs,
            events=[dict(name=n) for n in ('takeoff_command', 'hover_start', 'landed_disarmed')])
        save(run/'result.json', result)
        save(run/'parameter_restore.json', dict(source_head=source, gate=gate, job_id=job['id'],
            backup_path=str(backup), original_parameter_sha256=original, restored_parameter_sha256=original,
            parameter_restore_exact=True, remaining_simulators=[], stopped_before_restore=True))
        save(run/'qualification_reference.json', qref)
        d = dict(error=dict(rmse=[.1, .2, .3]), J=.2, seconds=32.0)
        for name in ('correction', 'acceleration', 'normalized_thrust'):
            d[name+'_tv'], d[name+'_tv_per_second'] = [1., 2., 3.], [1./32, 2./32, 3./32]
        metrics = dict(accepted=not failed, job=job, binding=dict(source_head=source, firmware_sha256=firmware),
                       diagnostic=d, position_rmse=[.01, .02, .03], yaw_rmse=.001)
        save(run/'r03_metrics.json', metrics)
        save(run/'spectra.json', {'fixture':True})
        ledger['attempts'].append(dict(attempt=i+1, job=job, directory=str(run),
            status='failed' if failed else 'accepted', metrics_sha256=m.digest(run/'r03_metrics.json')))
        if job['mode'] and not failed:
            ledger['pairs'].append(dict(seed=job['seed'], gate=gate, candidate=job['candidate'], accepted=True))
    save(batch/'ledger.json', ledger)
    if complete:
        summary = dict(replayed=9, source_inputs_unchanged=True, rows=[dict(id=j['id']) for j in p['jobs']],
                       source_batch_snapshot=dict(files={str(f):m.digest(f) for f in batch.rglob('*') if f.is_file()}))
        save(root/'replay01/summary.json', summary)
        receipt = dict(success=True, revision=api.REVISION, gate=gate, source_head=source,
                       attempts=9, accepted=9, independent_replays=9, paired_checks=6)
        save(root/'gate_pass.json', receipt)
        proof.receipts[gate] = receipt
    return root


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='r03-summary-test-')
        self.base = Path(self.tmp.name)
        self.api = Api(self.base)
        self.proof = Proof(self.api)

    def tearDown(self):
        self.tmp.cleanup()

    def run_gate(self, **kwargs):
        root = fixture(self.api, self.proof, **kwargs)
        return root, m.gate_summary(self.api, self.proof, kwargs.get('gate', 'B'))

    def mutate(self, root, relative, change):
        path = root/relative
        value = read(path)
        change(value)
        save(path, value)

    def test_complete_nine_runs_have_eighteen_ulog_files(self):
        root, result = self.run_gate()
        self.assertTrue(result['gate_passed'], result['issues'])
        self.assertEqual(result['ulog_files_verified'], 18)
        self.assertEqual(result['independent_replay']['replayed'], 9)
        self.assertEqual(len(result['independent_replay']['six_paired_decisions']), 6)
        self.assertEqual(self.proof.calls, [('B', str(root))])
        self.assertEqual(result['algorithms']['RSTA']['n'], 3)
        self.assertEqual(result['algorithms']['RSTA']['mean']['J_m_s'], .2)

    def test_missing_gate_counts_unknown_not_zero(self):
        value = m.gate_summary(self.api, self.proof, 'C')
        self.assertIsNone(value['attempted'])
        self.assertFalse(value['gate_passed'])
        self.assertEqual(value['rows'], [])

    def test_partial_no_future_seed_or_id_serialization(self):
        _, value = self.run_gate(count=1, complete=False)
        self.assertEqual(value['attempted'], 1)
        self.assertEqual(value['unattempted'], 8)
        serialized = json.dumps(value)
        for job in self.api.load_protocol('B')['jobs'][3:]:
            self.assertNotIn(str(job['seed']), serialized)
        self.assertNotIn('run018', serialized)
        self.assertEqual(value['algorithms']['ESTA']['n'], 0)
        self.assertNotIn('mean', value['algorithms']['ESTA'])

    def test_failed_row_excluded_and_failure_retained(self):
        _, value = self.run_gate(count=3, failure=True, complete=False)
        self.assertEqual((value['status'], value['failed'], value['accepted_metrics_verified']), ('stopped_failed', 1, 2))
        self.assertEqual(value['algorithms']['RSTA']['n'], 0)
        self.assertEqual(value['rows'][2]['error'], 'fixture mandatory failure')
        self.assertFalse(value['gate_passed'])

    def test_command_does_not_imply_airborne(self):
        root = fixture(self.api, self.proof, count=1, complete=False)
        self.mutate(root, 'batch01/run010/result.json', lambda x:x.update(events=[dict(name='takeoff_command')]))
        value = m.gate_summary(self.api, self.proof, 'B')
        self.assertEqual(value['takeoff_command_count'], 1)
        self.assertEqual(value['airborne_task_reached_count'], 0)
        self.assertEqual(value['landed_disarmed_count'], 0)

    def test_missing_result_not_invented_success(self):
        root = fixture(self.api, self.proof, count=1, complete=False)
        (root/'batch01/run010/result.json').unlink()
        value = m.gate_summary(self.api, self.proof, 'B')
        self.assertIsNone(value['airborne_task_reached_count'])
        self.assertEqual(value['accepted_metrics_verified'], 0)

    def test_incorrect_count_type_rejected(self):
        root = fixture(self.api, self.proof)
        self.mutate(root, 'batch01/ledger.json', lambda x:x.update(planned=9.0))
        self.assertEqual(m.gate_summary(self.api, self.proof, 'B')['status'], 'evidence_error')

    def test_wrong_revision_and_budget_rejected(self):
        for key, value in (('revision','r03_revision04'), ('total_budget',51), ('prior_attempts',31)):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                api=Api(Path(tmp)); proof=Proof(api); root=fixture(api,proof)
                self.mutate(root, 'batch01/ledger.json', lambda x:x.update({key:value}))
                self.assertFalse(m.gate_summary(api,proof,'B')['gate_passed'])

    def test_reordered_job_rejected(self):
        root = fixture(self.api, self.proof)
        self.mutate(root, 'batch01/ledger.json', lambda x:x['attempts'].reverse())
        self.assertFalse(m.gate_summary(self.api, self.proof, 'B')['gate_passed'])

    def test_orphan_directory_rejected(self):
        root = fixture(self.api, self.proof, count=1, complete=False)
        (root/'batch01/run099').mkdir()
        self.assertEqual(m.gate_summary(self.api,self.proof,'B')['status'], 'evidence_error')

    def test_foreign_run_directory_rejected(self):
        root = fixture(self.api, self.proof)
        self.mutate(root, 'batch01/ledger.json', lambda x:x['attempts'][0].update(directory='/tmp/foreign'))
        self.assertFalse(m.gate_summary(self.api,self.proof,'B')['gate_passed'])

    def test_result_source_binary_rejected(self):
        for key in ('source_head','binary_sha256'):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                api=Api(Path(tmp)); proof=Proof(api); root=fixture(api,proof)
                self.mutate(root, 'batch01/run010/result.json', lambda x:x.update({key:'wrong'}))
                self.assertFalse(m.gate_summary(api,proof,'B')['gate_passed'])

    def test_metric_sha_or_binding_changed_rejected(self):
        root = fixture(self.api,self.proof)
        self.mutate(root, 'batch01/run010/r03_metrics.json', lambda x:x['binding'].update(source_head='x'*40))
        self.assertFalse(m.gate_summary(self.api,self.proof,'B')['gate_passed'])

    def test_ulog_bytes_hash_are_actually_read(self):
        root = fixture(self.api,self.proof)
        path=root/'batch01/run010/main.ulg'; path.write_bytes(b'MAIN-'+bytes([0]))
        result=m.gate_summary(self.api,self.proof,'B')
        self.assertFalse(result['gate_passed'])
        self.assertTrue(any('ULog' in s for s in result['rows'][0]['issues']))

    def test_unregistered_startup_log_rejected(self):
        root=fixture(self.api,self.proof)
        (root/'batch01/run010/extra.ulg').write_bytes(b'additional')
        self.assertFalse(m.gate_summary(self.api,self.proof,'B')['gate_passed'])

    def test_duplicate_archive_rejected(self):
        root=fixture(self.api,self.proof)
        self.mutate(root,'batch01/run010/result.json',lambda x:x['logs'].append(x['logs'][0]))
        self.assertFalse(m.gate_summary(self.api,self.proof,'B')['gate_passed'])

    def test_restore_false_not_passed(self):
        root=fixture(self.api,self.proof)
        self.mutate(root,'batch01/run010/parameter_restore.json',lambda x:x.update(parameter_restore_exact=False))
        self.assertFalse(m.gate_summary(self.api,self.proof,'B')['gate_passed'])

    def test_parameter_backup_change_rejected(self):
        root=fixture(self.api,self.proof)
        (root/'batch01/original_parameters.bson').write_bytes(b'changed')
        self.assertFalse(m.gate_summary(self.api,self.proof,'B')['gate_passed'])

    def test_remaining_simulator_in_restore_rejected(self):
        root=fixture(self.api,self.proof)
        self.mutate(root,'batch01/run010/parameter_restore.json',lambda x:x.update(remaining_simulators=[123]))
        self.assertFalse(m.gate_summary(self.api,self.proof,'B')['gate_passed'])

    def test_qualification_changed_rejected(self):
        root=fixture(self.api,self.proof)
        self.mutate(root,'qualification01/evidence.json',lambda x:x.update(clean=False))
        self.assertFalse(m.gate_summary(self.api,self.proof,'B')['gate_passed'])

    def test_qualification_command_evidence_changed_rejected(self):
        root=fixture(self.api,self.proof)
        (root/'qualification01/command.log').write_text('modified')
        self.assertFalse(m.gate_summary(self.api,self.proof,'B')['gate_passed'])

    def test_wrong_qualification_reference_on_one_run_rejected(self):
        root=fixture(self.api,self.proof)
        self.mutate(root,'batch01/run010/qualification_reference.json',lambda x:x.update(sha256='0'*64))
        self.assertFalse(m.gate_summary(self.api,self.proof,'B')['gate_passed'])

    def test_nine_accepted_without_receipt_not_passed(self):
        root=fixture(self.api,self.proof)
        (root/'gate_pass.json').unlink()
        value=m.gate_summary(self.api,self.proof,'B')
        self.assertFalse(value['gate_passed'])
        self.assertEqual(self.proof.calls,[])

    def test_receipt_without_replay_not_passed(self):
        root=fixture(self.api,self.proof)
        (root/'replay01/summary.json').unlink()
        self.assertFalse(m.gate_summary(self.api,self.proof,'B')['gate_passed'])

    def test_independent_pair_failure_from_verifier_not_overridden(self):
        fixture(self.api,self.proof)
        self.proof.failure='Recomputed paired risk threshold failed fixture'
        result=m.gate_summary(self.api,self.proof,'B')
        self.assertFalse(result['gate_passed'])
        self.assertIn(self.proof.failure,result['issues'])

    def test_independent_replay_failure_from_verifier_not_overridden(self):
        fixture(self.api,self.proof)
        self.proof.failure='Replay metric content changed'
        self.assertFalse(m.gate_summary(self.api,self.proof,'B')['gate_passed'])

    def test_changed_receipt_does_not_match_full_verifier(self):
        root=fixture(self.api,self.proof)
        self.mutate(root,'gate_pass.json',lambda x:x.update(accepted=8))
        self.assertFalse(m.gate_summary(self.api,self.proof,'B')['gate_passed'])

    def test_previous_gate_raw_failure_blocks_complete_gate(self):
        fixture(self.api,self.proof)
        self.api.previous_error='Previous gate receipt differs from raw evidence'
        value=m.gate_summary(self.api,self.proof,'B')
        self.assertFalse(value['gate_passed'])
        self.assertIn(self.api.previous_error,value['issues'])

    def test_qualification_predecessor_binding_is_checked(self):
        fixture(self.api,self.proof)
        with patch.object(self.api,'require_previous_gates',return_value=[]):
            value=m.gate_summary(self.api,self.proof,'B')
        self.assertFalse(value['gate_passed'])
        self.assertIn('Qualification predecessor proof differs',value['issues'])

    def test_retained_failure_count_cannot_be_erased(self):
        root=fixture(self.api,self.proof)
        self.mutate(root,'batch01/ledger.json',lambda x:x.update(retained_invalid_attempts=0))
        self.assertFalse(m.gate_summary(self.api,self.proof,'B')['gate_passed'])

    def test_changed_input_after_complete_verification_rejected(self):
        root=fixture(self.api,self.proof)
        original=self.proof.verify_complete
        def mutate(gate,path):
            value=original(gate,path)
            (root/'batch01/journal.jsonl').write_text('changed in proof call\n')
            return value
        with patch.object(self.proof,'verify_complete',side_effect=mutate):
            result=m.gate_summary(self.api,self.proof,'B')
        self.assertFalse(result['gate_passed'])

    def test_nonfinite_negative_and_bad_j_rejected(self):
        job={'main_duration_s':32}
        root=fixture(self.api,self.proof)
        original=read(root/'batch01/run010/r03_metrics.json')
        for value in (float('nan'),float('inf'),-.1):
            with self.subTest(value=value):
                metrics=copy.deepcopy(original);metrics['diagnostic']['error']['rmse'][0]=value
                with self.assertRaises(ValueError):m.measures(metrics,job)
        original['diagnostic']['J']=99
        with self.assertRaises(ValueError):m.measures(original,job)

    def test_wrong_window_and_tv_over_t_rejected(self):
        root=fixture(self.api,self.proof)
        metrics=read(root/'batch01/run010/r03_metrics.json')
        with self.assertRaises(ValueError):m.measures(metrics,{'main_duration_s':64})
        metrics['diagnostic']['correction_tv_per_second'][0]=999
        with self.assertRaises(ValueError):m.measures(metrics,{'main_duration_s':32})

    def complete_scope(self,new_count=9,new_failure=False,new_complete=True,create_d=True):
        old=Api(self.base,old=True);oldproof=Proof(old)
        a=fixture(old,oldproof,'A')
        self.api.retained=dict(source_head='a'*40,receipt_sha256=m.digest(a/'gate_pass.json'))
        b=fixture(self.api,self.proof,'B');c=fixture(self.api,self.proof,'C')
        current=Api06(self.base);currentproof=Proof(current)
        current.retained=dict(accepted_design_runs=27,new_attempts=0,gates=[
            dict(gate=gate,revision=revision,source_head=source*40,receipt_sha256=m.digest(root/'gate_pass.json'))
            for gate,revision,source,root in [('A','r03_revision04','a',a),
                ('B','r03_revision05','b',b),('C','r03_revision05','b',c)]])
        if create_d:fixture(current,currentproof,'D',new_count,new_failure,new_complete)
        return current,currentproof,old,oldproof,self.api,self.proof

    def test_retained_abc_separate_not_added_to_new_d_n(self):
        readers=self.complete_scope()
        result=m.summarize(*readers)
        self.assertTrue(result['all_r03_gates_verified'])
        self.assertEqual(result['historical']['attempts'],49)
        self.assertEqual(result['historical']['failed'],5)
        self.assertEqual(result['gates'][0]['algorithms']['PID']['n'],3)
        self.assertEqual([g['revision'] for g in result['retained_abc']],
                         ['r03_revision04','r03_revision05','r03_revision05'])
        self.assertEqual(result['accepted_design']['verified_runs'],36)
        self.assertEqual(result['cumulative'],dict(attempts=58,takeoff_commands=57,accepted=53,
            failed=5,unused_budget=0,interpretation='Historical accounting only; not the scientific four-gate sample size'))

    def test_missing_d_keeps_counts_unknown_not_pseudo_zero(self):
        result=m.summarize(*self.complete_scope(create_d=False))
        self.assertFalse(result['all_r03_gates_verified'])
        self.assertIsNone(result['gates'][0]['attempted'])
        self.assertIsNone(result['cumulative']['attempts'])
        self.assertIsNone(result['cumulative']['accepted'])
        self.assertEqual(result['accepted_design']['verified_runs'],27)

    def test_failed_new_d_remains_failed_and_not_backfilled(self):
        result=m.summarize(*self.complete_scope(new_count=1,new_failure=True,new_complete=False))
        self.assertFalse(result['all_r03_gates_verified'])
        self.assertEqual(result['cumulative']['attempts'],50)
        self.assertEqual(result['cumulative']['accepted'],44)
        self.assertEqual(result['cumulative']['failed'],6)
        self.assertEqual(result['cumulative']['unused_budget'],8)
        self.assertEqual(result['accepted_design']['verified_runs'],27)
        self.assertEqual(result['gates'][0]['algorithms']['PID']['n'],0)

    def test_each_original_gate_verifier_failure_blocks_final_result(self):
        for index in (3,5):
            with self.subTest(verifier=index),tempfile.TemporaryDirectory() as tmp:
                before=self.base;before_api=self.api;before_proof=self.proof
                self.base=Path(tmp);self.api=Api(self.base);self.proof=Proof(self.api)
                readers=self.complete_scope();readers[index].failure='Original raw evidence changed'
                result=m.summarize(*readers)
                self.assertFalse(result['all_r03_gates_verified'])
                self.base=before;self.api=before_api;self.proof=before_proof

    def test_retained_receipt_sha_mismatch_rejected(self):
        readers=self.complete_scope();readers[0].retained['gates'][1]['receipt_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'Retained ABC fixed'):
            m.summarize(*readers)

    def test_wrong_history_budget_and_reordered_retained_gates_rejected(self):
        readers=self.complete_scope()
        for key,value in [('attempts',48),('takeoffs',49),('accepted',45),('failed',4)]:
            with self.subTest(key=key):
                original=readers[0].history[key];readers[0].history[key]=value
                with self.assertRaises(ValueError):m.summarize(*readers)
                readers[0].history[key]=original
        readers[0].retained['gates'].reverse()
        with self.assertRaises(ValueError):m.summarize(*readers)

    def test_d_qualification_retained_abc_is_checked(self):
        readers=self.complete_scope()
        readers[0].retained['new_attempts']=1
        result=m.gate_summary(readers[0],readers[1],'D')
        self.assertFalse(result['gate_passed'])

    def test_d_original_analysis_failure_not_hidden_by_physical_success(self):
        readers=self.complete_scope(new_count=1,new_failure=True,new_complete=False)
        run=readers[0].EXTERNAL/readers[0].DATA_STAGE/'D/batch01/run028'
        result=read(run/'result.json');result.update(success=True,error=None);save(run/'result.json',result)
        metrics=read(run/'r03_metrics.json');metrics['error']='Downstream XY target differs';save(run/'r03_metrics.json',metrics)
        value=m.gate_summary(readers[0],readers[1],'D')
        self.assertEqual(value['rows'][0]['analysis_error'],'Downstream XY target differs')
        self.assertFalse(value['rows'][0]['original_metric_accepted'])
        self.assertFalse(value['gate_passed'])

    def test_output_only_fresh_dedicated_external_directory(self):
        good=self.api.EXTERNAL/'R03_revision06_summaries/test01'
        m.write_fresh(good,{'fixture':True},self.api)
        self.assertEqual(read(good/'summary.json'),{'fixture':True})
        with self.assertRaises(FileExistsError):m.write_fresh(good,{},self.api)
        for bad in (self.api.REPO/'out',self.api.EXTERNAL/'R03_revision05/B/batch01/out',
                    self.api.EXTERNAL/'R03_revision06_summaries'):
            with self.subTest(path=bad),self.assertRaises(ValueError):m.write_fresh(bad,{},self.api)

    def test_output_symlink_escape_rejected(self):
        directory=self.api.EXTERNAL/'R03_revision06_summaries'
        directory.mkdir(parents=True)
        (directory/'escape').symlink_to(self.base,target_is_directory=True)
        with self.assertRaises(ValueError):m.write_fresh(directory/'escape/out',{},self.api)

    def test_top_level_output_alias_into_input_batch_rejected(self):
        batch=self.api.EXTERNAL/'R03_revision05/B/batch01'
        batch.mkdir(parents=True)
        alias=self.api.EXTERNAL/'R03_revision06_summaries'
        alias.symlink_to(batch,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'symbolic-link alias'):
            m.write_fresh(alias/'out',{},self.api)
        self.assertFalse((batch/'out').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
