import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np

spec=importlib.util.spec_from_file_location('policy_test',Path(__file__).with_name('policy.py'))
p=importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


def dataset(t=(100000,108000,108000,116000),s=(100000,104000,108000,116000)):
    d={k:np.zeros(len(t),dtype=np.float32) for k in p.POSITION_FIELDS}
    d['timestamp']=np.array(t,dtype=np.uint64); d['timestamp_sample']=np.array(s,dtype=np.uint64)
    for k in p.RESET_FIELDS: d[k]=np.zeros(len(t),dtype=np.uint8)
    for k in ('xy_valid','z_valid','v_xy_valid','v_z_valid'): d[k]=np.ones(len(t),dtype=np.uint8)
    d['x']=np.arange(len(t),dtype=np.float32)
    return d


class Log:
    def __init__(self):
        self.original=dataset(); self.mirror=copy.deepcopy(self.original)
        self.mirror['log_seq']=np.arange(11,15,dtype=np.uint32)
        self.diag={'input_timestamp':np.array([108000,108000],dtype=np.uint64),
                   'timestamp_sample':np.array([104000,108000],dtype=np.uint64)}
        self.dropouts=[]; self.file_corruption=False
    def get_dataset(self,name,multi_instance=0):
        return SimpleNamespace(data={'vehicle_local_position':self.original,
            'vehicle_local_position_log':self.mirror,'sta_velocity_ctrl_status':self.diag}[name])


