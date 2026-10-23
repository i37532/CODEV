import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
def load(name):
    s=importlib.util.spec_from_file_location(name,HERE/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
online=load('readiness');offline=load('evidence')

class Evidence(unittest.TestCase):
    def fixture(self, pending=False):
        state=online.Readiness();rows=[];samples=[];monitors=[]
        for i,now in enumerate((38524000,40000000,50000000,68524000) if not pending else (38524000,40000000,50000000,70000000)):
            ready=not(pending and i==0);reads=i+1 if ready else 0
            monitor=dict(phase='warmup',warmup_reads=reads,reader_path='/owned' if ready else None,
                failure_latched=False,raw_reader=dict(completed=ready))
            row=state.observe(now,ready);row.update(warmup_reads=reads,reader_path=monitor['reader_path'])
            rows.append(row);samples.append(dict(phase='warmup',position=dict(timestamp=now)));monitors.append(monitor)
        return rows,samples,monitors
    def test_exact_thirty_second_boundary(self):
        self.assertEqual(offline.replay_rows(*self.fixture())['elapsed_us'],30000000)
    def test_pending_file_does_not_start_clock(self):
        self.assertEqual(offline.replay_rows(*self.fixture(True))['first_prepared_sample_us'],40000000)
    def test_each_missing_or_extra_receipt_rejected(self):
        for which in range(3):
            for change in ('missing','extra'):
                data=self.fixture()
                if change=='missing':data[which].pop()
                else:data[which].append(copy.deepcopy(data[which][-1]))
                with self.subTest(which=which,change=change),self.assertRaises(ValueError):offline.replay_rows(*data)
    def test_forged_field_rejected(self):
        for key,value in dict(timestamp_us=1,first_prepared_sample_us=1,elapsed_us=30000000,minimum_us=1,
            ready=True,prepared=False,execution_authority_granted=True,warmup_reads=99,reader_path='/other').items():
            data=self.fixture();data[0][1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):offline.replay_rows(*data)
    def test_no_boundary_or_duplicate_or_backward(self):
        for now in (68523999,50000000,49999999,float('nan'),True):
            data=self.fixture();data[1][-1]['position']['timestamp']=now
            with self.subTest(now=now),self.assertRaises(ValueError):offline.replay_rows(*data)
    def test_missing_readiness_and_extra_sample_after_ready(self):
        data=self.fixture();data[0][-1]['ready']=False
        with self.assertRaises(ValueError):offline.replay_rows(*data)
        data=self.fixture()
        for part in data:part.append(copy.deepcopy(part[-1]))
        with self.assertRaises(ValueError):offline.replay_rows(*data)
    def test_reader_lost_or_failed(self):
        for key,value in (('failure_latched',True),('reader_path',None),('warmup_reads',False),('warmup_reads',0)):
            data=self.fixture();data[2][2][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):offline.replay_rows(*data)
    def test_type_substitution_and_extra_fields(self):
        for key,value in (('minimum_us',30000000.0),('ready',1),('extra',False)):
            data=self.fixture();data[0][-1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):offline.replay_rows(*data)
    def test_file_proof_and_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=self.fixture()
            for name,rows in zip(('r03_warmup10.jsonl','samples.jsonl','r03_prearm04_timing.jsonl'),data):
                (root/name).write_text(''.join(json.dumps(row)+'\n' for row in rows))
            self.assertEqual(len(offline.check(root)['sha256']),3)
            (root/'r03_warmup10.jsonl').unlink()
            with self.assertRaises(FileNotFoundError):offline.check(root)

if __name__=='__main__':unittest.main(verbosity=2)
