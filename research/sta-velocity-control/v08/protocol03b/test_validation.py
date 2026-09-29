"""Install with validation common/run after selecting from COMPLETE training."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import common
import run


class ValidationTests(unittest.TestCase):
    def test_exact_budget_one_candidate_each_and_disjoint_seeds(self):
        p=common.load_protocol();jobs=p['jobs'];self.assertEqual(len(jobs),12)
        for mode in (0,1):
            group=[j for j in jobs if j['mode']==mode]
            self.assertEqual(len(group),6);self.assertEqual(len({j['candidate'] for j in group}),1)
            self.assertEqual(len({(j['task'],j['seed']) for j in group}),6)
            self.assertEqual({j['axes'] for j in group},{mode*3})
        self.assertFalse({j['seed'] for j in jobs}&set(common.training.design()['training_seeds']))
        self.assertFalse({j['seed'] for j in jobs}&set(common.training.design()['formal_seeds']))

    def test_no_gain_change_or_reselection(self):
        selection=json.loads((common.CONFIG/'selection.json').read_text())
        for job in common.load_protocol()['jobs']:
            expected={**selection['parameters'][str(job['mode'])],'MPC_VCT_TEST':job['parameters']['MPC_VCT_TEST']}
            self.assertEqual(job['parameters'],expected)

    def test_changed_selection_refused(self):
        original=common.fingerprint
        with patch.object(common,'fingerprint',side_effect=lambda p:'changed' if p==common.CONFIG/'selection.json' else original(p)):
            with self.assertRaises(RuntimeError):common.load_protocol()

    def test_wrong_execution_job_list_refused(self):
        d=copy.deepcopy(common.design());d['jobs']=d['jobs'][::-1]
        with patch.object(common,'design',return_value=d),self.assertRaises(RuntimeError):common.load_protocol()

    def test_missing_authority_refused(self):
        with self.assertRaises(RuntimeError):common.require_authorization('',common.load_protocol())

    def test_seed_registry_does_not_ignore_real_prior_flight(self):
        matches=[dict(path='/tmp/actual_previous_flight/job.json')]
        with patch.object(common.training,'seed_audit',return_value=dict(matches=matches,invalid_json=[])):
            self.assertFalse(common.fresh_seeds()['accepted'])

    def fixture(self,job,accepted=True):
        error=dict(rmse=[.01]*3)
        return dict(accepted=accepted,job=job,diagnostic=dict(error=error,
                    windows={k:dict(error=error) for k in ('first_loop','second_loop')}),
                    position_rmse=[.01]*3,yaw_rmse=.01)

    def test_pair_gate_actual_compare_and_duplicate_rejection(self):
        jobs=common.load_protocol()['jobs'][:2];run.accepted.clear()
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)
            for job in jobs:
                with patch.object(run,'base_analyze',return_value=self.fixture(job)):
                    self.assertTrue(run.analyze(out,{},job)['accepted'])
            pair=json.loads((out/'validation_pair.json').read_text());self.assertTrue(pair['accepted'])
            with patch.object(run,'base_analyze',return_value=self.fixture(jobs[-1])),self.assertRaises(RuntimeError):
                run.analyze(out,{},jobs[-1])

    def test_pair_performance_rejection_is_not_swallowed(self):
        jobs=common.load_protocol()['jobs'][:2];run.accepted.clear()
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)
            for job in jobs:
                value=self.fixture(job)
                if job['mode']==1:value['diagnostic']['error']['rmse']=[1.,1.,1.]
                with patch.object(run,'base_analyze',return_value=value):
                    if len(run.accepted.get((job['task'],job['seed']),{}))==1:
                        with self.assertRaises(RuntimeError):run.analyze(out,{},job)
                    else:run.analyze(out,{},job)
            self.assertFalse(json.loads((out/'validation_pair.json').read_text())['accepted'])

    def test_rejected_individual_not_added_as_pair(self):
        job=common.load_protocol()['jobs'][0];run.accepted.clear()
        with tempfile.TemporaryDirectory() as t,patch.object(run,'base_analyze',return_value=self.fixture(job,False)):
            self.assertFalse(run.analyze(Path(t),{},job)['accepted'])
            self.assertEqual(run.accepted,{})

    def batch(self,**kwargs):
        import test_v04_protocol09 as inherited_tests
        from landing_health import require_passive
        from qualification import require_qualification
        soft=common.REPO/'research/sta-velocity-control/v06/soft_landing'
        with patch.object(run.runtime,'require_qualification',side_effect=lambda _:require_qualification(soft/'qualified_contact.json')), \
             patch.object(run.runtime,'require_passive',side_effect=lambda _:require_passive(soft/'offline03/evidence.json')), \
             patch.object(inherited_tests,'runner',run.runtime),patch.object(inherited_tests,'load_protocol',common.load_protocol), \
             patch.object(run.runtime.ram_log,'release_archived'):
            return inherited_tests.Protocol09Test.batch(self,**kwargs)

    def test_actual_runner_twelve_budget_and_restore(self):
        calls,ledger=self.batch();self.assertEqual(calls,common.load_protocol()['jobs']);self.assertTrue(ledger['success'])

    def test_actual_runner_first_failure_stops_restores(self):
        for n in (1,2,6,12):
            calls,ledger=self.batch(fail_at=n);self.assertEqual(len(calls),n);self.assertFalse(ledger['success'])


if __name__=='__main__':unittest.main(verbosity=2)