class PolicyTest(unittest.TestCase):
    def test_ties_retain_all_rows(self):
        l=Log(); d,e=p.checked(l)
        self.assertEqual(len(d.data['timestamp']),4); self.assertEqual(e['equal_publications'],1)
        self.assertEqual(e['consumed_records'],2); self.assertTrue(e['no_deduplication'])
        self.assertEqual(p.exact_indices(d.data,[108000,108000],[104000,108000]).tolist(),[1,2])
    def test_old_rule_remains_strict(self):
        with self.assertRaisesRegex(ValueError,'clock timestamp'): p.legacy.checked(Log())
    def test_wrong_composite_pair(self):
        with self.assertRaisesRegex(ValueError,'pair'): p.exact_indices(dataset(),[116000],[104000])
    def test_missing_sample(self):
        with self.assertRaises(ValueError): p.exact_indices(dataset(),[108000],[106000])
    def test_missing_pub(self):
        with self.assertRaises(ValueError): p.exact_indices(dataset(),[107000],[104000])
    def test_ambiguous_pub(self):
        with self.assertRaisesRegex(ValueError,'Ambiguous'): p.unique_at(dataset(),108000)
        self.assertEqual(p.unique_at(dataset(),108000,104000),1)
    def test_backward_publication(self):
        d=dataset(); d['timestamp'][2]=107000
        with self.assertRaisesRegex(ValueError,'Backward'): p.validate(d)
    def test_equal_sample(self):
        d=dataset(); d['timestamp_sample'][2]=104000
        with self.assertRaisesRegex(ValueError,'Repeated'): p.validate(d)
    def test_backward_sample(self):
        d=dataset(); d['timestamp_sample'][2]=103000
        with self.assertRaisesRegex(ValueError,'backward'): p.validate(d)
    def test_future_sample(self):
        d=dataset(); d['timestamp_sample'][-1]=117000
        with self.assertRaisesRegex(ValueError,'Future'): p.validate(d)
    def test_float_clock(self):
        with self.assertRaises(ValueError): p.clock([1.,2.])
    def test_zero_clock(self):
        with self.assertRaises(ValueError): p.clock([0,1])
    def test_bool_clock(self):
        with self.assertRaises(ValueError): p.clock([True,True])
    def test_overflow_clock(self):
        with self.assertRaises(ValueError): p.clock(np.array([2**63],dtype=np.uint64))
    def test_empty_clock(self):
        with self.assertRaises(ValueError): p.clock([])
    def test_shape_clock(self):
        with self.assertRaises(ValueError): p.clock([[1,2]])
    def test_column_length(self):
        d=dataset(); d['x']=d['x'][:-1]
        with self.assertRaises(ValueError): p.validate(d)
    def test_payload_mismatch(self):
        l=Log(); l.original['x'][1]+=1
        with self.assertRaisesRegex(ValueError,'payload mismatch x'): p.checked(l)
    def test_payload_dtype(self):
        l=Log(); l.original['x']=l.original['x'].astype(float)
        with self.assertRaisesRegex(ValueError,'payload mismatch x'): p.checked(l)
    def test_missing_payload(self):
        l=Log(); del l.mirror['z']
        with self.assertRaises(ValueError): p.checked(l)
    def test_sequence_gap(self):
        l=Log(); l.mirror['log_seq'][2]+=1
        with self.assertRaisesRegex(ValueError,'sequence'): p.checked(l)
    def test_sequence_missing(self):
        l=Log(); del l.mirror['log_seq']
        with self.assertRaisesRegex(ValueError,'sequence'): p.checked(l)
    def test_sequence_wrap(self):
        l=Log(); l.mirror['log_seq']=np.array([2**32-2,2**32-1,0,1],dtype=np.uint32)
        p.checked(l)
    def test_sequence_float(self):
        l=Log(); l.mirror['log_seq']=l.mirror['log_seq'].astype(float)
        with self.assertRaises(ValueError): p.checked(l)
    def test_dropout(self):
        l=Log(); l.dropouts=[1]
        with self.assertRaises(ValueError): p.checked(l)
    def test_corruption(self):
        l=Log(); l.file_corruption=True
        with self.assertRaises(ValueError): p.checked(l)
    def test_wrong_consumed_pair(self):
        l=Log(); l.diag['input_timestamp'][0]=116000
        with self.assertRaisesRegex(ValueError,'pair'): p.checked(l)
    def test_consumed_interior_cannot_escape(self):
        l=Log(); l.diag['timestamp_sample'][0]=90000
        with self.assertRaisesRegex(ValueError,'interior'): p.checked(l)
    def test_same_pub_tail_is_pending_not_discarded(self):
        l=Log(); l.mirror={k:v[:2] for k,v in l.mirror.items()}
        d,e=p.checked(l); self.assertEqual(e['raw_boundary_tail_records'],2)
        self.assertEqual(e['consumed_boundary_tail_records'],1)
        self.assertEqual(len(l.original['timestamp']),4)
    def test_missing_mirror_interior(self):
        l=Log(); l.mirror={k:np.delete(v,1) for k,v in l.mirror.items()}
        l.mirror['log_seq']=np.arange(3,dtype=np.uint32)
        with self.assertRaisesRegex(ValueError,'pair'): p.checked(l)
    def test_window_all_boundary_members(self):
        d=dataset(); self.assertEqual(p.window(d,108000,116000).tolist(),[0,1,2,3])
    def test_window_full_previous_group(self):
        d=dataset(); self.assertEqual(p.window(d,116000,116000).tolist(),[1,2,3])
    def test_window_no_predecessor(self):
        with self.assertRaisesRegex(ValueError,'predecessor'): p.window(dataset(),100000,116000)
    def test_window_future(self):
        with self.assertRaises(ValueError): p.window(dataset(),108000,120000)
    def test_window_gap(self):
        d=dataset(t=(100000,108000,108000,160000),s=(100000,104000,108000,160000))
        with self.assertRaisesRegex(ValueError,'gap'): p.window(d,108000,160000)
    def test_reference_unique(self):
        d=dataset(); ref={k:v[3].item() for k,v in d.items()}
        self.assertEqual(p.reference_window(d,ref,116000).tolist(),[3])
    def test_reference_tied_rejected(self):
        d=dataset(); ref={k:v[2].item() for k,v in d.items()}
        with self.assertRaisesRegex(ValueError,'Ambiguous'): p.reference_window(d,ref,116000)
    def test_hidden_reset_on_predecessor(self):
        d=dataset(); d['heading_reset_counter'][1]=1
        ref={k:v[3].item() for k,v in d.items()}
        with self.assertRaisesRegex(ValueError,'opening reset'): p.reference_window(d,ref,116000)
    def test_hidden_reference_change_on_predecessor(self):
        d=dataset(); d['ref_alt'][1]=1
        ref={k:v[3].item() for k,v in d.items()}
        with self.assertRaisesRegex(ValueError,'opening reset'): p.reference_window(d,ref,116000)
    def test_hidden_invalid_boundary(self):
        d=dataset(); d['xy_valid'][1]=0
        ref={k:v[3].item() for k,v in d.items()}
        with self.assertRaisesRegex(ValueError,'Invalid position boundary'): p.reference_window(d,ref,116000)
    def test_other_topics_not_whitelisted(self):
        log=SimpleNamespace(get_dataset=lambda *a:SimpleNamespace(data=dataset()))
        with self.assertRaisesRegex(ValueError,'nonmonotonic'): p.data(log,'vehicle_status')
    def test_public_instance_only(self):
        log=SimpleNamespace(get_dataset=lambda *a:SimpleNamespace(data=dataset()))
        with self.assertRaisesRegex(ValueError,'instance'): p.data(log,'vehicle_local_position',1)


if __name__=='__main__': unittest.main(verbosity=2)
