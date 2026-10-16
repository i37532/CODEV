"""Synthetic wiring/negative tests; not a simulated flight or acceptance claim."""
import copy
import json
from pathlib import Path
import tempfile
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
import analyzer as a
import targets


def job(gate='A', mode=3):
    task,axes,test,duration=targets.SPECS[gate]
    c=a.leaf('r02_config','research/sta-velocity-control/regularized_sta/r02/tools/config.py').candidate(mode,0 if mode==0 else axes)
    c.update(gate=gate,task=task,mode=mode,axes=0 if mode==0 else axes,candidate={0:'PID',1:'ESTA',3:'RSTA'}[mode],
             main_duration_s=duration,divisor=1,seed=999999,id='synthetic-'+gate+'-'+str(mode))
    c['parameters']['MPC_VCT_TEST']=test
    return c


class Log:
    def __init__(self, datasets):self.datasets=datasets
    def get_dataset(self,name):return SimpleNamespace(data=self.datasets[name])


def fixture(gate='A',mode=3):
    j=job(gate,mode);n=9100;t=np.arange(n,dtype=np.int64)*10000+1000000
    x={k:np.zeros(n,dtype=np.int64) for k in ('pending','reject','inner_mode','inner_axes','fault','failsafe','timing',
        'sta_fault','config_pending','sta_flags','constraint_bits','reset_bits','z_hte_shift','landed','contact')}
    for key in ('timestamp','timestamp_sample','input_timestamp','inner_timestamp','inner_check_timestamp','setpoint_timestamp','attitude_timestamp'):
        x[key]=t.copy()
    for key in ('publish_seq','update_seq','inner_seq'):x[key]=np.arange(n,dtype=np.int64)
    for key in ('pid_calls','enabled','armed','valid','inner_valid','inner_divisor','inner_reads'):
        x[key]=np.ones(n,dtype=np.int64)
    for key,value in dict(requested_mode=mode,effective_mode=mode,requested_axes=j['axes'],effective_axes=j['axes'],
            pid_axes=7^j['axes'],active_axes=j['axes'],committed_axes=j['axes'],z_phase=3 if j['axes']&4 else 0,
            takeoff_state=5,config_generation=1).items():x[key]=np.full(n,value,dtype=np.int64)
    for key in ('raw_dt','used_dt','input_dt'):x[key]=np.full(n,.01)
    x['hover_thrust']=np.full(n,.5);x['thrust_min']=np.full(n,.12);x['thrust_max']=np.ones(n)
    x['excitation_time']=np.arange(n)*.01-4
    x['excitation']=targets.waveform(x['excitation_time'],.2 if gate=='A' else .1) if gate in 'AB' else np.zeros(n)
    x['excitation_y']=np.zeros(n);x['excitation_z']=np.zeros(n)
    q={k:x[k].copy() for k in ('timestamp','timestamp_sample','input_timestamp','publish_seq','pid_calls','enabled','armed',
        'requested_mode','effective_mode','requested_axes','effective_axes','pending','reject')}
    for key,value in dict(div_req=1,div_eff=1,div_pending=0,div_reject=0,control_fault=0,clock=1,control_updated=1,
            control_held=0,path_ns=100,module_ns=200,interval_pos=0,interval_neg=0,variant_req=mode,variant_eff=mode,
            sta_gen=1,sta_pending=0,sta_reject=0).items():q[key]=np.full(n,value,dtype=np.int64)
    q['control_seq']=np.arange(n,dtype=np.int64);q['h']=np.full(n,.01)
    source={'timestamp':t.copy(),'yaw':np.zeros(n),'yawspeed':np.full(n,np.nan)}
    position={'timestamp':t.copy(),'timestamp_sample':t.copy()}
    attitude={'timestamp':t.copy(),'yaw_body':np.zeros(n),'yaw_sp_move_rate':np.zeros(n)}
    offsets=targets.old.offsets(j['parameters']['MPC_VCT_TEST'],x['excitation_time'])
    for axis,(name,suffix) in enumerate(zip(('x','y','z'),'XYZ')):
        base=np.full(n,-2.5 if axis==2 else 0.)
        source[name]=base.copy();source[('vx','vy','vz')[axis]]=np.full(n,np.nan)
        source[f'acceleration[{axis}]']=np.full(n,np.nan)
        x[f'p_sp[{axis}]']=base+offsets['p'][:,axis];position[name]=x[f'p_sp[{axis}]'].copy()
        x[f'v_ff[{axis}]']=offsets['v'][:,axis].copy() if gate in 'CD' else np.full(n,np.nan)
        x[f'a_ff[{axis}]']=offsets['a'][:,axis].copy() if gate in 'CD' else np.full(n,np.nan)
        v=np.where(np.isfinite(x[f'v_ff[{axis}]']),x[f'v_ff[{axis}]'],0.)
        if (gate=='A' and axis==0) or (gate=='B' and axis==2):v=v+x['excitation']
        x[f'v_sp[{axis}]']=v.copy();x[f'v[{axis}]']=v.copy();x[f'v_dot[{axis}]']=np.zeros(n);x[f's[{axis}]']=np.zeros(n)
        for name2 in ('nu_before','nu_ideal','nu_applied','a_sta'):
            x[f'{name2}[{axis}]']=np.full(n,0. if j['axes']&(1<<axis) else np.nan)
        q[f'integral[{axis}]']=np.zeros(n);q[f'correction[{axis}]']=np.zeros(n)
        eps=j['parameters']['MPC_VC_EPS_'+suffix];q[f'eps_req[{axis}]']=np.full(n,eps)
        q[f'eps_eff[{axis}]']=np.full(n,eps if mode==3 and j['axes']&(1<<axis) else np.nan)
        x[f'a_req[{axis}]']=np.nan_to_num(x[f'a_ff[{axis}]']);x[f'a_proxy[{axis}]']=x[f'a_req[{axis}]'].copy()
        x[f'thrust[{axis}]']=(x[f'a_req[{axis}]']-(9.80665 if axis==2 else 0))*.5/9.80665
    for axis in range(4):
        x[f'q_sp[{axis}]']=np.full(n,1. if axis==0 else 0.);attitude[f'q_d[{axis}]']=x[f'q_sp[{axis}]'].copy()
    u=Log({'trajectory_setpoint':source,'vehicle_local_position':position,'vehicle_attitude_setpoint':attitude})
    events=dict(hover_start=int(t[0]),hover_end=int(t[-1]+10000))
    return x,q,j,u,events


