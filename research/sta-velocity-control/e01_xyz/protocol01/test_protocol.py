"""Offline V05 wiring/negative fixtures; these are not flight results."""
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
import xyzcore
import test_v04
import test_v04_protocol09 as inherited_tests


class XYZProtocol(unittest.TestCase):
    def data(self,mode):
        d={k:np.resize(v,9000) for k,v in test_v04.V04AnalysisTest().data(0).items()}
        t=np.arange(9000,dtype=np.int64)*10000+1000000
        for k in ('timestamp','timestamp_sample','input_timestamp','output_timestamp','inner_check_timestamp'): d[k]=t.copy()
        for k in ('publish_seq','update_seq'): d[k]=np.arange(9000)
        d['inner_timestamp']=t-4000; d['inner_seq']=np.arange(9000)*2
        d['excitation_time']=np.arange(9000)*.01-10
        d['excitation'],d['excitation_y'],d['excitation_z']=xyzcore.waveform(d['excitation_time'])
        d['constraint_bits']=d['constraint_bits'].astype(np.uint16)
        d['z_phase']=np.full(9000,3 if mode else 0); d['z_hte_shift']=np.zeros(9000)
        for k in ('requested_mode','effective_mode'): d[k][:]=mode
        for k in ('requested_axes','effective_axes','active_axes','committed_axes'): d[k][:]=7*mode
        d['pid_axes'][:]=0 if mode else 7
        if mode:
            for axis in (0,1,2):
                for field in ('nu_before','nu_ideal','nu_applied','a_sta'): d[f'{field}[{axis}]'][:]=0
        return d

    def test_declared_budget_and_old_parameters(self):
        p=common.load_protocol(); old=common.inherited()
        self.assertEqual([(j['seed'],j['mode'],j['axes']) for j in p['jobs']],[(s,m,7*m) for s in (22001,22002,22003) for m in (0,1)])
        self.assertEqual(p['maximum_attempts'],6)
        for k,v in old['startup_overrides'].items():
            if k not in ('MPC_VCT_TEST','MPC_LAND_SPEED','MPC_Z_VEL_MAX_DN'): self.assertEqual(p['startup_overrides'][k],v,k)
        self.assertEqual(p['startup_overrides']['MPC_VCT_TEST'],4)
        self.assertEqual(p['startup_overrides']['MPC_LAND_SPEED'],.6)
        self.assertEqual(p['startup_overrides']['MPC_Z_VEL_MAX_DN'],.55)
        self.assertEqual([p['candidate'][f'MPC_VC_{k}_{a}'] for a in ('X','Y') for k in ('L1','L2','NU','A')],[1.,.2,.4,.8]*2)
        self.assertEqual([p['candidate'][f'MPC_VC_{k}_Z'] for k in ('L1','L2','NU','A')],[2.,1.,4.,6.])

    def test_only_observation_duration_changes_in_flight_and_baseline(self):
        old=(common.REPO/'research/sta-velocity-control/v04/protocol17/flight.py').read_text()
        expected=old.replace(' < 60e6:', ' < 90e6:').replace('60 s simulation hover wall timeout','90 s simulation observation wall timeout')
        self.assertEqual(expected,(common.CONFIG/'flight.py').read_text())
        old=(common.REPO/'research/sta-velocity-control/scripts/analyze_v00.py').read_text()
        expected=old.replace("'hover_60s': 60 <= (end-start)*1e-6 <= 62","'observation_90s': 90 <= (end-start)*1e-6 <= 92")
        expected=expected.replace('59.75','89.75')
        self.assertEqual(expected,(common.CONFIG/'baseline.py').read_text())

    def test_pid_xyz_windows(self):
        for mode in (0,1):
            r=xyzcore.check_diagnostic(self.data(mode),1000000,91000000,mode)
            self.assertEqual(r['samples'],6400)
            self.assertEqual([r['windows'][n]['samples'] for n in ('Z','XY','XYZ')],[1600,1600,3200])

    def test_waveforms_sign_area_and_norm(self):
        t=np.arange(64000)*.001; x,y,z=xyzcore.waveform(t)
        self.assertLessEqual(np.max(np.hypot(x,y)),.200001)
        for lo,hi in ((0,16),(16,32),(32,64)):
            m=(t>=lo)&(t<hi)
            for a in (x,y,z): self.assertAlmostEqual(a[m].sum()*.001,0,places=6)
        self.assertTrue(np.all(y[t<16]==0)); self.assertTrue(np.all(z[(t>=16)&(t<32)]==0))

    def test_wrong_mode_axes_inner_lifecycle_clock(self):
        for key in ('effective_axes','pid_axes','committed_axes','inner_mode','z_phase','timing','raw_dt','publish_seq','config_pending'):
            d=self.data(1); d[key][100]+=1
            with self.subTest(key=key),self.assertRaises(ValueError): xyzcore.check_diagnostic(d,1000000,91000000,1)

    def test_wrong_ff_state_proxy_and_y_excitation(self):
        keys=[f'{f}[{a}]' for a in (0,1,2) for f in ('a_req','a_sta','nu_before','nu_applied','nu_ideal','a_proxy')]
        for key in keys+['excitation','excitation_y','excitation_z','z_hte_shift']:
            d=self.data(1); d[key][100]=.2
            with self.subTest(key=key),self.assertRaises(ValueError): xyzcore.check_diagnostic(d,1000000,91000000,1)

    def test_independent_nonzero_y_candidate(self):
        d=self.data(1); d['s[1]'][100]=.04; d['v[1]'][100]=.04
        d['nu_before[1]'][101:]=-.002; d['nu_ideal[1]'][100:]=-.002; d['nu_applied[1]'][100:]=-.002
        d['a_sta[1]'][100]=-.2; d['a_sta[1]'][101:]=-.002
        d['a_req[1]']=d['a_sta[1]'].copy(); d['a_proxy[1]']=d['a_req[1]'].copy()
        d['thrust[1]']=d['a_req[1]']*.5/9.80665
        xyzcore.check_diagnostic(d,1000000,91000000,1)
        d['nu_applied[0]']=d['nu_applied[1]'].copy()
        with self.assertRaises(ValueError): xyzcore.check_diagnostic(d,1000000,91000000,1)

    def test_y_and_xy_clock_cannot_restart_or_drift(self):
        for index in (4700,6300):
            d=self.data(0); d['excitation_time'][index]+=.005
            d['excitation'],d['excitation_y'],d['excitation_z']=xyzcore.waveform(d['excitation_time'])
            with self.assertRaisesRegex(ValueError,'clock'): xyzcore.check_diagnostic(d,1000000,91000000,0)

    def test_missing_window_boundaries_or_y_topic(self):
        for mode in (0,1):
            d={k:np.delete(v,100) for k,v in self.data(mode).items()}
            with self.assertRaises(ValueError): xyzcore.check_diagnostic(d,1000000,91000000,mode)
            with self.assertRaises(ValueError): xyzcore.check_diagnostic(self.data(mode),1000000,61000000,mode)
            d=self.data(mode); del d['excitation_y']
            with self.assertRaises(ValueError): xyzcore.check_diagnostic(d,1000000,91000000,mode)

    def test_each_window_noncommand_axis_gate(self):
        r=dict(error=dict(rmse=[0.,0.,0.]),windows={n:dict(error=dict(rmse=[0.,0.,0.])) for n in ('Z','XY','XYZ')})
        pid=dict(accepted=True,job=dict(seed=22001,mode=0),diagnostic=r,position_rmse=[0.,0.,0.],yaw_rmse=0.)
        for name in ('Z','XY','XYZ'):
            esta=copy.deepcopy(pid); esta['job']['mode']=1
            self.assertTrue(xyzcore.compare(pid,esta)['accepted'])
            esta['diagnostic']['windows'][name]['error']['rmse'][2]=.01001
            self.assertFalse(xyzcore.compare(pid,esta)['accepted'])

    def test_authority_binding(self):
        p=common.load_protocol(); good=dict(approved=True,source_head='test',stage=p['stage'],maximum_attempts=6,
            execution_sha256=common.fingerprint(common.CONFIG/'execution.json'),basis='standing user authorization for ordinary repairs and new SITL batches')
        with tempfile.TemporaryDirectory() as tmp,patch.object(common.subprocess,'check_output',return_value='test\n'):
            f=Path(tmp)/'auth.json'; f.write_text(json.dumps(good)); self.assertEqual(common.require_authorization(str(f),p),good)
            for key,value in [('source_head','wrong'),('maximum_attempts',999),('approved',False),('stage','wrong'),('execution_sha256','wrong')]:
                f.write_text(json.dumps({**good,key:value}))
                with self.assertRaises(RuntimeError): common.require_authorization(str(f),p)

    def batch(self,**kwargs):
        def synthetic_compare(pid,esta):
            pid,esta=copy.deepcopy(pid),copy.deepcopy(esta)
            for r in (pid,esta):
                r['diagnostic']['windows']={n:dict(error=copy.deepcopy(r['diagnostic']['error'])) for n in ('Z','XY','XYZ')}
            return xyzcore.compare(pid,esta)
        with patch.object(inherited_tests,'runner',run),patch.object(inherited_tests,'load_protocol',common.load_protocol),patch.object(run,'compare',side_effect=synthetic_compare):
            return inherited_tests.Protocol09Test.batch(self,**kwargs)

    def test_mock_budget_and_restore(self):
        calls,ledger=self.batch(); self.assertEqual(len(calls),6); self.assertTrue(ledger['success'])

    def test_stop_failure_and_restore(self):
        for kwargs in (dict(fail_at=1),dict(reject=True)):
            calls,ledger=self.batch(**kwargs); self.assertEqual(len(calls),1); self.assertFalse(ledger['success'])

    def test_historical_or_missing_provenance_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(analyze.analyze(Path(tmp),common.load_protocol(),common.inherited()['jobs'][0])['accepted'])
            (Path(tmp)/'result.json').write_text('{}')
            self.assertFalse(analyze.analyze(Path(tmp),common.load_protocol(),common.load_protocol()['jobs'][0])['accepted'])

    def lifecycle(self):
        d=self.data(1)
        d['z_phase'][:100]=1; d['z_phase'][100]=2
        d['active_axes'][:101]=0; d['committed_axes'][:101]=0; d['pid_axes'][:101]=7
        d['landed']=np.zeros(9000); d['contact']=np.zeros(9000); d['takeoff_state']=np.full(9000,5)
        return d

    def test_xyz_lifecycle_single_atomic_seed_and_exclusive_output(self):
        d=self.lifecycle(); r=xyzcore.check_xyz_lifecycle(d,1000000,91000000,1)
        self.assertEqual(r['handovers'],1)
        for key,index,value in [('z_phase',200,2),('committed_axes',100,1),('pid_axes',300,1),
                                ('nu_applied[2]',100,.01),('nu_applied[0]',50,.01),
                                ('nu_before[1]',250,.01),('z_hte_shift',500,.01),('landed',500,1)]:
            d=self.lifecycle(); d[key][index]=value
            with self.subTest(key=key),self.assertRaises(ValueError): xyzcore.check_xyz_lifecycle(d,1000000,91000000,1)

    def test_hte_reconstruction_nonzero_not_inherited_into_xy(self):
        d=self.lifecycle(); start=500
        old=.5; new=.51; shift=(old/new-1)*(-9.80665)
        d['hover_thrust'][start:]=new; d['z_hte_shift'][start]=shift
        d['nu_before[2]'][start:]=shift; d['nu_applied[2]'][start:]=shift; d['nu_ideal[2]'][start:]=shift
        d['a_sta[2]'][start:]=shift; d['a_req[2]'][start:]=shift
        xyzcore.check_xyz_lifecycle(d,1000000,91000000,1)
        d['nu_before[0]'][start]=shift
        with self.assertRaises(ValueError): xyzcore.check_xyz_lifecycle(d,1000000,91000000,1)

if __name__=='__main__': unittest.main()
