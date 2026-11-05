"""All inherited checks plus full 200-job MOCK; no simulator processes."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import common
import run

spec=importlib.util.spec_from_file_location('pilot_cases',common.REPO/'research/sta-velocity-control/v08/protocol04/test_pilot.py')
pilot=importlib.util.module_from_spec(spec);spec.loader.exec_module(pilot)

class FormalRuntimeTests(pilot.PilotTests):
    def test_exact_eighteen_order_and_immutable_selection(self):
        jobs=common.jobs();self.assertEqual(len(jobs),200)
        self.assertEqual({j['phase'] for j in jobs},{'formal'})
        self.assertEqual({j['seed'] for j in jobs},set(range(41001,41021)))
        for i,scene in enumerate(('hover','figure8','heading','force','mass')):
            group=jobs[i*40:(i+1)*40];self.assertEqual({j['scene'] for j in group},{scene})
            self.assertEqual({(j['seed'],j['mode']) for j in group},{(s,m) for s in range(41001,41021) for m in (0,1)})
    def test_actual_eighteen_runner_and_parameter_restore(self):
        # Enable only the mocked protocol; frozen disk readiness stays unchanged.
        p=common.load_protocol();p['execution_ready']=True
        with patch.object(common,'load_protocol',return_value=p),patch.object(run.runtime,'load_protocol',return_value=p):
            calls,ledger=self.batch();self.assertEqual(calls,common.jobs());self.assertTrue(ledger['success'])
    def test_actual_first_failure_stops_before_next_gate(self):
        p=common.load_protocol();p['execution_ready']=True
        with patch.object(common,'load_protocol',return_value=p),patch.object(run.runtime,'load_protocol',return_value=p):
            for n in (1,40,41,80,81,120,121,160,161,200):
                calls,ledger=self.batch(fail_at=n);self.assertEqual(len(calls),n);self.assertFalse(ledger['success'])
    def test_pair_key_separates_force_and_mass(self):
        run.accepted.clear()
        with tempfile.TemporaryDirectory() as t:
            for scene in ('force','mass'):
                for j in [x for x in common.jobs() if x['scene']==scene and x['seed']==41001]:
                    with patch.object(run,'base_analyze',return_value=self.fixture(j)):run.analyze(Path(t),{},j)
                self.assertEqual(json.loads((Path(t)/'pilot_pair.json').read_text())['scene'],scene)
        self.assertEqual(len(run.accepted),2)
    def test_v08_authority_cannot_authorize_formal(self):
        p=common.load_protocol()
        with self.assertRaises(RuntimeError):common.require_authorization(None,p)
        with self.assertRaises(RuntimeError):common.require_authorization('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V08/authorization_pilots01.json',p)
    def test_nominal_scenes_exactly_same_physical_model(self):
        from scenario import expected_trees,shape
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);base=expected_trees(p,p/'plugins',p/'lib.so',dict(scene='heading',seed=41001))
            for scene in ('hover','figure8'):
                trees=expected_trees(p,p/'plugins',p/'lib.so',dict(scene=scene,seed=41001))
                self.assertEqual([shape(x) for x in trees],[shape(x) for x in base])
    def test_only_exact_empty_statistics_is_seed_registry_exempt(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);config=p/'config';config.mkdir();path=p/'zero_holdout_statistics.json'
            data=b'{"all200":"unattempted"}\n'
            (config/'zero_holdout_statistics_reference.json').write_bytes(data);path.write_bytes(data)
            def audit(_):return dict(matches=[dict(path=str(path),field='missing_pair_seeds',seeds=[41001])],invalid_json=[])
            with patch.object(common,'CONFIG',config),patch.object(common,'design',return_value=dict(formal_seeds=list(range(41001,41021)),seed_reservations={})),patch.object(common.training,'seed_audit',side_effect=audit):
                self.assertTrue(common.fresh_seeds()['accepted'])
                path.write_bytes(data+b' ');self.assertFalse(common.fresh_seeds()['accepted'])

if __name__=='__main__':unittest.main(verbosity=2)
