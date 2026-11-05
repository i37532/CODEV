"""Synthetic offline tests only; no acceptance of a real AX03 flight."""
import copy
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
import numpy as np
import common
import core
import cadence
import task
import analyze
import run

def metrics(job):
    return dict(accepted=True,job=job,diagnostic=dict(error=dict(rmse=[.01]*3),
        windows={key:dict(error=dict(rmse=[.01]*3)) for key in ('first_loop','second_loop')}),
        position_rmse=[.01]*3,yaw_rmse=.01)

def fixture(axes):
    job=copy.deepcopy(next(j for j in common.jobs() if j['axes']==axes)); n=9000
    t=np.arange(n,dtype=np.int64)*10000+1000000
    d={k:np.zeros(n,dtype=np.int64) for k in ('pending','reject','inner_mode','inner_axes','fault','failsafe','timing',
       'sta_fault','config_pending','sta_flags','constraint_bits','excitation','excitation_y','excitation_z','z_hte_shift')}
    for k in ('timestamp','timestamp_sample','input_timestamp','inner_timestamp','inner_check_timestamp'): d[k]=t.copy()
    for k in ('publish_seq','update_seq','inner_seq'): d[k]=np.arange(n)
    for k in ('pid_calls','enabled','armed','valid','inner_valid','inner_divisor','inner_reads'): d[k]=np.ones(n,dtype=int)
    for k,v in dict(requested_mode=job['mode'],effective_mode=job['mode'],requested_axes=axes,effective_axes=axes,
                    pid_axes=7^axes,active_axes=axes,committed_axes=axes,z_phase=3 if axes&4 else 0).items(): d[k]=np.full(n,v)
    for k in ('raw_dt','used_dt','input_dt'):d[k]=np.full(n,.01)
    d['excitation_time']=np.arange(n)*.01-12;d['hover_thrust']=np.full(n,.5)
    q={k:d[k].copy() for k in ('timestamp','timestamp_sample','input_timestamp','publish_seq','pid_calls','enabled','armed','effective_mode','effective_axes')}
    for k,v in dict(div_req=1,div_eff=1,div_pending=0,div_reject=0,control_fault=0,clock=1,
                    control_updated=1,control_held=0,path_ns=100,module_ns=200,interval_pos=0,interval_neg=0).items():q[k]=np.full(n,v)
    q['h']=np.full(n,.01);q['control_seq']=np.arange(n)+1
    for i,suffix in enumerate('XYZ'):
        s=np.where(np.arange(n)%2,1.,-1.)*(i+1)*.0001
        d[f's[{i}]']=s;d[f'v[{i}]']=s;d[f'v_sp[{i}]']=np.zeros(n)
        d[f'a_ff[{i}]']=np.full(n,.001*(i+1));q[f'integral[{i}]']=np.zeros(n)
        for name in ('nu_before','nu_ideal','nu_applied','a_sta'):d[f'{name}[{i}]']=np.full(n,np.nan)
        c=np.zeros(n)
        if axes&(1<<i):
            l1=job['parameters']['MPC_VC_L1_'+suffix];l2=job['parameters']['MPC_VC_L2_'+suffix]
            delta=-.01*l2*np.sign(s);post=np.cumsum(delta);before=np.r_[0.,post[:-1]]
            c=-l1*np.sqrt(abs(s))*np.sign(s)+before
            for key,v in dict(nu_before=before,nu_ideal=post,nu_applied=post,a_sta=c).items():d[f'{key}[{i}]']=v.copy()
        q[f'correction[{i}]']=c;d[f'a_req[{i}]']=c+d[f'a_ff[{i}]']
        d[f'a_proxy[{i}]']=d[f'a_req[{i}]'].copy()
        d[f'thrust[{i}]']=(d[f'a_req[{i}]']-(9.80665 if i==2 else 0))*.5/9.80665
    return d,q,job

