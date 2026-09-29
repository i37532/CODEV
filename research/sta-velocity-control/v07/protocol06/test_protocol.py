"""Synthetic full diagnostic and real runner wiring; never fly from tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import common
import core
import run
import analyze
import test_v04
import test_v04_protocol09 as inherited_tests

class ProtocolTest(unittest.TestCase):
    def data(self,mode,n):
        count=9000; d={k:np.resize(v,count) for k,v in test_v04.V04AnalysisTest().data(0).items()}
        t=np.arange(count,dtype=np.int64)*10000+1000000
        for k in ('timestamp','timestamp_sample','input_timestamp','output_timestamp','inner_check_timestamp'): d[k]=t.copy()
        for k in ('publish_seq','update_seq'): d[k]=np.arange(count)
        d['inner_timestamp']=t-4000; d['inner_seq']=np.arange(count)*2
        d['excitation_time']=np.arange(count)*.01-10
        for k in ('excitation','excitation_y','excitation_z','z_phase','z_hte_shift'): d[k]=np.zeros(count)
        d['constraint_bits']=d['constraint_bits'].astype(np.uint16)
        for k in ('requested_mode','effective_mode'): d[k][:]=mode
        for k in ('requested_axes','effective_axes','active_axes'): d[k][:]=3*mode
        updated=np.arange(count)%n==0; d['committed_axes']=updated.astype(int)*3*mode
        d['sta_flags']=(~updated).astype(int)*256*mode
        d['pid_axes'][:]=4 if mode else 7
        q={k:v.copy() for k,v in d.items()}
        q.update(div_req=np.full(count,n),div_eff=np.full(count,n),div_pending=np.zeros(count),div_reject=np.zeros(count),control_fault=np.zeros(count),
            control_seq=np.cumsum(updated),control_updated=updated,control_held=~updated,h=np.where(updated,.01*n,np.nan),
            path_ns=np.full(count,100),module_ns=np.full(count,200),clock=np.ones(count),interval_pos=np.zeros(count),interval_neg=np.zeros(count))
        q['h'][0]=.01
        for i in range(3):
            q[f'correction[{i}]']=d[f'a_req[{i}]'].copy(); q[f'integral[{i}]']=np.zeros(count)
            if mode and i<2:
                for f in ('nu_before','nu_ideal','nu_applied','a_sta'): d[f'{f}[{i}]'][:]=0
                if n>1:
                    for f in ('nu_ideal','a_sta'): d[f'{f}[{i}]'][~updated]=np.nan
        return d,q,dict(mode=mode,divisor=n)

    def test_full_diagnostic_six_cells(self):
        for mode in (0,1):
            for n in (1,2,4):
                d,q,j=self.data(mode,n); r=core.check_diagnostic(d,q,1000000,91000000,j)
                self.assertEqual(r['samples'],6400); self.assertAlmostEqual(r['cadence']['update_hz'],100/n)

    def test_wrong_mode_inner_axes_missing_time(self):
        for key in ('effective_axes','inner_mode','timing','raw_dt','publish_seq','config_pending','pid_axes','sta_flags'):
            d,q,j=self.data(1,4); d[key][100]+=1
            with self.subTest(key=key),self.assertRaises(ValueError): core.check_diagnostic(d,q,1000000,91000000,j)

    def test_wrong_candidate_ff_held_and_axis_state(self):
        for key in ('a_sta[0]','nu_applied[0]','nu_ideal[1]','nu_applied[2]','a_req[0]','excitation_y','z_phase'):
            d,q,j=self.data(1,4); d[key][100]=.01
            with self.subTest(key=key),self.assertRaises(ValueError): core.check_diagnostic(d,q,1000000,91000000,j)

    def test_budget_axes_gains_unique_seeds_and_divisors(self):
        p=common.load_protocol(); self.assertEqual(len(p['jobs']),18)
        self.assertEqual([j['divisor'] for j in p['jobs']],[1]*6+[2]*6+[4]*6)
        self.assertEqual([(j['seed'],j['mode'],j['axes']) for j in p['jobs']],[(s,m,3*m) for s in range(34001,34010) for m in (0,1)])
        for j in p['jobs']: self.assertEqual(j['parameters']['MPC_VCT_TEST'],6)
        for key,value in dict(MC_RTC_MODE=0,MC_STA_AXES=0,MC_RTC_DIV=1,MC_RATT_TEST=0,MC_STA_TKO_MGT=0).items(): self.assertEqual(p['startup_overrides'][key],value)
        self.assertEqual([p['candidate'][f'MPC_VC_{k}_Z'] for k in ('L1','L2','NU','A')],[0.]*4)

    def test_flight_target_landing_and_model_pipeline_not_rewritten(self):
        old=common.REPO/'research/sta-velocity-control/v06/protocol03'
        for name in ('height.py','handoff.py','handoff_capture.py','landing.py','landing_complete.py','task.py'):
            self.assertEqual((common.CONFIG/name).read_bytes(),(old/name).read_bytes(),name)

    def test_pair_noncommand_axis_bound_and_wrong_divisor(self):
        r=dict(error=dict(rmse=[0.,0.,0.]),windows={n:dict(error=dict(rmse=[0.,0.,0.])) for n in ('first_loop','second_loop')})
        pid=dict(accepted=True,job=dict(seed=34001,mode=0,task='figure8',divisor=1),diagnostic=r,position_rmse=[0.,0.,0.],yaw_rmse=0.)
        esta=copy.deepcopy(pid); esta['job']['mode']=1; self.assertTrue(core.compare(pid,esta)['accepted'])
        esta['diagnostic']['windows']['second_loop']['error']['rmse'][2]=.01001; self.assertFalse(core.compare(pid,esta)['accepted'])
        esta['job']['divisor']=2
        with self.assertRaises(ValueError): core.compare(pid,esta)

    def test_authority_binding(self):
        p=common.load_protocol(); good=dict(approved=True,source_head='test',stage=p['stage'],maximum_attempts=18,
            execution_sha256=common.fingerprint(common.CONFIG/'execution.json'),basis='V07 private tmpfs logging standing authorization 2026-09-29; new eighteen-attempt budget')
        with tempfile.TemporaryDirectory() as tmp,patch.object(common.subprocess,'check_output',return_value='test\n'):
            f=Path(tmp)/'auth.json'; f.write_text(json.dumps(good)); self.assertEqual(common.require_authorization(str(f),p),good)
            for key,value in [('source_head','wrong'),('maximum_attempts',999),('approved',False),('stage','wrong'),('execution_sha256','wrong')]:
                f.write_text(json.dumps({**good,key:value}))
                with self.assertRaises(RuntimeError): common.require_authorization(str(f),p)

    def batch(self,**kwargs):
        def compare(pid,esta):
            pid,esta=copy.deepcopy(pid),copy.deepcopy(esta)
            for r in (pid,esta): r['diagnostic']['windows']={n:dict(error=copy.deepcopy(r['diagnostic']['error'])) for n in ('first_loop','second_loop')}
            return core.compare(pid,esta)
        from landing_health import require_passive
        from qualification import require_qualification
        soft=common.REPO/'research/sta-velocity-control/v06/soft_landing'
        with patch.object(run,'require_qualification',side_effect=lambda _:require_qualification(soft/'qualified_contact.json')),patch.object(run,'require_passive',side_effect=lambda _:require_passive(soft/'offline03/evidence.json')),patch.object(inherited_tests,'runner',run),patch.object(inherited_tests,'load_protocol',common.load_protocol),patch.object(run,'compare',side_effect=compare):
            return inherited_tests.Protocol09Test.batch(self,**kwargs)

    def test_mock_budget_and_restore(self):
        calls,ledger=self.batch(); self.assertEqual(len(calls),18); self.assertTrue(ledger['success'])

    def test_failure_stops_before_next_divisor(self):
        for n in (1,6,7,12):
            calls,ledger=self.batch(fail_at=n); self.assertEqual(len(calls),n); self.assertFalse(ledger['success'])
        calls,ledger=self.batch(reject=True); self.assertEqual(len(calls),1)

    def test_missing_or_historical_provenance_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(analyze.analyze(Path(tmp),common.load_protocol(),common.inherited()['jobs'][0])['accepted'])
            (Path(tmp)/'result.json').write_text('{}')
            self.assertFalse(analyze.analyze(Path(tmp),common.load_protocol(),common.load_protocol()['jobs'][0])['accepted'])

if __name__=='__main__': unittest.main(verbosity=2)
