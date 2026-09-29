import copy
import unittest
import formal_design as design

class FormalDesignTests(unittest.TestCase):
    def selection(self):
        return dict(selected={'0':'pid2','1':'esta0'},parameters={str(m):dict(MPC_VC_MODE=m,MPC_VC_AXES=3*m,MPC_VC_DIV=1,MPC_VC_L1_Z=0,MPC_VC_L2_Z=0) for m in (0,1)})
    def test_exact_matrix_and_order_no_mutation(self):
        s=self.selection();original=copy.deepcopy(s);jobs=design.build_manifest(s)
        self.assertEqual(s,original);self.assertEqual(len(jobs),200)
        self.assertEqual({(j['scene'],j['seed'],j['mode']) for j in jobs},{(s,k,m) for s in design.SCENES for k in design.SEEDS for m in (0,1)})
        for i in range(0,200,2):
            a,b=jobs[i:i+2];self.assertEqual((a['scene'],a['seed']),(b['scene'],b['seed']))
            self.assertEqual({a['mode'],b['mode']},{0,1})
        self.assertEqual([j['id'] for j in jobs],[f'run{i:03d}' for i in range(1,201)])
    def test_no_formal_results_fabricated(self):
        rows=design.empty_outcomes(design.build_manifest(self.selection()))
        self.assertEqual({r['status'] for r in rows},{'unattempted'})
        self.assertFalse(any('xy_rmse' in r for r in rows))
    def test_paired_force_phase_and_scene_separation(self):
        jobs=design.build_manifest(self.selection())
        for i in range(0,200,2):
            a,b=jobs[i:i+2];self.assertEqual(a['force_phase_north_east'],b['force_phase_north_east'])
            self.assertEqual(a['density_scale'],1.1 if a['scene']=='mass' else 1.)
            self.assertEqual(a['force_phase_north_east'] is not None,a['scene']=='force')
    def test_invalid_z_mode_divisor_rejected(self):
        for k,v in [('MPC_VC_L1_Z',1),('MPC_VC_AXES',7),('MPC_VC_DIV',2),('MPC_VC_MODE',2)]:
            s=self.selection();s['parameters']['1'][k]=v
            with self.assertRaises(ValueError):design.build_manifest(s)

if __name__=='__main__':unittest.main(verbosity=2)
