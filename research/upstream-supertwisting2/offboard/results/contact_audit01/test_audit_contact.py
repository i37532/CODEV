import unittest
import numpy as np
from audit_contact import causal_index, own_origin_height, optional_row


class AlignmentTests(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(causal_index([10,20,30],20,0),1)

    def test_never_future(self):
        self.assertEqual(causal_index([10,20,30],29,9),1)

    def test_stale(self):
        with self.assertRaises(ValueError):causal_index([10,20,30],29,8)

    def test_before_first(self):
        with self.assertRaises(ValueError):causal_index([10,20],9,100)

    def test_duplicate(self):
        with self.assertRaises(ValueError):causal_index([10,10],10,100)

    def test_reversed(self):
        with self.assertRaises(ValueError):causal_index([20,10],20,100)

    def test_empty(self):
        with self.assertRaises(ValueError):causal_index([],20,100)

    def test_zero_clock_not_valid_sample_clock(self):
        with self.assertRaises(ValueError):causal_index([0,0],20,100)

    def test_independent_origins(self):
        np.testing.assert_allclose(own_origin_height([.73,-1.77],.73),[0,2.5])
        np.testing.assert_allclose(own_origin_height([-.01,-2.51],-.01),[0,2.5])

    def test_origin_shift_invariant(self):
        np.testing.assert_allclose(own_origin_height([8.,9.],10.),own_origin_height([18.,19.],20.))

    def test_ned_sign(self):
        self.assertEqual(float(own_origin_height(.51,-.01)),-.52)

    def test_nan(self):
        with self.assertRaises(ValueError):own_origin_height([0,float('nan')],0)

    def test_inf_reference(self):
        with self.assertRaises(ValueError):own_origin_height([0],float('inf'))

    def test_inactive_optional_topic_remains_missing(self):
        d={'timestamp':np.array([1000]),'value':np.array([2.])}
        r=optional_row(d,1001001,['timestamp','value'])
        self.assertFalse(r['available'])
        self.assertNotIn('values',r)


if __name__=='__main__':unittest.main()
