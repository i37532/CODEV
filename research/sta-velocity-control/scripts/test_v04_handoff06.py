"""Real failed ULog + exact ECL/MAVLink codecs + synthetic handoff lifecycle.

No simulator. Synthetic command responses are not claimed as flight evidence.
"""
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
from pyulog import ULog
from pymavlink.dialects.v20 import common as mavlink
from v04_handoff06 import capture, reproject, project, Handoff, matches_target, decode_current
from v04_heading_stream import data, replay
from v04_protocol05 import REPO, CONFIG
from v04_task04 import current_triplet
from test_v04_protocol04 import fixture


def setup_log():
    log, ref = fixture()
    t = data(log, 'trajectory_setpoint')
    n = len(t['timestamp'])
    t.update(x=np.full(n,.15), y=np.full(n,-.2), z=np.full(n,np.nan), vz=np.zeros(n))
    frozen = replay(log,ref)['freeze_candidate']
    return log, ref, frozen


def cli(target, timestamp=4100000, valid=True, **changes):
    w = target['wire']
    d = dict(timestamp=timestamp,valid=int(valid),type=2,lat=target['lat'],lon=target['lon'],
             alt=w['z'],yaw=w['param4'],yaw_valid=1)
    d.update(changes)
    lines=[]
    for k,v in d.items():
        if k in ('lat','lon'): text=f'{v:.6f}'
        elif k in ('alt','yaw'): text=f'{v:.4f}'
        else: text=str(v)
        lines.append('\t'+k+': '+text)
    return '\n\tcurrent position_setpoint_s\n'+'\n'.join(lines)+'\n\tnext position_setpoint_s\n'


def ack(wall=11.,result=0,system=1,component=1):
    return dict(received_monotonic=wall,system=system,component=component,message=dict(command=192,result=result))


