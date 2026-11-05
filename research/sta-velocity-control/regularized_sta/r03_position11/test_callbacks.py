import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np

spec=importlib.util.spec_from_file_location('callback_test',Path(__file__).with_name('callbacks.py'))
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


def fixture():
    t=np.array([100000,108000,108000,116000],dtype=np.uint64)
    d=dict(timestamp=t.copy(),timestamp_sample=np.array([100000,104000,108000,116000],dtype=np.uint64),
        input_timestamp=t.copy(),publish_seq=np.arange(4,dtype=np.uint32),output_timestamp=t.copy(),
        attitude_timestamp=t.copy(),value=np.arange(4,dtype=np.float32))
    out=dict(timestamp=t.copy(),actual=d['value'].copy())
    return d,out


class CallbackTest(unittest.TestCase):
    def test_full_equal_groups(self):
        d,o=fixture();c.validate(d)
        value=c.exact_output_match(d,o,'output_timestamp',[('value','actual')],100000,120000)
        self.assertEqual(value['matched'],4);self.assertEqual(value['coverage'],1)
    def test_first_tied_payload_wrong(self):
        d,o=fixture();o['actual'][1]+=1
        with self.assertRaisesRegex(ValueError,'differs'):c.exact_output_match(d,o,'output_timestamp',[('value','actual')],100000,120000)
    def test_second_tied_payload_wrong(self):
        d,o=fixture();o['actual'][2]+=1
        with self.assertRaisesRegex(ValueError,'differs'):c.exact_output_match(d,o,'output_timestamp',[('value','actual')],100000,120000)
    def test_missing_one_tied_output(self):
        d,o=fixture();o={k:np.delete(v,1) for k,v in o.items()}
        with self.assertRaisesRegex(ValueError,'group'):c.exact_output_match(d,o,'output_timestamp',[('value','actual')],100000,120000)
    def test_duplicated_extra_tied_output(self):
        d,o=fixture();o={k:np.insert(v,1,v[1]) for k,v in o.items()}
        with self.assertRaisesRegex(ValueError,'group'):c.exact_output_match(d,o,'output_timestamp',[('value','actual')],100000,120000)
    def test_reordered_group_payload(self):
        d,o=fixture();o['actual'][1:3]=o['actual'][1:3][::-1]
        with self.assertRaisesRegex(ValueError,'differs'):c.exact_output_match(d,o,'output_timestamp',[('value','actual')],100000,120000)
    def test_equal_values_still_count_records(self):
        d,o=fixture();d['value'][:]=1;o['actual'][:]=1
        v=c.exact_output_match(d,o,'output_timestamp',[('value','actual')],100000,120000)
        self.assertEqual(v['matched'],4)
    def test_missing_non_tied_coverage_reject(self):
        d,o=fixture();o={k:v[:-1] for k,v in o.items()}
        with self.assertRaisesRegex(ValueError,'coverage'):c.exact_output_match(d,o,'output_timestamp',[('value','actual')],100000,120000)
    def test_output_whitelist(self):
        d,o=fixture()
        with self.assertRaisesRegex(ValueError,'whitelist'):c.exact_output_match(d,o,'timestamp',[],100000,120000)
    def test_backward_output(self):
        d,o=fixture();o['timestamp'][-1]=1
        with self.assertRaisesRegex(ValueError,'Backward'):c.exact_output_match(d,o,'output_timestamp',[],100000,120000)
    def test_duplicate_sequence(self):
        d,_=fixture();d['publish_seq'][2]=1
        with self.assertRaisesRegex(ValueError,'sequence'):c.validate(d)
    def test_sequence_gap(self):
        d,_=fixture();d['publish_seq'][2:]+=1
        with self.assertRaisesRegex(ValueError,'sequence'):c.validate(d)
    def test_same_sample(self):
        d,_=fixture();d['timestamp_sample'][2]=104000
        with self.assertRaisesRegex(ValueError,'sample'):c.validate(d)
    def test_future_input(self):
        d,_=fixture();d['input_timestamp'][-1]+=1
        with self.assertRaisesRegex(ValueError,'Future'):c.validate(d)
    def test_future_sample(self):
        d,_=fixture();d['timestamp_sample'][-1]+=1
        with self.assertRaisesRegex(ValueError,'Future'):c.validate(d)
    def test_backward_input(self):
        d,_=fixture();d['input_timestamp'][-1]=100000
        with self.assertRaises(ValueError):c.validate(d)
    def test_unrecognized_clock(self):
        with self.assertRaisesRegex(ValueError,'whitelist'):c.callback_clock('something',[1,1])
    def test_tied_yaw_identical(self):
        _,o=fixture();o['yaw_body']=np.ones(4)
        i,age=c.yaw_previous(o,[108000,112000]);self.assertEqual(i.tolist(),[2,2])
    def test_tied_yaw_first_disagrees(self):
        _,o=fixture();o['yaw_body']=np.ones(4);o['yaw_body'][1]=2
        with self.assertRaisesRegex(ValueError,'Ambiguous'):c.yaw_previous(o,[108000])
    def test_tied_yaw_second_disagrees(self):
        _,o=fixture();o['yaw_body']=np.ones(4);o['yaw_body'][2]=2
        with self.assertRaisesRegex(ValueError,'Ambiguous'):c.yaw_previous(o,[116000])
    def test_stale_yaw(self):
        _,o=fixture();o['yaw_body']=np.ones(4)
        with self.assertRaisesRegex(ValueError,'Stale'):c.yaw_previous(o,[137000])
    def test_nonfinite_yaw(self):
        _,o=fixture();o['yaw_body']=np.ones(4);o['yaw_body'][1]=np.nan
        with self.assertRaisesRegex(ValueError,'Invalid'):c.yaw_previous(o,[116000])
    def test_no_previous_yaw(self):
        _,o=fixture();o['yaw_body']=np.ones(4)
        with self.assertRaisesRegex(ValueError,'Missing'):c.yaw_previous(o,[99000])


if __name__=='__main__':unittest.main(verbosity=2)