def component(f):
    x,q,j,_,e=f
    return a.check_components(x,q,j,e['hover_start'],e['hover_end'],True)


class Dispatch(unittest.TestCase):
    def test_all_four_tasks_three_modes(self):
        for gate in 'ABCD':
            for mode in (0,1,3):
                with self.subTest(gate=gate,mode=mode):
                    f=fixture(gate,mode);component(f)
                    x,q,j,u,e=f;result=targets.check_targets(u,x,e,j)
                    self.assertEqual(result['timing']['main_duration_s'],32 if gate in 'AB' else 64)

    def test_unknown_mode_axes_task_gate_and_window(self):
        for key,value in [('gate','E'),('task','V'),('mode',2),('axes',3),('divisor',2),('main_duration_s',64),('candidate','ESTA')]:
            j=job();j[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):a.validate_job(j)

    def test_seed_is_integral_positive(self):
        for seed in (0,-1,True,1.5,None):
            j=job();j['seed']=seed
            with self.assertRaises(ValueError):a.validate_job(j)

    def test_wrong_task_parameter(self):
        j=job();j['parameters']['MPC_VCT_TEST']=8
        with self.assertRaises(ValueError):a.validate_job(j)

    def test_nonzero_ff_applied_once(self):
        x,q,j,u,e=fixture('A');x['a_ff[0]'][:]=.01;u.datasets['trajectory_setpoint']['acceleration[0]'][:]=.01
        x['a_req[0]'][:]=.01;x['a_proxy[0]'][:]=.01;x['thrust[0]'][:]=.01*.5/9.80665
        component((x,q,j,u,e));targets.check_targets(u,x,e,j)
        x['a_req[0]'][:]=.02
        with self.assertRaises(ValueError):component((x,q,j,u,e))

    def test_direct_ff_nan_topology_not_normalized(self):
        x,q,j,u,e=fixture('B');targets.check_targets(u,x,e,j);x['v_ff[0]'][300]=0.
        with self.assertRaisesRegex(ValueError,'topology'):targets.check_targets(u,x,e,j)

    def test_figure8_ff_missing_addition(self):
        x,q,j,u,e=fixture('D');x['a_ff[0]'][1500]=0.
        with self.assertRaises(ValueError):targets.check_targets(u,x,e,j)

    def test_z_waveform_is_scalar_not_excitation_z(self):
        x,q,j,u,e=fixture('B');x['excitation_z']=x['excitation'].copy();x['excitation'][:]=0.
        with self.assertRaises(ValueError):targets.check_targets(u,x,e,j)

    def test_missing_main_boundary_and_wrong_clock(self):
        for value in (0.,80.):
            x,q,j,u,e=fixture();x['excitation_time'][:]=value
            with self.assertRaises(ValueError):targets.check_targets(u,x,e,j)
        x,q,j,u,e=fixture();x['excitation_time'][1000]+=.1
        with self.assertRaises(ValueError):targets.check_targets(u,x,e,j)

    def test_wrong_source_duplicate_missing_future(self):
        for mutation in ('duplicate','missing','future'):
            x,q,j,u,e=fixture();source=u.datasets['trajectory_setpoint']
            if mutation=='duplicate':source['timestamp'][100]=source['timestamp'][99]
            elif mutation=='missing':u.datasets['trajectory_setpoint']={k:np.delete(v,100) for k,v in source.items()}
            else:x['setpoint_timestamp'][100]=x['timestamp'][100]+1
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):targets.check_targets(u,x,e,j)

    def test_exact_consumed_position_not_latest(self):
        x,q,j,u,e=fixture();u.datasets['vehicle_local_position']['timestamp'][100]+=1
        with self.assertRaises(ValueError):targets.check_targets(u,x,e,j)

    def test_position_p_missing_wrong_injection_and_clamp(self):
        for key in ('p_sp[0]','v_sp[0]','v_sp[1]'):
            x,q,j,u,e=fixture();x[key][2000]+=.001
            with self.subTest(key=key),self.assertRaises(ValueError):targets.check_targets(u,x,e,j)

    def test_heading_and_missing_partial_boundaries(self):
        x,q,j,u,e=fixture();u.datasets['vehicle_attitude_setpoint']['yaw_body'][200]+=.01
        with self.assertRaises(ValueError):targets.check_targets(u,x,e,j)

    def test_unmatched_attitude_nan_not_hidden_by_partial_coverage(self):
        x,q,j,u,e=fixture();attitude=u.datasets['vehicle_attitude_setpoint']
        attitude['timestamp'][200]+=1;attitude['q_d[2]'][200]=np.nan
        with self.assertRaisesRegex(ValueError,'Nonfinite'):targets.check_targets(u,x,e,j)
        x,q,j,u,e=fixture();u.datasets['vehicle_attitude_setpoint']={k:v[40:] for k,v in u.datasets['vehicle_attitude_setpoint'].items()}
        with self.assertRaises(ValueError):targets.check_targets(u,x,e,j)


