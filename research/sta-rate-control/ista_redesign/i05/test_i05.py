#!/usr/bin/env python3
import unittest
from design import jobs
from analyze import summarize

class I05A(unittest.TestCase):
    def test_manifest(self):
        f,j=jobs('a'*40,'A');self.assertEqual(len(j),6);self.assertEqual({x['mode'] for x in j},{1,3})
        self.assertTrue(all(x['parameters']['MC_STA_AXES']==3 and x['parameters']['MC_RTC_DIV']==1 for x in j))
    def test_gate(self):
        rows=[]
        for seed in (6301,6302,6303):
            for algorithm in ('esta','proper_ista'):
                metrics={w:{'rmse':[.01,.01,.01]} for w in ('hover','tracking','roll_only','pitch_only','synchronous')}
                rows.append(dict(success=True,algorithm=algorithm,seed=seed,metrics=metrics))
        self.assertTrue(summarize(rows)['success']);rows[-1]['metrics']['pitch_only']['rmse'][1]=.013
        self.assertFalse(summarize(rows)['success'])
if __name__=='__main__':unittest.main()
