"""Offline V06 wiring/negative fixtures; these are not flight results."""
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


class TaskProtocol(unittest.TestCase):
    def data(self,mode):
        d={k:np.resize(v,9000) for k,v in test_v04.V04AnalysisTest().data(0).items()}
        t=np.arange(9000,dtype=np.int64)*10000+1000000
        for k in ('timestamp','timestamp_sample','input_timestamp','output_timestamp','inner_check_timestamp'): d[k]=t.copy()
        for k in ('publish_seq','update_seq'): d[k]=np.arange(9000)
        d['inner_timestamp']=t-4000; d['inner_seq']=np.arange(9000)*2
        d['excitation_time']=np.arange(9000)*.01-10
        d['excitation']=np.zeros(9000); d['excitation_y']=np.zeros(9000); d['excitation_z']=np.zeros(9000)
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
        self.assertEqual([(j['seed'],j['mode'],j['axes']) for j in p['jobs']],[(s,m,7*m) for s in range(27001,27010) for m in (0,1)])
        self.assertEqual(p['maximum_attempts'],18)
        for k,v in old['startup_overrides'].items():
            if k not in ('MPC_VCT_TEST','MPC_LAND_SPEED','MPC_Z_VEL_MAX_DN'): self.assertEqual(p['startup_overrides'][k],v,k)
        self.assertEqual(p['startup_overrides']['MPC_VCT_TEST'],0)
        self.assertEqual(p['startup_overrides']['MPC_LAND_SPEED'],.6)
        self.assertEqual(p['startup_overrides']['MPC_Z_VEL_MAX_DN'],.55)
        self.assertEqual([p['candidate'][f'MPC_VC_{k}_{a}'] for a in ('X','Y') for k in ('L1','L2','NU','A')],[1.,.2,.4,.8]*2)
        self.assertEqual([p['candidate'][f'MPC_VC_{k}_Z'] for k in ('L1','L2','NU','A')],[2.,1.,4.,6.])

    def test_only_observation_duration_changes_in_flight_and_baseline(self):
        old=(common.REPO/'research/sta-velocity-control/v04/protocol17/flight.py').read_text()
        expected=old.replace(' < 60e6:', ' < 90e6:').replace('60 s simulation hover wall timeout','90 s simulation observation wall timeout')
        expected=expected.replace('from v04_handoff09 import Handoff, local_xy_ok','from handoff_capture import Handoff, local_xy_ok')
        expected=expected.replace('checks("disarmed", cli, topic, output)', 'checks("disarmed", cli, topic, output)\n            checks.collect_landing_tail(topic, output, result["events"])')
        self.assertEqual(expected,(common.CONFIG/'flight.py').read_text())
        old=(common.REPO/'research/sta-velocity-control/scripts/analyze_v00.py').read_text()
        expected=old.replace("'hover_60s': 60 <= (end-start)*1e-6 <= 62","'observation_90s': 90 <= (end-start)*1e-6 <= 92")
        expected=expected.replace('59.75','89.75')
        self.assertEqual(expected,(common.CONFIG/'baseline.py').read_text())

    def test_pid_xyz_windows(self):
        for mode in (0,1):
            r=xyzcore.check_diagnostic(self.data(mode),1000000,91000000,mode)
            self.assertEqual(r['samples'],6400)
            self.assertEqual([r['windows'][n]['samples'] for n in ('first_loop','second_loop')],[3200,3200])

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
            d['excitation']=np.zeros(9000); d['excitation_y']=np.zeros(9000); d['excitation_z']=np.zeros(9000)
            with self.assertRaisesRegex(ValueError,'clock'): xyzcore.check_diagnostic(d,1000000,91000000,0)

    def test_missing_window_boundaries_or_y_topic(self):
        for mode in (0,1):
            d={k:np.delete(v,100) for k,v in self.data(mode).items()}
            with self.assertRaises(ValueError): xyzcore.check_diagnostic(d,1000000,91000000,mode)
            with self.assertRaises(ValueError): xyzcore.check_diagnostic(self.data(mode),1000000,61000000,mode)
            d=self.data(mode); del d['excitation_y']
            with self.assertRaises(ValueError): xyzcore.check_diagnostic(d,1000000,91000000,mode)

    def test_each_window_noncommand_axis_gate(self):
        r=dict(error=dict(rmse=[0.,0.,0.]),windows={n:dict(error=dict(rmse=[0.,0.,0.])) for n in ('first_loop','second_loop')})
        pid=dict(accepted=True,job=dict(seed=24001,mode=0,task='hover'),diagnostic=r,position_rmse=[0.,0.,0.],yaw_rmse=0.)
        for name in ('first_loop','second_loop'):
            esta=copy.deepcopy(pid); esta['job']['mode']=1
            self.assertTrue(xyzcore.compare(pid,esta)['accepted'])
            esta['diagnostic']['windows'][name]['error']['rmse'][2]=.01001
            self.assertFalse(xyzcore.compare(pid,esta)['accepted'])

    def test_authority_binding(self):
        p=common.load_protocol(); good=dict(approved=True,source_head='test',stage=p['stage'],maximum_attempts=18,
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
                r['diagnostic']['windows']={n:dict(error=copy.deepcopy(r['diagnostic']['error'])) for n in ('first_loop','second_loop')}
            return xyzcore.compare(pid,esta)
        from landing_health import require_passive
        from qualification import require_qualification
        # Only redirect the mocked CONFIG path; still validate real passive evidence.
        with patch.object(run,'require_qualification',side_effect=lambda _:require_qualification(common.CONFIG.parent/'soft_landing/qualified_contact.json')),patch.object(run,'require_passive',side_effect=lambda _:require_passive(common.CONFIG.parent/'soft_landing/offline03/evidence.json')),patch.object(inherited_tests,'runner',run),patch.object(inherited_tests,'load_protocol',common.load_protocol),patch.object(run,'compare',side_effect=synthetic_compare):
            return inherited_tests.Protocol09Test.batch(self,**kwargs)

    def test_mock_budget_and_restore(self):
        calls,ledger=self.batch(); self.assertEqual(len(calls),18); self.assertTrue(ledger['success'])

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



class TaskTargets(unittest.TestCase):
    def fixture(self,mode=7):
        from types import SimpleNamespace
        import task
        t=np.arange(9000,dtype=np.int64)*10000+1000000
        clock=np.arange(9000)*.01-10; o=task.offsets(mode,clock)
        src=dict(timestamp=t,x=np.ones(9000),y=np.full(9000,2.),z=np.full(9000,-2.5),
                 vx=np.full(9000,.02),vy=np.full(9000,np.nan),yaw=np.full(9000,.3),yawspeed=np.full(9000,np.nan))
        src['acceleration[0]']=np.full(9000,.01); src['acceleration[1]']=np.full(9000,np.nan)
        d=dict(timestamp=t,input_timestamp=t,attitude_timestamp=t,excitation_time=clock)
        for f,add,base in [('p_sp',o['p'],[1.,2.]),('v_ff',o['v'],[.02,0.]),('a_ff',o['a'],[.01,0.])]:
            for a in range(2): d[f'{f}[{a}]']=base[a]+add[:,a]
        d['p_sp[2]']=src['z'].copy()
        att=dict(timestamp=t.copy(),yaw_body=.3+o['yaw'],yaw_sp_move_rate=o['yaw_rate'].copy())
        tables=dict(trajectory_setpoint=src,vehicle_attitude_setpoint=att)
        u=SimpleNamespace(get_dataset=lambda n:SimpleNamespace(data=tables[n]))
        return u,d,dict(hover_start=1000000,hover_end=91000000),dict(task={5:'hover',6:'figure8',7:'heading'}[mode],parameters=dict(MPC_VCT_TEST=mode)),tables
    def test_targets_and_optional_ff_once(self):
        import task
        for mode in (5,6,7):
            u,d,e,j,_=self.fixture(mode); self.assertEqual(task.check_targets(u,d,e,j)['samples'],9000)
    def test_wrong_targets_and_duplicated_ff(self):
        import task
        for key in ('p_sp[0]','p_sp[1]','p_sp[2]','v_ff[0]','a_ff[1]'):
            for value in (.01,np.nan):
                u,d,e,j,_=self.fixture(); d[key][4000]+=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError): task.check_targets(u,d,e,j)
    def test_wrong_heading_rate_source_clock_task(self):
        import task
        for field in ('yaw_body','yaw_sp_move_rate','timestamp'):
            u,d,e,j,t=self.fixture(); t['vehicle_attitude_setpoint'][field][4000]+=.02 if field!='timestamp' else 1
            with self.assertRaises(ValueError):task.check_targets(u,d,e,j)
        u,d,e,j,t=self.fixture(); j['task']='hover'
        with self.assertRaises(ValueError):task.check_targets(u,d,e,j)
        u,d,e,j,t=self.fixture(); d['excitation_time'][-1]=63
        with self.assertRaises(ValueError):task.check_targets(u,d,e,j)
    def test_independent_numerical_derivatives_and_bounds(self):
        import task
        t=np.linspace(.1,63.9,2000); h=1e-3
        f=task.offsets(7,t); lo=task.offsets(7,t-h); hi=task.offsets(7,t+h)
        np.testing.assert_allclose((hi['p']-lo['p'])/(2*h),f['v'],atol=1e-8)
        np.testing.assert_allclose((hi['p']-2*f['p']+lo['p'])/h**2,f['a'],atol=1e-8)
        self.assertLess(np.max(np.linalg.norm(f['v'],axis=1)),.18)
        self.assertLess(np.max(np.linalg.norm(f['a'],axis=1)),.08)
        for mode in (5,6,7):
            for v in task.offsets(mode,np.array([-1.,0.,64.,65.])).values(): self.assertFalse(np.any(v))
    def test_checkpoint_failure_exhaustion_changed_configuration(self):
        p=common.load_protocol()
        current=dict(source_head='x',planned=18,firmware_sha256='y',original_parameter_sha256='z',applied_profile=1171)
        old={**current,'success':False,'attempts':[dict(job=j,status='accepted') for j in p['jobs'][:6]],
             'pairs':[dict(accepted=True)]*3,'parameter_restore_exact':True,'remaining_simulators':[]}
        run.validate_checkpoint(old,current,p['jobs'],b'x',b'x')
        for key,value in [('success',True),('parameter_restore_exact',False),('source_head','q'),('remaining_simulators',[123])]:
            with self.assertRaises(RuntimeError): run.validate_checkpoint({**old,key:value},current,p['jobs'],b'x',b'x')
        old['attempts'][0]['status']='failed'
        with self.assertRaises(RuntimeError): run.validate_checkpoint(old,current,p['jobs'],b'x',b'x')

class ScriptSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec=importlib.util.spec_from_file_location('v06_tools',common.CONFIG.parent/'scripts/toolbox.py')
        cls.t=importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.t)
    def test_explicit_xyz_and_rate_pid(self):
        for mode in (0,1):
            c=self.t.config(mode)
            self.assertEqual(c['MPC_VC_AXES'],7*mode); self.assertEqual(c['MPC_VCT_TEST'],0)
            for key,val in self.t.RATE.items(): self.assertEqual(c[key],val)
            self.assertEqual(c['MPC_USE_HTE'],1)
    def test_armed_switch_rejected_before_any_write(self):
        with patch.object(self.t.rate_io,'ground',side_effect=RuntimeError('armed')),patch.object(self.t.rate_io,'set_parameter') as write:
            with self.assertRaises(RuntimeError): self.t.apply(1)
            write.assert_not_called()
    def test_effective_and_inner_mode_verified(self):
        rate=dict(effective_mode=0,effective_axes=0,pending=False,fault=0)
        vel=dict(effective_mode=1,effective_axes=7,pending=False,reject=0)
        with patch.object(self.t.rate_io,'ground'),patch.object(self.t.rate_io,'parameter',side_effect=lambda k:self.t.RATE[k]),patch.object(self.t.rate_io,'topic',side_effect=lambda k:rate if k=='sta_rate_ctrl_status' else vel):
            self.t.verify(1)
            vel['pending']=True
            with self.assertRaises(RuntimeError): self.t.verify(1)
            vel['pending']=False; rate['effective_mode']=1
            with self.assertRaises(RuntimeError): self.t.verify(1)
    def test_wrappers_default_dry_run(self):
        import subprocess
        for name,extra in [('start',[]),('switch',['esta']),('fly',['hover'])]:
            r=subprocess.run([str(common.CONFIG.parent/'scripts'/f'{name}.sh'),*extra],capture_output=True,text=True,timeout=15)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertTrue('未飞行' in r.stdout or 'DRY RUN' in r.stdout)

class HoldTargetSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pyulog import ULog
        cls.folder=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260928/V06/series01/run02')
        record=json.loads((cls.folder/'result.json').read_text()); log=max(record['logs'],key=lambda r:r['bytes'])
        assert common.fingerprint(log['archive'])==log['sha256']
        cls.u=ULog(log['archive']); cls.ref=json.loads((cls.folder/'height_reference.json').read_text())
        cls.f=json.loads((cls.folder/'task_yaw.json').read_text())
    def test_reproduce_historical_failure_without_reaccepting_flight(self):
        from v04_handoff09 import capture
        with self.assertRaisesRegex(ValueError,'Local hold yaw changed'):
            capture(self.u,self.ref,self.f,self.f['timestamp']+100000,source_us=self.f['timestamp'])
        self.assertFalse(json.loads((self.folder/'result.json').read_text())['success'])
    def test_keep_source_target_separate_from_new_command(self):
        from handoff_capture import capture
        x=capture(self.u,self.ref,self.f,self.f['timestamp']+100000,source_us=self.f['timestamp'])
        self.assertAlmostEqual(x['wire']['param4'],self.f['yaw'],places=7)
        self.assertGreater(abs(self.f['yaw']-self.f['existing_target_yaw']),.001)
        self.assertLess(abs(self.f['yaw']-self.f['existing_target_yaw']),.002)
        self.assertEqual(x['yaw_freeze'],self.f)
    def test_fabricated_freeze_still_rejected(self):
        from handoff_capture import capture
        for k in ('yaw','existing_target_yaw','heading_counter'):
            f={**self.f,k:self.f[k]+.01}
            with self.subTest(key=k),self.assertRaises(ValueError): capture(self.u,self.ref,f,f['timestamp']+100000,source_us=f['timestamp'])
    def test_target_change_boundary_not_relaxed(self):
        from handoff_capture import capture
        source=self.f['timestamp']+20000
        for delta,ok in ((.000999,True),(.001001,False),(float('nan'),False)):
            u=copy.deepcopy(self.u); d=u.get_dataset('trajectory_setpoint').data
            k=np.searchsorted(d['timestamp'],source,side='right')-1
            self.assertGreater(d['timestamp'][k],self.f['timestamp'])
            d['yaw'][k]=self.f['existing_target_yaw']+delta
            if ok: capture(u,self.ref,self.f,source+100000,source_us=source)
            else:
                with self.assertRaises(ValueError): capture(u,self.ref,self.f,source+100000,source_us=source)
    def test_only_one_comparison_operand_changes(self):
        old=(common.REPO/'research/sta-velocity-control/scripts/v04_handoff09.py').read_text()
        actual=(common.CONFIG/'handoff_capture.py').read_text()
        expected=old.replace("q['yaw']-frozen['yaw']","q['yaw']-frozen['existing_target_yaw']")
        expected=expected.replace("    if abs(math.remainder(q['yaw']-frozen['existing_target_yaw']",
            "    # Source integrity compares the old hold target with the old hold target.\n    # The separately admitted measured-heading command is bounded by replay.\n    if abs(math.remainder(q['yaw']-frozen['existing_target_yaw']")
        self.assertEqual(actual,expected)

if __name__=='__main__': unittest.main()
