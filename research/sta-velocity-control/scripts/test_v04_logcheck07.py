"""Offline event/coordinate regression; original real logs are read-only fixtures."""
import copy
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from pyulog import ULog
from v04_logcheck07 import CONFIG, REPO, event_data, receiver_coordinate, receiver_target, validate_receiver_profile
from v04_heading_stream import data
from analyze_v04_handoff07 import check_handoff
from analyze_v04_logcheck07 import height_evidence


class Tables:
    def __init__(self, tables): self.tables=tables
    def get_dataset(self, name, instance=0):
        return type('Dataset', (), {'data':self.tables[name]})()


class Logcheck07Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_run=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series05/run01')
        record=json.loads((cls.fixture_run/'result.json').read_text())
        main=max(record['logs'],key=lambda x:x['bytes'])
        if hashlib.sha256(Path(main['archive']).read_bytes()).hexdigest()!=main['sha256']:
            raise ValueError('Historical ULog changed')
        cls.ulog=ULog(main['archive'])
        cls.events={e['name']:e['timestamp_us'] for e in record['events']}
        cls.ref=json.loads((cls.fixture_run/'height_reference.json').read_text())
        cls.frozen=json.loads((cls.fixture_run/'task_yaw.json').read_text())
        cls.target=json.loads((cls.fixture_run/'handoff_target.json').read_text())

    def log(self, mutate=None):
        # Private arrays: never modify the class fixture or the on-disk ULog.
        tables={s.name:{k:v.copy() for k,v in s.data.items()} for s in self.ulog.data_list if s.multi_id==0}
        # Preserve multi-instance estimator metadata via a copy-on-write wrapper.
        class Overlay:
            def __getattr__(inner, name): return getattr(self.ulog, name)
            def get_dataset(inner,name,instance=0):
                if instance==0 and name in tables:return Tables(tables).get_dataset(name)
                return self.ulog.get_dataset(name,instance)
        if mutate: mutate(tables)
        return Overlay()

    def handoff(self, mutate=None, events=None):
        return check_handoff(self.log(mutate),self.fixture_run,copy.deepcopy(self.ref),self.frozen,events or self.events)

    def test_real_same_timestamp_different_commands_preserved(self):
        for name in ('vehicle_command','vehicle_command_ack'):
            d=event_data(self.ulog,name)
            self.assertEqual(len(d['timestamp']),4)
            self.assertEqual(d['timestamp'][0],d['timestamp'][1])
            np.testing.assert_array_equal(d['command'][:2],[22,400])
            with self.assertRaisesRegex(ValueError,'nonmonotonic'):data(self.ulog,name)

    def test_event_accessor_rejects_sampled_topics_and_empty_or_bad_schema(self):
        with self.assertRaises(ValueError):event_data(self.ulog,'vehicle_local_position')
        for d in [dict(timestamp=np.array([]),command=np.array([])),
                  dict(timestamp=np.array([1,2]),command=np.array([22])),
                  dict(timestamp=np.array([1,np.nan]),command=np.array([22,400])),
                  dict(timestamp=np.array([1,1.5]),command=np.array([22,400])),
                  dict(timestamp=np.array([1,2]),command=np.array([22,np.nan]))]:
            with self.subTest(d=d),self.assertRaises(ValueError):event_data(Tables({'vehicle_command':d}),'vehicle_command')

    def test_backward_events_and_same_time_repeated_id_rejected(self):
        for t,ids in [([2,1],[22,400]),([1,1],[22,22]),([1,1,1],[22,400,22])]:
            log=Tables({'vehicle_command':dict(timestamp=np.array(t),command=np.array(ids))})
            with self.assertRaises(ValueError):event_data(log,'vehicle_command')

    def test_real_handoff_passes_new_checks_without_original_reclassification(self):
        result=self.handoff()
        self.assertEqual(result['raw_command_timestamp'],38756000)
        self.assertEqual(result['event_command_rows'],4)
        self.assertEqual(result['receiver_expected']['lon'],8.545607799999999)
        self.assertFalse(json.loads((self.fixture_run/'v04_protocol06_metrics.json').read_text())['accepted'])

    def test_exact_coordinate_reference_and_source_record_unchanged(self):
        before=copy.deepcopy(self.target);derived=receiver_target(self.target)
        self.assertEqual(json.dumps(before,sort_keys=True),json.dumps(self.target,sort_keys=True))
        self.assertEqual(self.target['lon'],8.5456078)
        self.assertEqual(derived['lon'],np.nextafter(self.target['lon'],-np.inf))
        self.assertEqual(derived['wire'],self.target['wire'])

    def test_invalid_integer_coordinate_and_sentinel_reject(self):
        for val,axis in [(True,'lat'),(1.,'lat'),(np.nan,'lat'),(2**31-1,'lon'),(0x7ff80000,'lon'),
                         (900000001,'lat'),(-900000001,'lat'),(1800000001,'lon'),(-1800000001,'lon'),(0,'x')]:
            with self.subTest(value=val,axis=axis),self.assertRaises(ValueError):receiver_coordinate(val,axis)

    def test_compiled_real_codec_and_receiver_flags_boundary_neighbors(self):
        p=validate_receiver_profile()
        with tempfile.TemporaryDirectory(prefix='v04-log07-probe-') as tmp:
            lib=Path(tmp)/'reference.so'
            argv=[p['compiler'],'-std=c++14','-shared','-fPIC','-Wno-address-of-packed-member',*p['numeric_flags'],
                  '-I'+str(REPO/'mavlink/include/mavlink/v2.0'),str(CONFIG/'ReceiverCoordinateProbe.cpp'),'-o',str(lib)]
            built=subprocess.run(argv,capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            fn=ctypes.CDLL(str(lib)).receive_coordinate;fn.argtypes=[ctypes.c_int32];fn.restype=ctypes.c_double
            count=0
            for axis,limit in [('lat',900000000),('lon',1800000000)]:
                values=set(map(int,np.linspace(-limit,limit,257)))
                values.update([0,1,-1,limit-1,1-limit])
                for center in [85456078,-85456078,473977504,-473977504]:
                    values.update(range(center-3,center+4))
                for value in sorted(values):
                    self.assertEqual(fn(value).hex(),receiver_coordinate(value,axis).hex(),(axis,value));count+=1
            self.assertGreater(count,570)

    def test_profile_rejects_changed_flags_compiler_or_source(self):
        original=Path.read_text
        for kind in ('flags','compiler','source'):
            def read(path,*a,**kw):
                text=original(path,*a,**kw)
                if kind in ('flags','compiler') and path.name=='compile_commands.json':
                    doc=json.loads(text)
                    for d in doc:
                        if d['file'].endswith('/mavlink_receiver.cpp'):
                            d['command']=d['command'].replace('-freciprocal-math','-fno-reciprocal-math') if kind=='flags' else d['command'].replace('/usr/bin/c++','/bin/false',1)
                    return json.dumps(doc)
                if kind=='source' and path.name=='receiver_profile.json':
                    doc=json.loads(text);doc['source_sha256']='0'*64;return json.dumps(doc)
                return text
            with patch.object(Path,'read_text',read),self.assertRaises(ValueError):validate_receiver_profile()

    def test_command_wrong_payload_address_origin_confirmation_reject(self):
        for key,val in [('source_system',254),('source_component',1),('target_system',2),('target_component',2),
                        ('from_external',0),('confirmation',1),('param1',0),('param4',np.nan),('param7',490.)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.handoff(lambda t:t['vehicle_command'][key].__setitem__(2,val))

    def test_missing_duplicate_command_at_equal_or_later_time_reject(self):
        def mutate(t,variant):
            d=t['vehicle_command']
            if variant=='missing':d['command'][2]=193;return
            for key,v in list(d.items()):d[key]=np.insert(v,3,v[2])
            if variant=='later':d['timestamp'][3]+=1000
        for variant in ('missing','equal','later'):
            with self.subTest(variant=variant),self.assertRaises(ValueError):self.handoff(lambda t:mutate(t,variant))

    def test_missing_duplicate_stale_late_wrong_address_ack_reject(self):
        def mutate(t,key,value):t['vehicle_command_ack'][key][2]=value
        for key,val in [('command',193),('result',1),('timestamp',38755000),('timestamp',39065000),
                        ('target_system',1),('target_component',1),('from_external',1)]:
            with self.subTest(key=key,value=val),self.assertRaises(ValueError):self.handoff(lambda t:mutate(t,key,val))
        for delta in (0,1000):
            def duplicate(t):
                d=t['vehicle_command_ack']
                for key,v in list(d.items()):d[key]=np.insert(v,3,v[2])
                d['timestamp'][3]+=delta
            with self.assertRaises(ValueError):self.handoff(duplicate)

    def test_one_ulp_or_one_wire_unit_corruption_still_rejected(self):
        expected=receiver_target(self.target)
        stamps=self.ulog.get_dataset('position_setpoint_triplet').data['timestamp']
        target_idx=int(np.searchsorted(stamps,self.events['handoff_ready'],side='right'))-1
        self.assertGreaterEqual(stamps[target_idx],self.events['reposition_command'])
        for topic,key,idx,val in [('vehicle_command','param6',2,self.target['lon']),
            ('vehicle_command','param6',2,receiver_coordinate(self.target['wire']['y']+1,'lon')),
            ('position_setpoint_triplet','current.lon',target_idx,np.nextafter(expected['lon'],np.inf))]:
            with self.subTest(topic=topic,key=key),self.assertRaises(ValueError):
                self.handoff(lambda t:t[topic][key].__setitem__(idx,val))

    def test_full_height_observation_chain_real_log(self):
        u=self.log();result=height_evidence(u,self.fixture_run,u.get_dataset('sta_velocity_ctrl_status').data,self.events)
        self.assertEqual(result['entry_samples'],301)
        self.assertLess(result['ready_after_gate_s'],10)

    def test_sample_duplicates_and_raw_reference_ulp_remain_rejected(self):
        for key in ('timestamp','ref_lon'):
            def mutate(t):
                d=t['vehicle_local_position'];i=int(np.searchsorted(d['timestamp'],60000000))
                d[key][i]=d[key][i-1] if key=='timestamp' else np.nextafter(d[key][i],np.inf)
            u=self.log(mutate)
            with self.subTest(key=key),self.assertRaises(ValueError):
                height_evidence(u,self.fixture_run,u.get_dataset('sta_velocity_ctrl_status').data,self.events)

    def test_offline_protocol_never_inherits_flight_authorization(self):
        from analyze_v04_logcheck07 import load_protocol
        p=load_protocol()
        self.assertFalse(p['flight_authorized']);self.assertFalse(p['execution_ready'])
        self.assertEqual(p['maximum_attempts'],0);self.assertEqual(p['jobs'],[]);self.assertEqual(p['seeds'],[])


if __name__=='__main__':unittest.main()
