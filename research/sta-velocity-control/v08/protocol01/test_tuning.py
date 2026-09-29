import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from common import REPO,CONFIG,design,candidates,jobs,load_protocol,require_authorization
from selection import score,select
from cadence import check

spec=importlib.util.spec_from_file_location('v07_fixture',REPO/'research/sta-velocity-control/v07/protocol07/test_cadence.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)

def esta_fixture(candidate='esta0'):
    d,q,j=old.fixture(1);j=copy.deepcopy(next(x for x in jobs() if x['candidate']==candidate))
    n=len(d['timestamp']);q['h'][:]=.01
    d.update(active_axes=np.full(n,3),committed_axes=np.full(n,3),pid_axes=np.full(n,4),
             sta_flags=np.zeros(n),constraint_bits=np.zeros(n))
    for axis,suffix in enumerate(('X','Y')):
        s=.0001*(1 if axis==0 else -1)*np.where(np.arange(n)%2==0,1.,-1.);nu=np.zeros(n+1)
        l1=j['parameters']['MPC_VC_L1_'+suffix];l2=j['parameters']['MPC_VC_L2_'+suffix]
        for k in range(n):nu[k+1]=nu[k]-.01*l2*np.sign(s[k])
        raw=-l1*np.sqrt(abs(s))*np.sign(s)+nu[:-1]
        d[f's[{axis}]']=s;d[f'nu_before[{axis}]']=nu[:-1];d[f'nu_ideal[{axis}]']=nu[1:]
        d[f'nu_applied[{axis}]']=nu[1:].copy();d[f'a_sta[{axis}]']=raw
        q[f'correction[{axis}]']=np.clip(raw,-.8,.8)
        d[f'a_req[{axis}]']=q[f'correction[{axis}]']+.1
        d[f'a_proxy[{axis}]']=d[f'a_req[{axis}]'].copy()
    return d,q,j

class TuningTest(unittest.TestCase):
    def rows(self):
        return [dict(accepted=True,job=x,diagnostic=dict(error=dict(rmse=[.01,.02,.003])),
                     spectral_summary=dict(correction_tv_per_second=[.2,.3,.1])) for x in jobs()]

    def test_budget_complete_balanced(self):
        j=jobs();self.assertEqual(len(j),24)
        for name in candidates():
            group=[x for x in j if x['candidate']==name]
            self.assertEqual(len(group),4);self.assertEqual(len({(x['seed'],x['task']) for x in group}),4)
        self.assertEqual({x['mode'] for x in j[::2]},{0,1})

    def test_disjoint_seeds(self):
        d=design();keys=['training_seeds','validation_seeds','pilot_seeds','formal_seeds']
        for a in keys:
            self.assertEqual(len(d[a]),len(set(d[a])))
            for b in keys:
                if a!=b:self.assertFalse(set(d[a])&set(d[b]))

    def test_horizontal_only_candidate_scope(self):
        c=candidates();base=c['pid1']
        allowed={f'MPC_XY_VEL_{x}_ACC' for x in 'PID'}|{'MPC_VC_MODE','MPC_VC_AXES'}|{f'MPC_VC_L{x}_{axis}' for x in (1,2) for axis in 'XY'}
        for p in c.values():
            self.assertTrue({k for k in p if p[k]!=base[k]}<=allowed)
            self.assertEqual(p['MPC_VC_DIV'],1);self.assertEqual(p['MPC_VC_L1_Z'],0)

    def test_fixed_score(self):
        self.assertAlmostEqual(score(self.rows()[0]),.775)
        r=self.rows()[0];r['accepted']=False;self.assertEqual(score(r),1000000)

    def test_tie_lower_index(self):
        self.assertEqual(select(self.rows())['selected'],{'0':'pid0','1':'esta0'})

    def test_equal_rule_selects_both_without_superiority_requirement(self):
        rows=self.rows()
        for r in rows:
            if r['job']['candidate'] in ('pid2','esta1'):r['diagnostic']['error']['rmse']=[.005,.005,.003]
        self.assertEqual(select(rows)['selected'],{'0':'pid2','1':'esta1'})

    def test_missing_failed_duplicate_reordered_rejected(self):
        rows=self.rows()
        variants=[rows[:-1],rows+[rows[0]],list(reversed(rows))]
        r=copy.deepcopy(rows);r[4]['accepted']=False;variants.append(r)
        r=copy.deepcopy(rows);r[4]=r[3];variants.append(r)
        for v in variants:
            with self.assertRaises(ValueError):select(v)

    def test_validation_exact_budget_and_no_reselection(self):
        v=jobs('validation',{'0':'pid1','1':'esta0'})
        self.assertEqual(len(v),12);self.assertEqual({x['candidate'] for x in v},{'pid1','esta0'})
        with self.assertRaises(ValueError):select([dict(accepted=True,job=x) for x in v])
        with self.assertRaises(ValueError):jobs('validation',{'0':'esta0','1':'pid1'})

    def test_formal_and_pilot_execution_rejected(self):
        for phase in ('formal','pilot','unknown'):
            with self.assertRaises(ValueError):jobs(phase)

    def test_all_esta_gains_reconstruct(self):
        for name in ('esta0','esta1','esta2'):
            d,q,j=esta_fixture(name);self.assertEqual(check(d,q,j,True)['updates'],401)

    def test_wrong_gain_old_nu_commit_and_axis_rejected(self):
        for kind in ('gain','output','state','axis'):
            d,q,j=esta_fixture()
            if kind=='gain':j['parameters']['MPC_VC_L1_X']=1.
            if kind=='output':d['a_sta[0]'][100]+=.001
            if kind=='state':d['nu_applied[0]'][100]+=.001
            if kind=='axis':d['nu_applied[0]']=d['nu_applied[1]'].copy()
            with self.assertRaises(ValueError):check(d,q,j,True)

    def test_invalid_score_rejected(self):
        for v in (float('nan'),float('inf'),-1.):
            r=self.rows()[0];r['diagnostic']['error']['rmse'][0]=v
            with self.assertRaises(ValueError):score(r)

    def test_missing_authority_rejected(self):
        with self.assertRaises(RuntimeError):require_authorization('',load_protocol())

    def release_fixture(self,root,run):
        import ram_log
        source=Path(root)/'test.ulg';source.write_bytes(b'original test bytes')
        archive=ram_log.archive(source,Path(run)/'test.ulg',root)
        (Path(run)/'result.json').write_text(json.dumps(dict(logs=[archive])))
        (Path(run)/'ram_log_root.json').write_text(json.dumps(dict(path=root,originals_retained_until_durable_archive=True)))
        return source,archive

    def test_release_preserves_durable_bytes(self):
        import ram_log
        with tempfile.TemporaryDirectory(prefix='px4-v07-',dir='/dev/shm') as root,tempfile.TemporaryDirectory() as run:
            source,item=self.release_fixture(root,run)
            with patch('flight.active_simulators',return_value=[]):ram_log.release_archived(Path(run),root)
            self.assertFalse(source.exists());self.assertEqual(ram_log.digest(item['archive']),item['sha256'])
            self.assertTrue((Path(run)/'ram_release.json').exists())

    def test_release_corrupt_archive_keeps_source(self):
        import ram_log
        with tempfile.TemporaryDirectory(prefix='px4-v07-',dir='/dev/shm') as root,tempfile.TemporaryDirectory() as run:
            source,item=self.release_fixture(root,run);Path(item['archive']).write_bytes(b'bad')
            with patch('flight.active_simulators',return_value=[]),self.assertRaises(ValueError):ram_log.release_archived(Path(run),root)
            self.assertTrue(source.exists())

    def test_release_extra_source_and_old_receipt_rejected(self):
        import ram_log
        for extra in (True,False):
            with tempfile.TemporaryDirectory(prefix='px4-v07-',dir='/dev/shm') as root,tempfile.TemporaryDirectory() as run:
                source,item=self.release_fixture(root,run)
                if extra:(Path(root)/'unarchived.ulg').write_bytes(b'keep')
                else:(Path(run)/'ram_log_root.json').write_text(json.dumps(dict(path=root,originals_retained=True)))
                with patch('flight.active_simulators',return_value=[]),self.assertRaises(ValueError):ram_log.release_archived(Path(run),root)
                self.assertTrue(source.exists())

    def test_original_production_and_launcher_unchanged(self):
        import subprocess
        self.assertEqual(subprocess.check_output(['git','diff','dd3da2e3827b978cd065771c8e1a80df88fce2eb','--','src','msg','sitl','Tools'],cwd=REPO),b'')

    def batch(self,**kwargs):
        import run
        import common
        import test_v04_protocol09 as inherited_tests
        from landing_health import require_passive
        from qualification import require_qualification
        soft=REPO/'research/sta-velocity-control/v06/soft_landing'
        with patch.object(run,'require_qualification',side_effect=lambda _:require_qualification(soft/'qualified_contact.json')), \
             patch.object(run,'require_passive',side_effect=lambda _:require_passive(soft/'offline03/evidence.json')), \
             patch.object(inherited_tests,'runner',run),patch.object(inherited_tests,'load_protocol',common.load_protocol), \
             patch.object(run.ram_log,'release_archived'):
            return inherited_tests.Protocol09Test.batch(self,**kwargs)

    def test_actual_runner_mock_complete_budget_restore(self):
        calls,ledger=self.batch();self.assertEqual(calls,jobs());self.assertTrue(ledger['success'])

    def test_actual_runner_mock_first_failure_stops_and_restores(self):
        for n in (1,6,13,24):
            calls,ledger=self.batch(fail_at=n);self.assertEqual(len(calls),n);self.assertFalse(ledger['success'])
        calls,ledger=self.batch(reject=True);self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main(verbosity=2)
