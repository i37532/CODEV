import json
import unittest
from replay_batch import compare_metrics

def encode(x):return (json.dumps(x,indent=2)+'\n').encode()

class ReplayTests(unittest.TestCase):
    def test_exact_bytes(self):
        a=encode({'cli_receipts':{'counts':{'a':1,'b':2}},'rmse':.01})
        self.assertTrue(compare_metrics(a,a)['bytes_identical'])
    def test_only_counts_order(self):
        a=encode({'cli_receipts':{'counts':{'a':1,'b':2}},'rmse':.01})
        b=encode({'cli_receipts':{'counts':{'b':2,'a':1}},'rmse':.01})
        self.assertTrue(compare_metrics(a,b)['counts_order_only'])
    def test_value_key_type_and_other_order_changes_rejected(self):
        a=encode({'cli_receipts':{'counts':{'a':1,'b':2}},'rmse':.01})
        for b in [
            {'cli_receipts':{'counts':{'b':3,'a':1}},'rmse':.01},
            {'cli_receipts':{'counts':{'b':2,'a':1.}},'rmse':.01},
            {'cli_receipts':{'counts':{'b':2,'a':1}},'rmse':.02},
            {'cli_receipts':{'counts':{'b':2}},'rmse':.01},
            {'rmse':.01,'cli_receipts':{'counts':{'b':2,'a':1}}},
        ]:
            with self.assertRaises(ValueError):compare_metrics(a,encode(b))

if __name__=='__main__':unittest.main(verbosity=2)
