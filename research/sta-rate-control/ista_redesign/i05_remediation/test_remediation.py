#!/usr/bin/env python3
import unittest
from design import jobs
from summary import summarize
class TestRA(unittest.TestCase):
 def test_manifest(self):
  f,j=jobs('a'*40);self.assertEqual(len(j),10);self.assertEqual({x['seed'] for x in j},set(f['paired_seeds']))
 def test_paired_gate(self):
  rows=[]
  for s in range(6601,6606):
   for alg,val in [('esta',.004),('proper_ista',.0042)]:rows.append(dict(success=True,algorithm=alg,seed=s,metrics={w:{'rmse':[val,val,val]} for w in ('hover','tracking','roll_only','pitch_only','synchronous')}))
  self.assertTrue(summarize(rows)['success']);rows[-1]['metrics']['pitch_only']['rmse'][1]=.006;self.assertFalse(summarize(rows)['success'])
if __name__=='__main__':unittest.main()
