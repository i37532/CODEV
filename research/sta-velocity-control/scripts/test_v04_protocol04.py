"""Offline synthetic streams and real recorded ULog; zero simulated flights."""
import copy
import io
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
import numpy as np
from pyulog import ULog
from v04_heading_stream import (LiveLog, complete_prefix, replay, data, row, index,
                                 REFERENCE, FORBIDDEN_EVENTS)
from v04_task04 import freeze_reference
from v04_protocol04 import CONFIG, REPO, TOKEN, load_protocol, require_authorization


class Log:
    dropouts=[]
    def __init__(self,tables): self.tables=tables
    def get_dataset(self,name,instance=0):
        return type('Dataset',(),{'data':self.tables[(name,instance)]})()


def fixture():
    t=np.arange(1000000,4010000,10000,dtype=np.uint64); n=len(t)
    def table(**values):
        return dict(timestamp=t.copy(),**{k:np.full(n,v) for k,v in values.items()})
    p=table(timestamp_sample=0,x=0.,y=0.,z=-1.6,vz=0.,heading=1.,delta_heading=.01,
        heading_reset_counter=2,xy_valid=1,z_valid=1,v_xy_valid=1,v_z_valid=1,xy_global=1,z_global=1,
        **{k:0 for k in REFERENCE})
    p['ref_alt']=np.full(n,488.);p['timestamp_sample']=t.copy();p['z'][0]=0.
    p['heading_reset_counter'][t>=1500000]=3
    a=table(quat_reset_counter=2,**{'delta_q_reset[0]':math.cos(.005),'delta_q_reset[1]':0.,
        'delta_q_reset[2]':0.,'delta_q_reset[3]':math.sin(.005)})
    a['quat_reset_counter'][t>=1510000]=3
    selector=table(primary_instance=1,instance_changed_count=2,gyro_fault_detected=0,
                   accel_fault_detected=0,**{'healthy[1]':1})
    flags=table(cs_mag_aligned_in_flight=0,cs_yaw_align=1,cs_mag_fault=0,cs_mag_field_disturbed=0,
                cs_ev_yaw=0,cs_gps_yaw=0,fs_bad_hdg=0)
    flags['cs_mag_aligned_in_flight'][t>=1500000]=1
    status=table(nav_state=17,arming_state=2,failsafe=0,failure_detector_status=0)
    status['arming_state'][0]=1;status['nav_state'][t>=1700000]=2
    land=table(landed=0,ground_contact=0);land['landed'][0]=1;land['ground_contact'][0]=1
    diag=table(publish_seq=0,update_seq=0,enabled=1,armed=1,first_fail=0,retry_result=0,
        fault=0,failsafe=0,timing=0,valid=1,pid_calls=1,sta_fault=0,inner_mode=0,inner_axes=0,
        inner_divisor=1,inner_valid=1,excitation=0.)
    diag['publish_seq']=np.arange(n);diag['update_seq']=np.arange(n)
    diag['input_timestamp']=t.copy();diag['timestamp_sample']=t.copy()
    ev={k:np.array([0]) for k in FORBIDDEN_EVENTS}
    ev.update(timestamp=np.array([900000],np.uint64),information_event_changes=np.array([3]),warning_event_changes=np.array([0]))
    tables={('vehicle_local_position',0):p,('vehicle_attitude',0):a,
        ('trajectory_setpoint',0):table(yaw=1.),('estimator_selector_status',0):selector,
        ('estimator_status',1):table(filter_fault_flags=0),('estimator_status_flags',1):flags,
        ('estimator_event_flags',1):ev,('vehicle_status',0):status,('vehicle_land_detected',0):land,
        ('sta_velocity_ctrl_status',0):diag}
    return Log(tables),freeze_reference(row(p,0))


def binary_fixture(log):
    """Actual binary ULog with all fixture topic instances, not a mocked parser."""
    def msg(k,v): return struct.pack('<HB',len(v),ord(k))+v
    blob=bytearray(ULog.HEADER_BYTES+b'\x01'+struct.pack('<Q',0))
    records=[]
    for ident,((name,instance),d) in enumerate(log.tables.items(),1):
        # Float64 preserves these offline test values; real replay separately tests float32 production.
        fields=[f'double {k};' for k in d]
        blob.extend(msg('F',(name+':'+''.join(fields)).encode()))
        records.append((ident,name,instance,d))
    for ident,name,instance,d in records:
        blob.extend(msg('A',struct.pack('<BH',instance,ident)+name.encode()))
    messages=[]
    for ident,name,instance,d in records:
        for i,t in enumerate(d['timestamp']):
            payload=struct.pack('<H',ident)+struct.pack('<'+'d'*len(d),*(float(v[i]) for v in d.values()))
            messages.append((int(t),msg('D',payload)))
    for _,record in sorted(messages,key=lambda x:x[0]): blob.extend(record)
    return bytes(blob)


