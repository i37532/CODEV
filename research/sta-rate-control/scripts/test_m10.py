"""Prospective design/analysis checks; no simulator is launched here."""
import unittest
import numpy as np
from m10_design import candidate,equal_gains,scenario,select,formal_jobs,fixed_parameters,TRAIN_SEEDS,PILOT_SEEDS,TEST_SEEDS
from analyze_m10 import recovery
from summarize_m10 import paired_interval,wilson
from analyze_m09 import fixed_tracking_window,tv
from run_m10 import scale_inertia,check_param_show,trigger_origin,REPO
import xml.etree.ElementTree as ET
from adjudicate_prearm_gap_m10 import check_gap


class M10Test(unittest.TestCase):
    def test_retained_prearm_gap_is_narrow(self):
        seq=np.array([1,2,4,5,6]);d=dict(publish_seq=seq,timestamp_sample=seq*4000,
            armed=np.array([False,False,False,True,True]),effective_mode=np.ones(5),effective_axes=np.ones(5)*7)
        for k in ('fault','abort_requested','termination','pending','config_pending','div_wait'):d[k]=np.zeros(5)
        self.assertEqual(check_gap(d,[],1),1)
        with self.assertRaises(AssertionError):check_gap(d,[1],1)
        d['armed'][2]=True
        with self.assertRaises(AssertionError):check_gap(d,[],1)
        d['armed'][2]=False;d['fault'][4]=1
        with self.assertRaises(AssertionError):check_gap(d,[],1)

    def test_trigger_origin_not_host_arrival(self):
        for latency in (.004,.208,.58,1.49):
            self.assertAlmostEqual(trigger_origin(dict(timestamp_sample=(60+latency)*1e6,research_elapsed=latency)),60.)
        for invalid in ({},dict(timestamp_sample=60e6,research_elapsed=-1),
                        dict(timestamp_sample=60e6,research_elapsed=1.5),
                        dict(timestamp_sample=float('nan'),research_elapsed=0)):
            with self.assertRaises(RuntimeError):trigger_origin(invalid)

    def test_prearm_parameter_snapshot(self):
        raw='x + IMU_GYRO_CUTOFF [1,22] : 30.0000\nx   SYS_AUTOSTART [2,23] : 10016\n'
        check_param_show(raw,dict(IMU_GYRO_CUTOFF=30.,SYS_AUTOSTART=10016))
        with self.assertRaises(RuntimeError):check_param_show(raw,dict(IMU_GYRO_CUTOFF=31.))
        with self.assertRaises(RuntimeError):check_param_show(raw,dict(MC_ROLL_P=6.))

    def test_success_intervals(self):
        zero=wilson(0,20);full=wilson(20,20)
        self.assertAlmostEqual(zero[0],0);self.assertAlmostEqual(full[1],1)
        self.assertAlmostEqual(zero[1],1-full[0]);self.assertLess(zero[1],.17)
        with self.assertRaises(ValueError):wilson(0,0)

    def test_freeze_nonexperimental_parameters(self):
        p=dict(candidate(0,1),COM_FLIGHT_UUID=12,MC_RATT_TEST=4,IMU_GYRO_CUTOFF=30.,MC_ROLL_P=6.,SYS_AUTOSTART=10016)
        self.assertEqual(fixed_parameters(p),dict(IMU_GYRO_CUTOFF=30.,MC_ROLL_P=6.,SYS_AUTOSTART=10016))

    def test_physical_inertia_and_fixed_mass(self):
        for name in ('iris','gps'):
            tree=ET.parse(REPO/f'Tools/sitl_gazebo/models/{name}/{name}.sdf').getroot()
            masses=[x.text for x in tree.findall('.//link/inertial/mass')]
            values=[float(x.text) for x in tree.findall('.//link/inertial/inertia/*')]
            scale_inertia(tree,1.2)
            self.assertEqual(masses,[x.text for x in tree.findall('.//link/inertial/mass')])
            np.testing.assert_allclose([float(x.text) for x in tree.findall('.//link/inertial/inertia/*')],np.array(values)*1.2)
            with self.assertRaises(ValueError):scale_inertia(tree,-1)

    def test_repeated_elapsed_boundary(self):
        t=np.arange(9004,dtype=np.int64)*4000+1000000
        elapsed=np.maximum(0,(t-t[1])*1e-6)
        mask=fixed_tracking_window(t,elapsed,np.ones(len(t),bool))
        self.assertEqual(int(mask.sum()),9000)
        self.assertEqual(int(t[mask][-1]-t[mask][0]),35996000)
        tv(t[mask],np.zeros((9000,3)),36.)

    def test_paired_bootstrap(self):
        r=paired_interval([1.,1.,1.]);self.assertEqual(r['ci95'],[1.,1.])
        self.assertEqual(r,paired_interval([1.,1.,1.]))
        r=paired_interval([-1.,0.,1.,2.])
        self.assertLessEqual(r['family_interval'][0],r['ci95'][0])
        self.assertGreaterEqual(r['family_interval'][1],r['ci95'][1])
        with self.assertRaises(ValueError):paired_interval([1.])

    def test_equal_gain_group(self):
        a=equal_gains(1);b=equal_gains(2);a.pop('MC_RTC_MODE');b.pop('MC_RTC_MODE')
        self.assertEqual(a,b);self.assertEqual(a['MC_STA_L1_P'],2.4)

    def test_disjoint_seeds(self):
        self.assertFalse(set(TRAIN_SEEDS)&set(PILOT_SEEDS))
        self.assertFalse(set(TRAIN_SEEDS+PILOT_SEEDS)&set(TEST_SEEDS))
        self.assertEqual(len(TEST_SEEDS),20)

    def test_seeded_scenarios(self):
        self.assertEqual(scenario('torque',3101),scenario('torque',3101))
        self.assertNotEqual(scenario('torque',3101)['torque_phases'],scenario('torque',3102)['torque_phases'])
        self.assertEqual(scenario('inertia',1)['inertia_scale'],1.2)
        self.assertEqual(scenario('noise',1)['gyro_density_scale'],2.)

    def test_candidates_and_fixed_mapping(self):
        for mode in range(3):
            p=candidate(mode,1)
            for i in range(3):
                q=candidate(mode,i)
                for axis in 'RPY':self.assertEqual(p['MC_STA_G_'+axis],q['MC_STA_G_'+axis])
            if mode==0:self.assertAlmostEqual(candidate(mode,0)['MC_ROLLRATE_P'],.1275)

    def test_complete_manifest(self):
        frozen=dict(selection={str(m):dict(parameters=candidate(m,1)) for m in range(3)})
        jobs=formal_jobs(frozen)
        self.assertEqual(len(jobs),600)
        self.assertEqual(len({(j['scene'],j['seed'],j['mode'],j['group']) for j in jobs}),600)
        self.assertEqual(jobs,formal_jobs(frozen))

    def test_training_budget_failures(self):
        rows=[dict(mode=m,candidate=c,scene=s,seed=seed,success=True,rmse_tracking=[.01+c]*3)
              for m in range(3) for c in range(3) for s in ('nominal','torque') for seed in TRAIN_SEEDS]
        rows[0]['success']=False
        result=select(rows)
        self.assertEqual(result['selection']['0']['candidate'],1)
        self.assertEqual(result['selection']['1']['candidate'],0)
        with self.assertRaises(ValueError):select(rows[:-1])

    def test_recovery_hold_and_censor(self):
        t=np.arange(0,15,.004);e=np.ones((len(t),3))*.03;e[t>=4]=.01
        self.assertAlmostEqual(recovery(t,e,2)['time_s'],2)
        e[:]=.03;r=recovery(t,e,2)
        self.assertTrue(r['censored']);self.assertIsNone(r['time_s'])
        e[(t>3)&(t<3.5)]=0
        self.assertFalse(recovery(t,e,2)['recovered'])

    def test_recovery_exact_stop_microsecond_grid(self):
        t=(np.arange(1000,dtype=np.int64)*4000+70400000)*1e-6
        e=np.zeros((len(t),3))
        for start in (70.4,np.nextafter(70.4,np.inf),np.nextafter(70.4,-np.inf)):
            self.assertEqual(recovery(t,e,start)['time_s'],0.)

    def test_torque_bounds(self):
        t=np.arange(0,15,.004);q=np.zeros((len(t),3));m=(t>=2)&(t<=12)
        for seed in TEST_SEEDS:
            phase=np.array(scenario('torque',seed)['torque_phases'])
            q[m]=np.array([.004,.004,.002])*np.sin(np.pi*(t[m,None]-2)/10)**2*np.sin(2*np.pi*.4*(t[m,None]-2)+phase)
            self.assertLessEqual(abs(q).max(),.004)
            self.assertLess(abs(np.diff(q,axis=0)/.004).max(),.0115)


if __name__=='__main__':unittest.main()
