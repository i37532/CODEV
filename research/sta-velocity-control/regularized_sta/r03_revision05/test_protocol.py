"""Offline continuation contract: no simulator, parameter write or seed use."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('r03_rev05_test_protocol', HERE/'protocol.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class DesignTests(unittest.TestCase):
    def test_exact_registered_design(self):
        self.assertTrue(p.validate_manifest())

    def test_budget_and_history_are_not_new_acceptance(self):
        d=p.design()
        self.assertEqual((d['maximum_attempts'],d['historical_attempts'],d['new_matrix_attempts']),(57,30,27))
        h=p.retained_history()
        self.assertEqual((h['attempts'],h['takeoffs'],h['accepted'],h['failed']),(30,29,26,4))
        self.assertEqual(h['accepted_for_new_matrix'],0)
        self.assertEqual([b['attempts'] for b in h['batches']],[1,7,7,9,6])

    def test_only_new_bcd_and_preserved_ids(self):
        d=p.design()
        self.assertEqual(list(d['gates']),['B','C','D'])
        self.assertEqual([j['id'] for j in d['jobs']],['run%03d'%i for i in range(10,37)])
        self.assertEqual([j['gate'] for j in d['jobs']],list('B'*9+'C'*9+'D'*9))

    def test_science_and_order_exact_old_bcd(self):
        old=[j for j in p.read(p.PREVIOUS_DESIGN/'manifest.json') if j['gate']!='A']
        for a,b in zip(old,p.design()['jobs']):
            self.assertTrue(p.exact({k:v for k,v in a.items() if k not in ('revision','seed')},
                                    {k:v for k,v in b.items() if k not in ('revision','seed')}))
            self.assertNotEqual(a['seed'],b['seed'])

    def test_pid_first_and_balanced_tail_accounted(self):
        jobs=p.design()['jobs'];tails=[]
        for i in range(0,27,3):
            block=jobs[i:i+3]
            self.assertEqual(block[0]['candidate'],'PID')
            self.assertEqual(len({j['seed'] for j in block}),1)
            tails.append(block[1]['candidate'])
        self.assertEqual(tails.count('RSTA'),5)
        self.assertEqual(tails.count('ESTA'),4)

    def test_nine_new_seed_blocks_do_not_reuse_reserved(self):
        self.assertEqual(len(set(p.SEEDS)),9)
        self.assertFalse(set(p.SEEDS)&p.PROTECTED_SEEDS)
        self.assertFalse(set(p.SEEDS)&set(p.read(p.PREVIOUS_DESIGN/'execution.json')['seeds']))

    def test_all127_parameters_and_inner_pid_fixed(self):
        jobs=p.design()['jobs'];reference=None
        for j in jobs:
            params=j['parameters'];self.assertEqual(len(params),127)
            constant={k:v for k,v in params.items() if k not in ('MPC_VC_MODE','MPC_VC_AXES','MPC_VCT_TEST')}
            if reference is None:reference=constant
            self.assertTrue(p.exact(reference,constant))
            for k,v in dict(MC_RTC_MODE=0,MC_STA_AXES=0,MC_RTC_DIV=1,MC_RATT_TEST=0,MC_STA_TKO_MGT=0,MPC_VC_DIV=1).items():
                self.assertEqual(params[k],v)

    def test_retained_a_is_complete_fixed_old_gate(self):
        a=p.retained_a()
        self.assertEqual((a['accepted'],a['independent_replays'],a['paired_checks']),(9,9,6))
        self.assertEqual(a['revision'],'r03_revision04')
        self.assertEqual(a['accepted_for_new_matrix'],0)
        self.assertTrue(p.exact(a,p.design()['retained_a']))

    def test_retained_a_sha_change_rejected(self):
        real=p.fingerprint
        with patch.object(p,'fingerprint',side_effect=lambda x:'0'*64 if Path(x).name=='gate_pass.json' else real(x)):
            with self.assertRaisesRegex(ValueError,'Retained A proof'):p.retained_a()

    def test_retained_a_count_type_alias_rejected(self):
        real=p.read
        def changed(x):
            d=real(x)
            if Path(x).name=='gate_pass.json':d['accepted']=9.0
            return d
        with patch.object(p,'read',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'Retained A acceptance'):p.retained_a()

    def test_old_b_failure_cannot_be_regraded(self):
        real=p.read
        def changed(x):
            d=real(x)
            if Path(x)==p.EXTERNAL/'R03_revision04/B/batch01/ledger.json':d['attempts'][-1]['status']='accepted'
            return d
        with patch.object(p,'read',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'count/verdict'):p.retained_history()

    def test_old_prearm_failure_cannot_gain_takeoff(self):
        real=p.read
        def changed(x):
            d=real(x)
            if Path(x)==p.EXTERNAL/'R03_revision03/A/batch01/run007/result.json':d['events'].append({'name':'takeoff_command'})
            return d
        with patch.object(p,'read',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'takeoff count'):p.retained_history()

    def test_old_sources_and_authorization_pinned(self):
        for name in ('SOURCE_SHA','AUTHORIZATION_SHA','PREVIOUS_MANIFEST_SHA'):
            with self.subTest(name=name),patch.object(p,name,'0'*64):
                with self.assertRaises((ValueError,PermissionError)):p.build()

    def test_no_manifest_budget_or_authority_mutation(self):
        for key,value in [('maximum_attempts',58),('historical_attempts',29),('new_matrix_attempts',28),
                          ('flight_authorized',1),('execution_ready',False),('revision','r03_revision04')]:
            d=copy.deepcopy(p.design());d[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_manifest(d)

    def test_no_missing_extra_duplicate_or_reordered_job(self):
        for action in ('missing','extra','duplicate','reorder'):
            d=copy.deepcopy(p.design())
            if action=='missing':d['jobs'].pop()
            elif action=='extra':d['jobs'].append(copy.deepcopy(d['jobs'][0]))
            elif action=='duplicate':d['jobs'][1]=copy.deepcopy(d['jobs'][0])
            else:d['jobs'][0],d['jobs'][1]=d['jobs'][1],d['jobs'][0]
            with self.subTest(action=action),self.assertRaises(ValueError):p.validate_manifest(d)

    def test_no_gain_mode_axis_seed_or_type_mutation(self):
        for key,value in [('mode',2),('axes',True),('seed',41001),('divisor',1.0),('gate','A')]:
            d=copy.deepcopy(p.design());d['jobs'][1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_manifest(d)
        d=copy.deepcopy(p.design());d['jobs'][1]['parameters']['MPC_VC_EPS_Z']=.03
        with self.assertRaises(ValueError):p.validate_manifest(d)

    def test_gate_windows_and_isolation(self):
        for gate,axes,duration in [('B',4,32),('C',3,64),('D',7,64)]:
            d=p.load_protocol(gate)
            self.assertEqual(d['gate_config']['axes'],axes)
            self.assertEqual(d['excitation']['duration_s'],duration)
            self.assertEqual(d['diagnostic_gate']['minimum_excitation_samples'],duration*100-10)
            self.assertEqual(d['data_gate']['hover_duration_s'],[90,92])
            self.assertEqual(d['maximum_attempts'],9)
            self.assertEqual(d['total_maximum_attempts'],57)
            self.assertTrue(p.exact(d['retained_a'],p.retained_a()))
        d['jobs'][0]['parameters']['MPC_VC_EPS_Z']=.3
        self.assertEqual(p.load_protocol('D')['jobs'][0]['parameters']['MPC_VC_EPS_Z'],.02)

    def test_a_unknown_and_lowercase_gate_rejected(self):
        for gate in ('A','E','b','X',None,1):
            for fn in (p.load_protocol,p.require_execution_authority,p.require_previous_gates,p.fresh_seeds):
                if gate is None and fn is p.fresh_seeds:continue
                with self.subTest(fn=fn.__name__,gate=gate),self.assertRaises(ValueError):fn(gate)

    def test_disabled_authority_cannot_use_older_grant(self):
        with patch.object(p,'EXECUTION_AUTHORIZED',False):
            with self.assertRaises(PermissionError):p.require_execution_authority('B')

    def test_authority_alone_is_not_qualification(self):
        self.assertTrue(p.require_execution_authority('B')['approved'])
        with self.assertRaises(FileNotFoundError):
            p.require_qualification('B','f'*40,p.EXTERNAL/p.DATA_STAGE/'B/no-qualification/evidence.json')

    def test_prepare_cannot_overwrite_registration(self):
        with self.assertRaisesRegex(ValueError,'replace'):p.prepare()


class GateBindingTests(unittest.TestCase):
    def test_b_requires_exact_complete_old_a(self):
        receipt=p.read(p.EXTERNAL/'R03_revision04/A/gate_pass.json')
        fake=types.SimpleNamespace(verify_complete=lambda gate,root:copy.deepcopy(receipt))
        with patch.object(p,'load_file',return_value=fake):
            result=p.require_previous_gates('B')
        self.assertEqual(result,[dict(gate='A',revision='r03_revision04',receipt_sha256=p.retained_a()['receipt_sha256'])])

    def test_old_a_full_replay_mismatch_or_failure_stops_b(self):
        for outcome in ({},None):
            fake=types.SimpleNamespace(verify_complete=lambda *args:outcome)
            with self.subTest(outcome=outcome),patch.object(p,'load_file',return_value=fake):
                with self.assertRaisesRegex(ValueError,'Retained A receipt'):p.require_previous_gates('B')

    def test_c_cannot_skip_missing_new_b(self):
        receipt=p.read(p.EXTERNAL/'R03_revision04/A/gate_pass.json')
        fake=types.SimpleNamespace(verify_complete=lambda *args:copy.deepcopy(receipt))
        original=p.read
        def missing(x):
            if Path(x)==p.EXTERNAL/p.DATA_STAGE/'B/gate_pass.json':raise FileNotFoundError(x)
            return original(x)
        with patch.object(p,'load_file',return_value=fake),patch.object(p,'read',side_effect=missing):
            with self.assertRaises(FileNotFoundError):p.require_previous_gates('C')


class SeedTests(unittest.TestCase):
    def audit(self,matches=None,invalid=None):
        return dict(matches=list(matches or []),invalid_json=list(invalid or []),accepted=True,files_parsed=1)

    def loader(self,result):
        original=p.load_file
        def load(name,path):
            if Path(path).name=='check_v04_protocol02.py':
                return types.SimpleNamespace(CONFIG=None,seed_audit=lambda _:copy.deepcopy(result))
            return original(name,path)
        return patch.object(p,'load_file',side_effect=load)

    def test_exact_four_unattempted_registrations_only(self):
        reservations=p.read(p.HERE/'seed_reservations.json')
        self.assertEqual(len(reservations),4)
        path=next(iter(reservations))
        with self.loader(self.audit([dict(path=path,seeds=[p.SEEDS[0]])])):
            self.assertTrue(p.fresh_seeds('B')['accepted'])

    def test_same_directory_foreign_use_not_exempt(self):
        match=dict(path=str(p.HERE/'already_used.json'),seeds=[p.SEEDS[0]])
        with self.loader(self.audit([match])):
            self.assertFalse(p.fresh_seeds('B')['accepted'])

    def test_invalid_json_not_ignored(self):
        with self.loader(self.audit(invalid=['/broken.json'])):
            self.assertFalse(p.fresh_seeds()['accepted'])

    def test_no_prior_seed_migration(self):
        d=p.seed_migration()
        self.assertEqual((d['kind'],d['files'],d['seed_count'],d['jobs']),('none',{},0,0))
        self.assertNotIn('seeds',d)

    def test_changed_reservation_hash_rejected(self):
        real=p.fingerprint
        with self.loader(self.audit()),patch.object(p,'fingerprint',side_effect=lambda x:'0'*64 if Path(x).name=='seed_audit_initial.json' else real(x)):
            with self.assertRaisesRegex(ValueError,'Changed exact'):p.fresh_seeds()

    def test_attempted_outcome_not_reserved(self):
        real=p.read
        def read(x):
            d=real(x)
            if Path(x).name=='outcomes_unattempted.json':d[0]['status']='accepted'
            return d
        with self.loader(self.audit()),patch.object(p,'read',side_effect=read):
            with self.assertRaisesRegex(ValueError,'Reservation'):p.fresh_seeds()

    def test_no_whole_directory_or_extra_registration_exemption(self):
        real=p.read
        def read(x):
            d=real(x)
            if Path(x).name=='seed_reservations.json':d['/history/used.json']='0'*64
            return d
        with self.loader(self.audit()),patch.object(p,'read',side_effect=read):
            with self.assertRaisesRegex(ValueError,'Only exact'):p.fresh_seeds()

    def test_real_scanner_distinguishes_used_current_and_future_gate(self):
        with tempfile.TemporaryDirectory(prefix='r03-rev05-seed-test-') as folder:
            root=Path(folder);files=[root/'receipt.json']
            files[0].write_text(json.dumps(dict(seed_migration=p.seed_migration(),retained_a=p.retained_a())))
            original=p.load_file
            def loader(name,path):
                module=original(name,path)
                if Path(path).name=='check_v04_protocol02.py':
                    module.subprocess=types.SimpleNamespace(check_output=lambda *a,**kw:'\n'.join(map(str,files)))
                return module
            with patch.object(p,'load_file',side_effect=loader):
                self.assertTrue(p.fresh_seeds('B')['accepted'])
                used=root/'used.json';used.write_text(json.dumps(dict(seed=p.GATES['B']['seeds'][0])));files.append(used)
                self.assertFalse(p.fresh_seeds('B')['accepted'])
                self.assertTrue(p.fresh_seeds('C')['accepted'])


if __name__=='__main__':unittest.main()
