import unittest
import final_package as f

class Package(unittest.TestCase):
    def test_complete_formal_only(self):
        rows=f.formal_rows(dict(PID=0,RSTA=1,RISTA=2));self.assertEqual(len(rows),200)
        self.assertTrue(all(r['status']=='unattempted' and r['flight_authorized'] is False for r in rows))
    def test_A_stays_baseline_not_B_tuned(self):
        rows=f.formal_rows(dict(PID=0,RSTA=0,RISTA=2))
        self.assertEqual({r['candidate_index'] for r in rows if r['group']=='A'},{1})
        self.assertEqual({r['candidate_index'] for r in rows if r['group']=='B' and r['candidate']=='RISTA'},{2})
    def test_A_parameters_common(self):
        rows=f.formal_rows(dict(PID=0,RSTA=0,RISTA=2));block=[r for r in rows if r['group']=='A' and r['block']==1 and r['task']=='H']
        self.assertEqual({k:v for k,v in block[0]['parameters'].items() if k!='MPC_VC_MODE'},
                         {k:v for k,v in block[1]['parameters'].items() if k!='MPC_VC_MODE'})
    def test_B_complete127_each(self):
        self.assertTrue(all(len(r['parameters'])==127 for r in f.formal_rows(dict(PID=0,RSTA=1,RISTA=2))))
    def test_missing_selection_rejected(self):
        with self.assertRaises(ValueError):f.formal_rows(dict(PID=0,RSTA=1))
    def test_unknown_candidate_rejected(self):
        with self.assertRaises(ValueError):f.formal_rows(dict(PID=0,RSTA=1,RISTA=3))
    def test_parameter_fingerprints_change_with_B_only(self):
        x=f.formal_rows(dict(PID=1,RSTA=1,RISTA=1));y=f.formal_rows(dict(PID=1,RSTA=1,RISTA=2))
        for a,b in zip(x,y):
            changed=a['group']=='B' and a['candidate']=='RISTA'
            self.assertEqual(a['parameters_sha256']!=b['parameters_sha256'],changed)

if __name__=='__main__':unittest.main()
