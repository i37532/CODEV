"""Offline RI05 finite design and A-to-B authority tests."""
import copy
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_ri05_protocol_tests', HERE/'protocol.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


class DesignTests(unittest.TestCase):
    def test18_exact_ids(self):
        self.assertEqual([j['id'] for j in p.design()['jobs']], [f'run{i:03d}' for i in range(1, 19)])

    def test_gate_mapping(self):
        self.assertEqual((p.GATES['C']['milestone_gate'], p.GATES['D']['milestone_gate']), ('A', 'B'))
        self.assertEqual((p.GATES['C']['test'], p.GATES['D']['test']), (6, 8))

    def test_each_gate9_three_paired_newseeds(self):
        for gate in p.GATES:
            jobs = p.jobs(gate); self.assertEqual(len(jobs), 9)
            for seed in p.GATES[gate]['seeds']:
                self.assertEqual(sorted(j['mode'] for j in jobs if j['seed']==seed), [0, 3, 4])

    def test_balanced_predeclared_order_pid_first(self):
        for gate in p.GATES:
            self.assertEqual([j['mode'] for j in p.jobs(gate)], [0,3,4,0,4,3,0,3,4])

    def test_no_shared_seeds_across_gates(self):
        self.assertFalse(set(p.GATES['C']['seeds']) & set(p.GATES['D']['seeds']))

    def test_gate_budget18_not_retry(self):
        for gate in p.GATES:
            b=p.budget(gate)
            self.assertEqual((b['maximum_attempts'],b['total_maximum_attempts'],b['historical_attempts']), (9,18,0))

    def test_all127_parameters_fixed_across_gates(self):
        fixed=p.design()['fixed_parameters']; self.assertEqual(len(fixed),127)
        for j in p.design()['jobs']:
            omitted={'MPC_VC_MODE','MPC_VC_AXES','MPC_VCT_TEST'}
            self.assertEqual({k:v for k,v in j['parameters'].items() if k not in omitted},
                             {k:v for k,v in fixed.items() if k not in omitted})

    def test_not_bandwidth_candidate(self):
        for j in p.design()['jobs']:
            self.assertEqual([j['parameters'][k] for k in ('MPC_VC_L1_Z','MPC_VC_L2_Z','MPC_VC_EPS_Z')],[2,1,.02])

    def test_inner_fixed_actual_profile(self):
        for j in p.design()['jobs']:
            for key,value in dict(MC_RTC_MODE=0,MC_STA_AXES=0,MC_RTC_DIV=1,MC_RATT_TEST=0,MC_STA_TKO_MGT=0,MPC_VC_DIV=1).items():
                self.assertEqual(j['parameters'][key],value)

    def test_invalid_gate_no_defaulttox(self):
        for value in ('A','B','E','',None,3):
            with self.subTest(value=value),self.assertRaises(ValueError):p.valid_gate(value)

    def test_main_window64_and_original_thresholds(self):
        for gate in p.GATES:
            value=p.load_protocol(gate)
            self.assertEqual(value['excitation']['duration_s'],64)
            self.assertEqual(value['diagnostic_gate']['minimum_excitation_samples'],6390)
            self.assertEqual(value['diagnostic_gate']['minimum_excitation_span_s'],63.96)

    def test_authority_exact_bytes(self):
        self.assertEqual(p.fingerprint(p.AUTHORIZATION),p.AUTHORIZATION_SHA)

    def test_manifest_parameter_tamper_rejected(self):
        changed=p.design();changed['jobs'][0]['parameters']['MPC_VC_L1_Z']=20
        with self.assertRaises(ValueError):p.validate_manifest(changed)

    def test_manifest_more_budget_rejected(self):
        changed=p.design();changed['maximum_attempts']=19
        with self.assertRaises(ValueError):p.validate_manifest(changed)

    def test_c_prerequisite_does_not_read_future_gate(self):
        with patch.object(p,'read',side_effect=AssertionError('unexpected read')):
            self.assertIsNone(p.require_prior_gate('C'))

    def test_d_missing_prior_receipt_rejected(self):
        with patch.object(p,'read',side_effect=FileNotFoundError('missing C')):
            with self.assertRaises(FileNotFoundError):p.require_prior_gate('D')

    def test_d_partial_boolean_not_enough(self):
        with patch.object(p,'read',return_value={'accepted':True}):
            with self.assertRaises(PermissionError):p.require_prior_gate('D')

    def test_d_wrong_replay_identity_rejected(self):
        receipt=self.receipt();receipt['replay_summary_path']='/tmp/foreign/summary.json'
        with patch.object(p,'read',return_value=receipt):
            with self.assertRaises(PermissionError):p.require_prior_gate('D')

    @staticmethod
    def receipt():
        return dict(stage='RI05-C',revision='ri05',gate='C',accepted=True,planned=9,attempts=9,
            accepted_runs=9,independent_replays=9,paired_checks=6,missing=0,parameter_restore_exact=True,
            new_flights_by_replay=0,replay_summary_path=str(p.DATA_ROOT/'C/replay01/summary.json'),
            replay_summary_sha256='b'*64,ledger_sha256='b'*64,source_head='c'*40,firmware_sha256='d'*64)

    def test_d_checks_full_independent_replay_notjust_counts(self):
        receipt=self.receipt()
        decoder=types.SimpleNamespace(verify_complete=lambda *args,**kwargs: (_ for _ in ()).throw(ValueError('bad replay')))
        with patch.object(p,'read',return_value=receipt),patch.object(p,'fingerprint',return_value='b'*64),\
             patch.object(p,'load_file',return_value=types.SimpleNamespace(local=lambda name:decoder)):
            with self.assertRaisesRegex(ValueError,'bad replay'):p.require_prior_gate('D')

    def test_d_complete_fixture_replays_c_only(self):
        receipt=self.receipt();calls=[]
        ledger=dict(source_head=receipt['source_head'],firmware_sha256=receipt['firmware_sha256'])
        decoder=types.SimpleNamespace(verify_complete=lambda *args,**kwargs:calls.append((args,kwargs)))
        with patch.object(p,'read',side_effect=[receipt,ledger]),patch.object(p,'fingerprint',return_value='b'*64),\
             patch.object(p,'load_file',return_value=types.SimpleNamespace(local=lambda name:decoder)):
            self.assertEqual(p.require_prior_gate('D'),receipt)
        self.assertEqual(calls, [((p.DATA_ROOT/'C/replay01',),{'gate':'C'})])

    def test_d_ledger_source_mismatch_rejected(self):
        receipt=self.receipt();ledger=dict(source_head='e'*40,firmware_sha256=receipt['firmware_sha256'])
        decoder=types.SimpleNamespace(verify_complete=lambda *args,**kwargs:True)
        with patch.object(p,'read',side_effect=[receipt,ledger]),patch.object(p,'fingerprint',return_value='b'*64),\
             patch.object(p,'load_file',return_value=types.SimpleNamespace(local=lambda name:decoder)):
            with self.assertRaises(PermissionError):p.require_prior_gate('D')

    def test_new_proper_not_in_manifest(self):
        self.assertEqual({j['candidate'] for j in p.design()['jobs']},{'PID','RSTA','RISTA'})


if __name__=='__main__':unittest.main()
