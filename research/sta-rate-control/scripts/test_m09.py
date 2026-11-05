import os
import unittest
from unittest.mock import patch
import numpy as np
from analyze_m09 import tv, common_band, spectrum
from run_m09 import Checks


class M09Tests(unittest.TestCase):
    def test_frozen_configs_only_div_changes(self):
        for mode in (0,1,2):
            for div in (1,2,4):
                with patch.dict(os.environ,{'M09_MODE':str(mode),'M09_DIV':str(div)}):
                    c=Checks()
                    self.assertEqual(c.div,div);self.assertEqual(c.axes,7 if mode else 0)
                    self.assertEqual(c.config['MC_STA_L1_P'],2.0 if mode==2 else 2.4)
                    self.assertEqual(c.protocol['tracking_seconds'],36)
                    self.assertEqual(c.protocol['trigger'],4)

    def test_invalid_div_and_mode(self):
        for env in ({'M09_DIV':'3'},{'M09_MODE':'3'}):
            with patch.dict(os.environ,env):
                with self.assertRaises(ValueError):Checks()

    def test_tv_uses_actual_sequence_and_duration(self):
        t=np.array([1000,9000,17000]);x=np.array([[0,0,0],[1,-2,0],[-1,1,0]])
        r=tv(t,x);self.assertEqual(r['tv'],[3.,5.,0.]);self.assertEqual(r['duration_s'],.016)
        fixed=tv(t,x,.02);self.assertEqual(fixed['tv_per_s'],[150.,250.,0.])
        with self.assertRaises(ValueError):tv(np.array([1000,1000,9000]),x)

    def test_antialias_rejects_80hz_preserves_10hz(self):
        t=np.arange(10000)/250
        x=np.column_stack([np.sin(2*np.pi*f*t) for f in (10,80,40)])
        y,hz=common_band(x,250)
        self.assertEqual(hz,62.5)
        rms=np.sqrt(np.mean(y*y,axis=0))
        self.assertLess(abs(rms[0]-np.sqrt(.5)),.002)
        self.assertLess(rms[1],1e-5);self.assertLess(rms[2],1e-5)

    def test_native_spectrum_distinct_from_common(self):
        t=np.arange(10000)/250
        x=np.tile(np.sin(2*np.pi*80*t)[:,None],(1,3))
        f,p=spectrum(x,250);self.assertAlmostEqual(f[np.argmax(p[:,0])],80)
        y,hz=common_band(x,250);cf,cp=spectrum(y,hz)
        self.assertLessEqual(cf.max(),31.25+1e-12);self.assertLess(cp.max(),1e-8)


if __name__=='__main__':unittest.main()
