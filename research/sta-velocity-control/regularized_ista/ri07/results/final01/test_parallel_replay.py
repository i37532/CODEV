"""Offline orchestration tests: no decoder, simulator, or real experiment data."""
import importlib.util
from pathlib import Path
import threading
import time
import unittest

spec=importlib.util.spec_from_file_location('ri07_parallel_tested',Path(__file__).with_name('parallel_replay.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


class ParallelTests(unittest.TestCase):
    def test_order_survives_different_completion_order(self):
        def work(i):
            time.sleep((4-i)*.005);return i
        self.assertEqual(list(p.ordered_map(work,range(4),4)),list(range(4)))
    def test_worker_bound(self):
        lock=threading.Lock();state=[0,0]
        def work(i):
            with lock:state[0]+=1;state[1]=max(state)
            time.sleep(.01)
            with lock:state[0]-=1
            return i
        self.assertEqual(list(p.ordered_map(work,range(12),2)),list(range(12)))
        self.assertLessEqual(state[1],2);self.assertEqual(state[0],0)
    def test_single_worker(self):
        self.assertEqual(list(p.ordered_map(lambda x:x+1,range(3),1)),[1,2,3])
    def test_empty_input(self):
        self.assertEqual(list(p.ordered_map(lambda x:x,[],4)),[])
    def test_exceptions_not_passed(self):
        def fail(x):raise ValueError('test failure')
        with self.assertRaisesRegex(ValueError,'test failure'):list(p.ordered_map(fail,[1],2))
    def test_reject_zero(self):
        with self.assertRaises(ValueError):list(p.ordered_map(lambda x:x,[],0))
    def test_reject_unbounded_or_wrong_type(self):
        for value in (5,-1,True,2.0,'2'):
            with self.assertRaises(ValueError):list(p.ordered_map(lambda x:x,[],value))


if __name__=='__main__':unittest.main(verbosity=2)
