#!/usr/bin/env python3
"""Result-only completeness checks, not extra flight or controller tests."""
import copy
import unittest

import collect


def complete():
    jobs = collect.common.jobs()
    return dict(success=True, planned=48, parameter_restore_exact=True, remaining_simulators=[],
        H_gate='accepted24', V_PID_safety_gate='accepted_budgeted_run25',
        attempts=[dict(attempt=i, status='accepted', job=j) for i,j in enumerate(jobs,1)],
        pairs=[dict(task=j['task'],seed=j['seed'],candidate=j['candidate'],axes=j['axes'],
                    accepted=True,checks={'frozen_gate':True}) for j in jobs if j['axes']])


def rows():
    return [dict(task=j['task'],candidate=j['candidate'],seed=j['seed'],
                 rmse_m_s=[1.,2.,3.],position_rmse_m=[.1,.2,.3],yaw_rmse_rad=.01,
                 correction_tv_per_s=[2.,3.,4.],acceleration_tv_per_s=[3.,4.,5.],
                 normalized_thrust_tv_per_s=[.2,.3,.4],common_0_7hz_rms=[.1,.1,.1],
                 constraint_fraction=0.,update_hz=100.) for j in collect.common.jobs()]


class CollectTest(unittest.TestCase):
    def reject(self, ledger):
        with self.assertRaises(ValueError):
            collect.validate_ledger(ledger, collect.common.jobs())

    def test_complete(self):
        self.assertTrue(collect.validate_ledger(complete(), collect.common.jobs()))

    def test_missing(self):
        x=complete(); x['attempts'].pop(); self.reject(x)

    def test_reordered(self):
        x=complete(); x['attempts'][1:3]=reversed(x['attempts'][1:3]); self.reject(x)

    def test_duplicate_attempt(self):
        x=complete(); x['attempts'][4]['attempt']=4; self.reject(x)

    def test_failed_attempt(self):
        x=complete(); x['attempts'][-1]['status']='failed'; self.reject(x)

    def test_failed_pair(self):
        x=complete(); x['pairs'][0]['checks']['frozen_gate']=False; self.reject(x)

    def test_missing_pair(self):
        x=complete(); x['pairs'].pop(); self.reject(x)

    def test_changed_seed(self):
        x=copy.deepcopy(complete()); x['attempts'][1]['job']['seed']=52001; self.reject(x)

    def test_cleanup(self):
        for field,value in [('parameter_restore_exact',False),('remaining_simulators',[1234]),
                            ('H_gate',None),('V_PID_safety_gate',None),('success',False)]:
            with self.subTest(field=field):
                x=complete(); x[field]=value; self.reject(x)

    def test_group_means(self):
        result=collect.aggregate(rows())
        self.assertEqual(result['H']['X']['rmse_m_s']['mean'],[1.,2.,3.])
        self.assertEqual(result['V']['XYZ']['n'],3)

    def test_group_missing_or_duplicate_seed(self):
        for x in (rows()[:-1],rows()):
            if len(x)==48: x[8]['seed']=x[0]['seed']
            with self.assertRaises(ValueError): collect.aggregate(x)

    def test_nonfinite(self):
        for value in (float('nan'),float('inf')):
            x=rows(); x[0]['rmse_m_s'][0]=value
            with self.assertRaises(ValueError): collect.aggregate(x)


if __name__=='__main__': unittest.main()
