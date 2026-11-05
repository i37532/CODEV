"""Offline R03 registration/authority negatives. Never launches a simulator.

Qualification receipts below are in-memory mock payloads, NOT flight authority.
Historical seed traversal is mocked so tests cannot register/consume any seed.
"""
import copy
import hashlib
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('r03_revision02_protocol_under_test', HERE/'protocol.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.value = copy.deepcopy(p.design())

    def rejected(self, value):
        with self.assertRaises(ValueError):
            p.validate_manifest(value)

    def test_real_registration_matches_pinned_source_and_current_authority(self):
        self.assertTrue(p.validate_manifest(self.value))
        self.assertEqual(p.fingerprint(p.SOURCE), p.SOURCE_SHA)
        self.assertEqual(self.value['authorization_sha256'], p.fingerprint(p.AUTHORIZATION))
        self.assertEqual(self.value['maximum_attempts'], 44)
        self.assertEqual(self.value['attempts_per_gate'], 9)
        self.assertEqual(self.value['baseline_head'], '080528bd30f4a8b7816f5097d789fc71e56ecefe')

    def test_exact_unique_jobs_and_four_ordered_gates(self):
        jobs = self.value['jobs']
        self.assertEqual([j['id'] for j in jobs], ['run%03d' % i for i in range(1, 37)])
        self.assertEqual([j['gate'] for j in jobs], list('A'*9+'B'*9+'C'*9+'D'*9))
        self.assertEqual(len({(j['gate'], j['seed'], j['candidate']) for j in jobs}), 36)

    def test_twelve_new_blocks_do_not_overlap_any_protected_family(self):
        expected = [71101,71102,71103,71111,71112,71113,71121,71122,71123,71131,71132,71133]
        self.assertEqual(self.value['seeds'], expected)
        self.assertEqual(len(set(expected)), 12)
        protected = set(range(41001,41021)) | set(range(52001,52021)) | {51001,51002,51003,51011,51012,51013}
        self.assertFalse(set(expected) & protected)
        for seed in expected:
            rows = [j for j in self.value['jobs'] if j['seed'] == seed]
            self.assertEqual(len(rows), 3)
            self.assertEqual({j['candidate'] for j in rows}, {'PID', 'ESTA', 'RSTA'})
            self.assertEqual(len({j['gate'] for j in rows}), 1)

    def test_pid_safety_first_and_old_new_order_balanced_globally(self):
        orders = []
        for offset in range(0, 36, 3):
            block = self.value['jobs'][offset:offset+3]
            self.assertEqual([j['position'] for j in block], [1, 2, 3])
            self.assertEqual(block[0]['candidate'], 'PID')
            self.assertEqual(len({j['seed'] for j in block}), 1)
            orders.append(tuple(j['candidate'] for j in block[1:]))
        self.assertEqual(orders.count(('ESTA', 'RSTA')), 6)
        self.assertEqual(orders.count(('RSTA', 'ESTA')), 6)

    def test_all127_parameters_fixed_across_algorithms_and_axes(self):
        excluded = {'MPC_VC_MODE', 'MPC_VC_AXES', 'MPC_VCT_TEST'}
        reference = None
        for job in self.value['jobs']:
            params = job['parameters']
            self.assertEqual(len(params), 127)
            constant = {k:v for k,v in params.items() if k not in excluded}
            if reference is None:
                reference = constant
            self.assertEqual(constant, reference)
            self.assertEqual(params['MPC_VC_MODE'], job['mode'])
            self.assertEqual(params['MPC_VC_AXES'], job['axes'])
            self.assertEqual(params['MPC_VC_DIV'], 1)
            for key, value in {'MC_RTC_MODE':0, 'MC_STA_AXES':0, 'MC_RTC_DIV':1,
                               'MC_RATT_TEST':0, 'MC_STA_TKO_MGT':0}.items():
                self.assertEqual(params[key], value)
            for axis, epsilon in zip('XYZ', (.01,.01,.02)):
                self.assertEqual(params['MPC_VC_EPS_'+axis], epsilon)

    def test_original_fixed_parameter_values_not_reoptimized(self):
        original = p.read(p.SOURCE)['fixed_parameters']
        self.assertEqual({k:self.value['fixed_parameters'][k] for k in original}, original)
        self.assertEqual(set(self.value['fixed_parameters']) - set(original),
                         {'MPC_VC_EPS_X', 'MPC_VC_EPS_Y', 'MPC_VC_EPS_Z'})

    def test_duplicate_missing_or_extra_jobs_rejected(self):
        for action in ('duplicate', 'missing', 'extra'):
            value = copy.deepcopy(self.value)
            if action == 'duplicate':
                value['jobs'][1] = copy.deepcopy(value['jobs'][0])
            elif action == 'missing':
                value['jobs'].pop()
            else:
                value['jobs'].append(copy.deepcopy(value['jobs'][0]))
            with self.subTest(action=action):
                self.rejected(value)

    def test_gate_or_safety_order_swaps_rejected(self):
        for first, second in ((0,1), (0,9), (9,18), (27,28)):
            value = copy.deepcopy(self.value)
            value['jobs'][first], value['jobs'][second] = value['jobs'][second], value['jobs'][first]
            with self.subTest(indices=(first,second)):
                self.rejected(value)

    def test_unknown_mode_axis_gate_or_divisor_rejected(self):
        for key, val in (('mode',2), ('mode',4), ('axes',2), ('gate','E'), ('divisor',2)):
            value = copy.deepcopy(self.value); value['jobs'][2][key] = val
            with self.subTest(key=key, value=val):
                self.rejected(value)

    def test_boolean_or_float_cannot_impersonate_exact_integer_payload(self):
        for key, val in (('mode',True), ('axes',True), ('divisor',1.0), ('position',2.0)):
            value = copy.deepcopy(self.value); value['jobs'][1][key] = val
            with self.subTest(key=key, value=val):
                self.rejected(value)

    def test_single_algorithm_retune_or_scope_change_rejected(self):
        for key, val in (('MPC_VC_L1_X',.6), ('MPC_VC_EPS_Z',.03), ('MPC_VC_NU_X',.5),
                         ('MC_RTC_MODE',1), ('MPC_VCT_TEST',8), ('MPC_VC_DIV',2)):
            value = copy.deepcopy(self.value); value['jobs'][2]['parameters'][key] = val
            with self.subTest(key=key):
                self.rejected(value)

    def test_budget_authority_and_source_payload_mutations_rejected(self):
        for key, val in (('maximum_attempts',38), ('attempts_per_gate',10),
                         ('authorization_sha256','0'*64), ('parameter_source_sha256','0'*64),
                         ('baseline_head','0'*40)):
            value = copy.deepcopy(self.value); value[key] = val
            with self.subTest(key=key):
                self.rejected(value)

    def test_seed_duplicate_or_protected_payload_rejected(self):
        for seed in (71101,41001,41020,52001,52020,51003):
            value = copy.deepcopy(self.value); value['jobs'][3]['seed'] = seed
            with self.subTest(seed=seed):
                self.rejected(value)

    def test_protected_seed_guard_rejects_even_rebuilt_design(self):
        for seed in (41001,52020):
            gates = copy.deepcopy(p.GATES); gates['A']['seeds'][0] = seed
            seeds = [s for g in gates.values() for s in g['seeds']]
            with self.subTest(seed=seed), patch.object(p, 'GATES', gates), patch.object(p, 'SEEDS', seeds):
                self.rejected(copy.deepcopy(p.build()))

    def test_source_sha_failure_and_prepare_overwrite_are_closed(self):
        with patch.object(p, 'SOURCE_SHA', '0'*64):
            with self.assertRaisesRegex(ValueError, 'Historical'):
                p.build()
        with self.assertRaisesRegex(ValueError, 'replace'):
            p.prepare()

    def test_build_payload_mutation_cannot_change_canonical_gate_or_seeds(self):
        before_gates, before_seeds = copy.deepcopy(p.GATES), list(p.SEEDS)
        # Isolate constants even when this negative discovers an alias bug.
        with patch.object(p, 'GATES', copy.deepcopy(before_gates)), patch.object(p, 'SEEDS', list(before_seeds)):
            value = p.build(); value['gates']['A']['seeds'][0] = 99999; value['seeds'][1] = 99998
            self.assertEqual(p.GATES, before_gates)
            self.assertEqual(p.SEEDS, before_seeds)

    def test_load_protocol_exact_gate_budget_windows_and_isolation(self):
        expected = {'A':(1,1,32), 'B':(4,2,32), 'C':(3,6,64), 'D':(7,8,64)}
        for gate, (axes,test,duration) in expected.items():
            value = p.load_protocol(gate)
            self.assertEqual(len(value['jobs']), 9)
            self.assertEqual(value['maximum_attempts'], 9)
            self.assertEqual(value['total_maximum_attempts'], 44)
            self.assertEqual(value['excitation']['duration_s'], duration)
            self.assertEqual(value['excitation']['parameter'], test)
            self.assertEqual(value['excitation']['settle_after_auto_loiter_s'], 12)
            self.assertEqual(value['gate_config']['axes'], axes)
            self.assertEqual(value['data_gate']['hover_duration_s'], [90,92])
            self.assertEqual(value['height_task']['observation_sim_s'], 90)
            self.assertEqual(value['diagnostic_gate']['minimum_excitation_samples'], duration*100-10)
            self.assertAlmostEqual(value['diagnostic_gate']['minimum_excitation_span_s'], duration-.04)
            self.assertFalse(value['automatic_retry']); self.assertTrue(value['stop_on_any_required_failure'])
            self.assertEqual({j['gate'] for j in value['jobs']}, {gate})
            self.assertEqual(len({j['seed'] for j in value['jobs']}), 3)
        first = p.load_protocol('A'); first['jobs'][0]['parameters']['MPC_VC_EPS_X'] = .999
        first['gate_config']['seeds'][0] = 99999
        self.assertEqual(p.load_protocol('A')['jobs'][0]['parameters']['MPC_VC_EPS_X'], .01)
        self.assertEqual(p.load_protocol('A')['gate_config']['seeds'][0], 71101)

    def test_unknown_gate_never_silently_becomes_x(self):
        for gate in ('', 'E', 'a', 'X', 1, None):
            with self.subTest(gate=gate), self.assertRaises(ValueError):
                p.load_protocol(gate)

    def test_load_protocol_authority_and_interpretation_not_stale_v04_or_ax(self):
        value = p.load_protocol('A')
        self.assertNotIn('six attempts', str(value['authorization']))
        self.assertEqual(value['authorization']['maximum_attempts'], 44)
        self.assertEqual(value['authorization']['this_gate_attempts'], 9)
        self.assertEqual(value['pair_gate']['candidates'], 2)
        self.assertNotIn('axis configuration development ablation', value['metrics']['interpretation'])


class SeedHistoryTest(unittest.TestCase):
    def audit(self, matches=None, invalid=None):
        return dict(seeds=list(p.SEEDS), matches=list(matches or []), invalid_json=list(invalid or []),
                    accepted=not matches and not invalid, files_parsed=1)

    def mock_loader(self, result):
        fake = types.SimpleNamespace(CONFIG=Path('/old-exempt-root'),
                                     seed_audit=lambda _: copy.deepcopy(result))
        return patch.object(p, 'load_file', return_value=fake)

    def test_exact_current_unattempted_registration_is_not_a_used_seed(self):
        allowed = p.read(p.HERE/'seed_reservations.json')
        path = next(iter(allowed)); result = self.audit([dict(path=path, seeds=[71101])])
        with self.mock_loader(result):
            value = p.fresh_seeds()
        self.assertTrue(value['accepted']); self.assertEqual(value['matches'], [])
        self.assertEqual(len(value['design_registrations']), 1)

    def test_historical_used_seed_is_not_exempt_by_directory(self):
        result = self.audit([dict(path=str(p.HERE/'used_run.json'), seeds=[71101])])
        with self.mock_loader(result):
            value = p.fresh_seeds('A')
        self.assertFalse(value['accepted']); self.assertEqual(len(value['matches']), 1)

    def test_invalid_history_json_prevents_fresh_claim(self):
        with self.mock_loader(self.audit(invalid=['/history/broken.json'])):
            self.assertFalse(p.fresh_seeds()['accepted'])

    def test_changed_exact_registration_rejected(self):
        with self.mock_loader(self.audit()), patch.object(p, 'fingerprint', return_value='0'*64):
            with self.assertRaises(ValueError):
                p.fresh_seeds()

    def test_unknown_seed_gate_rejected_before_audit(self):
        with self.mock_loader(self.audit()):
            with self.assertRaises(ValueError):
                p.fresh_seeds('E')

    def test_registration_cannot_whitelist_arbitrary_used_history(self):
        original_read = p.read
        payload = {'/history/already_flown.json': '1'*64}
        def read(path):
            return payload if Path(path).name == 'seed_reservations.json' else original_read(path)
        result = self.audit([dict(path='/history/already_flown.json', seeds=[71101])])
        with self.mock_loader(result), patch.object(p, 'read', side_effect=read), patch.object(p, 'fingerprint', return_value='1'*64):
            with self.assertRaises(ValueError):
                p.fresh_seeds()

    def test_attempted_outcomes_cannot_stay_exempt_registration(self):
        original_read = p.read
        def read(path):
            value = original_read(path)
            if Path(path).name == 'outcomes_unattempted.json':
                value[0]['status'] = 'accepted'
            return value
        with self.mock_loader(self.audit()), patch.object(p, 'read', side_effect=read):
            with self.assertRaises(ValueError):
                p.fresh_seeds()


class QualificationTest(unittest.TestCase):
    def setUp(self):
        self.head = 'f'*40
        self.gate = 'A'
        self.protocol = p.load_protocol('A')
        self.path = p.EXTERNAL/p.DATA_STAGE/'A/qualification01/evidence.json'
        self.hash = lambda path: hashlib.sha256(str(Path(path)).encode()).hexdigest()
        self.historical = p.retained_failure()
        revision = dict(revision=p.REVISION, maximum_attempts=9, new_matrix_attempts=36,
                        historical_attempts=8, total_maximum_attempts=44, historical_budget=self.historical)
        self.q = dict(**revision, success=True, clean=True, stage=self.protocol['stage'], gate='A', source_head=self.head,
                      execution_authorized=False,flight_authorized=False,execution_ready=False,
                      new_flights=0, execution_sha256=self.hash(p.HERE/'execution.json'),
                      frozen_sha256=self.hash(Path(self.protocol['config_dir'])/'frozen.json'),
                      firmware_sha256=self.hash(p.REPO/'build/px4_sitl_default/bin/px4'),
                      counts=dict(cpp_unique_tests=475, python_tests=750), previous_gates=[],
                      evidence_files={str(self.path.parent/'offline/evidence.json'):
                                      self.hash(self.path.parent/'offline/evidence.json')})
        self.receipt = dict(**revision, approved=False, stage=self.protocol['stage'], gate='A', source_head=self.head,
                           execution_authorized=False,flight_authorized=False,execution_ready=False,
                           execution_sha256=self.q['execution_sha256'], frozen_sha256=self.q['frozen_sha256'],
                           firmware_sha256=self.q['firmware_sha256'], qualification_sha256=self.hash(self.path),
                           authorization_sha256=self.hash(p.AUTHORIZATION))
        self.branch = 'research/sta-velocity-regularized'; self.dirty = ''

    def invoke(self, gate='A', path=None):
        original_read = p.read
        def read(path):
            if Path(path) == self.path:
                return copy.deepcopy(self.q)
            if Path(path) == self.path.parent/'authorization.json':
                return copy.deepcopy(self.receipt)
            return original_read(path)
        def git(*args):
            if args == ('rev-parse','HEAD'):
                return self.head
            if args == ('status','--porcelain'):
                return self.dirty
            if args == ('branch','--show-current'):
                return self.branch
            raise AssertionError('Unexpected git command '+repr(args))
        with patch.object(p, 'load_protocol', return_value=copy.deepcopy(self.protocol)), \
             patch.object(p, 'read', side_effect=read), patch.object(p, 'fingerprint', side_effect=self.hash), \
             patch.object(p, 'git', side_effect=git), patch.object(p, 'retained_failure', return_value=self.historical):
            return p.require_qualification(gate, self.head, path or self.path)

    def test_bound_current_gate_receipt_accepts_only_mocked_offline_record(self):
        self.assertEqual(self.invoke(), self.q)

    def test_failed_dirty_wrong_source_or_firmware_qualification_rejected(self):
        original = copy.deepcopy(self.q)
        for key, value in (('success',False), ('clean',False), ('source_head','e'*40),
                           ('gate','B'), ('stage','R03-B'), ('new_flights',1),
                           ('firmware_sha256','0'*64), ('execution_sha256','0'*64), ('frozen_sha256','0'*64),
                           ('execution_authorized',True),('flight_authorized',True),('execution_ready',True)):
            self.q = copy.deepcopy(original); self.q[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.invoke()

    def test_authority_receipt_payload_changes_never_grant_more_budget(self):
        original = copy.deepcopy(self.receipt)
        for key, value in (('approved',True), ('maximum_attempts',10), ('total_maximum_attempts',38),
                           ('source_head','e'*40), ('qualification_sha256','0'*64),
                           ('authorization_sha256','0'*64), ('gate','B'), ('stage','R03-B'),
                           ('execution_authorized',True),('flight_authorized',True),('execution_ready',True)):
            self.receipt = copy.deepcopy(original); self.receipt[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.invoke()

    def test_empty_or_noninteger_test_counts_rejected(self):
        for count in (0, -1, True, 1.5, None, 474):
            self.q['counts']['cpp_unique_tests'] = count
            with self.subTest(count=count), self.assertRaises(ValueError):
                self.invoke()

    def test_missing_changed_or_foreign_offline_evidence_rejected(self):
        path = self.path.parent/'offline/evidence.json'
        for files in ({}, {str(path):'0'*64}, {'/history/unrelated.json':self.hash('/history/unrelated.json')}):
            self.q['evidence_files'] = files
            with self.subTest(files=files), self.assertRaises(ValueError):
                self.invoke()

    def test_previous_gate_binding_cannot_be_invented(self):
        self.q['previous_gates'] = [dict(gate='invented', receipt_sha256='0'*64)]
        with self.assertRaises(ValueError):
            self.invoke()

    def test_wrong_output_gate_branch_or_dirty_source_rejected(self):
        with self.assertRaises(ValueError):
            self.invoke(path=p.EXTERNAL/p.DATA_STAGE/'B/qualification01/evidence.json')
        self.branch = 'research/sta-velocity-control'
        with self.assertRaises(ValueError):
            self.invoke()
        self.branch = 'research/sta-velocity-regularized'; self.dirty = ' M src/changed.cpp'
        with self.assertRaises(ValueError):
            self.invoke()

    def test_later_gate_requires_actual_previous_gate_acceptance(self):
        self.gate = 'B'; self.protocol = p.load_protocol('B')
        self.path = p.EXTERNAL/p.DATA_STAGE/'B/qualification01/evidence.json'
        self.q.update(gate='B', stage=self.protocol['stage'],
                      frozen_sha256=self.hash(Path(self.protocol['config_dir'])/'frozen.json'))
        self.receipt.update(gate='B', stage=self.protocol['stage'], frozen_sha256=self.q['frozen_sha256'],
                            qualification_sha256=self.hash(self.path))
        # Matching current-gate receipts are insufficient: no A completion exists.
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.invoke(gate='B')


class RevisionBudgetTest(unittest.TestCase):
    def test_actual_both_histories_counted_without_reusing_acceptance(self):
        value = p.retained_history()
        self.assertEqual(value['attempts'], 8)
        self.assertEqual(value['accepted'], 6)
        self.assertEqual(value['failed'], 2)
        self.assertEqual(value['accepted_for_new_matrix'], 0)
        self.assertEqual([(b['attempts'],b['accepted'],b['failed']) for b in value['batches']],
                         [(1,0,1),(7,6,1)])
        self.assertEqual(p.retained_failure(),value)
        self.assertEqual(sum(b['attempts'] for b in value['batches']),8)
        self.assertEqual(len(value['batches'][1]['run_ids']),7)

    def test_either_history_ledger_fingerprint_drift_rejected(self):
        original=p.fingerprint
        for spec in p.HISTORY_SPECS:
            path=p.EXTERNAL/spec['stage']/'A/batch01/ledger.json'
            with self.subTest(stage=spec['stage']), patch.object(p,'fingerprint',
                    side_effect=lambda x: '0'*64 if Path(x)==path else original(x)):
                with self.assertRaisesRegex(ValueError,'ledger changed'):
                    p.retained_history()

    def test_either_history_journal_fingerprint_drift_rejected(self):
        original=p.fingerprint
        for spec in p.HISTORY_SPECS:
            path=p.EXTERNAL/spec['stage']/'A/batch01/journal.jsonl'
            with self.subTest(stage=spec['stage']), patch.object(p,'fingerprint',
                    side_effect=lambda x: '0'*64 if Path(x)==path else original(x)):
                with self.assertRaisesRegex(ValueError,'journal changed'):
                    p.retained_history()

    def test_extra_old_attempt_ledger_or_journal_rejected(self):
        original=Path.glob
        for spec in p.HISTORY_SPECS:
            for pattern in ('*/batch*/ledger.json','*/batch*/journal.jsonl'):
                root=p.EXTERNAL/spec['stage']
                def glob(path,pat):
                    found=list(original(path,pat))
                    if path==root and pat==pattern:
                        found.append(root/'B/batch02'/Path(pattern).name)
                    return iter(found)
                with self.subTest(stage=spec['stage'],pattern=pattern), patch.object(Path,'glob',glob):
                    with self.assertRaisesRegex(ValueError,'set changed'):
                        p.retained_history()

    def test_restore_false_and_original_verdict_change_rejected(self):
        original=p.read
        for spec in p.HISTORY_SPECS:
            path=p.EXTERNAL/spec['stage']/'A/batch01/ledger.json'
            for mutation in ('restore','failed_reclassified','extra'):
                def read(file):
                    value=original(file)
                    if Path(file)==path:
                        if mutation=='restore':
                            value['parameter_restore_exact']=False
                        elif mutation=='failed_reclassified':
                            value['attempts'][-1]['status']='accepted'
                        else:
                            value['attempts'].append(copy.deepcopy(value['attempts'][-1]))
                    return value
                with self.subTest(stage=spec['stage'],mutation=mutation), patch.object(p,'read',side_effect=read):
                    with self.assertRaisesRegex(ValueError,'count/verdict/cleanup'):
                        p.retained_history()

    def test_orphan_history_batch_without_ledger_is_not_free_budget(self):
        original=Path.glob
        root=p.EXTERNAL/'R03_revision01'
        def glob(path,pat):
            found=list(original(path,pat))
            if path==root and pat=='*/batch*':
                found.append(root/'B/batch02')
            return iter(found)
        with patch.object(Path,'glob',glob),self.assertRaisesRegex(ValueError,'batch set'):
            p.retained_history()

    def test_orphan_history_run_without_ledger_row_is_rejected(self):
        original=Path.glob
        root=p.EXTERNAL/'R03_revision01/A/batch01'
        def glob(path,pat):
            found=list(original(path,pat))
            if path==root and pat=='run[0-9][0-9][0-9]':
                found.append(root/'run008')
            return iter(found)
        with patch.object(Path,'glob',glob),self.assertRaisesRegex(ValueError,'run directory set'):
            p.retained_history()

    def test_per_attempt_restore_receipt_is_required(self):
        original=p.read
        target=p.EXTERNAL/'R03_revision01/A/batch01/run007/parameter_restore.json'
        for key,val in (('parameter_restore_exact',False),('remaining_simulators',[99]),
                        ('restored_parameter_sha256','0'*64),('stopped_before_restore',False)):
            def read(file):
                value=original(file)
                if Path(file)==target:
                    value[key]=val
                return value
            with self.subTest(key=key), patch.object(p,'read',side_effect=read):
                with self.assertRaisesRegex(ValueError,'restore receipt'):
                    p.retained_history()

    def test_old_accepted_metrics_change_is_not_ignored(self):
        original=p.fingerprint
        target=p.EXTERNAL/'R03_revision01/A/batch01/run006/r03_metrics.json'
        with patch.object(p,'fingerprint',side_effect=lambda f:'0'*64 if Path(f)==target else original(f)):
            with self.assertRaisesRegex(ValueError,'accepted result changed'):
                p.retained_history()

    def test_exact_budget_and_fresh_seeds_across_both_old_designs(self):
        value=p.design()
        self.assertEqual(value['maximum_attempts'],value['historical_attempts']+len(value['jobs']))
        self.assertEqual(value['maximum_attempts'],44)
        self.assertEqual(value['new_matrix_attempts'],36)
        for name in ('r03','r03_revision01'):
            old=p.read(p.HERE.parent/name/'execution.json')
            self.assertFalse(set(value['seeds']) & set(old['seeds']))
        self.assertTrue(all(j['revision']==p.REVISION for j in value['jobs']))
        self.assertEqual(44+54+200,298)

    def test_old_new_full_parameters_tasks_thresholds_and_order_unchanged(self):
        old=p.read(p.HERE.parent/'r03_revision01/execution.json')
        for new,previous in zip(p.design()['jobs'],old['jobs']):
            for key in set(new)-{'revision','seed'}:
                self.assertTrue(p.exact(new[key],previous[key]),key)
        self.assertTrue(p.exact(p.design()['protocol_overrides'],old['protocol_overrides']))
        self.assertTrue(p.exact(p.design()['fixed_parameters'],old['fixed_parameters']))

    def test_old_reserved_but_unflown_seeds_also_rejected(self):
        for seed in (71002,71011,71031,71043,71051,71073):
            gates=copy.deepcopy(p.GATES);gates['A']['seeds'][0]=seed
            seeds=[s for g in gates.values() for s in g['seeds']]
            with self.subTest(seed=seed),patch.object(p,'GATES',gates),patch.object(p,'SEEDS',seeds):
                with self.assertRaisesRegex(ValueError,'Protected seed'):
                    p.validate_manifest(p.build())

    def test_historical_budget_cannot_become_new_attempts(self):
        for key,value in (('historical_attempts',2),('new_matrix_attempts',44),
                          ('maximum_attempts',45),('revision','r03_revision01')):
            d=copy.deepcopy(p.design());d[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                p.validate_manifest(d)


class OfflineAuthorizationTest(unittest.TestCase):
    def test_all_gate_plans_explicitly_closed(self):
        for gate in p.GATES:
            value=p.load_protocol(gate)
            for key in ('execution_authorized','flight_authorized','execution_ready'):
                self.assertIs(value[key],False)
                self.assertIs(p.design()[key],False)
            self.assertEqual(value['status'],'plan_frozen_but_execution_not_started')
            self.assertEqual(value['historical_attempts'],8)
            self.assertEqual(value['authorization']['maximum_attempts'],44)

    def test_no_gate_may_execute_even_if_qualification_or_legacy_authority_exists(self):
        for gate in p.GATES:
            with self.subTest(gate=gate),patch.object(p,'read',side_effect=AssertionError('No receipt reads needed')):
                with self.assertRaisesRegex(PermissionError,'offline-only'):
                    p.require_execution_authority(gate)

    def test_manifest_cannot_turn_authority_on_using_bool_or_integer(self):
        for key in ('execution_authorized','flight_authorized','execution_ready'):
            for value in (True,1,0,None,'false'):
                d=copy.deepcopy(p.design());d[key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                    p.validate_manifest(d)

    def test_unknown_execution_gate_rejected(self):
        with self.assertRaises(ValueError):
            p.require_execution_authority('E')


if __name__ == '__main__':
    unittest.main()
