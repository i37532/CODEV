"""Real frozen ULogs and opt-in analysis wiring. Inputs are never rewritten."""
import copy
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from pyulog import ULog
import analyze_v00
import analyze_v04_core04 as core
import analyze_v04_protocol08 as old_height
import analyze_v04_height_clock09 as new_height
from replay_v04_clock09 import ROOT, digest, copy_metadata, historical_protocol
from v04_attitude_clock09 import AttitudeClockPolicy
from v04_heading_stream import data, replay


class Clock09IntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.logs={};cls.records={};cls.paths={}
        for series,record_id in ((5,6),(6,7),(7,8)):
            r=json.loads((ROOT/f'results{record_id:02d}/run01.json').read_text())
            entry=max(r['logs'],key=lambda e:e['bytes'])
            if digest(entry['archive'])!=entry['sha256']:raise ValueError('Frozen input changed')
            cls.logs[series]=ULog(entry['archive']);cls.records[series]=r
            cls.paths[series]=Path(entry['archive']).parent
        cls.policy=AttitudeClockPolicy()

    def test_height_numerical_rules_exactly_inherited(self):
        new=inspect.getsource(new_height.height_evidence)
        new=new.replace(', *, attitude_policy):','):').replace(',attitude_policy=attitude_policy)',' )')
        new=new.replace('frozen=frozen )','frozen=frozen)')
        self.assertEqual(new,inspect.getsource(old_height.height_evidence))

    def test_series07_tied_group_new_heading_but_no_unique_consumption(self):
        u=self.logs[7];source=self.paths[7]
        ref=json.loads((source/'height_reference.json').read_text())
        frozen=json.loads((source/'task_yaw.json').read_text())
        with self.assertRaisesRegex(ValueError,'nonmonotonic'):replay(u,ref,frozen=frozen)
        r=replay(u,ref,frozen=frozen,attitude_policy=self.policy)
        self.assertTrue(r['ready'])
        a=self.policy.data(u)
        groups=self.policy.candidates(a,60128000)
        self.assertEqual(a['timestamp_sample'][groups[0]].tolist(),[60124000,60128000])
        with self.assertRaisesRegex(ValueError,'Ambiguous'):self.policy.unique_index(a,60128000)
        self.assertFalse(self.records[7]['success'])
        self.assertNotIn('hover_end',[e['name'] for e in self.records[7]['events']])

    def test_series06_real_landing_reference_switch_still_rejected(self):
        source=self.paths[6]
        ref=json.loads((source/'height_reference.json').read_text())
        frozen=json.loads((source/'task_yaw.json').read_text())
        with self.assertRaisesRegex(ValueError,'Coordinate/reset changed'):
            replay(self.logs[6],ref,frozen=frozen,attitude_policy=self.policy)

    def analyze_baseline(self, root, name, policy, u=None):
        dest=root/name;copy_metadata(self.paths[5],dest)
        p=historical_protocol(6);job=json.loads((dest/'job.json').read_text())
        p['startup_overrides'].update(job['parameters'])
        with patch.object(analyze_v00,'CONFIG',ROOT/'protocol06/pid'):
            if u is None:return analyze_v00.analyze(dest,p,attitude_policy=policy)
            main=max(self.records[5]['logs'],key=lambda e:e['bytes'])['archive']
            with patch.object(analyze_v00,'ULog',side_effect=lambda path:u if str(path)==main else ULog(path)):
                return analyze_v00.analyze(dest,p,attitude_policy=policy)

    def test_complete_recorded_pid_metrics_and_limits_unchanged(self):
        with tempfile.TemporaryDirectory(prefix='v04-clock09-equivalence-') as tmp:
            root=Path(tmp)
            old=self.analyze_baseline(root,'legacy',None)
            new=self.analyze_baseline(root,'revised',self.policy)
        self.assertEqual(old['metrics'],new['metrics'])
        self.assertEqual(old['checks'],new['checks'])
        self.assertEqual(old['actuator_matches'],new['actuator_matches'])
        # These are baseline components; original whole-flight rejection is retained.
        original=json.loads((self.paths[5]/'v04_protocol06_metrics.json').read_text())
        self.assertFalse(original['accepted'])

    def tied_complete_log(self):
        u=copy.deepcopy(self.logs[5]);a=u.get_dataset('vehicle_attitude').data
        events={e['name']:e['timestamp_us'] for e in self.records[5]['events']}
        k=int(np.searchsorted(a['timestamp'],events['hover_start']+1e6))
        a['timestamp'][k]=a['timestamp'][k+1]
        return u,k

    def test_complete_baseline_opt_in_handles_ties_legacy_rejects(self):
        u,k=self.tied_complete_log()
        with tempfile.TemporaryDirectory(prefix='v04-clock09-tied-') as tmp:
            root=Path(tmp)
            with self.assertRaisesRegex(ValueError,'nonmonotonic'):
                self.analyze_baseline(root,'legacy',None,u)
            new=self.analyze_baseline(root,'revised',self.policy,u)
        self.assertTrue(new['accepted'])  # synthetic baseline component ONLY
        self.assertEqual(new['topic_rates']['vehicle_attitude']['equal_publish'],1)
        self.assertEqual(new['attitude_yaw_semantics']['records'],
                         new['topic_rates']['vehicle_attitude']['sample']['n'])

    def test_complete_baseline_first_tied_row_violation_not_hidden(self):
        u,k=self.tied_complete_log();a=u.get_dataset('vehicle_attitude').data
        a['q[0]'][k]=np.cos(.2);a['q[1]'][k]=np.sin(.2);a['q[2]'][k]=a['q[3]'][k]=0
        with tempfile.TemporaryDirectory(prefix='v04-clock09-unsafe-') as tmp:
            with self.assertRaisesRegex(ValueError,'tilt'):
                self.analyze_baseline(Path(tmp),'revised',self.policy,u)

    def test_complete_height_chain_equivalent_without_ties(self):
        source=self.paths[5];u=self.logs[5]
        events={e['name']:e['timestamp_us'] for e in self.records[5]['events']}
        d=u.get_dataset('sta_velocity_ctrl_status').data
        a=old_height.height_evidence(u,source,d,events)
        b=new_height.height_evidence(u,source,d,events,attitude_policy=self.policy)
        self.assertEqual(json.dumps(a,sort_keys=True),json.dumps(b,sort_keys=True))

    def test_core_revised_downstream_rejects_duplicate_output(self):
        # Real rows, one conflicting output added at the same publication key.
        u=copy.deepcopy(self.logs[5]);output=u.get_dataset('vehicle_attitude_setpoint').data
        start=next(e['timestamp_us'] for e in self.records[5]['events'] if e['name']=='hover_start')
        k=int(np.searchsorted(output['timestamp'],start+1e6))
        for field,values in list(output.items()):output[field]=np.insert(values,k,values[k])
        output['q_d[0]'][k+1]+=0.01
        with tempfile.TemporaryDirectory(prefix='v04-clock09-output-') as tmp:
            root=Path(tmp);copy_metadata(self.paths[5],root/'run')
            p=historical_protocol(6);job=json.loads((root/'run/job.json').read_text())
            p['startup_overrides'].update(job['parameters'])
            old=analyze_v00.CONFIG
            try:
                with patch.object(core,'CONFIG',ROOT/'protocol06'),patch.object(core,'ULog',return_value=u):
                    result=core.analyze(root/'run',p,job,attitude_policy=self.policy)
            finally:analyze_v00.CONFIG=old
        self.assertFalse(result['accepted']);self.assertIn('Nonunique',result['error'])


if __name__=='__main__':unittest.main()
