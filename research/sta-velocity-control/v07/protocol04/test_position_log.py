"""New evidence transport contract: synthetic data only, no flight acceptance."""
import copy
import io
import struct
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
import position_log as policy
from position_live import PositionLiveLog
import common

class Raw:
    dropouts=[]
    file_corruption=False
    def __init__(self,tables):self.tables=tables
    def get_dataset(self,name,multi_instance=0):return SimpleNamespace(data=self.tables[(name,multi_instance)],name=name,multi_id=multi_instance)

def fixture():
    pos={k:np.zeros(5,dtype=np.float32) for k in policy.POSITION_FIELDS}
    for k in ('timestamp','timestamp_sample','ref_timestamp'):pos[k]=np.arange(1,6,dtype=np.uint64)*10000
    for k in ('ref_lat','ref_lon'):pos[k]=np.full(5,47.3977508,dtype=np.float64)
    pos['x'][1]=-0.;pos['vxy_max'][:]=np.nan
    mirror={k:v.copy() for k,v in pos.items()};mirror['log_seq']=np.arange(1,6,dtype=np.uint32)
    diag={k:pos['timestamp'].copy() for k in ('timestamp','timestamp_sample','input_timestamp')}
    return Raw({('vehicle_local_position',0):pos,(policy.TOPIC,0):mirror,('sta_velocity_ctrl_status',0):diag})

def binary(log, first_id=0):
    def record(kind,payload):return struct.pack('<HB',len(payload),ord(kind))+payload
    types={'f':'float','d':'double','Q':'uint64_t','I':'uint32_t'}
    tags={np.dtype('float32'):'f',np.dtype('float64'):'d',np.dtype('uint64'):'Q',np.dtype('uint32'):'I'}
    out=bytearray(b'ULog\x01\x12\x35\x01'+struct.pack('<Q',0))
    packets=[]; subscriptions=[]
    for mid,((name,instance),d) in enumerate(log.tables.items(),first_id):
        # Scalar bracket names are valid ULog fields and retain the generated names.
        fields=''.join(types[tags[v.dtype]]+' '+k+';' for k,v in d.items())
        out.extend(record('F',(name+':'+fields).encode()))
        subscriptions.append(record('A',struct.pack('<BH',instance,mid)+name.encode()))
        fmt='<H'+''.join(tags[v.dtype] for v in d.values())
        for i in range(len(d['timestamp'])):
            packets.append((int(d['timestamp'][i]),mid,record('D',struct.pack(fmt,mid,*[v[i] for v in d.values()]))))
    for p in subscriptions:out.extend(p)
    for _,_,p in sorted(packets):out.extend(p)
    return bytes(out)

