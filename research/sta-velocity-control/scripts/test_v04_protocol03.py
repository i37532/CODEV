import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import io
from contextlib import redirect_stdout
import unittest
from unittest.mock import patch
import numpy as np
from v04_task03 import (REFERENCE, scalars, current_triplet, freeze_reference, check_reference,
                        command_params, check_readback, accepted_ack, entry_ok, EntryGate, excitation_class)
from analyze_v04_protocol03 import CONFIG, check_first_invocation, check_excitation_exit, height_evidence
import test_v04


class Protocol03Test(unittest.TestCase):
    def reference(self):
        p=dict.fromkeys(REFERENCE,0)
        p.update(timestamp=30e6,timestamp_sample=30e6,x=0,y=0,z=.5,heading=1.5708,ref_alt=488.)
        p.update(dict.fromkeys(('xy_valid','z_valid','v_xy_valid','v_z_valid','xy_global','z_global'),True))
        return freeze_reference(p)

    def test_command_units_and_finite_reference(self):
        r=self.reference(); c=command_params(r)
        self.assertEqual(c[:4],[-1,1,0,1.5708]); self.assertTrue(math.isnan(c[4]) and math.isnan(c[5]))
        self.assertEqual(c[6],490.); self.assertEqual(r['target_z'],-2.)
        for k in REFERENCE:
            p=r['position'].copy(); p.pop(k)
            with self.assertRaises(ValueError): freeze_reference(p)

    def test_reset_and_reference_changes_reject(self):
        r=self.reference()
        for k in REFERENCE:
            p=r['position'].copy(); p[k]+=1
            with self.assertRaises(ValueError): check_reference(p,r)

    def test_generated_nested_print_parse(self):
        raw=' position_setpoint_triplet_s\n\ttimestamp: 10\n\tprevious position_setpoint_s\n\tlat: 8\n\tcurrent position_setpoint_s\n\tlat: 47\n\tlon: 8\n\talt: 490\n\tyaw: 1.5708\n\tvalid: True\n\tyaw_valid: True\n\tnext position_setpoint_s\n\tlat: 9\n'
        d=current_triplet(raw); self.assertEqual(d['lat'],47)
        check_readback(d,d,self.reference())
        for k in ('lat','alt','yaw','valid','yaw_valid'):
            bad=d.copy(); bad[k]=False if k.endswith('valid') else d[k]+.1
            with self.assertRaises(ValueError): check_readback(d,bad,self.reference())
        with self.assertRaises(ValueError): current_triplet('missing')

    def test_ack_identity_time_and_rejection(self):
        r=dict(received_monotonic=10,system=1,component=1,message=dict(command=192,result=0))
        self.assertTrue(accepted_ack(r,10))
        for key in ('system','component','received_monotonic'):
            bad=copy.deepcopy(r); bad[key]=0
            self.assertFalse(accepted_ack(bad,10))
        r['message']['result']=1; self.assertFalse(accepted_ack(r,10))

    def test_height_gate_and_disabled_targets(self):
        r=self.reference(); p={**r['position'],'z':-2,'vz':0}; st=dict(arming_state=2,nav_state=4,failsafe=0)
        land=dict(landed=0,ground_contact=0); sp=dict(z=-2,vz=0,yaw=r['yaw'])
        self.assertTrue(entry_ok(p,st,land,sp,r))
        for z in (-1.49,-2.51): self.assertFalse(entry_ok({**p,'z':z},st,land,sp,r))
        self.assertFalse(entry_ok({**p,'vz':.2},st,land,sp,r))
        self.assertFalse(entry_ok(p,st,{**land,'ground_contact':1},sp,r))
        self.assertFalse(entry_ok(p,st,land,{**sp,'z':math.nan},r))

    def test_entry_contiguous_three_seconds(self):
        g=EntryGate()
        for i in range(13):
            t=1e6+i*250000
            done=g.update(t,True,dict(timestamp_sample=t,excitation_time=-12+i*.25))
            self.assertEqual(done,i==12)

    def test_entry_reset_gap_and_deadline(self):
        g=EntryGate()
        for i in range(20):
            t=1e6+i*250000
            done=g.update(t,i!=8,dict(timestamp_sample=t,excitation_time=-12+i*.25))
            self.assertFalse(done)
        for sample in (g.last,g.last-1,g.last+1000001):
            with self.assertRaises(ValueError): copy.deepcopy(g).update(sample,True,dict(timestamp_sample=sample,excitation_time=-7))
        g=EntryGate()
        for i in range(41): g.update(1e6+i*250000,False,dict(timestamp_sample=1e6+i*250000,excitation_time=-12+i*.25))
        with self.assertRaises(ValueError): g.update(11.25e6,True,dict(timestamp_sample=11.25e6,excitation_time=-1.75))

    def test_only_planned_landing_exact_gate_allowed(self):
        self.assertEqual(excitation_class(2,True,18,True,True,0),'expected_planned_landing_gate')
        for fault in (1,3,4,5,6,7,8):
            with self.assertRaises(ValueError): excitation_class(fault,True,18,True,True,0)
        for args in ((2,False,18,True,True,0),(2,True,4,True,True,0),
                     (2,True,18,False,True,0),(2,True,18,True,False,0),(2,True,18,True,True,.01)):
            with self.assertRaises(ValueError): excitation_class(*args)

    def invocation_data(self):
        d=test_v04.V04AnalysisTest().data(0); n=len(d['timestamp'])
        for k in ('first_fail','first_input','retry_result','excitation_fault'): d[k]=np.zeros(n,np.uint16)
        for group,field in enumerate(('p_sp','v_ff','a_ff','v','v_dot')):
            for axis in range(3):
                key=f'{field}[{axis}]'
                if key not in d: d[key]=np.zeros(n)
                d['first_input'] |= np.isfinite(d[key]).astype(np.uint16) << (3*group+axis)
        return d

    def test_first_input_nan_channels_valid(self):
        d=self.invocation_data(); self.assertEqual(check_first_invocation(d,np.ones(len(d['timestamp']),bool))['retries'],0)

    def test_first_failure_retry_missing_mask_reject(self):
        for key in ('first_fail','retry_result','first_input'):
            d=self.invocation_data(); d[key][50]+=1
            with self.assertRaises(ValueError): check_first_invocation(d,np.ones(len(d['timestamp']),bool))
        for key in ('first_fail','retry_result','first_input','excitation_fault'):
            d=self.invocation_data(); del d[key]
            with self.assertRaises(ValueError): check_first_invocation(d,np.ones(len(d['timestamp']),bool))

    def exit_data(self):
        t=np.arange(0,73e6,10000,dtype=np.uint64)
        d=dict(timestamp=t,armed=(t<72e6),excitation_fault=np.where((t>=65e6)&(t<72e6),2,0),excitation=np.zeros(len(t)))
        st=dict(timestamp=np.array([0,65e6]),nav_state=np.array([4,18]))
        ev=dict(takeoff_command=1e6,hover_start=4e6,hover_end=64e6,land_command=64e6,landed_disarmed=72e6)
        return d,st,ev

    def test_logged_landing_phase(self):
        d,s,e=self.exit_data(); self.assertEqual(check_excitation_exit(d,s,e)['raw_fault_counts']['2'],700)

    def test_early_exit_clock_fault_and_restart_reject(self):
        for t,f in ((3e6,2),(64.5e6,2),(66e6,3),(66e6,6),(72e6,2)):
            d,s,e=self.exit_data(); d['excitation_fault'][d['timestamp']==t]=f
            with self.assertRaises(ValueError): check_excitation_exit(d,s,e)
        d,s,e=self.exit_data(); s=dict(timestamp=np.array([0,65e6,67e6]),nav_state=np.array([4,18,4]))
        with self.assertRaises(ValueError): check_excitation_exit(d,s,e)

    def test_new_protocol_budget_and_unchanged_gates(self):
        p=json.loads((CONFIG/'protocol.json').read_text()); old=json.loads((CONFIG.parent/'protocol01/protocol.json').read_text())
        for key in p['inherit']['unchanged_fields']: self.assertEqual(p[key],old[key],key)
        self.assertEqual(len(p['jobs']),6); self.assertEqual(p['maximum_attempts'],6)
        self.assertEqual([(j['seed'],j['mode']) for j in p['jobs']],[(9201,0),(9201,1),(9202,0),(9202,1),(9203,0),(9203,1)])
        self.assertFalse(p['automatic_retry']); self.assertTrue(p['stop_on_any_required_failure'])

    def test_default_dryrun_has_no_side_effects(self):
        script=Path(__file__).with_name('run_v04_protocol03.py')
        out=Path('/tmp/V04-dryrun-MUST-NOT-BE-CREATED')
        self.assertFalse(out.exists())
        r=subprocess.run([sys.executable,str(script),'--output',str(out),'--source-head','dryrun'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr); self.assertIn('DRY RUN',r.stdout); self.assertFalse(out.exists())

    def test_real_production_excitation_trace(self):
        with tempfile.TemporaryDirectory(prefix='v04-trace-') as tmp:
            binary=str(Path(tmp)/'trace')
            repo=CONFIG.parents[3]
            compile_result=subprocess.run(['g++','-std=c++14','-I'+str(repo/'src/modules/mc_pos_control/PositionControl'),
                str(CONFIG/'ExcitationExitTrace.cpp'),'-o',binary],capture_output=True,text=True)
            self.assertEqual(compile_result.returncode,0,compile_result.stderr)
            r=subprocess.run([binary],capture_output=True,text=True); self.assertEqual(r.returncode,0)
            trace={line.split()[0]:(int(line.split()[1]),float(line.split()[2])) for line in r.stdout.splitlines()}
            self.assertEqual(trace['landing'],(2,0.)); self.assertEqual(trace['disarm'],(0,0.))
            self.assertEqual(excitation_class(*trace['landing'][:1],True,18,True,True,trace['landing'][1]),'expected_planned_landing_gate')
            for key in ('duplicate','controller'):
                with self.assertRaises(ValueError): excitation_class(trace[key][0],True,18,True,True,trace[key][1])

    def batch_fixture(self, fail_at=None, reject=False):
        import run_v04_protocol03 as runner
        with tempfile.TemporaryDirectory(prefix='v04-batch-test-') as tmp:
            root=Path(tmp); conf=root/'config'; conf.mkdir(); rootfs=root/'rootfs'; (rootfs/'eeprom').mkdir(parents=True)
            param=rootfs/'eeprom/parameters_10016'; param.write_bytes(b'original-full-eeprom')
            (root/'build/px4_sitl_default/src/lib/version').mkdir(parents=True)
            (root/'build/px4_sitl_default/src/lib/version/build_git_version.h').write_text('source-test')
            (root/'build/px4_sitl_default/parameters.json').write_text('{"parameters": []}')
            plugins=root/'plugins'; plugins.mkdir(); (plugins/'manifest.json').write_text('{}')
            p=json.loads((CONFIG/'protocol.json').read_text()); p['plugins']=str(plugins)
            p['artifacts']['new_run_root']=str(root/'series')
            (conf/'protocol.json').write_text(json.dumps(p)); (conf/'frozen.json').write_text('{"assets":{},"control_parameters":{}}')
            calls=[]
            def git(*args):
                return 'research/sta-velocity-control' if args[0]=='branch' else ('source-test' if args[0]=='rev-parse' else '')
            def flight(**kwargs):
                calls.append(kwargs['checks'].job)
                if fail_at==len(calls): raise RuntimeError('injected failure')
            def metrics(run,protocol,job):
                return dict(accepted=not reject,job=job,diagnostic=dict(error=dict(rmse=[.01]*3)),position_rmse=[.01]*3,yaw_rmse=.01)
            with patch.multiple(runner,REPO=root,ROOTFS=rootfs,CONFIG=conf,git=git,active_simulators=lambda:[],
                    digest=lambda path:'hash',persisted_bson=lambda data:{},check_parameters=lambda a,b:None,
                    encode_bson=lambda values,types:b'experiment-eeprom',flight=flight,analyze=metrics,
                    noise_prefix=lambda run:np.array([p['jobs'][int(run.name[3:])-1]['seed']],dtype=float),
                    fresh_seeds=lambda:dict(accepted=True)), \
                    patch.object(runner.socket,'socket'),patch.object(runner.shutil,'disk_usage',return_value=type('Space',(),{'free':20*1024**3})()), \
                    patch.object(sys,'argv',['runner','--execute','--output',str(root/'series'),'--source-head','source-test']),redirect_stdout(io.StringIO()):
                if fail_at or reject:
                    with self.assertRaises(RuntimeError): runner.main()
                else: runner.main()
            ledger=json.loads((root/'series/ledger.json').read_text())
            self.assertEqual(param.read_bytes(),b'original-full-eeprom')
            self.assertTrue(ledger['parameter_restore_exact'])
            return len(calls),ledger

    def test_batch_six_only_and_exact_parameter_restore(self):
        count,ledger=self.batch_fixture(); self.assertEqual(count,6); self.assertTrue(ledger['success'])
        self.assertEqual(len(ledger['pairs']),3)

    def test_batch_first_failure_stops_without_retry(self):
        for fail in (1,2):
            count,ledger=self.batch_fixture(fail_at=fail); self.assertEqual(count,fail); self.assertFalse(ledger['success'])
        count,ledger=self.batch_fixture(reject=True); self.assertEqual(count,1); self.assertFalse(ledger['success'])

    def height_fixture(self, failure=None):
        with tempfile.TemporaryDirectory(prefix='v04-height-test-') as tmp:
            run=Path(tmp); ref=self.reference(); ref['position']['timestamp']=0; ref['position']['timestamp_sample']=0
            (run/'height_reference.json').write_text(json.dumps(ref))
            (run/'reposition_command.json').write_text(json.dumps(dict(sent_monotonic=10)))
            (run/'reposition_ack.json').write_text(json.dumps(dict(received_monotonic=11,system=1,component=1,message=dict(command=192,result=0))))
            text='\n\tcurrent position_setpoint_s\n\tlat: 47.123456\n\tlon: 8\n\talt: {alt}\n\tyaw: 1.5708\n\tvalid: True\n\tyaw_valid: True\n\tnext position_setpoint_s\n'
            (run/'triplet_before.txt').write_text(text.format(alt=488)); (run/'triplet_after.txt').write_text(text.format(alt=490))
            t=np.arange(0,73e6,10000,dtype=np.uint64); n=len(t)
            pos={k:np.full(n,v) for k,v in ref['position'].items()}; pos.update(timestamp=t,timestamp_sample=t,z=np.full(n,-2.),vz=np.zeros(n))
            traj=dict(timestamp=t,z=np.full(n,-2.),vz=np.zeros(n),yaw=np.full(n,1.5708))
            trip=dict(timestamp=np.array([0,3.1e6]))
            for k,v in dict(lat=47.123456123,lon=8.,alt=490.,yaw=1.5708,valid=1,yaw_valid=1).items(): trip['current.'+k]=np.full(2,v)
            trip['current.alt'][0]=488
            cmd={k:np.array([v]) for k,v in dict(timestamp=3e6,command=192,param1=-1,param2=1,param3=0,param4=1.5708,
                param5=np.nan,param6=np.nan,param7=490.,target_system=1,target_component=1,source_system=255,source_component=190).items()}
            tables=dict(vehicle_command=cmd,vehicle_command_ack=dict(timestamp=np.array([3.01e6]),command=np.array([192]),result=np.array([0])),
                position_setpoint_triplet=trip,vehicle_local_position=pos,trajectory_setpoint=traj,
                vehicle_status=dict(timestamp=t,arming_state=np.full(n,2),nav_state=np.full(n,4),failsafe=np.zeros(n)),
                vehicle_land_detected=dict(timestamp=t,landed=np.zeros(n),ground_contact=np.zeros(n)))
            class Log:
                def get_dataset(self,name): return type('Dataset',(),{'data':tables[name]})()
            d=dict(timestamp=t,timestamp_sample=t,excitation_time=t.astype(float)*1e-6-16,**{'p_sp[2]':np.full(n,-2.)})
            ev=dict(takeoff_command=1e6,hover_start=7e6,hover_end=67e6,landed_disarmed=72e6)
            if failure: failure(tables,d,ev)
            return height_evidence(Log(),run,d,ev)

    def test_offline_height_and_complete_window(self):
        self.assertEqual(self.height_fixture()['ready_after_gate_s'],3.)

    def test_offline_height_rejects_missing_and_wrong_evidence(self):
        changes=[lambda x,d,e:x['trajectory_setpoint']['z'].__setitem__(500,np.nan),
                 lambda x,d,e:x['vehicle_local_position']['vz'].__setitem__(500,.21),
                 lambda x,d,e:x['vehicle_local_position']['z_reset_counter'].__setitem__(500,1),
                 lambda x,d,e:x['vehicle_command_ack']['result'].__setitem__(0,1),
                 lambda x,d,e:x['position_setpoint_triplet']['current.lat'].__setitem__(1,48),
                 lambda x,d,e:d['p_sp[2]'].__setitem__(1000,np.nan),
                 lambda x,d,e:e.__setitem__('hover_end',40e6)]
        for change in changes:
            with self.assertRaises(ValueError): self.height_fixture(change)


if __name__=='__main__': unittest.main()
