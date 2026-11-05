"""Real failed-prefix regression. Passing components never reclassify the flight."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from pyulog import ULog

HERE=Path(__file__).resolve().parent


def load(name,path):
    spec=importlib.util.spec_from_file_location('_position11_recorded_'+name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


class RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.diag=load('diag',HERE/'diagnostic.py')
        cls.old=load('original',HERE.parent/'r03_revision10/analyzer.py')
        cls.a,cls.b=cls.diag.bindings(cls.old)
        cls.record_dir=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision10/D/batch01/run033')
        cls.raw=ULog(str(cls.record_dir/'log001.ulg'));cls.log=cls.a.policy.PositionLogView(cls.raw)
        cls.d=cls.raw.get_dataset('sta_velocity_ctrl_status').data
        cls.q=cls.raw.get_dataset('velocity_ctrl_selection').data
        cls.job=json.loads((cls.record_dir/'job.json').read_text())
        cls.events={e['name']:e['timestamp_us'] for e in json.loads((cls.record_dir/'result.json').read_text())['events']}
        cls.start=cls.events['hover_start'];cls.end=int(cls.d['timestamp'][-1])
        cls.mask=(cls.d['timestamp']>=cls.start)&(cls.d['timestamp']<cls.end)
        cls.x={k:v[cls.mask] for k,v in cls.d.items()}
    def test_old_rejection_preserved(self):
        with self.assertRaisesRegex(ValueError,'clock timestamp'):self.a.policy.legacy.checked(self.raw)
        self.assertFalse(json.loads((self.record_dir/'result.json').read_text())['success'])
        self.assertNotIn('landed_disarmed',self.events)
    def test_actual_components_with_tied_callbacks(self):
        result,x,q=self.b['check_components'](self.d,self.q,self.job,self.start,self.end,True)
        self.assertGreater(result['samples'],3000)
        ix=np.flatnonzero(np.diff(x['timestamp'].astype(np.int64))==0)
        self.assertEqual(len(ix),1)
        self.assertGreater(float(x['raw_dt'][ix[0]+1]),.007)
        self.assertLess(float(x['used_dt'][ix[0]+1]),.003)
    def test_position_p_ff_consumption_pair(self):
        target=self.b['check_targets'].__globals__['check_position_sum']
        evidence=target(self.log,self.x,self.job)
        self.assertGreater(evidence['samples'],3000)
    def test_exact_both_actual_output_groups(self):
        self.a.check_output_groups(self.log)
    def test_wrong_sequence_rejected(self):
        q=copy.deepcopy(self.q);q['publish_seq'][100]+=1
        with self.assertRaises(ValueError):self.b['r02'].aligned(self.d,q)
    def test_selection_sample_mismatch_rejected(self):
        q=copy.deepcopy(self.q);i=np.flatnonzero(np.diff(q['timestamp'].astype(np.int64))==0)[0]+1
        q['timestamp_sample'][i]+=1
        with self.assertRaises(ValueError):self.b['r02'].aligned(self.d,q)
    def test_actual_yaw_target_ties_are_unambiguous(self):
        p=self.b['AttitudeClockPolicy']();d=self.raw.get_dataset('vehicle_attitude').data
        target=self.raw.get_dataset('vehicle_attitude_setpoint').data
        self.assertGreater(p.safety(d,target,self.start,self.end)['records'],1000)
    def test_real_output_group_missing_first_rejected(self):
        d=self.raw.get_dataset('vehicle_local_position_setpoint').data
        i=np.flatnonzero(np.diff(d['timestamp'].astype(np.int64))==0)[0]
        broken={k:np.delete(v,i) for k,v in d.items()}
        with self.assertRaisesRegex(ValueError,'group'):
            self.a.callbacks.exact_output_match(self.d,broken,'output_timestamp',[],self.start,self.end)
    def test_real_output_group_reordered_rejected(self):
        target=copy.deepcopy(self.raw.get_dataset('vehicle_attitude_setpoint').data)
        i=np.flatnonzero(np.diff(target['timestamp'].astype(np.int64))==0)[0]
        for k in target:
            if k!='timestamp':target[k][i:i+2]=target[k][i:i+2][::-1]
        with self.assertRaisesRegex(ValueError,'differs'):
            self.a.callbacks.exact_output_match(self.d,target,'attitude_timestamp',
                [(f'q_sp[{j}]',f'q_d[{j}]') for j in range(4)],self.start,self.end)
    def test_runner_private_binding_constructs(self):
        runner=load('runner',HERE.parent/'r03_revision10/runner.py')
        old=runner.execution_checks_class(); new=self.a.make_checks(old,self.a.build_heading())
        self.assertTrue(issubclass(new,old))
        self.assertIsNot(new._phase_monitor.__globals__,old._phase_monitor.__globals__)
        self.assertIsNot(new._position11_parent_monitor.__globals__['replay'],old._phase_monitor.__globals__['replay'])
    def test_runner_monitor_wrapper_keeps_failure_latch_and_receipt(self):
        runner=load('runner_latch',HERE.parent/'r03_revision10/runner.py')
        new=self.a.make_checks(runner.execution_checks_class(),self.a.build_heading())
        obj=object.__new__(new)
        with tempfile.TemporaryDirectory(prefix='position11-monitor-') as tmp:
            output=Path(tmp)
            with patch.object(new,'_position11_ax04_monitor',side_effect=ValueError('deliberate safety failure')) as parent:
                with self.assertRaisesRegex(ValueError,'deliberate'):obj.monitor('hover',None,None,output,{})
                with self.assertRaisesRegex(RuntimeError,'latched'):obj.monitor('hover',None,None,output,{})
                self.assertEqual(parent.call_count,1)
            rows=[json.loads(line) for line in (output/'r03_prearm04_timing.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),2);self.assertTrue(all(row['failure_latched'] for row in rows))
            self.assertTrue(all(row['transport_max_age_us']==500000 for row in rows))
    def test_runner_phase_and_landing_bind_same_live_policy(self):
        runner=load('runner_scopes',HERE.parent/'r03_revision10/runner.py')
        heading=self.a.build_heading();new=self.a.make_checks(runner.execution_checks_class(),heading)
        self.assertIs(new._phase_monitor.__globals__['replay'],heading.live_replay)
        self.assertIs(new._position11_parent_monitor.__globals__['replay'],heading.live_replay)
        self.assertEqual(new._position11_ax04_monitor.position11_changes[0]['before'],'parent=super().monitor')


if __name__=='__main__':unittest.main(verbosity=2)
