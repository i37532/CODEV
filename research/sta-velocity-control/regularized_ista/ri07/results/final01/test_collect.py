"""Post-run aggregation checks; synthetic fixtures never enter flight data."""
import copy
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np

spec=importlib.util.spec_from_file_location('ri07_collection_tests',Path(__file__).with_name('collect.py'))
c=importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


def rows():
    out=[]
    for group in ('A','B'):
        for block in range(1,21):
            for task in ('H','V'):
                for name in (('RSTA','RISTA') if group=='A' else ('PID','RSTA','RISTA')):
                    out.append(dict(job=dict(group=group,block=block,seed=(85000 if group=='A' else 85100)+block,
                        task=task,candidate=name), accepted=True,
                        J={'PID':.01,'RSTA':.005,'RISTA':.004}[name]+block*.00001))
    return out


class CollectionTests(unittest.TestCase):
    def test_exact_dimensions(self):
        a=c.paired_matrices(rows()); self.assertEqual(a['A'].shape,(20,2)); self.assertEqual(a['B'].shape,(20,6))
    def test_difference_direction(self):
        a=c.paired_matrices(rows()); np.testing.assert_allclose(a['A'],-.001)
    def test_b_order(self):
        a=c.paired_matrices(rows()); np.testing.assert_allclose(a['B'][0],[-.005,-.006,-.001]*2)
    def test_order_independent(self):
        a=c.paired_matrices(rows()); z=c.paired_matrices(list(reversed(rows())))
        np.testing.assert_array_equal(a['B'],z['B'])
    def test_duplicate_rejected(self):
        r=rows()
        with self.assertRaises(ValueError):c.paired_matrices(r+[r[0]])
    def test_bad_seed_rejected(self):
        r=rows(); r[0]['job']['seed']=85101
        with self.assertRaises(ValueError):c.paired_matrices(r)
    def test_zero_block_rejected(self):
        r=rows(); r[0]['job']['block']=0
        with self.assertRaises(ValueError):c.paired_matrices(r)
    def test_extra_block_rejected(self):
        r=rows(); r[0]['job']['block']=21
        with self.assertRaises(ValueError):c.paired_matrices(r)
    def test_bool_block_rejected(self):
        r=rows(); r[0]['job']['block']=True
        with self.assertRaises(ValueError):c.paired_matrices(r)
    def test_invalid_group_rejected(self):
        r=rows(); r[0]['job']['group']='C'
        with self.assertRaises(ValueError):c.paired_matrices(r)
    def test_invalid_task_rejected(self):
        r=rows(); r[0]['job']['task']='yaw'
        with self.assertRaises(ValueError):c.paired_matrices(r)
    def test_pid_in_a_rejected(self):
        r=rows(); r[0]['job']['candidate']='PID'
        with self.assertRaises(ValueError):c.paired_matrices(r)
    def test_old_esta_rejected(self):
        r=rows(); r[0]['job']['candidate']='ESTA'
        with self.assertRaises(ValueError):c.paired_matrices(r)
    def test_failed_not_zero(self):
        r=rows(); r[0]['accepted']=False; r[0]['J']=0
        self.assertTrue(math.isnan(c.paired_matrices(r)['A'][0,0]))
    def test_missing_not_zero(self):
        self.assertTrue(math.isnan(c.paired_matrices(rows()[1:])['A'][0,0]))
    def test_untouched_group_with_missing(self):
        np.testing.assert_allclose(c.paired_matrices(rows()[1:])['B'][0],[-.005,-.006,-.001]*2)
    def test_nonfinite_J_rejected(self):
        for value in (float('inf'),float('-inf'),float('nan'),True,'0.1'):
            r=rows(); r[0]['J']=value
            with self.assertRaises(ValueError):c.paired_matrices(r)
    def test_zero_metric_valid(self):
        r=rows(); r[0]['J']=0; self.assertTrue(math.isfinite(c.paired_matrices(r)['A'][0,0]))
    def test_vectors_require_xyz(self):
        with self.assertRaises(ValueError):c.vector([1,2])
    def test_vectors_reject_nan(self):
        with self.assertRaises(ValueError):c.vector([0,1,float('nan')])
    def test_finite_vector_unchanged(self):
        self.assertEqual(c.vector([-1,0,1]),[-1,0,1])
    def test_strict_json_rejects_nonfinite(self):
        with self.assertRaises(ValueError):c.strict({'J':float('inf')})
    def test_log_fingerprint_good(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'log.ulg'; p.write_bytes(b'fixture')
            self.assertEqual(c.verify_log(dict(archive=str(p),bytes=7,sha256=c.b.digest(p)))['bytes'],7)
    def test_log_size_changed(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'log.ulg'; p.write_bytes(b'fixture')
            with self.assertRaises(ValueError):c.verify_log(dict(archive=str(p),bytes=8,sha256=c.b.digest(p)))
    def test_log_hash_changed(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'log.ulg'; p.write_bytes(b'fixture')
            with self.assertRaises(ValueError):c.verify_log(dict(archive=str(p),bytes=7,sha256='0'*64))
    def test_common_complete_not_favourable_pairs(self):
        r=rows(); r[0]['accepted']=False; a=c.paired_matrices(r)['A']
        s=c.stats.summarize(a,'A',replicates=100)
        self.assertEqual(s['common_complete_blocks'],19)
        self.assertEqual([x['n'] for x in s['available_pairs']],[19,20])
        self.assertNotIn(1,s['included_blocks']); self.assertEqual(s['family_size'],8)
    def test_insufficient_n_no_ci(self):
        a=np.full((20,2),np.nan); a[0]=[-1,-2]
        self.assertIsNone(c.stats.summarize(a,'A',replicates=100)['primary_ci'])
    def test_shared_resampling_keeps_hv_correlation(self):
        a=np.stack([np.arange(20)/1000,2*np.arange(20)/1000],axis=1)
        s=c.stats.summarize(a,'A',replicates=1000)['primary_ci']
        np.testing.assert_allclose(s[1]['family95_bonferroni'],2*np.asarray(s[0]['family95_bonferroni']))
    def test_statistics_repeat_exact(self):
        a=c.paired_matrices(rows())['B']
        self.assertEqual(c.stats.summarize(a,'B',replicates=100),c.stats.summarize(a,'B',replicates=100))
    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'out.json'; c.write_new(p,{'x':1})
            with self.assertRaises(FileExistsError):c.write_new(p,{'x':2})
            self.assertEqual(c.b.read(p),{'x':1})
    def test_nominal_and_weighted_windows_exact(self):
        d=dict(seconds=64,windows=dict(first_half=dict(seconds=32),second_half=dict(seconds=32)))
        self.assertEqual(c.window_semantics(d,64)['weighted_main_seconds'],64)
    def test_unclipped_boundary_weights_preserved(self):
        d=dict(seconds=64.00399999999999,windows=dict(first_half=dict(seconds=32.004),second_half=dict(seconds=32)))
        r=c.window_semantics(d,64)
        self.assertEqual(r['nominal_main_seconds'],64)
        self.assertEqual(r['weighted_main_seconds'],d['seconds'])
        self.assertEqual(r['weighted_half_seconds']['first_half'],32.004)
    def test_wrong_nominal_window_rejected(self):
        d=dict(seconds=64,windows=dict(first_half=dict(seconds=32),second_half=dict(seconds=32)))
        for n in (32,64.004,True,'64'):
            with self.assertRaises(ValueError):c.window_semantics(d,n)
    def test_missing_half_rejected(self):
        with self.assertRaises(ValueError):c.window_semantics(dict(seconds=64,windows={}),64)
    def test_invalid_sample_weight_rejected(self):
        for n in (0,-1,float('nan'),float('inf'),True):
            d=dict(seconds=n,windows=dict(first_half=dict(seconds=32),second_half=dict(seconds=32)))
            with self.assertRaises(ValueError):c.window_semantics(d,64)
    def test_inconsistent_half_weight_sum_rejected(self):
        d=dict(seconds=64,windows=dict(first_half=dict(seconds=32.01),second_half=dict(seconds=32)))
        with self.assertRaises(ValueError):c.window_semantics(d,64)


if __name__=='__main__':unittest.main(verbosity=2)
