"""Actual finite design, candidate and deterministic selection regression."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import protocol as p

selection=p.load_file('_ri06_selection_test',Path(__file__).with_name('choose_candidate.py'))

class Design(unittest.TestCase):
    def test_exact54_and200(self):
        d=p.design();self.assertEqual(len(d['jobs']),54);self.assertEqual(len(d['formal_jobs']),200)
        self.assertEqual([j['id'] for j in d['jobs']],[f'run{i:03d}' for i in range(1,55)])
    def test_equal_budgets(self):
        rows=p.templates()
        for a,_ in p.ALGORITHMS:
            self.assertEqual(sum(j['candidate']==a and j['phase']=='training' for j in rows),12)
            self.assertEqual(sum(j['candidate']==a and j['phase']=='validation' for j in rows),6)
    def test_training_blocks(self):
        for gate in ('TH','TV'):
            rows=p.jobs(gate)
            for k in range(0,18,3):
                self.assertEqual(rows[k]['mode'],0)
                self.assertEqual({j['mode'] for j in rows[k:k+3]},{0,3,4})
                self.assertEqual(len({(j['seed'],j['candidate_index']) for j in rows[k:k+3]}),1)
    def test_train_validation_formal_isolation(self):
        sets=[set(p.GATES[g]['seeds']) for g in ('TH','VH')]+[set(s) for s in p.FORMAL_SEEDS.values()]
        for i,s in enumerate(sets):
            for t in sets[i+1:]:self.assertFalse(s&t)
        self.assertEqual(p.GATES['TH']['seeds'],p.GATES['TV']['seeds'])
    def test_xyz_both_tasks(self):
        for j in p.templates():self.assertEqual(j['axes'],7 if j['mode'] else 0)
    def test_formal80_120_no_authority(self):
        rows=p.formal_templates()
        self.assertEqual(sum(j['group']=='A' for j in rows),80)
        self.assertEqual(sum(j['group']=='B' for j in rows),120)
        self.assertTrue(all(j['status']=='unattempted' and j['flight_authorized'] is False for j in rows))
    def test_all127_no_inner_change(self):
        for a,_ in p.ALGORITHMS:
            for i in range(3):
                v=p.candidate_parameters(a,i,'H');self.assertEqual(len(v),127)
                for k,x in dict(MC_RTC_MODE=0,MC_STA_AXES=0,MC_RTC_DIV=1,MC_RATT_TEST=0,MC_STA_TKO_MGT=0,MPC_VC_DIV=1).items():self.assertEqual(v[k],x)
    def test_epsilon_and_limits_fixed(self):
        base=p.fixed_parameters()
        for a,_ in p.ALGORITHMS:
            for i in range(3):
                v=p.candidate_parameters(a,i,'V')
                for k in base:
                    if k.startswith(('MPC_VC_EPS','MPC_VC_A_','MPC_VC_NU')):self.assertEqual(v[k],base[k])
    def test_sta_candidate_equal_sources(self):
        for i in range(3):
            a=p.candidate_parameters('RSTA',i,'H');b=p.candidate_parameters('RISTA',i,'H')
            self.assertEqual({k:v for k,v in a.items() if k!='MPC_VC_MODE'},{k:v for k,v in b.items() if k!='MPC_VC_MODE'})
    def test_baseline_reproduces(self):
        for a,_ in p.ALGORITHMS:
            v=p.candidate_parameters(a,1,'H');o={'MPC_VC_MODE','MPC_VC_AXES','MPC_VCT_TEST'}
            self.assertEqual({k:x for k,x in v.items() if k not in o},{k:x for k,x in p.fixed_parameters().items() if k not in o})
    def test_unknown_candidates_rejected(self):
        for a,i,t in [('ESTA',1,'H'),('PID',True,'H'),('RISTA',3,'V'),('PID',0,'A')]:
            with self.assertRaises(ValueError):p.candidate_parameters(a,i,t)
    def test_validation_unselected_rejected(self):
        with patch.object(p,'selected',side_effect=ValueError('not selected')):
            with self.assertRaises(ValueError):p.jobs('VH')
    def test_manifest_changes_rejected(self):
        v=p.design();v['maximum_attempts']=55
        with self.assertRaises(ValueError):p.validate_manifest(v)
    def test_missing_prior_stops(self):
        with patch.object(p,'read',side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):p.require_prior_gate('TV')
    def test_formal_gate_rejected(self):
        for g in ('A','B','C','D','formal',None):
            with self.assertRaises(ValueError):p.valid_gate(g)
    def test_thresholds_unchanged(self):
        for gate in ('TH','TV'):
            d=p.load_protocol(gate)
            self.assertEqual(d['diagnostic_gate']['minimum_excitation_samples'],6390)
            self.assertEqual(d['diagnostic_gate']['minimum_excitation_span_s'],63.96)

def rows():
    return [dict(accepted=True,job=j,diagnostic=dict(J=.01,error=dict(rmse=[.01]*3),correction_tv_per_second=[.1]*3)) for g in ('TH','TV') for j in p.jobs(g)]

class Selection(unittest.TestCase):
    def test_tie_baseline(self):self.assertEqual(selection.choose(rows())['indices'],dict(PID=1,RSTA=1,RISTA=1))
    def test_improvement_selected(self):
        r=rows()
        for x in r:
            if x['job']['candidate_index']==2:x['diagnostic'].update(J=.005,error=dict(rmse=[.005]*3))
        self.assertEqual(selection.choose(r)['indices'],dict(PID=2,RSTA=2,RISTA=2))
    def test_missing_no_selection(self):
        with self.assertRaises(ValueError):selection.choose(rows()[:-1])
    def test_duplicate_no_selection(self):
        r=rows();r[-1]=r[0]
        with self.assertRaises(ValueError):selection.choose(r)
    def test_failure_no_fallback(self):
        r=rows();r[0]['accepted']=False
        with self.assertRaises(ValueError):selection.choose(r)
    def test_nonfinite_no_selection(self):
        r=rows();r[0]['diagnostic']['error']['rmse'][0]=float('nan')
        with self.assertRaises(ValueError):selection.choose(r)
    def test_wrong_j_rejected(self):
        r=rows();r[0]['diagnostic']['J']=.5
        with self.assertRaises(ValueError):selection.choose(r)
    def test_unregistered_parameter_rejected(self):
        r=rows();r[0]['job']['parameters']['MPC_VC_L1_Z']=20
        with self.assertRaises(ValueError):selection.choose(r)
    def test_tv_penalty(self):
        r=rows()[0];s=selection.score(r);r['diagnostic']['correction_tv_per_second']=[1]*3
        self.assertAlmostEqual(selection.score(r)-s,.09)

if __name__=='__main__':unittest.main()