class Components(unittest.TestCase):
    def test_wrong_mode_axis_inner_and_pending(self):
        for key,value in [('effective_mode',1),('effective_axes',3),('inner_mode',1),('inner_axes',1),('inner_divisor',2),('pending',1),('config_pending',1),('fault',1),('sta_fault',1)]:
            f=fixture();f[0][key][100]=value
            with self.subTest(key=key),self.assertRaises(ValueError):component(f)

    def test_time_reversal_duplicate_missing_and_wrong_rawdt(self):
        for key in ('timestamp','timestamp_sample','input_timestamp','publish_seq','update_seq'):
            f=fixture();f[0][key][100]=f[0][key][99]
            with self.subTest(key=key),self.assertRaises(ValueError):component(f)
        f=fixture();f[0]['raw_dt'][100]=.04
        with self.assertRaises(ValueError):component(f)
        f=fixture();f[1].update({k:np.delete(v,100) for k,v in list(f[1].items())})
        with self.assertRaises(ValueError):component(f)

    def test_reset_invalid_nonengaged_and_partial_commit(self):
        for key,value in [('reset_bits',1),('valid',0),('active_axes',0),('committed_axes',0),('pid_axes',7),('sta_flags',1)]:
            f=fixture();f[0][key][100]=value
            with self.subTest(key=key),self.assertRaises(ValueError):component(f)

    def test_metadata_generation_epsilon(self):
        for key,value in [('variant_req',1),('variant_eff',1),('sta_gen',2),('eps_eff[0]',.02),('eps_eff[1]',.01),('eps_req[2]',.01),('sta_reject',1)]:
            f=fixture();f[1][key][100]=value
            with self.subTest(key=key),self.assertRaises(ValueError):component(f)

    def test_both_generation_fields_zero_still_rejected(self):
        f=fixture();f[0]['config_generation'][:]=0;f[1]['sta_gen'][:]=0
        with self.assertRaisesRegex(ValueError,'no accepted configuration'):component(f)

    def test_candidate_and_cross_axis_states(self):
        for key in ('nu_before[0]','nu_ideal[0]','nu_applied[0]','a_sta[0]','nu_applied[1]'):
            f=fixture();f[0][key][100]=.001
            with self.subTest(key=key),self.assertRaises(ValueError):component(f)

    def test_weighted_bias_variance_rmse_and_update_tv(self):
        f=fixture();x,q,j,u,e=f;x['s[0]'][:]=.002
        result=a.window_metrics(x,q,j,0,32)
        self.assertAlmostEqual(result['error']['mean'][0],.002)
        self.assertAlmostEqual(result['error']['rmse'][0],.002)
        self.assertLess(result['error']['variance'][0],1e-25)
        self.assertEqual(result['actual_updates'],3200)

    def test_constraint_fraction_and_continuous_limits(self):
        f=fixture();x,q,j,u,e=f;x['constraint_bits'][401:460]=1
        with self.assertRaisesRegex(ValueError,'Constraint'):a.window_metrics(x,q,j,0,32)

    def test_spectra_32_and_64_seconds(self):
        for gate in ('A','D'):
            x,q,j,u,e=fixture(gate);result=a.spectral_metrics(x,q,targets.spec(j)[3])
            self.assertAlmostEqual(result['update_hz'],100.)
            self.assertEqual(result['common_0_7hz_rms'],[0.,0.,0.])


