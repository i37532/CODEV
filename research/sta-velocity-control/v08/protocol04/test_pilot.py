"""Offline wiring/budget/model/clock negative tests; never starts Gazebo."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import common
import run
import analyze
import scenario

class PilotTests(unittest.TestCase):
    def fixture(self,job,accepted=True):
        error=dict(rmse=[.01]*3)
        return dict(accepted=accepted,job=job,diagnostic=dict(error=error,
            windows={name:dict(error=error) for name in ('first_loop','second_loop')}),position_rmse=[.01]*3,yaw_rmse=.01)

    def test_exact_eighteen_order_and_immutable_selection(self):
        p=common.load_protocol();self.assertEqual(len(p['jobs']),18)
        selection=json.loads((common.CONFIG/'selection.json').read_text())
        for i,scene in enumerate(('heading','force','mass')):
            group=p['jobs'][6*i:6*i+6]
            self.assertEqual({j['scene'] for j in group},{scene})
            self.assertEqual({(j['mode'],j['seed']) for j in group},{(m,s) for m in (0,1) for s in common.design()['pilot_seeds']})
            for job in group:
                expected={**selection['parameters'][str(job['mode'])],'MPC_VCT_TEST':7 if scene=='heading' else 6}
                self.assertEqual(job['parameters'],expected)
                self.assertEqual(job['axes'],3*job['mode']);self.assertEqual(job['divisor'],1)

    def test_actual_runtime_uses_pilot_analysis_not_training_whitelist(self):
        self.assertIs(run.base_analyze,analyze.analyze)
        self.assertIs(analyze.base.verify_model,analyze.verify_model)
        self.assertIs(run.runtime.Checks,run.Checks)
        self.assertEqual(run.runtime.CONFIG,common.CONFIG)

    def test_pair_key_separates_force_and_mass(self):
        run.accepted.clear()
        with tempfile.TemporaryDirectory() as t:
            for scene in ('force','mass'):
                jobs=[j for j in common.load_protocol()['jobs'] if j['scene']==scene and j['seed']==common.design()['pilot_seeds'][0]]
                for job in jobs:
                    with patch.object(run,'base_analyze',return_value=self.fixture(job)):
                        self.assertTrue(run.analyze(Path(t),{},job)['accepted'])
                pair=json.loads((Path(t)/'pilot_pair.json').read_text())
                self.assertEqual(pair['scene'],scene);self.assertTrue(pair['accepted'])
            self.assertEqual(len(run.accepted),2)

    def test_pair_failure_not_ignored(self):
        run.accepted.clear();jobs=common.load_protocol()['jobs'][:2]
        with tempfile.TemporaryDirectory() as t:
            for job in jobs:
                value=self.fixture(job)
                if job['mode']==1:value['yaw_rmse']=1.
                with patch.object(run,'base_analyze',return_value=value):
                    if job==jobs[-1]:
                        with self.assertRaises(RuntimeError):run.analyze(Path(t),{},job)
                    else:run.analyze(Path(t),{},job)

    def test_diagnostic_trigger_clock_and_only_once(self):
        job=common.load_protocol()['jobs'][0]
        checker=object.__new__(run.Checks);checker.job=job;checker.force_started=False
        checker.latest_diagnostic=dict(timestamp=10204000,timestamp_sample=10200000,excitation_time=.2)
        with tempfile.TemporaryDirectory() as t,patch.object(run.OriginalChecks,'monitor'):
            path=Path(t);checker.monitor('hover',None,None,path,{})
            self.assertEqual(float((path/'force.trigger').read_text()),10.)
            original=(path/'force.trigger').read_bytes()
            checker.latest_diagnostic['excitation_time']=20
            checker.monitor('hover',None,None,path,{})
            self.assertEqual((path/'force.trigger').read_bytes(),original)

    def test_late_trigger_rejected_before_publication(self):
        checker=object.__new__(run.Checks);checker.force_started=False
        checker.latest_diagnostic=dict(timestamp=12000000,timestamp_sample=12000000,excitation_time=2.)
        with tempfile.TemporaryDirectory() as t,patch.object(run.OriginalChecks,'monitor'),self.assertRaises(ValueError):
            checker.monitor('hover',None,None,Path(t),{})

    def force_fixture(self,folder,scene='force'):
        job=dict(scene=scene,seed=40201)
        sim=np.arange(0.,80.,.004);elapsed=np.where(sim>=10.2,sim-10.,-1.)
        force=scenario.force_enu(elapsed,scenario.phases(job['seed'])) if scene=='force' else np.zeros((len(sim),3))
        np.savetxt(folder/'force.csv',np.column_stack([sim,elapsed,force]),delimiter=',',header='sim_s,elapsed_s,fx_enu_N,fy_enu_N,fz_enu_N',comments='',fmt='%.17g')
        t=np.arange(6400)*.01;d=dict(timestamp=((10+t)*1e6+1000).astype(np.uint64),
            timestamp_sample=((10+t)*1e6).astype(np.uint64),excitation_time=t.astype(np.float32))
        receipt=dict(origin_sim_s=10.,diagnostic=dict(timestamp_sample=10200000,excitation_time=.2))
        (folder/'force_trigger_origin.json').write_text(json.dumps(receipt))
        events=dict(hover_start=9e6,hover_end=75e6,land_command=77e6)
        return job,d,events

    def test_full_force_waveform_clock_and_off_scene(self):
        for scene in ('force','mass','heading'):
            with tempfile.TemporaryDirectory() as t:
                p=Path(t);job,d,e=self.force_fixture(p,scene)
                result=scenario.force_evidence(p,job,d,e)
                self.assertGreater(result['samples'],10000)
                self.assertEqual(result['nonzero_samples']>0,scene=='force')

    def test_force_gap_wrong_origin_and_outside_observation_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);job,d,e=self.force_fixture(p)
            bad=dict(e,land_command=30e6)
            with self.assertRaises(ValueError):scenario.force_evidence(p,job,d,bad)
            broken={**d,'timestamp_sample':d['timestamp_sample']+100000}
            with self.assertRaises(ValueError):scenario.force_evidence(p,job,broken,e)
            lines=(p/'force.csv').read_text().splitlines();del lines[3000]
            (p/'force.csv').write_text('\n'.join(lines)+'\n')
            with self.assertRaises(ValueError):scenario.force_evidence(p,job,d,e)

    def test_gps_include_is_absolute_and_cannot_fall_back(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);iris,_=scenario.expected_trees(p,p/'plugins',p/'lib.so',dict(scene='mass',seed=40201))
            self.assertEqual(iris.findtext('model/include/uri'),str(p/'models/gps'))

    def test_actual_prepare_refreshes_manifest_for_changed_model(self):
        job=next(j for j in common.load_protocol()['jobs'] if j['scene']=='mass')
        checker=object.__new__(run.Checks);checker.job=job
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t);output=folder/'run';output.mkdir();library=folder/'lib.so';library.write_bytes(b'offline fixture only')
            checker.plugins=folder/'seeded';d={**common.design(),'force_library':str(library),'force_library_sha256':common.fingerprint(library)}
            def parent(_self,path):
                (path/'models/iris').mkdir(parents=True)
                (path/'model_manifest.json').write_text(json.dumps(dict(original='original-immutable',derived='old-derived',only_change='old')))
                return dict(FIXTURE='no launch')
            with patch.object(common,'design',return_value=d),patch.object(run.OriginalChecks,'prepare_environment',parent):
                result=checker.prepare_environment(output)
            manifest=json.loads((output/'model_manifest.json').read_text())
            self.assertEqual(result['FIXTURE'],'no launch');self.assertFalse(checker.force_started)
            self.assertEqual(manifest['original'],'original-immutable')
            self.assertEqual(manifest['derived'],common.fingerprint(output/'models/iris/iris.sdf'))
            self.assertEqual(manifest['derived_gps'],common.fingerprint(output/'models/gps/gps.sdf'))
            self.assertEqual(manifest['density_scale'],1.1)

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

    def test_actual_eighteen_runner_and_parameter_restore(self):
        calls,ledger=self.batch();self.assertEqual(calls,common.load_protocol()['jobs']);self.assertTrue(ledger['success'])

    def test_actual_first_failure_stops_before_next_gate(self):
        for n in (1,6,7,12,13,18):
            calls,ledger=self.batch(fail_at=n);self.assertEqual(len(calls),n);self.assertFalse(ledger['success'])

if __name__=='__main__':unittest.main(verbosity=2)