class PositionLogTest(unittest.TestCase):
    def test_raw_loss_kept_separate_and_consumed_copy_complete(self):
        log=fixture();p=log.tables[('vehicle_local_position',0)]
        log.tables[('vehicle_local_position',0)]={k:np.delete(v,2) for k,v in p.items()}
        before=copy.deepcopy(log.tables);view=policy.PositionLogView(log)
        self.assertEqual(len(view.get_dataset('vehicle_local_position').data['timestamp']),5)
        self.assertEqual(view.position_log_evidence['raw_missing_records'],1)
        for name,d in before.items():
            for k,v in d.items():self.assertEqual(log.tables[name][k].tobytes(),v.tobytes())

    def test_missing_copy_never_falls_back_to_original(self):
        log=fixture();del log.tables[(policy.TOPIC,0)]
        with self.assertRaises(KeyError):policy.checked(log)

    def test_gap_duplicate_restart_and_invalid_sequence_rejected(self):
        for values in ([1,2,4,5,6],[1,2,2,3,4],[9,10,1,2,3],[-1,0,1,2,3],[1,2,3,4,2**32]):
            log=fixture();log.tables[(policy.TOPIC,0)]['log_seq']=np.array(values,dtype=np.int64)
            with self.subTest(values=values),self.assertRaisesRegex(ValueError,'sequence'):policy.checked(log)

    def test_uint32_wrap_not_a_restart(self):
        log=fixture();log.tables[(policy.TOPIC,0)]['log_seq']=np.array([2**32-2,2**32-1,0,1,2],dtype=np.uint32)
        policy.checked(log)

    def test_each_payload_field_compared_bitwise(self):
        for k in policy.POSITION_FIELDS:
            log=fixture();a=log.tables[(policy.TOPIC,0)][k];a[2]=1 if not np.isfinite(a[2]) else a[2]+1
            with self.subTest(field=k),self.assertRaises(ValueError):policy.checked(log)

    def test_signed_zero_and_nan_payload_not_normalized(self):
        for key in ('x','vxy_max'):
            log=fixture();a=log.tables[(policy.TOPIC,0)][key]
            a.view(np.uint32)[1]^=1 if key=='vxy_max' else 0x80000000
            with self.assertRaisesRegex(ValueError,'payload mismatch'):policy.checked(log)

    def test_clock_duplicates_reverse_future_zero_and_float_rejected(self):
        for key in ('timestamp','timestamp_sample'):
            for value in (0,10000,60000):
                log=fixture();log.tables[(policy.TOPIC,0)][key][1]=value
                with self.assertRaises(ValueError):policy.checked(log)
            log=fixture();log.tables[(policy.TOPIC,0)][key]=log.tables[(policy.TOPIC,0)][key].astype(float)
            with self.assertRaises(ValueError):policy.checked(log)

    def test_missing_field_bad_lengths_empty_and_missing_seq(self):
        for kind in ('field','length','empty','sequence'):
            log=fixture();d=log.tables[(policy.TOPIC,0)]
            if kind=='field':del d['heading_reset_counter']
            elif kind=='length':d['x']=d['x'][:-1]
            elif kind=='empty':log.tables[(policy.TOPIC,0)]={k:v[:0] for k,v in d.items()}
            else:del d['log_seq']
            with self.assertRaises(ValueError):policy.checked(log)

    def test_original_only_record_inside_copy_window_rejected(self):
        log=fixture();d=log.tables[(policy.TOPIC,0)]
        log.tables[(policy.TOPIC,0)]={k:np.delete(v,2) for k,v in d.items()}
        log.tables[(policy.TOPIC,0)]['log_seq']=np.arange(1,5,dtype=np.uint32)
        with self.assertRaisesRegex(ValueError,'Original publication missing'):policy.checked(log)

    def test_missing_consumed_record_or_wrong_sample_rejected(self):
        for field in ('input_timestamp','timestamp_sample'):
            log=fixture();log.tables[('sta_velocity_ctrl_status',0)][field][2]+=1
            with self.assertRaisesRegex(ValueError,'consumed|Consumed'):policy.checked(log)

    def test_bounded_tail_is_not_filled_from_original(self):
        log=fixture();d=log.tables[(policy.TOPIC,0)]
        log.tables[(policy.TOPIC,0)]={k:v[:-1] for k,v in d.items()}
        p,e=policy.checked(log);self.assertEqual(e['publication_end_us'],40000)
        self.assertEqual(len(p.data['timestamp']),4)

    def test_transport_corruption_and_dropout_rejected(self):
        for field,value in [('dropouts',[1]),('file_corruption',True)]:
            log=fixture();setattr(log,field,value)
            with self.assertRaisesRegex(ValueError,'transport'):policy.checked(log)

    def test_other_topics_are_not_replaced(self):
        log=fixture();view=policy.PositionLogView(log)
        self.assertIs(view.get_dataset('sta_velocity_ctrl_status').data,log.tables[('sta_velocity_ctrl_status',0)])
        with self.assertRaises(KeyError):view.get_dataset('vehicle_local_position',multi_instance=1)

    def test_real_binary_reader_partial_record_and_truncation(self):
        raw=binary(fixture())
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'test.ulg';p.write_bytes(raw[:-2]);reader=PositionLiveLog(p)
            first=reader.read();self.assertIsInstance(first,policy.PositionLogView)
            with p.open('ab') as f:f.write(raw[-2:])
            final=reader.read();final.get_dataset('vehicle_local_position')
            self.assertEqual(final.position_log_evidence['records'],5)
            p.write_bytes(raw[:16])
            with self.assertRaisesRegex(ValueError,'truncated'):reader.read()

    def test_new_offline_and_live_sources_explicitly_wired(self):
        import baseline,core,analyze,run
        for module in (baseline,core,analyze):self.assertIs(module.ULog,policy.ULog)
        self.assertIn('PositionLiveLog',run.Checks.start_heading.__code__.co_names)
        old=common.REPO/'research/sta-velocity-control/v07/protocol02/baseline.py'
        new=(common.CONFIG/'baseline.py').read_text()
        expected=old.read_text().replace('from pyulog import ULog','from position_log import ULog')
        expected=expected.replace('    entry, log = candidates[0]','    entry, log = candidates[0]\n    log.get_dataset(\'vehicle_local_position\')\n    save(run/\'position_log_evidence.json\', log.position_log_evidence)')
        self.assertEqual(new,expected)

    def test_ulog_message_ids_cross_255_without_alias(self):
        view=policy.ULog(io.BytesIO(binary(fixture(),254)))
        view.get_dataset('vehicle_local_position')
        self.assertEqual(view.position_log_evidence['records'],5)

if __name__=='__main__':unittest.main(verbosity=2)