class Paired(unittest.TestCase):
    def result(self,mode=0,gate='A'):
        return dict(accepted=True,job=job(gate,mode),binding={'source_head':'synthetic'},position_rmse=[0.,0.,0.],yaw_rmse=0.,
            diagnostic=dict(error={'rmse':[0.,0.,0.]},windows={name:{'error':{'rmse':[0.,0.,0.]}} for name,_,_ in targets.windows(job(gate,mode))}))

    def test_both_candidates_exact_risk_boundary(self):
        for mode in (1,3):
            p=self.result();c=self.result(mode);c['diagnostic']['error']['rmse']=[.02,.02,.01]
            self.assertTrue(a.compare(p,c)['accepted'])
            c['diagnostic']['error']['rmse'][2]=np.nextafter(.01,np.inf)
            self.assertFalse(a.compare(p,c)['accepted'])

    def test_pair_wrong_seed_source_gate_and_fixed_gain(self):
        for mutation in ('seed','source','gate','gain','invalid'):
            p=self.result();c=self.result(3)
            if mutation=='seed':c['job']['seed']+=1
            elif mutation=='source':c['binding']['source_head']='other'
            elif mutation=='gate':c=self.result(3,'B')
            elif mutation=='gain':c['job']['parameters']['MPC_VC_L1_X']+=.01
            else:c['accepted']=False
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):a.compare(p,c)

    def test_half_and_noncommanded_axis_failure(self):
        p=self.result();c=self.result(3);c['diagnostic']['windows']['second_half']['error']['rmse'][1]=.02001
        self.assertFalse(a.compare(p,c)['accepted'])
        c=self.result(3);c['position_rmse'][2]=.05001
        self.assertFalse(a.compare(p,c)['accepted'])

    def test_missing_real_provenance_cannot_accept(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);protocol={'jobs':[job()]}
            result=a.analyze(run,protocol,job())
            self.assertFalse(result['accepted']);self.assertIn('error',result)
            self.assertTrue((run/'r03_metrics.json').exists())


