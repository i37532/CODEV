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
import zcore
import test_v04
import test_v04_protocol09 as inherited_tests

class ZProtocol(unittest.TestCase):
    def data(self,mode):
        d=test_v04.V04AnalysisTest().data(0); n=len(d['timestamp'])
        d['excitation']*=.5
        d['constraint_bits']=d['constraint_bits'].astype(np.uint16)
        d['z_phase']=np.full(n,3*mode); d['z_hte_shift']=np.zeros(n)
        for k in ('requested_mode','effective_mode'): d[k][:]=mode
        for k in ('requested_axes','effective_axes','active_axes','committed_axes'): d[k][:]=4*mode
        d['pid_axes'][:]=3 if mode else 7
        if mode:
            for f in ('nu_before','nu_ideal','nu_applied','a_sta'): d[f+'[2]'][:]=0
        return d

    def test_only_declared_protocol_changes(self):
        p=common.load_protocol(); self.assertEqual(len(p['jobs']),p['maximum_attempts'])
        self.assertEqual(p['jobs'][0]['mode'],0); self.assertEqual(p['startup_overrides']['MPC_VCT_TEST'],2)
        self.assertEqual(p['startup_overrides']['MPC_LAND_SPEED'],.6); self.assertEqual(p['startup_overrides']['MPC_Z_VEL_MAX_DN'],.55)
        self.assertEqual(p['candidate']['MPC_VC_L1_X'],0)

    def test_flight_identical_to_accepted_v04(self):
        old=common.REPO/'research/sta-velocity-control/v04/protocol17/flight.py'
        self.assertEqual(old.read_bytes(),(common.CONFIG/'flight.py').read_bytes())

    def test_pid_and_z_windows(self):
        for mode in (0,1): self.assertEqual(zcore.check_diagnostic(self.data(mode),1000000,61000000,mode)['samples'],3200)

    def test_frozen_nonzero_candidate_and_old_gain_rejection(self):
        d=self.data(1); d['s[2]'][100]=.04; d['v[2]'][100]=.04
        d['nu_before[2]'][101:]=-.01; d['nu_ideal[2]'][100:]=-.01; d['nu_applied[2]'][100:]=-.01
        d['a_sta[2]'][100]=-.4; d['a_sta[2]'][101:]=-.01
        d['a_req[2]']=d['a_sta[2]'].copy(); d['a_proxy[2]']=d['a_req[2]'].copy()
        d['thrust[2]']=(d['a_req[2]']/9.80665-1)*.5
        zcore.check_diagnostic(d,1000000,61000000,1)
        for field,value in [('a_sta[2]',-.2),('nu_ideal[2]',-.002),('nu_applied[2]',-.002)]:
            bad=copy.deepcopy(d); bad[field][100]=value
            with self.subTest(field=field),self.assertRaises(ValueError): zcore.check_diagnostic(bad,1000000,61000000,1)

    def test_exact_three_pairs_and_no_axis_expansion(self):
        p=common.load_protocol(); self.assertEqual(p['maximum_attempts'],6)
        self.assertEqual([(j['seed'],j['mode'],j['axes']) for j in p['jobs']],
                         [(s,m,4*m) for s in [19001,19002,19003] for m in [0,1]])
        for job in p['jobs']:
            self.assertEqual([job['parameters'][k] for k in ('MPC_VC_L1_Z','MPC_VC_L2_Z','MPC_VC_NU_Z','MPC_VC_A_Z')],[2.,1.,4.,6.])

    def test_wrong_axis_inner_lifecycle_and_timing(self):
        for key in ('effective_axes','pid_axes','committed_axes','inner_mode','z_phase','timing','raw_dt','publish_seq'):
            d=self.data(1); d[key][100]+=1
            with self.subTest(key=key),self.assertRaises(ValueError): zcore.check_diagnostic(d,1000000,61000000,1)

    def test_wrong_ff_nu_proxy_and_x_waveform_rejected(self):
        for key in ('a_req[2]','a_sta[2]','nu_before[2]','nu_applied[2]','nu_ideal[2]','nu_applied[0]','a_proxy[2]','excitation','z_hte_shift'):
            d=self.data(1); d[key][100]=.2
            with self.subTest(key=key),self.assertRaises(ValueError): zcore.check_diagnostic(d,1000000,61000000,1)

    def test_missing_boundaries_and_sample(self):
        for mode in (0,1):
            d={k:np.delete(v,100) for k,v in self.data(mode).items()}
            with self.assertRaises(ValueError): zcore.check_diagnostic(d,1000000,61000000,mode)
            with self.assertRaises(ValueError): zcore.check_diagnostic(self.data(mode),1000000,31000000,mode)

    def test_authority_binding(self):
        p=common.load_protocol(); good=dict(approved=True,source_head='test',stage=p['stage'],maximum_attempts=p['maximum_attempts'],
            execution_sha256=common.fingerprint(common.CONFIG/'execution.json'),basis='standing user authorization for ordinary repairs and new SITL batches')
        with tempfile.TemporaryDirectory() as tmp,patch.object(common.subprocess,'check_output',return_value='test\n'):
            f=Path(tmp)/'auth.json'; f.write_text(json.dumps(good)); self.assertEqual(common.require_authorization(str(f),p),good)
            for key,value in [('source_head','wrong'),('maximum_attempts',999),('approved',False),('stage','wrong'),('execution_sha256','wrong')]:
                f.write_text(json.dumps({**good,key:value}))
                with self.assertRaises(RuntimeError): common.require_authorization(str(f),p)

    def batch(self,**kwargs):
        with patch.object(inherited_tests,'runner',run),patch.object(inherited_tests,'load_protocol',common.load_protocol):
            return inherited_tests.Protocol09Test.batch(self,**kwargs)

    def test_mock_budget_and_restore(self):
        calls,ledger=self.batch(); self.assertEqual(len(calls),common.load_protocol()['maximum_attempts']); self.assertTrue(ledger['success'])

    def test_stop_failure_and_restore(self):
        for kwargs in (dict(fail_at=1),dict(reject=True)):
            calls,ledger=self.batch(**kwargs); self.assertEqual(len(calls),1); self.assertFalse(ledger['success'])

    def test_historical_or_missing_provenance_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(analyze.analyze(Path(tmp),common.load_protocol(),common.inherited()['jobs'][0])['accepted'])
            (Path(tmp)/'result.json').write_text('{}')
            self.assertFalse(analyze.analyze(Path(tmp),common.load_protocol(),common.load_protocol()['jobs'][0])['accepted'])

    def test_lifecycle_handover_ground_reset_and_hte(self):
        import re
        message=(common.REPO/'msg/takeoff_status.msg').read_text()
        self.assertEqual(int(re.search(r'TAKEOFF_STATE_FLIGHT\s*=\s*(\d+)',message)[1]),5)
        d=self.data(1); n=len(d['timestamp']); d['landed']=np.zeros(n); d['contact']=np.zeros(n); d['takeoff_state']=np.full(n,5)
        d['z_phase'][:10]=1; d['z_phase'][10]=2; d['active_axes'][:11]=d['committed_axes'][:11]=0; d['pid_axes'][:11]=7
        self.assertEqual(zcore.check_z_lifecycle(d,1000000,61000000,1)['handovers'],1)
        for key,index,value in [('z_phase',30,2),('pid_axes',30,7),('nu_applied[2]',2,.1),('nu_before[2]',31,.1),('z_hte_shift',31,.1),('contact',30,1)]:
            bad=copy.deepcopy(d); bad[key][index]=value
            with self.subTest(key=key),self.assertRaises(ValueError): zcore.check_z_lifecycle(bad,1000000,61000000,1)

if __name__=='__main__': unittest.main()
