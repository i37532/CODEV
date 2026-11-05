"""Draft-only offline tests; never imports or calls a flight entry."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import numpy as np
import scenario

spec=importlib.util.spec_from_file_location('v08_statistics',Path(__file__).with_name('paired_statistics.py'))
stats=importlib.util.module_from_spec(spec);spec.loader.exec_module(stats)

class DesignTest(unittest.TestCase):
    def test_force_bounds_zero_endpoints_and_frame(self):
        t=np.linspace(-20,100,30001);f=scenario.force_enu(t,[.4,.7])
        self.assertTrue(np.all(np.linalg.norm(f,axis=1)<=.15*np.sqrt(2)+1e-12))
        self.assertTrue(np.all(f[(t<=8)|(t>=56)]==0));self.assertTrue(np.all(f[:,2]==0))
        t=20.;f=scenario.force_enu(t,[.4,.7]);e=np.sin(np.pi*12/48)**2
        self.assertAlmostEqual(f[1],.15*e*np.sin(2*np.pi*12/16+.4))
        self.assertAlmostEqual(f[0],.15*e*np.sin(2*np.pi*12/24+.7))

    def test_force_continuous_slope_at_boundaries(self):
        for boundary in (8.,56.):
            f=scenario.force_enu(np.array([boundary-1e-5,boundary,boundary+1e-5]),[.4,.7])
            self.assertLess(np.max(abs(np.diff(f,axis=0)))/1e-5,1e-7)

    def test_invalid_force_and_trigger(self):
        for value in (float('nan'),float('inf')):
            with self.assertRaises(ValueError):scenario.force_enu(value,[0.,0.])
            with self.assertRaises(ValueError):scenario.force_enu(10,[value,0.])
        for t in (-1,1.5,float('nan')):
            with self.assertRaises(ValueError):scenario.trigger_origin(dict(excitation_time=t,timestamp_sample=2000000))

    def test_mass_scales_every_link_preserving_pose_and_source(self):
        for name in ('iris','gps'):
            root=ET.parse(scenario.REPO/f'Tools/sitl_gazebo/models/{name}/{name}.sdf').getroot()
            original=ET.tostring(root);before=scenario.inertials(root);after=scenario.inertials(scenario.scale_density(root,1.1))
            self.assertEqual(ET.tostring(root),original)
            for key in before:
                self.assertEqual(before[key]['cog'],after[key]['cog'])
                self.assertAlmostEqual(after[key]['mass'],1.1*before[key]['mass'])
                for axis in before[key]['inertia']:self.assertAlmostEqual(after[key]['inertia'][axis],before[key]['inertia'][axis]*1.1)

    def test_model_whitelist_rejects_unrelated_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);plugins=root/'plugins';lib=root/'libforce.so'
            job=dict(scene='mass',seed=38201)
            scenario.prepare_model(root,plugins,lib,job)
            tree=ET.parse(root/'models/iris/iris.sdf');tree.find('./model/link/inertial/mass').text='99'
            tree.write(root/'models/iris/iris.sdf')
            with self.assertRaises(ValueError):scenario.verify_model(root,plugins,lib,job)

    def rows(self):
        return [dict(scene=scene,seed=seed,mode=mode,status='accepted',xy_rmse=.01-.002*mode+.00001*seed)
                for scene in stats.SCENES for seed in range(1,21) for mode in (0,1)]

    def test_pair_differences_no_frame_replication(self):
        r=stats.paired_summary(self.rows(),list(range(1,21)))
        self.assertEqual(r['accepted'],200)
        for scene in stats.SCENES:
            self.assertEqual(r['scenes'][scene]['complete_pairs'],20)
            self.assertAlmostEqual(r['scenes'][scene]['paired_mean_difference_m_s'],-.002)

    def test_missing_pairs_and_no_zero_imputation(self):
        rows=self.rows();rows[0]['status']='failed';rows[0].pop('xy_rmse')
        rows[2]['status']='invalid';rows[2].pop('xy_rmse')
        rows[4]['status']='unattempted';rows[4].pop('xy_rmse')
        r=stats.paired_summary(rows,list(range(1,21)))
        self.assertEqual(r['scenes']['hover']['complete_pairs'],17)
        self.assertEqual(r['scenes']['hover']['acceptance']['0']['count'],17)
        self.assertEqual(r['scenes']['hover']['acceptance']['0']['attempted'],19)
        self.assertAlmostEqual(r['scenes']['hover']['acceptance']['0']['fraction_of_attempted'],17/19)
        self.assertFalse(r['complete_manifest_executed'])
        self.assertAlmostEqual(r['scenes']['hover']['paired_mean_difference_m_s'],-.002)

    def test_invalid_duplicate_or_missing_manifest_rejected(self):
        rows=self.rows()
        for values in (rows[:-1],rows+[rows[0]]):
            with self.assertRaises(ValueError):stats.paired_summary(values,list(range(1,21)))
        rows[0]['xy_rmse']=float('nan')
        with self.assertRaises(ValueError):stats.paired_summary(rows,list(range(1,21)))

    def test_wilson_endpoints_and_precision(self):
        self.assertEqual(stats.wilson(0,20)[0],0.)
        self.assertAlmostEqual(stats.wilson(20,20)[1],1.)
        self.assertGreater(stats.precision_projection([-.001,0,.001])['n20_approximate_95_halfwidth_m_s'],0)

    def test_acceptance_rate_not_raw_count_with_unequal_attempts(self):
        rows=self.rows()
        for row in rows:
            if row['scene']!='hover':continue
            if row['mode']==0 and row['seed']>5:row['status']='unattempted';row.pop('xy_rmse')
            if row['mode']==1 and row['seed']>10:row['status']='failed';row.pop('xy_rmse')
        result=stats.paired_summary(rows,list(range(1,21)))['scenes']['hover']
        self.assertEqual(result['acceptance']['0']['fraction_of_attempted'],1)
        self.assertEqual(result['acceptance']['1']['fraction_of_attempted'],.5)
        self.assertFalse(result['acceptance_not_lower'])

if __name__=='__main__':unittest.main(verbosity=2)