class Provenance(unittest.TestCase):
    def prepare(self,root):
        run=root/'run';run.mkdir();cfg=root/'config';cfg.mkdir()
        j=job();execution=cfg/'execution.json';execution.write_text(json.dumps({'jobs':[j]}))
        (cfg/'frozen.json').write_text(json.dumps({'source':'fixture'}))
        qp=cfg/'qualification.json';qp.write_text(json.dumps(dict(source_head='a'*40,firmware_sha256='b'*64,success=True,
            clean=True,stage='R03-A',gate='A',new_flights=0,execution_sha256=a.digest(execution),frozen_sha256=a.digest(cfg/'frozen.json'))))
        p=dict(jobs=[j],stage='R03-A',maximum_attempts=9,total_maximum_attempts=36,config_dir=str(cfg),execution_path=str(execution),qualification_path=str(qp))
        approval=dict(approved=True,stage='R03-A',gate='A',source_head='a'*40,execution_sha256=a.digest(execution),
            frozen_sha256=a.digest(cfg/'frozen.json'),firmware_sha256='b'*64,qualification_sha256=a.digest(qp),maximum_attempts=9)
        approval['total_maximum_attempts']=36
        record=dict(source_head='a'*40,binary_sha256='b'*64,scenario_sha256=a.digest(execution),scenario_path=str(execution))
        (run/'original_parameters.bson').write_bytes(b'fixture-complete-EEPROM')
        restored=dict(source_head='a'*40,gate='A',job_id=j['id'],original_parameter_sha256=a.digest(run/'original_parameters.bson'),
            restored_parameter_sha256=a.digest(run/'original_parameters.bson'),parameter_restore_exact=True,
            remaining_simulators=[],backup_path=str(run/'original_parameters.bson'),stopped_before_restore=True)
        reference=dict(path=str(qp),sha256=a.digest(qp))
        for name,value in [('job.json',j),('authorization.json',approval),('result.json',record),('parameter_restore.json',restored),('run_protocol.json',p),('qualification_reference.json',reference)]:
            (run/name).write_text(json.dumps(value))
        return run,p,j

    def test_complete_binding_positive_not_flight(self):
        with tempfile.TemporaryDirectory() as directory:
            run,p,j=self.prepare(Path(directory));binding=a.provenance(run,p,j)
            self.assertEqual(binding['maximum_attempts'],9)

    def test_wrong_source_budget_protocol_and_manifest_rejected(self):
        for filename,key,value in [('authorization.json','source_head','c'*40),('authorization.json','maximum_attempts',10),
                ('authorization.json','approved',False),('result.json','scenario_path','/wrong'),('job.json','seed',1)]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as directory:
                run,p,j=self.prepare(Path(directory));data=json.loads((run/filename).read_text());data[key]=value
                (run/filename).write_text(json.dumps(data))
                with self.assertRaises(ValueError):a.provenance(run,p,j)

    def test_restoration_stop_and_digest_mandatory(self):
        for key,value in [('parameter_restore_exact',False),('stopped_before_restore',False),('remaining_simulators',[123]),
                ('restored_parameter_sha256','0'*64),('gate','B'),('job_id','wrong')]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as directory:
                run,p,j=self.prepare(Path(directory));path=run/'parameter_restore.json';data=json.loads(path.read_text());data[key]=value
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):a.provenance(run,p,j)

    def test_changed_source_files_invalidate_qualification(self):
        for name in ('execution.json','frozen.json','qualification.json'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                run,p,j=self.prepare(Path(directory));path=Path(p['config_dir'])/name
                path.write_text(path.read_text()+'\n')
                with self.assertRaises(ValueError):a.provenance(run,p,j)

    def test_failed_or_dirty_qualification_not_receipt_only(self):
        for key,value in [('success',False),('clean',False),('new_flights',1),('gate','B')]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as directory:
                run,p,j=self.prepare(Path(directory));path=Path(p['qualification_path']);data=json.loads(path.read_text());data[key]=value
                path.write_text(json.dumps(data));approval=run/'authorization.json';receipt=json.loads(approval.read_text())
                receipt['qualification_sha256']=a.digest(path);approval.write_text(json.dumps(receipt))
                (run/'qualification_reference.json').write_text(json.dumps(dict(path=str(path),sha256=a.digest(path))))
                with self.assertRaises(ValueError):a.provenance(run,p,j)

    def test_replay_uses_explicit_second_qualification_not_default(self):
        with tempfile.TemporaryDirectory() as directory:
            run,p,j=self.prepare(Path(directory));p['startup_overrides']={'unchanged':1}
            saved={**p,'qualification_path':str(Path(p['qualification_path']).parent/'qualification02/evidence.json'),
                'startup_overrides':{**p['startup_overrides'],**j['parameters']}}
            qp=Path(saved['qualification_path']);qp.parent.mkdir();qp.write_text('{}')
            (run/'qualification_reference.json').write_text(json.dumps(dict(path=str(qp),sha256=a.digest(qp))))
            (run/'run_protocol.json').write_text(json.dumps(saved))
            with patch.object(a,'_protocol',return_value=SimpleNamespace(load_protocol=lambda gate:p)):
                self.assertEqual(a.replay_protocol(run,j),saved)

    def test_replay_changed_gate_or_startup_not_trusted(self):
        for change in ('gate','startup','path'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                run,p,j=self.prepare(Path(directory));p['startup_overrides']={}
                saved={**p,'startup_overrides':dict(j['parameters'])}
                if change=='gate':saved['stage']='R03-B'
                elif change=='startup':saved['startup_overrides']['MPC_VC_L1_X']+=.1
                else:saved['qualification_path']='/outside/evidence.json'
                (run/'run_protocol.json').write_text(json.dumps(saved))
                with patch.object(a,'_protocol',return_value=SimpleNamespace(load_protocol=lambda gate:p)),self.assertRaises(ValueError):a.replay_protocol(run,j)

    def test_absolute_import_without_r03_searchpath(self):
        command='import importlib.util; s=importlib.util.spec_from_file_location("isolated_r03",'+repr(str(a.HERE/'analyzer.py'))+'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.REPO)'
        result=subprocess.run([sys.executable,'-c',command],cwd=a.REPO,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn(str(a.REPO),result.stdout)


if __name__=='__main__':unittest.main(verbosity=2)
