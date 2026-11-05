"""Mocked offline evidence tests; synthetic bytes are NOT decoded flight logs."""
import ast
import copy
import importlib.util
import json
import math
from pathlib import Path
import shutil
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('r03_replay_under_test', HERE/'replay.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def sample_metrics(job):
    return dict(accepted=True, job=copy.deepcopy(job),
                diagnostic=dict(error=dict(rmse=[.01,.02,.03]), windows={
                    name:dict(error=dict(rmse=[.01,.02,.03])) for name in ('first_half','second_half')}),
                position_rmse=[.02,.03,.04], yaw_rmse=.01,
                binding=dict(source_head='a'*40, firmware_sha256='b'*64, gate=job['gate']),
                cli_receipts=dict(counts={'listener':1,'param':2}))


class ComparisonTest(unittest.TestCase):
    def test_dictionary_order_only_does_not_change_numbers(self):
        a = b'{"accepted":true,"x":0.1,"counts":{"a":1,"b":2}}'
        b = b'{"counts":{"b":2,"a":1},"x":0.1,"accepted":true}'
        out = r.compare_metrics(a, b)
        self.assertTrue(out['numeric_equal']); self.assertFalse(out['bytes_identical'])

    def test_numeric_type_sign_small_change_or_list_order_rejected(self):
        original = dict(accepted=True, value=1, zero=0.0, array=[1,2], small=.001)
        for key, value in [('value',True), ('value',1.0), ('zero',-0.0), ('array',[2,1]), ('small',.0010000000000000002)]:
            changed = copy.deepcopy(original); changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                r.compare_metrics(json.dumps(original).encode(), json.dumps(changed).encode())

    def test_unaccepted_null_or_missing_values_not_imputed(self):
        for value in ({'accepted':False}, {'accepted':None}, {'accepted':True,'value':None}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                r.compare_metrics(b'{"accepted":true,"value":1}', json.dumps(value).encode())


class PairMathTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Extract only the real analyzer's arithmetic function. Its unrelated
        # ULog/import/validation machinery is not run or claimed tested here.
        tree = ast.parse((HERE/'analyzer.py').read_text())
        function = next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name == 'compare')
        namespace = dict(validate_job=lambda job:None,
                         windows=lambda job:[('first_half',0,1),('second_half',1,2)])
        exec(compile(ast.Module(body=[function],type_ignores=[]),str(HERE/'analyzer.py'),'exec'),namespace)
        cls.original_compare = staticmethod(namespace['compare'])

    def test_independent_math_matches_actual_compare_at_all_boundaries_and_neighbors(self):
        for gate in r.protocol.GATES:
            jobs = r.protocol.load_protocol(gate)['jobs']
            pid = sample_metrics(jobs[0])
            for job in jobs[1:3]:
                candidate = sample_metrics(job)
                self.assertEqual(r.paired_decision(pid,candidate),self.original_compare(pid,candidate))
                for family in ('velocity','position','first_half','second_half','yaw'):
                    for axis in range(1 if family == 'yaw' else 3):
                        value = copy.deepcopy(candidate)
                        if family == 'velocity':
                            target = value['diagnostic']['error']['rmse']; previous = pid['diagnostic']['error']['rmse'][axis]
                        elif family == 'position':
                            target = value['position_rmse']; previous = pid['position_rmse'][axis]
                        elif family in ('first_half','second_half'):
                            target = value['diagnostic']['windows'][family]['error']['rmse']
                            previous = pid['diagnostic']['windows'][family]['error']['rmse'][axis]
                        else:
                            target = value; previous = pid['yaw_rmse']
                        key = 'yaw_rmse' if family == 'yaw' else axis
                        allowance = .02 if family == 'yaw' else .05 if family == 'position' else (.02,.02,.01)[axis]
                        boundary = 1.25*previous+allowance
                        for tested, accepted in ((boundary,True),(math.nextafter(boundary,math.inf),False)):
                            target[key] = tested
                            with self.subTest(gate=gate,mode=job['mode'],family=family,axis=axis,accepted=accepted):
                                independent = r.paired_decision(pid,value)
                                self.assertEqual(independent,self.original_compare(pid,value))
                                self.assertEqual(independent['accepted'],accepted)

    def test_invalid_numbers_shape_or_pair_identity_rejected(self):
        jobs = r.protocol.load_protocol('A')['jobs']
        pid, candidate = sample_metrics(jobs[0]),sample_metrics(jobs[1])
        for value in (float('nan'),float('inf'),-1.,True,None,'0.01'):
            changed = copy.deepcopy(candidate); changed['diagnostic']['error']['rmse'][0] = value
            with self.subTest(value=value),self.assertRaises(ValueError): r.paired_decision(pid,changed)
        for kind in ('short','binding','seed','mode','parameter','not_accepted'):
            changed = copy.deepcopy(candidate)
            if kind == 'short':changed['position_rmse'].pop()
            if kind == 'binding':changed['binding']['firmware_sha256'] = 'c'*64
            if kind == 'seed':changed['job']['seed'] += 1
            if kind == 'mode':changed['job']['mode'] = True
            if kind == 'parameter':changed['job']['parameters']['MPC_VC_EPS_X'] = .02
            if kind == 'not_accepted':changed['accepted'] = False
            with self.subTest(kind=kind),self.assertRaises(ValueError): r.paired_decision(pid,changed)


class EvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='r03-replay-unit-')
        self.addCleanup(self.temporary.cleanup)
        external = Path(self.temporary.name)
        protocols = {gate:r.protocol.load_protocol(gate) for gate in r.protocol.GATES}
        self.addCleanup(patch.stopall)
        patch('builtins.print').start()  # silence mock row progress, not unittest's stderr summary
        patch.object(r.protocol, 'EXTERNAL', external).start()
        patch.object(r.protocol, 'load_protocol', side_effect=lambda gate: copy.deepcopy(protocols[gate])).start()
        self.root = external/'R03/A'; self.batch = self.root/'batch01'; self.replay = self.root/'replay01'
        self.batch.mkdir(parents=True)
        self.jobs = copy.deepcopy(protocols['A']['jobs'])
        self.ledger = dict(stage='R03-A', gate='A', source_head='a'*40, firmware_sha256='b'*64,
                           success=True, planned=9, total_budget=36, parameter_restore_exact=True,
                           remaining_simulators=[], unattempted=[], attempts=[], pairs=[])
        required = {'yaw'} | {prefix+str(i) for prefix in
            ('velocity_','position_','first_half_velocity_','second_half_velocity_') for i in range(3)}
        for index, job in enumerate(self.jobs, 1):
            run = self.batch/job['id']; run.mkdir()
            log = run/'log001.ulg'; log.write_bytes(b'SYNTHETIC-NOT-A-FLIGHT-ULOG-'+job['id'].encode())
            metrics = sample_metrics(job)
            r.save_new(run/'r03_metrics.json', metrics)
            r.save_new(run/'spectra.json', dict(frequency=[0.,1.], psd=[.01,.02]))
            r.save_new(run/'job.json', job)
            r.save_new(run/'result.json', dict(success=True, source_head='a'*40, binary_sha256='b'*64,
                logs=[dict(archive=str(log), bytes=log.stat().st_size, sha256=r.digest(log))]))
            self.ledger['attempts'].append(dict(attempt=index, job=job, directory=str(run), status='accepted',
                                               metrics_sha256=r.digest(run/'r03_metrics.json')))
            if job['mode']:
                self.ledger['pairs'].append(dict(seed=job['seed'], gate='A', candidate=job['candidate'],
                    accepted=True, checks={k:True for k in required},
                    criterion='Inherited development risk, not a requirement to beat PID or ESTA'))
        r.save_new(self.batch/'ledger.json', self.ledger)

    def fake_analyzer(self, argv, **kwargs):
        source, output = Path(argv[2]), Path(argv[4]); output.mkdir()
        metrics = r.read(source/'r03_metrics.json')
        # Formatting and dictionary insertion order differ; scientific values do not.
        (output/'r03_metrics.json').write_text(json.dumps(dict(reversed(list(metrics.items()))), separators=(',',':')))
        shutil.copyfile(source/'spectra.json', output/'spectra.json')
        kwargs['stdout'].write('MOCK OFFLINE ANALYZER: no ULog decode or simulator executed\n')
        return types.SimpleNamespace(returncode=0)

    def complete(self, finalize=True):
        with patch.object(r.subprocess, 'run', side_effect=self.fake_analyzer) as process:
            result = r.replay_gate('A', self.replay, finalize_after=finalize)
        self.assertEqual(process.call_count, 9)
        return result

    def test_ledger_exact_identity_order_pairs_and_cleanup(self):
        self.assertTrue(r.validate_ledger(self.ledger, self.jobs, self.batch))

    def test_duplicate_reordered_failed_or_short_attempts_rejected(self):
        for kind in ('duplicate','reorder','failed','missing','foreign_directory','integer_alias'):
            ledger = copy.deepcopy(self.ledger)
            if kind == 'duplicate': ledger['attempts'][1] = copy.deepcopy(ledger['attempts'][0])
            if kind == 'reorder': ledger['attempts'][0],ledger['attempts'][1] = ledger['attempts'][1],ledger['attempts'][0]
            if kind == 'failed': ledger['attempts'][1]['status'] = 'failed'
            if kind == 'missing': ledger['attempts'].pop()
            if kind == 'foreign_directory': ledger['attempts'][0]['directory'] = str(self.batch/'other')
            if kind == 'integer_alias': ledger['attempts'][0]['attempt'] = True
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                r.validate_ledger(ledger, self.jobs, self.batch)

    def test_null_fake_success_or_missing_cleanup_not_complete(self):
        for key, value in [('attempts',[None]*9), ('success',1), ('planned',9.0), ('total_budget',37),
                           ('parameter_restore_exact',False), ('remaining_simulators',['px4']), ('unattempted',['run009'])]:
            ledger = copy.deepcopy(self.ledger); ledger[key] = value
            with self.subTest(key=key), self.assertRaises((ValueError,TypeError,AttributeError)):
                r.validate_ledger(ledger, self.jobs, self.batch)

    def test_six_pairs_require_exact_unique_axes_seed_and_all_checks(self):
        for kind in ('duplicate','missing','failed','wrong_seed','wrong_gate','omitted_check','fake_true'):
            ledger = copy.deepcopy(self.ledger)
            if kind == 'duplicate': ledger['pairs'][1] = copy.deepcopy(ledger['pairs'][0])
            if kind == 'missing': ledger['pairs'].pop()
            if kind == 'failed': ledger['pairs'][0]['accepted'] = False
            if kind == 'wrong_seed': ledger['pairs'][0]['seed'] = 71011
            if kind == 'wrong_gate': ledger['pairs'][0]['gate'] = 'B'
            if kind == 'omitted_check': ledger['pairs'][0]['checks'].pop('yaw')
            if kind == 'fake_true': ledger['pairs'][0]['checks']['yaw'] = 1
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                r.validate_ledger(ledger, self.jobs, self.batch)

    def test_source_fingerprints_include_all_original_files_and_log(self):
        run = self.batch/'run001'; before = r.raw_snapshot(run)
        self.assertEqual(before['files'], {str(path):r.digest(path) for path in run.iterdir() if path.is_file()})
        (run/'log001.ulg').write_bytes(b'changed bytes')
        with self.assertRaises(ValueError): r.raw_snapshot(run)

    def test_unregistered_extra_ulog_rejected(self):
        run = self.batch/'run001'; (run/'extra.ulg').write_bytes(b'not registered')
        with self.assertRaises(ValueError): r.raw_snapshot(run)

    def test_successful_mock_chain_retains_source_and_issues_bound_receipt_only_last(self):
        before = r.tree_snapshot(self.batch)
        evidence = self.complete()
        self.assertTrue(evidence['success']); self.assertEqual(evidence['replayed'],9)
        self.assertEqual(r.tree_snapshot(self.batch), before)
        self.assertEqual(r.read(self.root/'gate_pass.json'), r.verify_complete('A'))
        self.assertEqual(len(evidence['rows']),9)
        self.assertTrue(all(row['numeric_equal'] for row in evidence['rows']))

    def test_no_finalize_means_no_success_receipt_and_existing_output_refused(self):
        self.complete(finalize=False)
        self.assertFalse((self.root/'gate_pass.json').exists())
        with self.assertRaises(ValueError): r.replay_gate('A',self.replay)
        r.finalize('A')
        with self.assertRaises(ValueError): r.finalize('A')

    def test_analyzer_nonzero_stops_at_first_preserves_summary_and_no_receipt(self):
        with patch.object(r.subprocess,'run',return_value=types.SimpleNamespace(returncode=2)) as process:
            with self.assertRaises(ValueError): r.replay_gate('A',self.replay,finalize_after=True)
        self.assertEqual(process.call_count,1)
        summary = r.read(self.replay/'summary.json')
        self.assertFalse(summary['success']); self.assertEqual(summary['replayed'],0)
        self.assertEqual(summary['rows'][0]['exit_code'],2)
        self.assertFalse((self.root/'gate_pass.json').exists())

    def test_numeric_replay_change_cannot_be_accepted_or_finalized(self):
        def analyzer(argv, **kwargs):
            result = self.fake_analyzer(argv,**kwargs)
            path = Path(argv[4])/'r03_metrics.json'; value = r.read(path); value['diagnostic']['error']['rmse'][0] += 1e-12
            path.write_text(json.dumps(value)); return result
        with patch.object(r.subprocess,'run',side_effect=analyzer):
            with self.assertRaises(ValueError): r.replay_gate('A',self.replay,finalize_after=True)
        self.assertFalse(r.read(self.replay/'summary.json')['success'])
        self.assertFalse((self.root/'gate_pass.json').exists())

    def test_spectrum_drift_rejected_even_if_metrics_match(self):
        def analyzer(argv, **kwargs):
            result = self.fake_analyzer(argv,**kwargs)
            (Path(argv[4])/'spectra.json').write_text('{}\n'); return result
        with patch.object(r.subprocess,'run',side_effect=analyzer):
            with self.assertRaises(ValueError): r.replay_gate('A',self.replay)
        self.assertEqual(r.read(self.replay/'summary.json')['replayed'],0)

    def test_source_mutation_rejected_and_retained_not_restored_by_auditor(self):
        def analyzer(argv, **kwargs):
            result = self.fake_analyzer(argv,**kwargs)
            (Path(argv[2])/'unexpected.txt').write_text('changed during analysis\n'); return result
        with patch.object(r.subprocess,'run',side_effect=analyzer):
            with self.assertRaises(ValueError): r.replay_gate('A',self.replay)
        self.assertFalse(r.read(self.replay/'summary.json')['source_inputs_unchanged'])
        self.assertEqual(r.read(self.replay/'summary.json')['replayed'],0)
        self.assertFalse(r.read(self.replay/'summary.json')['rows'][0]['accepted'])
        self.assertTrue((self.batch/'run001/unexpected.txt').exists())

    def test_final_verification_recomputes_metrics_not_only_boolean(self):
        self.complete(finalize=False)
        path = self.replay/'run001/r03_metrics.json'; value = r.read(path); value['diagnostic']['error']['rmse'][0] = .03
        path.write_text(json.dumps(value))
        summary = r.read(self.replay/'summary.json')
        summary['rows'][0]['replay_metrics_sha256'] = r.digest(path)
        (self.replay/'summary.json').write_text(json.dumps(summary))
        with self.assertRaises(ValueError): r.finalize('A')
        self.assertFalse((self.root/'gate_pass.json').exists())

    def test_final_verification_rejects_omitted_raw_input_fingerprints(self):
        self.complete(finalize=False)
        summary = r.read(self.replay/'summary.json'); summary['rows'][0]['input_files'].pop(str(self.batch/'run001/log001.ulg'))
        (self.replay/'summary.json').write_text(json.dumps(summary))
        with self.assertRaises(ValueError): r.finalize('A')

    def test_actual_previous_gate_checker_revalidates_raw_evidence(self):
        self.complete()
        with patch.object(r.protocol,'load_file',return_value=r):
            checked = r.protocol.require_previous_gates('B')
            self.assertEqual(checked,[dict(gate='A',receipt_sha256=r.digest(self.root/'gate_pass.json'))])
            (self.batch/'run001/log001.ulg').write_bytes(b'changed after qualification')
            with self.assertRaises(ValueError): r.protocol.require_previous_gates('B')

    def test_later_gate_cannot_skip_an_incomplete_middle_gate(self):
        self.complete()
        with patch.object(r.protocol,'load_file',return_value=r):
            with self.assertRaises(FileNotFoundError): r.protocol.require_previous_gates('C')

    def test_forged_gate_receipt_counts_not_enough(self):
        self.complete()
        receipt = r.read(self.root/'gate_pass.json'); receipt['accepted'] = 9.0
        (self.root/'gate_pass.json').write_text(json.dumps(receipt))
        with patch.object(r.protocol,'load_file',return_value=r):
            with self.assertRaises(ValueError): r.protocol.require_previous_gates('B')

    def test_all_saved_checks_true_cannot_override_real_risk_failure(self):
        path = self.batch/'run002/r03_metrics.json'; value = r.read(path)
        value['diagnostic']['error']['rmse'][0] = .5
        path.write_text(json.dumps(value))
        self.ledger['attempts'][1]['metrics_sha256'] = r.digest(path)
        (self.batch/'ledger.json').write_text(json.dumps(self.ledger))
        with patch.object(r.subprocess,'run',side_effect=self.fake_analyzer) as process:
            with self.assertRaisesRegex(ValueError,'Recomputed paired risk threshold failed'):
                r.replay_gate('A',self.replay,finalize_after=True)
        self.assertEqual(process.call_count,9)
        self.assertFalse(r.read(self.replay/'summary.json')['success'])
        self.assertFalse((self.root/'gate_pass.json').exists())

    def test_original_pair_decision_extra_or_wrong_fields_rejected(self):
        self.ledger['pairs'][0]['criterion'] = 'invented permissive decision'
        self.ledger['pairs'][0]['unregistered_field'] = True
        (self.batch/'ledger.json').write_text(json.dumps(self.ledger))
        with patch.object(r.subprocess,'run',side_effect=self.fake_analyzer):
            with self.assertRaisesRegex(ValueError,'Stored paired decisions differ'):
                r.replay_gate('A',self.replay,finalize_after=True)
        self.assertFalse(r.read(self.replay/'summary.json')['success'])
        self.assertFalse((self.root/'gate_pass.json').exists())

    def test_final_verification_recomputes_pairs_despite_consistent_rewritten_hashes(self):
        self.complete(finalize=False)
        original,repeated = self.batch/'run002/r03_metrics.json',self.replay/'run002/r03_metrics.json'
        value = r.read(original); value['yaw_rmse'] = .5
        original.write_text(json.dumps(value)); repeated.write_text(json.dumps(value))
        self.ledger['attempts'][1]['metrics_sha256'] = r.digest(original)
        (self.batch/'ledger.json').write_text(json.dumps(self.ledger))
        summary = r.read(self.replay/'summary.json')
        summary['ledger_sha256'] = r.digest(self.batch/'ledger.json')
        summary['source_batch_snapshot'] = r.tree_snapshot(self.batch)
        row = summary['rows'][1]; row['input_files'] = r.raw_snapshot(original.parent)['files']
        row['source_metrics_sha256'] = r.digest(original); row['replay_metrics_sha256'] = r.digest(repeated)
        (self.replay/'summary.json').write_text(json.dumps(summary))
        with self.assertRaisesRegex(ValueError,'Recomputed paired risk threshold failed'): r.finalize('A')
        self.assertFalse((self.root/'gate_pass.json').exists())


if __name__ == '__main__':
    unittest.main()