class Protocol04Test(unittest.TestCase):
    def test_positive_complete_alignment_and_exact_freeze(self):
        log,ref=fixture();r=replay(log,ref);self.assertTrue(r['ready'])
        self.assertEqual(r['packet']['quat_pair_offset_s'],.01)
        self.assertEqual(replay(log,ref,frozen=r['freeze_candidate'])['freeze_candidate']['yaw'],1.)

    def test_negative_zero_and_wrapped_counter(self):
        for delta in (-.01,0.,math.radians(5)):
            log,ref=fixture();p=data(log,'vehicle_local_position');a=data(log,'vehicle_attitude')
            p['delta_heading'][:]=delta;a['delta_q_reset[0]'][:]=math.cos(delta/2);a['delta_q_reset[3]'][:]=math.sin(delta/2)
            p['heading_reset_counter']=np.where(p['timestamp']<1500000,255,0)
            a['quat_reset_counter']=np.where(a['timestamp']<1510000,255,0)
            ref=freeze_reference(row(p,0));self.assertTrue(replay(log,ref)['ready'])

    def test_pending_does_not_borrow_future_flags(self):
        log,ref=fixture();self.assertTrue(replay(log,ref,end=1500000,allow_pending=True)['pending'])
        self.assertFalse(replay(log,ref,end=1510000,allow_pending=True)['ready'])
        with self.assertRaises(ValueError): replay(log,ref,end=1500000)

    def test_no_alignment_no_admission_and_late_flags_fail(self):
        log,ref=fixture();data(log,'vehicle_local_position')['heading_reset_counter'][:]=2
        data(log,'vehicle_attitude')['quat_reset_counter'][:]=2
        self.assertFalse(replay(log,ref)['ready'])
        log,ref=fixture();data(log,'estimator_status_flags',1)['cs_mag_aligned_in_flight'][:]=0
        with self.assertRaises(ValueError): replay(log,ref,allow_pending=True)

    def test_wrong_primary_and_return_switch_rejected(self):
        for key,value in [('primary_instance',2),('instance_changed_count',4),('healthy[1]',0),('gyro_fault_detected',1)]:
            log,ref=fixture();data(log,'estimator_selector_status')[key][100]=value
            with self.subTest(key=key),self.assertRaises(ValueError): replay(log,ref)

    def test_coordinate_counters_never_rebased(self):
        for k in REFERENCE:
            log,ref=fixture();data(log,'vehicle_local_position')[k][100]+=1
            with self.subTest(k=k),self.assertRaises(ValueError): replay(log,ref)

    def test_second_heading_and_unpaired_quaternion(self):
        for name,key in [('vehicle_local_position','heading_reset_counter'),('vehicle_attitude','quat_reset_counter')]:
            log,ref=fixture();data(log,name)[key][200:]+=1
            with self.assertRaises(ValueError): replay(log,ref)

    def test_counter_jump_and_quaternion_disagreement(self):
        for name,key,value in [('vehicle_local_position','heading_reset_counter',5),('vehicle_attitude','delta_q_reset[3]',-.005)]:
            log,ref=fixture();data(log,name)[key][51:]=value
            with self.assertRaises(ValueError): replay(log,ref)

    def test_failed_estimator_and_first_control_call_rejected(self):
        for name,instance,key in [('estimator_status',1,'filter_fault_flags'),('estimator_status_flags',1,'cs_mag_fault'),
            ('estimator_status_flags',1,'fs_bad_hdg'),('sta_velocity_ctrl_status',0,'first_fail'),
            ('sta_velocity_ctrl_status',0,'retry_result'),('sta_velocity_ctrl_status',0,'inner_mode')]:
            log,ref=fixture();data(log,name,instance)[key][100]=1
            with self.assertRaises(ValueError): replay(log,ref)

    def test_raw_missing_samples_and_diagnostic_sequence_fail(self):
        log,ref=fixture();p=data(log,'vehicle_local_position');p['timestamp_sample'][90]+=50000
        with self.assertRaises(ValueError): replay(log,ref)
        log,ref=fixture();data(log,'sta_velocity_ctrl_status')['publish_seq'][100:]+=1
        with self.assertRaises(ValueError): replay(log,ref)

    def test_event_only_old_snapshot_allowed_new_gap_or_emergency_rejected(self):
        log,ref=fixture();self.assertTrue(replay(log,ref)['ready'])
        for key,value in [('information_event_changes',5),('emergency_yaw_reset_mag_stopped',1)]:
            log,ref=fixture();ev=data(log,'estimator_event_flags',1)
            for k,v in ev.items(): ev[k]=np.r_[v,v]
            ev['timestamp'][1]=1600000;ev[key][1]=value
            with self.assertRaises(ValueError): replay(log,ref)

    def test_missing_consumed_position_and_clock_mismatch_reject(self):
        log,ref=fixture();p=data(log,'vehicle_local_position')
        log.tables[('vehicle_local_position',0)]={k:np.delete(v,60) for k,v in p.items()}
        with self.assertRaises(ValueError): replay(log,ref)
        log,ref=fixture();data(log,'sta_velocity_ctrl_status')['timestamp_sample'][60]+=1
        with self.assertRaises(ValueError): replay(log,ref)

    def test_missing_metadata_not_treated_as_zero(self):
        for key in [('estimator_status',1),('estimator_event_flags',1),('estimator_status_flags',1)]:
            log,ref=fixture();del log.tables[key]
            with self.assertRaises(KeyError): replay(log,ref)

    def test_fabricated_ground_or_prearm_heading_rejected(self):
        for k in ('z','heading','timestamp_sample','heading_reset_counter'):
            log,ref=fixture();ref['position'][k]+=1
            with self.assertRaises(ValueError): replay(log,ref)

    def test_stale_selector_or_periodic_metadata_rejected(self):
        for key in [('estimator_selector_status',0),('estimator_status',1),('estimator_status_flags',1)]:
            log,ref=fixture();d=log.tables[key]
            log.tables[key]={k:v[:1] for k,v in d.items()}
            with self.assertRaises(ValueError): replay(log,ref)

    def test_quiet_break_resets_timer_no_freeze_before_one_second(self):
        log,ref=fixture();data(log,'vehicle_land_detected')['ground_contact'][-50]=1
        self.assertFalse(replay(log,ref)['ready'])
        log,ref=fixture();data(log,'trajectory_setpoint')['yaw'][-50]=2.
        self.assertFalse(replay(log,ref)['ready'])

    def test_fabricated_freeze_and_reset_after_freeze_rejected(self):
        log,ref=fixture();f=replay(log,ref)['freeze_candidate'];f['yaw']+=.01
        with self.assertRaises(ValueError): replay(log,ref,frozen=f)
        f['timestamp']=1400000
        with self.assertRaises(ValueError): replay(log,ref,frozen=f)

    def test_binary_partial_tail_and_incremental_decoder(self):
        log,ref=fixture();raw=binary_fixture(log)
        with tempfile.TemporaryDirectory(prefix='v04-raw-tail-') as tmp:
            p=Path(tmp)/'synthetic.ulg';p.write_bytes(raw[:-13]);live=LiveLog(p)
            live.read()
            with p.open('ab') as stream: stream.write(raw[-13:])
            decoded=live.read();self.assertTrue(replay(decoded,ref)['ready'])
            independent=ULog(io.BytesIO(raw))
            for topic,instance in log.tables:
                for k,v in data(independent,topic,instance).items():
                    np.testing.assert_array_equal(v,data(decoded,topic,instance)[k])
            self.assertEqual(complete_prefix(raw[:-13]),raw[:len(complete_prefix(raw[:-13]))])

    def test_tail_rejects_truncate_dropout_and_bad_header(self):
        log,_=fixture();raw=binary_fixture(log)
        with tempfile.TemporaryDirectory(prefix='v04-tail-bad-') as tmp:
            p=Path(tmp)/'x.ulg';p.write_bytes(raw);live=LiveLog(p);live.read();p.write_bytes(raw[:100])
            with self.assertRaises(ValueError): live.read()
        with self.assertRaises(ValueError): complete_prefix(b'bad-header')
        with self.assertRaises(ValueError): complete_prefix(raw+struct.pack('<HBH',2,ord('O'),1))

    def test_real_failed_run_is_classifiable_but_not_quiet_or_accepted(self):
        record=json.loads((CONFIG.parent/'results03/run01.json').read_text())
        live=LiveLog(record['logs'][-1]['archive']);log=live.read()
        t=next(e['timestamp_us'] for e in record['events'] if e['name']=='takeoff_command')
        p=data(log,'vehicle_local_position');ref=freeze_reference(row(p,index(p,t)))
        r=replay(log,ref);self.assertTrue(r['confirmed']);self.assertFalse(r['ready'])
        self.assertFalse(record['success'])

    def test_real_ulog_chunked_replay_matches_independent_decoder(self):
        from v04_heading_stream import TOPICS
        record=json.loads((CONFIG.parent/'results03/run01.json').read_text())
        raw=Path(record['logs'][-1]['archive']).read_bytes()
        with tempfile.TemporaryDirectory(prefix='v04-real-tail-') as tmp:
            path=Path(tmp)/'copy.ulg';path.write_bytes(raw[:1000000]);live=LiveLog(path);live.read()
            for begin in range(1000000,len(raw),1000000):
                with path.open('ab') as stream:stream.write(raw[begin:begin+1000000])
                decoded=live.read()
            independent=ULog(io.BytesIO(raw))
            for ds in independent.data_list:
                if ds.name not in TOPICS:continue
                actual=data(decoded,ds.name,ds.multi_id)
                for k,v in ds.data.items():np.testing.assert_array_equal(actual[k],v)

    def test_dryrun_and_missing_authorization_have_no_side_effects(self):
        from run_v04_flight04 import main
        with self.assertRaises(RuntimeError): main()
        with self.assertRaises(RuntimeError): require_authorization('',load_protocol())
        with tempfile.TemporaryDirectory(prefix='v04-dry-') as tmp:
            out=Path(tmp)/'not-created'
            args=[sys.executable,str(Path(__file__).with_name('run_v04_protocol04.py')),
                  '--output',str(out),'--source-head','not-a-source']
            p=subprocess.run(args,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr);self.assertFalse(out.exists())
            p=subprocess.run(args+['--execute'],capture_output=True,text=True)
            self.assertNotEqual(p.returncode,0);self.assertFalse(out.exists())

    def test_exact_new_jobs_and_inherited_numerical_limits(self):
        p=load_protocol();old=json.loads((CONFIG.parent/'protocol03/protocol.json').read_text())
        self.assertEqual([(j['seed'],j['mode']) for j in p['jobs']],[(9301,0),(9301,1),(9302,0),(9302,1),(9303,0),(9303,1)])
        for k in ('candidate','bounds','pair_gate','data_gate','diagnostic_gate','additional_log_gates'):
            self.assertEqual(p[k],old[k])
        self.assertFalse(p['flight_authorized']);self.assertFalse(p['automatic_retry'])

    def test_shutdown_only_owned_group_and_escalation(self):
        from run_v04_flight04 import shutdown_owned
        from unittest.mock import Mock
        proc=Mock(pid=12345);proc.poll.return_value=None
        proc.wait.side_effect=[subprocess.TimeoutExpired('owned',15),subprocess.TimeoutExpired('owned',15),0]
        with patch('run_v04_flight04.os.getpgid',return_value=12345),patch('run_v04_flight04.os.killpg') as kill:
            shutdown_owned(proc,Mock());self.assertEqual(kill.call_count,2)
            self.assertTrue(all(call.args[0]==12345 for call in kill.call_args_list))
        proc.wait.side_effect=[subprocess.TimeoutExpired('owned',15)]
        with patch('run_v04_flight04.os.getpgid',return_value=77),patch('run_v04_flight04.os.killpg') as kill:
            with self.assertRaises(RuntimeError): shutdown_owned(proc,Mock())
            kill.assert_not_called()

    def test_environment_setup_failure_closes_link_without_launch(self):
        import run_v04_flight04 as flight
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory(prefix='v04-setup-fault-') as tmp:
            root=Path(tmp);checks=Mock(execution_permitted=True,simulation_speed=1)
            checks.prepare_environment.side_effect=RuntimeError('injected setup error')
            with patch.multiple(flight,ROOTFS=root,REPO=root,active_simulators=lambda:[],digest=lambda p:'hash'), \
                patch.object(flight.subprocess,'check_output',side_effect=lambda *a,**k:'source-test' if k.get('text') else b''), \
                patch.object(flight.subprocess,'Popen') as launch, \
                patch.object(flight.mavutil,'mavlink_connection') as connection, \
                patch.object(flight.threading,'Thread') as worker, \
                patch.object(sys,'argv',['runner','--output',str(root/'output')]):
                with self.assertRaisesRegex(RuntimeError,'injected setup'):flight.main(checks=checks)
                launch.assert_not_called();connection.return_value.close.assert_called_once()
                worker.return_value.join.assert_called_once()

    def height_fixture04(self,mutation=None):
        from analyze_v04_protocol04 import height_evidence
        log,ref=fixture()
        # Extend the explicit synthetic fixture through loiter and planned landing.
        for key,table in list(log.tables.items()):
            if key==('estimator_event_flags',1): continue
            t=np.arange(1000000,73010000,10000,dtype=np.uint64)
            n=len(t);old=len(table['timestamp'])
            log.tables[key]={k:np.r_[v,np.full(n-old,v[-1],dtype=v.dtype)] for k,v in table.items()}
            log.tables[key]['timestamp']=t.copy()
        pos=data(log,'vehicle_local_position');t=pos['timestamp'];n=len(t)
        pos['timestamp_sample']=t.copy();pos['z'][t>=3000000]=-2.5
        status=data(log,'vehicle_status');status['nav_state'][t>=3000000]=4;status['nav_state'][t>=67000000]=18
        status['arming_state'][t>=72000000]=1
        land=data(log,'vehicle_land_detected');land['landed'][t>=72000000]=1;land['ground_contact'][t>=72000000]=1
        d=data(log,'sta_velocity_ctrl_status');d['publish_seq']=np.arange(n);d['update_seq']=np.arange(n)
        d['timestamp_sample']=t.copy();d['input_timestamp']=t.copy();d['excitation_time']=t.astype(float)/1e6-15
        d['p_sp[2]']=np.full(n,-2.5)
        target=data(log,'trajectory_setpoint');target.update(z=np.full(n,-2.5),vz=np.zeros(n))
        frozen=replay(log,ref,end=2800000)['freeze_candidate']
        command=dict(timestamp=3000000,command=192,param1=-1,param2=1,param3=0,param4=1.,param7=490.5,
            target_system=1,target_component=1,source_system=255,source_component=190,param5=np.nan,param6=np.nan)
        log.tables[('vehicle_command',0)]={k:np.array([v]) for k,v in command.items()}
        log.tables[('vehicle_command_ack',0)]={k:np.array([v]) for k,v in dict(timestamp=3010000,command=192,result=0).items()}
        trip={'timestamp':np.array([1000000,3020000])}
        for k,v in dict(lat=47.1,lon=8.,alt=490.5,yaw=1.,valid=1,yaw_valid=1).items():trip['current.'+k]=np.full(2,v)
        trip['current.alt'][0]=488.;log.tables[('position_setpoint_triplet',0)]=trip
        ev=dict(takeoff_command=1010000,reposition_command=3000000,hover_start=7000000,
                hover_end=67000000,land_command=67000000,landed_disarmed=72000000)
        with tempfile.TemporaryDirectory(prefix='v04-height04-') as tmp:
            out=Path(tmp)
            for name,value in [('height_reference',ref),('task_yaw',frozen),('reposition_command',dict(sent_monotonic=10)),
                ('reposition_ack',dict(received_monotonic=11,system=1,component=1,message=dict(command=192,result=0)))]:
                (out/(name+'.json')).write_text(json.dumps(value))
            text='\n\tcurrent position_setpoint_s\n\tlat: 47.1\n\tlon: 8\n\talt: {alt}\n\tyaw: 1\n\tvalid: True\n\tyaw_valid: True\n\tnext position_setpoint_s\n'
            (out/'triplet_before.txt').write_text(text.format(alt=488));(out/'triplet_after.txt').write_text(text.format(alt=490.5))
            if mutation:mutation(log,ref,ev,out)
            return height_evidence(log,out,d,ev)

    def test_full_synthetic_heading_height_and_observation_chain(self):
        r=self.height_fixture04();self.assertEqual(r['ready_after_gate_s'],4.)
        self.assertTrue(r['heading']['confirmed']);self.assertEqual(r['entry_samples'],301)

    def test_full_chain_rejects_later_reset_wrong_target_and_outside_window(self):
        changes=[lambda u,r,e,o:data(u,'vehicle_local_position')['heading_reset_counter'].__setitem__(-200,4),
            lambda u,r,e,o:data(u,'trajectory_setpoint')['yaw'].__setitem__(500,1.1),
            lambda u,r,e,o:e.__setitem__('hover_end',40000000)]
        for change in changes:
            with self.assertRaises(ValueError):self.height_fixture04(change)

    def test_logged_disabled_samples_keep_publication_but_do_not_integrate(self):
        log,ref=fixture();d=data(log,'sta_velocity_ctrl_status')
        d['enabled'][-10:]=0;d['armed'][-10:]=0;d['pid_calls'][-10:]=0
        d['update_seq'][-10:]=d['update_seq'][-11]
        self.assertTrue(replay(log,ref)['ready'])
        d['update_seq'][-1]+=1
        with self.assertRaises(ValueError): replay(log,ref)

    def test_numerical_core_matches_old_enabled_pid_esta_and_rejects_wrong_mode(self):
        from analyze_v04_core04 import check_diagnostic
        from analyze_v04 import check_diagnostic as old
        from test_v04 import V04AnalysisTest
        for mode in (0,1):
            d=V04AnalysisTest().data(mode);start=d['timestamp'][0];end=d['timestamp'][-1]+10000
            self.assertEqual(check_diagnostic(d,start,end,mode),old(d,start,end,mode))
            with self.assertRaises(ValueError): check_diagnostic(d,start,end,1-mode)

    def test_disabled_numerical_core_enforces_zero_calls_without_zero_fill(self):
        from analyze_v04_core04 import check_diagnostic
        from test_v04 import V04AnalysisTest
        d=V04AnalysisTest().data(0)
        d['enabled'][-10:]=0;d['pid_calls'][-10:]=0;d['update_seq'][-10:]=d['update_seq'][-11]
        check_diagnostic(d,d['timestamp'][0],d['timestamp'][-1]+10000,0,False)
        d['pid_calls'][-1]=1
        with self.assertRaises(ValueError): check_diagnostic(d,d['timestamp'][0],d['timestamp'][-1]+10000,0,False)


    def batch_fixture(self, fail_at=None, reject=False):
        import run_v04_protocol04 as runner
        with tempfile.TemporaryDirectory(prefix='v04-batch-test-') as tmp:
            root=Path(tmp); conf=root/'config'; conf.mkdir(); rootfs=root/'rootfs'; (rootfs/'eeprom').mkdir(parents=True)
            param=rootfs/'eeprom/parameters_10016'; param.write_bytes(b'original-full-eeprom')
            (root/'build/px4_sitl_default/src/lib/version').mkdir(parents=True)
            (root/'build/px4_sitl_default/src/lib/version/build_git_version.h').write_text('source-test')
            (root/'build/px4_sitl_default/parameters.json').write_text('{"parameters": []}')
            plugins=root/'plugins'; plugins.mkdir(); (plugins/'manifest.json').write_text('{}')
            p=load_protocol();p['execution_ready']=True;p['plugins']=str(plugins)
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
                    fresh_seeds=lambda:dict(accepted=True),load_protocol=lambda:p), \
                    patch.object(runner.socket,'socket'),patch.object(runner.shutil,'disk_usage',return_value=type('Space',(),{'free':20*1024**3})()), \
                    patch.object(sys,'argv',['runner','--authorization',TOKEN,'--execute','--output',str(root/'series'),'--source-head','source-test']),redirect_stdout(io.StringIO()):
                if fail_at or reject:
                    with self.assertRaises(RuntimeError): runner.main()
                else: runner.main()
            ledger=json.loads((root/'series/ledger.json').read_text())
            self.assertEqual(param.read_bytes(),b'original-full-eeprom')
            self.assertTrue(ledger['parameter_restore_exact'])
            return len(calls),ledger

    def test_protocol04_batch_six_only_and_exact_parameter_restore(self):
        count,ledger=self.batch_fixture(); self.assertEqual(count,6); self.assertTrue(ledger['success'])
        self.assertEqual(len(ledger['pairs']),3)

    def test_batch_first_failure_stops_without_retry(self):
        for fail in (1,2):
            count,ledger=self.batch_fixture(fail_at=fail); self.assertEqual(count,fail); self.assertFalse(ledger['success'])
        count,ledger=self.batch_fixture(reject=True); self.assertEqual(count,1); self.assertFalse(ledger['success'])

if __name__=='__main__': unittest.main()
