"""Separate six-job mass gate, exact Q6 model and inherited safety checks."""
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

class MassTests(pilot.PilotTests):
    def test_exact_eighteen_order_and_immutable_selection(self):
        jobs=common.jobs();self.assertEqual(len(jobs),6)
        self.assertEqual({j['scene'] for j in jobs},{'mass'})
        self.assertEqual({(j['seed'],j['mode']) for j in jobs},{(s,m) for s in range(40401,40404) for m in (0,1)})
        selection=json.loads((common.CONFIG/'selection.json').read_text())
        for j in jobs:self.assertEqual(j['parameters'],{**selection['parameters'][str(j['mode'])],'MPC_VCT_TEST':6})
    def test_actual_eighteen_runner_and_parameter_restore(self):
        # Enable only the mocked protocol; frozen disk readiness stays unchanged.
        p=common.load_protocol();p['execution_ready']=True
        with patch.object(common,'load_protocol',return_value=p),patch.object(run.runtime,'load_protocol',return_value=p):
            calls,ledger=self.batch();self.assertEqual(calls,common.jobs());self.assertTrue(ledger['success'])
    def test_actual_first_failure_stops_before_next_gate(self):
        p=common.load_protocol();p['execution_ready']=True
        with patch.object(common,'load_protocol',return_value=p),patch.object(run.runtime,'load_protocol',return_value=p):
            for n in range(1,7):
                calls,ledger=self.batch(fail_at=n);self.assertEqual(len(calls),n);self.assertFalse(ledger['success'])
    def test_pair_key_separates_force_and_mass(self):
        run.accepted.clear()
        with tempfile.TemporaryDirectory() as t:
            for seed in (40401,40402):
                scene='mass'
                for j in [x for x in common.jobs() if x['seed']==seed]:
                    with patch.object(run,'base_analyze',return_value=self.fixture(j)):run.analyze(Path(t),{},j)
                self.assertEqual(json.loads((Path(t)/'pilot_pair.json').read_text())['scene'],scene)
        self.assertEqual(len(run.accepted),2)
    def test_old_budget_cannot_authorize_new_mass_gate(self):
        p=common.load_protocol()
        with self.assertRaises(RuntimeError):common.require_authorization(None,p)
        with self.assertRaises(RuntimeError):common.require_authorization('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V08/authorization_pilots01.json',p)
    def test_quantization_explicit_bounded_idempotent(self):
        import scenario as s
        import xml.etree.ElementTree as ET
        root=ET.parse(common.REPO/'Tools/sitl_gazebo/models/iris/iris.sdf').getroot()
        scaled=s.scale_density(root,1.1);quantized=s.quantize_inertia(scaled)
        self.assertEqual(s.shape(quantized),s.shape(s.quantize_inertia(quantized)))
        peak=0
        for name,x in s.inertials(scaled).items():
            y=s.inertials(quantized)[name];self.assertEqual(x['mass'],y['mass']);self.assertEqual(x['cog'],y['cog'])
            for k,v in x['inertia'].items():
                self.assertEqual(y['inertia'][k],float(format(v,'.6g')))
                if v:peak=max(peak,abs(y['inertia'][k]/v-1))
        self.assertLess(peak,1.4e-6);self.assertGreater(peak,1e-6)
    def test_unquantized_old_model_not_reaccepted(self):
        import scenario as s
        import xml.etree.ElementTree as ET
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);job=common.jobs()[0];s.prepare_model(p,p/'plugins',p/'lib.so',job)
            tree=ET.parse(p/'models/iris/iris.sdf');node=tree.find("model/link[@name='rotor_0']/inertial/inertia/iyy")
            node.text='0.00030041440000000002';tree.write(p/'models/iris/iris.sdf')
            with self.assertRaises(ValueError):s.verify_model(p,p/'plugins',p/'lib.so',job)

if __name__=='__main__':unittest.main(verbosity=2)
