import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('readiness_under_test',HERE/'readiness.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Warmup(unittest.TestCase):
    def test_actual_late_restart_clock_boundary(self):
        r=m.Readiness();self.assertFalse(r.observe(38_524_000,True)['ready'])
        self.assertFalse(r.observe(68_523_999,True)['ready'])
        self.assertTrue(r.observe(68_524_000,True)['ready'])

    def test_early_restart_still_requires_relative_interval(self):
        r=m.Readiness();r.observe(2_000_000,True)
        self.assertFalse(r.observe(30_000_001,True)['ready'])
        self.assertTrue(r.observe(32_000_000,True)['ready'])

    def test_first_complete_read_anchors_interval(self):
        r=m.Readiness();self.assertIsNone(r.observe(30_000_000,False)['elapsed_us'])
        self.assertFalse(r.observe(60_000_000,True)['ready'])
        self.assertTrue(r.observe(90_000_000,True)['ready'])

    def test_missing_preparation_never_ready(self):
        r=m.Readiness()
        for t in (1,30_000_000,180_000_000):self.assertFalse(r.observe(t,False)['ready'])

    def test_irregular_time_not_iteration_count(self):
        r=m.Readiness()
        for t in (1,10001,20000001,29999999):self.assertFalse(r.observe(t,True)['ready'])
        self.assertTrue(r.observe(30000001,True)['ready'])

    def test_duplicate_backward_latch(self):
        for t in (10,9):
            r=m.Readiness();r.observe(10,True)
            with self.assertRaises(ValueError):r.observe(t,True)
            with self.assertRaises(ValueError):r.observe(30_000_100,True)

    def test_invalid_numbers_latch(self):
        for t in (0,-1,True,None,'1',1.5,float('nan'),float('inf'),2**53):
            with self.subTest(t=t):
                r=m.Readiness()
                with self.assertRaises(ValueError):r.observe(t,True)
                self.assertTrue(r.failed)

    def test_prepared_requires_boolean(self):
        for v in (0,1,None,'yes'):
            with self.assertRaises(ValueError):m.Readiness().observe(1,v)

    def test_prepared_log_loss_latches(self):
        r=m.Readiness();r.observe(1,True)
        with self.assertRaises(ValueError):r.observe(2,False)

    def test_state_isolation(self):
        a,b=m.Readiness(),m.Readiness();a.observe(1,True)
        self.assertFalse(b.observe(40_000_000,True)['ready'])
        self.assertTrue(a.observe(30_000_001,True)['ready']);self.assertFalse(b.ready)

    def test_start_requires_complete_and_no_repeated_warmup(self):
        obj=SimpleNamespace()
        with self.assertRaises(ValueError):m.require_ready(obj)
        obj._warmup10=m.Readiness();obj._warmup10.observe(1,True)
        with self.assertRaises(ValueError):m.require_ready(obj)
        obj._warmup10.observe(30_000_001,True);m.require_ready(obj)
        with self.assertRaises(ValueError):obj._warmup10.observe(30_000_002,True)
        with self.assertRaises(ValueError):m.require_ready(obj)

    def test_wrapper_receipt_is_not_authority(self):
        state=dict(reader=SimpleNamespace(path=Path('/tmp/synthetic.ulg'),last_timing={'completed':True}),failed=False,warmup_reads=1)
        obj=SimpleNamespace(_prearm_state=lambda:state)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(m.warmup_ready(obj,{'position':{'timestamp':38_524_000}},tmp))
            state['warmup_reads']=31
            self.assertTrue(m.warmup_ready(obj,{'position':{'timestamp':68_524_000}},tmp))
            rows=[json.loads(x) for x in (Path(tmp)/m.RECEIPT).read_text().splitlines()]
            self.assertEqual(rows[-1]['elapsed_us'],30_000_000)
            self.assertFalse(rows[-1]['execution_authority_granted']);m.require_ready(obj)

    def test_wrapper_preserves_existing_failure(self):
        obj=SimpleNamespace(_prearm_state=lambda:dict(reader=None,failed=True,warmup_reads=0))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):m.warmup_ready(obj,{'position':{'timestamp':1}},tmp)
            self.assertTrue(obj._warmup10.failed)


if __name__=='__main__':unittest.main(verbosity=2)
