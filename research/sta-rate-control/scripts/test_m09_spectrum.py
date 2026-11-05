"""PSD normalization must hold for both odd and even update counts."""
import unittest
import numpy as np
from analyze_m09 import spectrum


class SpectrumNormalizationTest(unittest.TestCase):
    def test_parseval_even_and_odd_windows(self):
        for count in (8,9,101):
            x=np.tile(np.arange(count,dtype=float)[:,None],(1,3))
            f,p=spectrum(x,250)
            w=np.hanning(count)
            expected=np.sum(((x-x.mean(axis=0))*w[:,None])**2,axis=0)/np.sum(w*w)
            np.testing.assert_allclose(np.sum(p,axis=0)*(f[1]-f[0]),expected,rtol=1e-13,atol=1e-13)


if __name__=='__main__':unittest.main()
