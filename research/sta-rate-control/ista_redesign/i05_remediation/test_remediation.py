#!/usr/bin/env python3
import unittest
from design import jobs
from summary import summarize
from design_rb import jobs as jobs_rb
from summary_rb import summarize as summarize_rb
from design_rc import jobs as jobs_rc
from summary_rc import summarize as summarize_rc
class TestRA(unittest.TestCase):
    def test_manifest(self):
        f,j=jobs('a'*40);self.assertEqual(len(j),10);self.assertEqual({x['seed'] for x in j},set(f['paired_seeds']))
    def test_paired_gate(self):
        rows=[]
        for s in range(6601,6606):
            for alg,val in [('esta',.004),('proper_ista',.0042)]:rows.append(dict(success=True,algorithm=alg,seed=s,metrics={w:{'rmse':[val,val,val]} for w in ('hover','tracking','roll_only','pitch_only','synchronous')}))
        self.assertTrue(summarize(rows)['success']);rows[-1]['metrics']['pitch_only']['rmse'][1]=.006;self.assertFalse(summarize(rows)['success'])
    def test_rb_manifest_and_gate(self):
        f,j=jobs_rb('b'*40);self.assertEqual(len(j),6);rows=[]
        for s in f['paired_seeds']:
            for alg,val in [('esta',.004),('proper_ista',.0041)]:rows.append(dict(success=True,algorithm=alg,seed=s,metrics={w:{'rmse':[val,val,val]} for w in ('yaw_only','synchronous_low','synchronous_repeat')}))
        self.assertTrue(summarize_rb(rows)['success']);rows[-1]['metrics']['yaw_only']['rmse'][2]=.006;self.assertFalse(summarize_rb(rows)['success'])
    def test_rc_manifest_and_gate(self):
        f,j=jobs_rc('c'*40);self.assertEqual(len(j),18);rows=[]
        for div in f['divisors']:
            for s in f['paired_seeds']:
                for alg,val in [('esta',.004),('proper_ista',.0041)]:rows.append(dict(success=True,algorithm=alg,seed=s,divisor=div,metrics={w:{'rmse':[val,val,val]} for w in ('yaw_only','synchronous_low','synchronous_repeat')}))
        self.assertTrue(summarize_rc(rows)['success']);rows[-1]['metrics']['synchronous_low']['rmse'][0]=.006;self.assertFalse(summarize_rc(rows)['success'])
if __name__=='__main__':unittest.main()