class Handoff06Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record=json.loads((CONFIG.parent/'results05/run01.json').read_text())
        cls.path=Path(cls.record['logs'][-1]['archive'])
        if hashlib.sha256(cls.path.read_bytes()).hexdigest()!=cls.record['logs'][-1]['sha256']:
            raise ValueError('Original ULog changed')
        cls.real=ULog(str(cls.path))
        cls.ref=json.loads((cls.path.parent/'height_reference.json').read_text())
        cls.frozen=json.loads((cls.path.parent/'task_yaw.json').read_text())

    def test_real_posctl_invalid_triplet_no_longer_used_as_source(self):
        with self.assertRaisesRegex(ValueError,'Invalid navigator target'):
            current_triplet((self.path.parent/'triplet_before.txt').read_text())
        t=capture(self.real,self.ref,self.frozen,38096000)
        self.assertLess(t['encoding_error_m'],.02)
        self.assertTrue(all(math.isfinite(x) for x in t['source_xy']))
        self.assertFalse(self.record['success'])
        np.testing.assert_array_equal(t['source_xy'],[-.013065318576991558,.03298546001315117])

    def test_real_replay_wire_is_int_not_float_coordinates(self):
        t=capture(self.real,self.ref,self.frozen,38096000)
        stream=io.BytesIO(); mav=mavlink.MAVLink(stream,srcSystem=255,srcComponent=190)
        h=Handoff();h.start(mav,self.real,self.ref,self.frozen,38096000,10.)
        decoder=mavlink.MAVLink(None);msg=decoder.parse_char(stream.getvalue())
        self.assertEqual(msg.get_type(),'COMMAND_INT');self.assertEqual(msg.frame,5)
        self.assertEqual((msg.x,msg.y),(t['wire']['x'],t['wire']['y']))
        self.assertEqual(msg.param4,t['wire']['param4']);self.assertEqual(msg.z,t['wire']['z'])
        self.assertEqual((msg.get_srcSystem(),msg.get_srcComponent()),(255,190))

    def test_capture_preserves_reference_and_target_not_actual_position(self):
        log,ref,frozen=setup_log();before=copy.deepcopy(ref)
        t=capture(log,ref,frozen,4000000)
        self.assertEqual(ref,before);self.assertEqual(t['source_xy'],[.15,-.2])
        self.assertEqual(t['reference']['x'],0.)
        self.assertEqual(t['wire']['z'],490.5)

    def test_mixed_z_velocity_legal_but_missing_all_vertical_invalid(self):
        log,ref,frozen=setup_log();capture(log,ref,frozen,4000000)
        data(log,'trajectory_setpoint')['vz'][:]=np.nan
        with self.assertRaises(ValueError):capture(log,ref,frozen,4000000)

    def test_missing_half_xy_nonfinite_or_outside_target_rejected(self):
        for field,value in [('x',np.nan),('y',np.inf),('x',3.)]:
            log,ref,frozen=setup_log();data(log,'trajectory_setpoint')[field][-1]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):capture(log,ref,frozen,4000000)

    def test_no_heading_gate_source_future_stale_and_target_stale_reject(self):
        log,ref,frozen=setup_log()
        for now in (3999999,4500001):
            with self.assertRaises(ValueError):capture(log,ref,frozen,now)
        wrong=copy.deepcopy(frozen);wrong['yaw']+=.01
        with self.assertRaises(ValueError):capture(log,ref,wrong,4000000)
        target=data(log,'trajectory_setpoint');log.tables[('trajectory_setpoint',0)]={k:v[:-10] for k,v in target.items()}
        with self.assertRaises(ValueError):capture(log,ref,frozen,4000000)

    def test_reference_changes_and_posctl_exit_never_allowed(self):
        for name,key,value in [('vehicle_local_position','ref_lat',1.),('vehicle_status','nav_state',4),
                               ('vehicle_land_detected','ground_contact',1)]:
            log,ref,frozen=setup_log();data(log,name)[key][-1]=value
            with self.subTest(key=key),self.assertRaises(ValueError):capture(log,ref,frozen,4000000)

    def test_projection_domain_nonfinite_and_cardinal_directions(self):
        for north,east in [(1,0),(-1,0),(0,1),(0,-1),(0,0)]:
            lat,lon=reproject(47.,8.,north,east)
            np.testing.assert_allclose(project(47.,8.,lat,lon),(north,east),atol=1e-6)
        for vals in [(90,0,0,0),(0,181,0,0),(0,0,np.nan,0),(0,0,10001,0)]:
            with self.assertRaises(ValueError):reproject(*vals)

    def make_started(self):
        log,ref,frozen=setup_log();h=Handoff();mav=Mock()
        h.start(mav,log,ref,frozen,4000000,10.)
        return h,mav

    def test_full_pending_ack_target_join_and_single_send(self):
        h,mav=self.make_started()
        self.assertFalse(h.poll(10.1,[],cli(h.target,valid=False,lat=np.nan,lon=np.nan),2))
        self.assertFalse(h.poll(10.2,[ack(10.15)],cli(h.target,alt=489.),4))
        self.assertTrue(h.poll(10.3,[ack(10.15)],cli(h.target),4))
        self.assertTrue(h.poll(11.,[ack(10.15)],cli(h.target),4))
        mav.command_int_send.assert_called_once();mav.command_long_send.assert_not_called()
        log,ref,frozen=setup_log()
        with self.assertRaises(ValueError):h.start(mav,log,ref,frozen,4000000,12.)

    def test_target_first_ack_later_and_stale_triplet_pending(self):
        h,_=self.make_started();self.assertFalse(h.poll(10.1,[],cli(h.target),4))
        self.assertFalse(h.poll(10.2,[ack(10.15)],cli(h.target,timestamp=3999999),4))
        self.assertTrue(h.poll(10.3,[ack(10.15)],cli(h.target),4))

    def test_stale_foreign_ack_does_not_accept_and_timeout_latches(self):
        h,_=self.make_started()
        self.assertFalse(h.poll(11.,[ack(9.),ack(system=2)],cli(h.target),4))
        with self.assertRaises(ValueError):h.poll(15.0001,[],cli(h.target),4)
        with self.assertRaises(ValueError):h.poll(16.,[ack(16.)],cli(h.target),4)

    def test_rejected_duplicate_ack_and_backward_clock(self):
        for records,wall in [([ack(result=1)],11.),([ack(),ack()],11.),([],9.)]:
            h,_=self.make_started()
            with self.assertRaises(ValueError):h.poll(wall,records,cli(h.target),4)

    def test_late_success_future_ack_and_midpoll_clock_rollback_reject(self):
        for records,wall in [([ack(15.01)],15.01),([ack(12.)],11.)]:
            h,_=self.make_started()
            with self.assertRaises(ValueError):h.poll(wall,records,cli(h.target),4)
        h,_=self.make_started();h.poll(11.,[],cli(h.target),4)
        with self.assertRaises(ValueError):h.poll(10.5,[],cli(h.target),4)
        self.assertTrue(h.failed)

    def test_target_loss_after_acceptance_and_cli_precision(self):
        for changes,nav in [({'alt':400.},4),({'lat':47.},4),({},2),({'yaw_valid':0},4)]:
            h,_=self.make_started();self.assertTrue(h.poll(11.,[ack()],cli(h.target),4))
            with self.assertRaises(ValueError):h.poll(12.,[ack()],cli(h.target,**changes),nav)
        t=capture(self.real,self.ref,self.frozen,38096000)
        self.assertTrue(matches_target(decode_current(cli(t)),t,cli=True))
        d=decode_current(cli(t));d['lat']+=1e-6
        self.assertFalse(matches_target(d,t,cli=True))

    def test_send_failure_is_recorded_before_io_and_not_retried(self):
        log,ref,frozen=setup_log();h=Handoff();mav=Mock();records=[]
        mav.command_int_send.side_effect=OSError('uncertain send')
        with self.assertRaises(OSError):h.start(mav,log,ref,frozen,4000000,10.,lambda *args:records.append(args))
        self.assertEqual(len(records),1);self.assertTrue(h.failed)
        with self.assertRaises(ValueError):h.start(mav,log,ref,frozen,4000000,11.)
        mav.command_int_send.assert_called_once()
        bad=Handoff()
        with self.assertRaises(ValueError):bad.start(mav,log,ref,frozen,3900000,10.)
        self.assertTrue(bad.failed)
        with self.assertRaises(ValueError):bad.start(mav,log,ref,frozen,4000000,11.)

    def test_flight_entry_is_hard_disabled_before_any_side_effect(self):
        import run_v04_flight06 as flight
        with patch.object(flight.subprocess,'Popen') as launch,patch.object(flight.mavutil,'mavlink_connection') as wire:
            with self.assertRaisesRegex(RuntimeError,'offline-only'):flight.main(checks=Mock(execution_permitted=True))
            launch.assert_not_called();wire.assert_not_called()
        p=json.loads((CONFIG.parent/'handoff06/protocol.json').read_text())
        self.assertFalse(p['flight_authorized']);self.assertEqual(p['maximum_attempts'],0)
        self.assertEqual(p['jobs'],[]);self.assertEqual(p['seeds'],[])

    def test_cpp_real_ecl_projection_and_mavlink_codecs(self):
        source=CONFIG.parent/'handoff06/ProjectionWireProbe.cpp'
        with tempfile.TemporaryDirectory(prefix='handoff06-probe-') as tmp:
            binary=Path(tmp)/'probe'
            cmd=['g++','-std=c++14','-Wno-address-of-packed-member','-Wl,--gc-sections',
                 '-I'+str(REPO/'src/lib/ecl'),'-I'+str(REPO/'mavlink/include/mavlink/v2.0'),str(source),
                 str(REPO/'build/px4_sitl_test/src/lib/ecl/geo/libecl_geo.a'),'-o',str(binary)]
            compiled=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            cases=[(lat,lon,x,y) for lat,lon in [(47.3977508,8.5456073),(-47.,-8.),(0.,0.),(80.,179.99999)]
                   for x,y in [(0.,0.),(.15,-.2),(-2.,1.),(1.,0.),(0.,1.),(2.,2.)]]
            p=subprocess.run([str(binary)],input=''.join(' '.join(map(str,c))+'\n' for c in cases),capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(len(p.stdout.splitlines()),24)
            for args,line in zip(cases,p.stdout.splitlines()):
                lat,lon,ilat,ilon,north,east=map(float,line.split());a,b=reproject(*args)
                self.assertAlmostEqual(a,lat,places=11);self.assertAlmostEqual(b,lon,places=11)
                self.assertEqual((round(a*1e7),round(b*1e7)),(int(ilat),int(ilon)))
                np.testing.assert_allclose(project(args[0],args[1],ilat/1e7,ilon/1e7),(north,east),atol=1e-6)

    def chain(self, mutation=None):
        from test_v04_protocol04 import Protocol04Test
        from analyze_v04_flight06 import height_evidence
        def adapt(log,ref,ev,out):
            q=data(log,'trajectory_setpoint');n=len(q['timestamp'])
            # Realistic nonzero global origin and local XY; integer quantization is observable.
            pos=data(log,'vehicle_local_position')
            pos['ref_lat']=np.full(n,47.3977508);pos['ref_lon']=np.full(n,8.5456073)
            ref['position']['ref_lat']=47.3977508;ref['position']['ref_lon']=8.5456073
            (out/'height_reference.json').write_text(json.dumps(ref))
            q.update(x=np.full(n,.15),y=np.full(n,-.2))
            d=data(log,'sta_velocity_ctrl_status');d['p_sp[0]']=np.full(n,.15);d['p_sp[1]']=np.full(n,-.2)
            frozen=json.loads((out/'task_yaw.json').read_text())
            target=capture(log,ref,frozen,3000000,source_us=frozen['timestamp'])
            (out/'handoff_target.json').write_text(json.dumps(target))
            (out/'reposition_command.json').write_text(json.dumps(dict(timestamp_us=3000000,sent_monotonic=10.,
                message='COMMAND_INT',wire=target['wire'],maximum_sends=1)))
            w=target['wire'];c=data(log,'vehicle_command')
            for key,value in dict(param5=target['lat'],param6=target['lon'],param4=w['param4'],param7=w['z'],from_external=1,confirmation=0).items():
                c[key]=np.array([value])
            trip=data(log,'position_setpoint_triplet');trip['timestamp'][0]=1700000
            for key,val in dict(lat=target['lat'],lon=target['lon'],alt=w['z'],yaw=w['param4'],valid=1,yaw_valid=1,type=2).items():
                trip['current.'+key]=np.array([val,val])
            trip['current.valid'][0]=0;trip['current.type'][0]=5
            trip['current.lat'][0]=np.nan;trip['current.lon'][0]=np.nan
            (out/'triplet_after.txt').write_text(cli(target,timestamp=3020000))
            ev['handoff_ready']=3100000
            if mutation:mutation(log,ref,ev,out)
        with patch('analyze_v04_protocol04.height_evidence',height_evidence):
            return Protocol04Test().height_fixture04(adapt)

    def test_full_synthetic_handoff_height_observation_and_landing(self):
        result=self.chain()
        self.assertEqual(result['entry_samples'],301)
        self.assertTrue(result['heading']['confirmed'])
        self.assertEqual(result['handoff']['raw_command_timestamp'],3000000)

    def test_chain_rejects_corrupt_provenance_wire_and_missing_artifacts(self):
        def edit(out,name,key,value):
            p=out/name;d=json.loads(p.read_text());d[key]=value;p.write_text(json.dumps(d))
        for change in [lambda u,r,e,o:edit(o,'handoff_target.json','source_xy',[1.,0.]),
                       lambda u,r,e,o:edit(o,'reposition_command.json','message','COMMAND_LONG'),
                       lambda u,r,e,o:(o/'handoff_target.json').unlink()]:
            with self.assertRaises((ValueError,FileNotFoundError)):self.chain(change)

    def test_chain_rejects_wrong_or_duplicate_logged_command_and_ack(self):
        changes=[lambda u,r,e,o:data(u,'vehicle_command')['param5'].__setitem__(0,.01),
                 lambda u,r,e,o:data(u,'vehicle_command_ack')['result'].__setitem__(0,1),
                 lambda u,r,e,o:data(u,'vehicle_command_ack')['timestamp'].__setitem__(0,3200000)]
        def duplicate(u,r,e,o):
            d=data(u,'vehicle_command')
            for key,value in list(d.items()):d[key]=np.r_[value,value]
            d['timestamp'][1]+=1000
        changes.append(duplicate)
        for change in changes:
            with self.assertRaises(ValueError):self.chain(change)

    def test_chain_rejects_sub_cli_precision_raw_target_drift(self):
        def change(u,r,e,o):
            d=data(u,'position_setpoint_triplet')
            d['current.lat'][-1]=np.nextafter(d['current.lat'][-1],1.)
        with self.assertRaisesRegex(ValueError,'raw Navigator'):self.chain(change)

    def test_chain_rejects_downstream_nan_wrong_xy_or_missing_window(self):
        for topic,key,value in [('trajectory_setpoint','x',np.nan),('trajectory_setpoint','y',.06),
                                ('sta_velocity_ctrl_status','p_sp[0]',.06)]:
            with self.subTest(topic=topic,key=key),self.assertRaises(ValueError):
                self.chain(lambda u,r,e,o:data(u,topic)[key].__setitem__(500,value))
        def remove(u,r,e,o):
            d=data(u,'trajectory_setpoint');mask=(d['timestamp']<5000000)|(d['timestamp']>5100000)
            for key in list(d):d[key]=d[key][mask]
        with self.assertRaisesRegex(ValueError,'Missing downstream'):self.chain(remove)

    def test_local_xy_online_gate_and_command_configuration_not_flight_authority(self):
        from v04_handoff06 import local_xy_ok
        from analyze_v04_flight06 import load_protocol
        h,_=self.make_started();x,y=h.target['xy_encoded']
        self.assertTrue(local_xy_ok(dict(x=x,y=y),h.target))
        self.assertFalse(local_xy_ok(dict(x=x+.06,y=y),h.target))
        self.assertFalse(local_xy_ok(dict(x=x,y=np.nan),h.target))
        p=load_protocol();self.assertFalse(p['flight_authorized']);self.assertEqual(p['jobs'],[])

    def test_chain_rejects_reset_after_handoff_or_excitation_outside_window(self):
        for change in [lambda u,r,e,o:data(u,'vehicle_local_position')['heading_reset_counter'].__setitem__(-200,4),
                       lambda u,r,e,o:e.__setitem__('hover_end',40000000),
                       lambda u,r,e,o:data(u,'vehicle_status')['nav_state'].__setitem__(500,2)]:
            with self.assertRaises(ValueError):self.chain(change)

    def test_original_failed_run_remains_failed_in_new_analyzer(self):
        from analyze_v04_flight06 import analyze
        from v04_protocol05 import load_protocol
        import shutil
        with tempfile.TemporaryDirectory(prefix='handoff06-old-reject-') as tmp:
            out=Path(tmp)
            for name in ('result.json','job.json'):
                shutil.copyfile(self.path.parent/name,out/name)
            job=json.loads((out/'job.json').read_text());p=load_protocol()
            p['startup_overrides'].update(job['parameters'])
            result=analyze(out,p,job)
            self.assertFalse(result['accepted']);self.assertIn('hover_start',result['error'])


if __name__=='__main__':unittest.main()