class Protocol(unittest.TestCase):
    def test_exact48_task_gates_full_fixed_parameters(self):
        self.assertTrue(common.validate_manifest()); self.assertFalse(common.load_protocol()['flight_authorized'])
        for j in common.jobs():
            p=json.loads((common.CONFIG/'parameters'/(j['candidate'].lower()+'.json')).read_text())
            p['MPC_VCT_TEST']=j['parameters']['MPC_VCT_TEST'];self.assertEqual(p,j['parameters'])

    def test_invalid_axes_mode_div_gains_order_budget(self):
        for kind in ('axes','mode','divisor','gain','order','budget','seed'):
            d=common.design()
            if kind in ('axes','mode','divisor'):d['jobs'][2][kind]=99
            if kind=='gain':d['jobs'][2]['parameters']['MPC_VC_L1_Y']=1.
            if kind=='order':d['jobs'][0],d['jobs'][1]=d['jobs'][1],d['jobs'][0]
            if kind=='budget':d['jobs'].pop()
            if kind=='seed':d['seeds'][0]=41001
            with self.subTest(kind=kind),self.assertRaises(ValueError):common.validate_manifest(d)

    def test_actual_module_bindings(self):
        self.assertEqual(core.CONFIG,common.CONFIG);self.assertEqual(analyze.CONFIG,common.CONFIG);self.assertEqual(run.CONFIG,common.CONFIG)
        self.assertIs(core.check_cadence,cadence.check);self.assertIs(run.analyze,analyze.analyze)
        self.assertEqual(Path(sys.modules['task'].__file__).parent,common.CONFIG)
        self.assertEqual(Path(sys.modules['flight'].__file__).parent,common.LEGACY)

    def test_default_dryrun_and_unauthorized_execution_no_files(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'unused'
            for extra,code in [([],0),(['--execute','--output',str(out)],1)]:
                p=subprocess.run(['bash',str(common.CONFIG.parent/'run.sh'),*extra],capture_output=True,text=True)
                self.assertEqual(p.returncode,code,p.stderr);self.assertFalse(out.exists())
        with patch('flight.subprocess.Popen') as spawn:
            with self.assertRaises(RuntimeError):run.flight()
            spawn.assert_not_called()

    def test_receipt_cannot_inherit_ax02_authority_or_wrong_commit(self):
        with tempfile.TemporaryDirectory() as td,patch.object(common.subprocess,'check_output',return_value='head\n'):
            path=Path(td)/'SYNTHETIC.json';p=common.load_protocol()
            receipt=dict(approved=True,stage=p['stage'],source_head='head',execution_sha256=common.fingerprint(common.CONFIG/'execution.json'),maximum_attempts=48,
                         basis='User explicitly requested AX03, limited to this frozen 48-attempt batch')
            path.write_text(json.dumps(receipt));common.require_authorization(str(path),p)
            for key,value in [('approved',False),('source_head','old'),('stage','AX02'),('execution_sha256','bad'),('maximum_attempts',49),('basis','AX02 continuous execution')]:
                path.write_text(json.dumps({**receipt,key:value}))
                with self.assertRaises(RuntimeError):common.require_authorization(str(path),p)

    def test_admission_exact42_pairs_and_budget_exhausted(self):
        gate=common.Admission();pairs=[]
        for j in common.jobs():
            pair=gate.accept(j,metrics(j))
            if pair:pairs.append(pair)
        self.assertEqual(len(pairs),42)
        with self.assertRaises(RuntimeError):gate.before(common.jobs()[0])

    def test_failed_pid_v_safety_pair_and_no_reordering(self):
        for fail in (1,2,24,25,26,48):
            gate=common.Admission()
            for j in common.jobs()[:fail-1]:gate.accept(j,metrics(j))
            j=common.jobs()[fail-1];m=metrics(j);m['accepted']=False
            with self.assertRaises(RuntimeError):gate.accept(j,m)
            with self.assertRaises(RuntimeError):gate.before(j)
        gate=common.Admission()
        with self.assertRaises(RuntimeError):gate.before(common.jobs()[24])
        gate.accept(common.jobs()[0],metrics(common.jobs()[0]));j=common.jobs()[1];m=metrics(j);m['diagnostic']['error']['rmse'][2]=1.
        with self.assertRaises(RuntimeError):gate.accept(j,m)

    def test_core_all_eight_masks_nonzero_sequence(self):
        for axes in range(8):
            d,q,j=fixture(axes);r=core.check_diagnostic(d,q,1000000,91000000,j)
            self.assertEqual(r['cadence']['updates'],9000);self.assertEqual(r['samples'],6400)

    def test_wrong_mode_axes_rate_time_gap_reset_and_nonengagement(self):
        cases=[('effective_mode',0),('requested_axes',1),('inner_mode',1),('inner_axes',1),('inner_divisor',2),
               ('inner_valid',0),('publish_seq',0),('timestamp_sample',1),('input_timestamp',1),('sta_flags',1),
               ('pid_axes',7),('active_axes',0),('committed_axes',1),('z_phase',2),('raw_dt',.04),('sta_fault',1)]
        for field,value in cases:
            d,q,j=fixture(7);d[field][2000]=value
            with self.subTest(field=field),self.assertRaises(ValueError):core.check_diagnostic(d,q,1000000,91000000,j)
        d,q,j=fixture(7);d={k:np.delete(v,2000) for k,v in d.items()}
        with self.assertRaises(ValueError):core.check_diagnostic(d,q,1000000,91000000,j)

    def test_independent_nu_old_state_and_no_cross_axis(self):
        for axes in (1,2,3,4,5,6,7):
            axis=next(i for i in range(3) if axes&(1<<i))
            for name in ('nu_before','nu_ideal','nu_applied','a_sta'):
                d,q,j=fixture(axes);d[f'{name}[{axis}]'][100]+=.001
                with self.assertRaises(ValueError):cadence.check(d,q,j,True)
        d,q,j=fixture(1);d['nu_applied[1]'][:]=0
        with self.assertRaises(ValueError):cadence.check(d,q,j,True)

    def test_double_ff_and_bad_update_ownership(self):
        for field in ('correction[2]','h','control_seq','control_updated','control_held'):
            d,q,j=fixture(7);q[field][100]+=1
            with self.assertRaises(ValueError):cadence.check(d,q,j,True)

    def test_hte_selected_z_continuity_and_directional_constraint(self):
        d,q,j=fixture(4)
        # A constant nonzero HTE shift at one sample must translate both the
        # candidate and all subsequent states/correction, not X/Y state.
        shift=.001;at=100;d['z_hte_shift']=d['z_hte_shift'].astype(float);d['z_hte_shift'][at]=shift
        for k in ('nu_before[2]','nu_ideal[2]','nu_applied[2]','a_sta[2]','a_req[2]'):d[k][at:]+=shift
        q['correction[2]'][at:]+=shift
        cadence.check(d,q,j,True)
        d['z_hte_shift'][at]=0
        with self.assertRaises(ValueError):cadence.check(d,q,j,True)
        d,q,j=fixture(4);d['constraint_bits'][:]=1
        # Tilt only is NOT a Z constraint, even if map residual points outward.
        d['a_proxy[2]']-=np.sign(d['nu_ideal[2]']-d['nu_before[2]'])*.01
        cadence.check(d,q,j,True)
        d['constraint_bits'][:]=2
        with self.assertRaises(ValueError):cadence.check(d,q,j,True)

    def test_historical_job_never_becomes_new_acceptance(self):
        with tempfile.TemporaryDirectory() as td:
            old=copy.deepcopy(common.jobs()[0]);old['seed']=39001
            r=analyze.analyze(Path(td),common.load_protocol(),old)
            self.assertFalse(r['accepted']);self.assertIn('historical',r['error'])

    def test_derived_asset_and_actual_preparation_without_process(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);output=root/'output';output.mkdir();ram=root/'ram';ram.mkdir()
            (root/'frozen.json').write_text(json.dumps(dict(derived_iris_sha256=common.fingerprint(common.CONFIG/'models/iris.sdf'))))
            p=common.load_protocol();c=run.Checks(p,{},p['jobs'][0],Path(p['plugins']));c.authorization_token='SYNTHETIC'
            with patch.object(run,'CONFIG',root),patch.object(run,'require_authorization',return_value=dict(synthetic=True)), \
                 patch.object(run.ram_log,'create',return_value=ram),patch('flight.subprocess.Popen') as spawn:
                env=c.prepare_environment(output);spawn.assert_not_called()
            self.assertEqual((output/'models/iris/iris.sdf').read_bytes(),(common.CONFIG/'models/iris.sdf').read_bytes())
            self.assertEqual(env['M10_IMU_SEED'],str(p['jobs'][0]['seed']))
            self.assertEqual(env['PX4_SIM_SPEED_FACTOR'],'1')

    def batch(self,fail_at=None,reject_at=None,pair_at=None):
        # Exercise the actual main loop and complete EEPROM restore with mocks
        # only at process/device boundaries. Never spawn PX4/Gazebo.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);conf=root/'config';conf.mkdir();rootfs=root/'rootfs';(rootfs/'eeprom').mkdir(parents=True)
            param=rootfs/'eeprom/parameters_10016';param.write_bytes(b'original-full-eeprom')
            (root/'build/px4_sitl_default/src/lib/version').mkdir(parents=True)
            (root/'build/px4_sitl_default/src/lib/version/build_git_version.h').write_text('source-test')
            (root/'build/px4_sitl_default/parameters.json').write_text('{"parameters": []}')
            plugins=root/'plugins';plugins.mkdir();(plugins/'manifest.json').write_text('{}')
            p=common.load_protocol();p['plugins']=str(plugins);p['artifacts']['new_run_root']=str(root/'series')
            (conf/'frozen.json').write_text('{"assets":{},"control_parameters":{}}');calls=[]
            def git(*args):return 'research/sta-velocity-control' if args[0]=='branch' else ('source-test' if args[0]=='rev-parse' else '')
            def flight(**kwargs):
                calls.append(kwargs['checks'].job);directory=Path(sys.argv[-1]);directory.mkdir()
                self.assertEqual(kwargs['scenario_path'],conf/'execution.json');self.assertEqual(param.read_bytes(),b'experiment-eeprom')
                if fail_at==len(calls):raise RuntimeError('injected process failure')
            def analyze_mock(directory,protocol,job):
                m=metrics(job)
                if reject_at==len(calls):m['accepted']=False
                if pair_at==len(calls):m['diagnostic']['windows']['second_loop']['error']['rmse'][1]=10.
                return m
            with patch.multiple(run,REPO=root,ROOTFS=rootfs,CONFIG=conf,git=git,active_simulators=lambda:[],
                 digest=lambda path:'hash',persisted_bson=lambda data:{},check_parameters=lambda a,b:None,
                 encode_bson=lambda values,types:b'experiment-eeprom',flight=flight,analyze=analyze_mock,
                 noise_prefix=lambda path:np.array([p['jobs'][int(path.name[3:])-1]['seed']],float),
                 fresh_seeds=lambda:dict(accepted=True),load_protocol=lambda:p,
                 require_authorization=lambda *_:dict(synthetic=True),require_passive=lambda _:None,
                 require_qualification=lambda _:None,validate_receiver_profile=lambda:None), \
                 patch.object(run.socket,'socket'),patch.object(run.ram_log,'release_archived'), \
                 patch.object(run.shutil,'disk_usage',return_value=type('Space',(),{'free':20*1024**3})()), \
                 patch.object(sys,'argv',['runner','--execute','--authorization','SYNTHETIC','--output',str(root/'series'),'--source-head','source-test']), \
                 contextlib.redirect_stdout(io.StringIO()):
                if fail_at or reject_at or pair_at:
                    with self.assertRaises(RuntimeError):run.main()
                else:run.main()
            ledger=json.loads((root/'series/ledger.json').read_text())
            self.assertEqual(param.read_bytes(),b'original-full-eeprom');self.assertTrue(ledger['parameter_restore_exact'])
            self.assertEqual((root/'series/original_parameters.bson').read_bytes(),b'original-full-eeprom')
            return calls,ledger

    def test_runner_full48_gated_and_parameter_restore(self):
        calls,ledger=self.batch();self.assertEqual(len(calls),48);self.assertEqual(len(ledger['pairs']),42)
        self.assertTrue(ledger['success']);self.assertEqual(ledger['V_PID_safety_gate'],'accepted_budgeted_run25')

    def test_runner_failures_at_h_v_and_last_no_retry(self):
        for n in (1,24,25,26,48):
            calls,ledger=self.batch(fail_at=n);self.assertEqual(len(calls),n);self.assertFalse(ledger['success'])
            self.assertEqual(ledger['attempts'][-1]['status'],'failed')

    def test_runner_log_and_pair_failure_restore_and_stop(self):
        for kwargs in ({'reject_at':25},{'pair_at':26}):
            calls,ledger=self.batch(**kwargs);self.assertEqual(len(calls),next(iter(kwargs.values())))
            self.assertFalse(ledger['success'])

if __name__=='__main__':unittest.main(verbosity=2)
