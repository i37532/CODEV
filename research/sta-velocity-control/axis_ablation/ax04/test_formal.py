"""Offline synthetic tests; never uses formal seed to run a simulator."""
import copy
import ast
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import design
import common
import core
import analyze
import run
import package
import collect
import paired_stats as stats

spec = importlib.util.spec_from_file_location('ax02_test_fixtures', design.OLD/'test_protocol.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


def accepted_rows():
    rows = design.empty_outcomes(design.build())
    for row in rows:
        row.update(status='accepted', rmse_m_s=[.01 if row['candidate']=='PID' else .008]*3)
        row.pop('reason')
    return rows


class DesignTest(unittest.TestCase):
    def test_deterministic320(self):
        self.assertEqual(design.build(), common.design())
        self.assertEqual(common.jobs(), json.loads((common.CONFIG/'manifest.json').read_text()))
        self.assertEqual(len(common.jobs()),320)

    def test_exact_paired_blocks(self):
        for task in ('H','V'):
            for seed in design.SEEDS:
                jobs = [j for j in common.jobs() if j['task']==task and j['seed']==seed]
                self.assertEqual({j['axes'] for j in jobs},set(range(8)))
                self.assertEqual([j['position'] for j in jobs],list(range(1,9)))

    def test_position_balance(self):
        pooled = np.zeros((8,8),int)
        for task in ('H','V'):
            counts = np.zeros((8,8),int)
            for j in common.jobs():
                if j['task']==task:
                    counts[design.NAMES.index(j['candidate']),j['position']-1]+=1
            self.assertTrue(np.all((counts==2)|(counts==3)))
            pooled += counts
        self.assertTrue(np.all(pooled==5))

    def test_all_parameters_inherited(self):
        old=json.loads((design.OLD/'execution.json').read_text())
        self.assertEqual(common.design()['fixed_parameters'],old['fixed_parameters'])
        for j in common.jobs():
            p=json.loads((common.CONFIG/'parameters'/(j['candidate'].lower()+'.json')).read_text())
            p['MPC_VCT_TEST']=j['parameters']['MPC_VCT_TEST']
            self.assertEqual(p,j['parameters'])

    def test_illegal_design_rejected(self):
        for key in ('mode','axes','seed','divisor','candidate'):
            d=common.design();d['jobs'][0][key]=999
            with self.subTest(key=key), self.assertRaises(ValueError):common.validate_manifest(d)

    def test_no_budget_order_or_gain_drift(self):
        for kind in ('budget','order','gain'):
            d=common.design()
            if kind=='budget':d['maximum_attempts']=321
            if kind=='order':d['jobs'].reverse()
            if kind=='gain':d['fixed_parameters']['MPC_VC_L1_Z']=3
            with self.subTest(kind=kind), self.assertRaises(ValueError):common.validate_manifest(d)

    def test_old_protocol_unchanged(self):
        self.assertEqual(common.fingerprint(design.OLD/'execution.json'),'ba1ce4086e175eb30668c7ce3afcdbd734c31af5a5dc83adb4db7dfb45b7681a')

    def test_dry_run_no_flight(self):
        with patch.object(sys,'argv',['run.py']), patch.object(run,'flight') as flight, contextlib.redirect_stdout(io.StringIO()):run.main()
        flight.assert_not_called()

    def test_execute_without_authority_cannot_fly(self):
        with patch.object(sys,'argv',['run.py','--execute','--output','/tmp/not-authorized-AX05']), patch.object(run,'flight') as flight, contextlib.redirect_stdout(io.StringIO()),self.assertRaises(RuntimeError):run.main()
        flight.assert_not_called()

    def test_old_authority_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'authority.json';p.write_text(json.dumps(dict(approved=True,stage='AX03-axis-ablation-protocol01',maximum_attempts=48)))
            with self.assertRaises(RuntimeError):common.require_authorization(str(p),common.load_protocol())

    def test_actual_bindings(self):
        self.assertEqual(core.CONFIG,common.CONFIG)
        self.assertEqual(analyze.CONFIG,common.CONFIG)
        self.assertIs(run.analyze,analyze.analyze)
        self.assertEqual(Path(sys.modules['task'].__file__).parent,design.OLD)
        self.assertEqual(Path(sys.modules['flight'].__file__).parent,common.LEGACY)

    def test_numerical_metric_functions_unchanged(self):
        def functions(path):
            return {n.name:ast.dump(n) for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef)}
        old=functions(design.OLD/'core.py');new=functions(common.CONFIG/'core.py')
        for name in ('check_diagnostic','window_metrics','compare'):
            self.assertEqual(old[name],new[name])


class AdmissionTest(unittest.TestCase):
    def test_all320_synthetic_gates(self):
        a=common.Admission();pairs=[]
        for j in a.jobs:pairs.extend(a.accept(j,fixtures.metrics(j)))
        self.assertEqual(len(a.accepted),320);self.assertEqual(len(pairs),280)
        with self.assertRaises(RuntimeError):a.before(a.jobs[0])

    def test_pid_can_come_last_no_unresolved_block(self):
        a=common.Admission()
        with patch.object(core,'compare',wraps=core.compare) as compare:
            for j in a.jobs[:8]:a.accept(j,fixtures.metrics(j))
            self.assertEqual(compare.call_count,7)
            a.before(a.jobs[8])

    def test_immediate_individual_failure_stops(self):
        a=common.Admission();j=a.jobs[0];m=fixtures.metrics(j);m['accepted']=False
        with self.assertRaises(RuntimeError):a.accept(j,m)
        with self.assertRaises(RuntimeError):a.before(j)

    def test_deferred_bad_pair_stops_when_pid_available(self):
        a=common.Admission();failed=False
        for j in a.jobs[:8]:
            m=fixtures.metrics(j)
            if j['mode']:m['diagnostic']['error']['rmse'][2]=1.
            try:a.accept(j,m)
            except RuntimeError:failed=True;break
        self.assertTrue(failed);self.assertTrue(a.failed)
        with self.assertRaises(RuntimeError):a.before(a.jobs[8])

    def test_order_v_gate_and_abort(self):
        a=common.Admission()
        for j in (a.jobs[1],a.jobs[160]):
            with self.assertRaises(RuntimeError):a.before(j)
        a.abort()
        with self.assertRaises(RuntimeError):a.before(a.jobs[0])


class MetricTest(unittest.TestCase):
    def test_all_masks_logged_and_nonunit_ff(self):
        for mask in range(8):
            d,q,j=fixtures.fixture(mask)
            x=core.check_diagnostic(d,q,d['timestamp'][0],d['timestamp'][-1]+10000,j)
            self.assertAlmostEqual(x['seconds'],64.)
            np.testing.assert_allclose(x['error']['rmse'],[.0001,.0002,.0003],atol=1e-14)

    def test_wrong_mode_axes_rate_time_gap_reset_rejected(self):
        for key in ('effective_mode','effective_axes','inner_mode','inner_divisor','fault','timing','publish_seq','timestamp_sample'):
            d,q,j=fixtures.fixture(7);d[key][1500]+=1
            with self.subTest(key=key),self.assertRaises(ValueError):core.check_diagnostic(d,q,d['timestamp'][0],d['timestamp'][-1]+10000,j)

    def test_missing_and_uncommitted_rejected(self):
        for key in ('active_axes','committed_axes','pid_calls'):
            d,q,j=fixtures.fixture(3);d[key][1500]=0
            with self.subTest(key=key),self.assertRaises(ValueError):core.check_diagnostic(d,q,d['timestamp'][0],d['timestamp'][-1]+10000,j)


class StatisticsTest(unittest.TestCase):
    def summary(self,rows):return stats.summarize(rows,repetitions=1000,sign_draws=1000)

    def test_zero_outcomes(self):
        rows=package.outcome_rows(json.loads((common.CONFIG/'outcomes_unattempted.json').read_text()))
        s=self.summary(rows);self.assertEqual(s['attempted'],0);self.assertEqual(s['accepted'],0)
        self.assertTrue(all(not x['inference_available'] for x in s['primary_comparisons'].values()))

    def test_known_constant_paired_difference(self):
        s=self.summary(accepted_rows());self.assertEqual(len(s['primary_comparisons']),14)
        for r in s['primary_comparisons'].values():
            self.assertEqual(r['n'],20);self.assertAlmostEqual(r['mean_difference_m_s'],-.002)
            np.testing.assert_allclose(r['ci_bonferroni14'],[-.002,-.002],atol=1e-15)
            self.assertTrue(r['qualified_improvement'])

    def test_missing_failure_never_zero_imputed(self):
        rows=accepted_rows();target=next(r for r in rows if r['task']=='H' and r['candidate']=='X')
        target.update(status='failed',reason='synthetic loss');target.pop('rmse_m_s')
        s=self.summary(rows);r=s['primary_comparisons']['H/X-PID']
        self.assertEqual(r['n'],19);self.assertFalse(r['qualified_improvement'])
        self.assertAlmostEqual(r['mean_difference_m_s'],-.002)

    def test_zero_one_pair_no_interval(self):
        rows=design.empty_outcomes(design.build())
        for r in rows:
            if r['seed']==design.SEEDS[0]:r.update(status='accepted',rmse_m_s=[.01]*3)
        s=self.summary(rows)
        self.assertTrue(all(r['n']==1 and not r['inference_available'] for r in s['primary_comparisons'].values()))

    def test_duplicate_and_incomplete_rejected(self):
        rows=accepted_rows()
        for bad in (rows[:-1],rows[:-1]+[rows[0]]):
            with self.assertRaises(ValueError):self.summary(bad)

    def test_nonfinite_and_negative_rejected(self):
        for value in (float('nan'),float('inf'),-.1):
            rows=accepted_rows();rows[0]['rmse_m_s'][0]=value
            with self.assertRaises(ValueError):self.summary(rows)

    def test_reproducible_joint_sampling(self):
        rows=accepted_rows()
        for r in rows:r['rmse_m_s'][0]+=(r['seed']%7)*.0001
        self.assertEqual(self.summary(rows),self.summary(rows))

    def test_factorial_main_and_interaction(self):
        cube=np.zeros((2,20,8))
        for i,name in enumerate(design.NAMES):
            x,y,z=[bool(design.MASKS[name]&b) for b in (1,2,4)]
            cube[:,:,i]=10+2*x+3*y+4*z+5*x*y
        r=stats.contrasts(cube)['H']
        self.assertEqual(r['Z_given_XY']['mean_difference_m_s'],4)
        self.assertEqual(r['factorial_average_X']['mean_difference_m_s'],4.5)
        self.assertEqual(r['factorial_interaction_XY']['mean_difference_m_s'],5)
        self.assertEqual(r['factorial_interaction_XYZ']['mean_difference_m_s'],0)

    def test_factorial_requires_complete_eight(self):
        cube=np.ones((2,20,8));cube[0,0,1]=np.nan
        r=stats.contrasts(cube)['H']
        self.assertEqual(r['factorial_average_Z']['n'],19)
        self.assertEqual(r['Z_given_XY']['n'],20)

    def test_precision_only_development(self):
        d=json.loads((common.CONFIG.parent/'ax03/results/summary.json').read_text());p=stats.precision(d)
        self.assertEqual(p['attempts'],320);self.assertEqual(len(p['comparisons']),14)
        self.assertTrue(all(x['development_n']==3 for x in p['comparisons'].values()))

    def test_fabricated_failed_error_rejected(self):
        rows=design.empty_outcomes(design.build());rows[0]['rmse_m_s']=[0]*3
        with self.assertRaises(ValueError):package.outcome_rows(rows)

    def test_outcome_order_rejected(self):
        rows=design.empty_outcomes(design.build());rows.reverse()
        with self.assertRaises(ValueError):package.outcome_rows(rows)

    def test_accepted_needs_independent_replay(self):
        rows=design.empty_outcomes(design.build())
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'metrics.json';p.write_text('{}')
            rows[0].update(status='accepted',metrics_path=str(p),replay_metrics_path=str(p),
                metrics_sha256=common.fingerprint(p),replay_metrics_sha256=common.fingerprint(p))
            with self.assertRaises(ValueError):package.outcome_rows(rows)

    def test_changed_replay_hash_rejected(self):
        rows=design.empty_outcomes(design.build())
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.json';q=Path(tmp)/'b.json';p.write_text('{}');q.write_text('{}')
            rows[0].update(status='accepted',metrics_path=str(p),replay_metrics_path=str(q),
                metrics_sha256=common.fingerprint(p),replay_metrics_sha256='wrong')
            with self.assertRaises(ValueError):package.outcome_rows(rows)

    def test_secondary_real_development_schema_readonly(self):
        s=json.loads((common.CONFIG.parent/'ax03/results/summary.json').read_text())
        m=json.loads((Path(s['runs'][0]['directory'])/'xyz_metrics.json').read_text())
        row=dict(task='H',candidate='PID',status='accepted',secondary=m)
        r=package.secondary_summary([row])['H/PID']
        self.assertEqual(r['n'],1)
        self.assertEqual(r['means']['module_ns_us_per_sim_second'],m['diagnostic']['cadence']['host_us_per_sim_second']['module_ns'])

    def test_unknown_and_missing_reason_rejected(self):
        rows=design.empty_outcomes(design.build())
        rows[0]['status']='canceled'
        with self.assertRaises(ValueError):self.summary(rows)
        rows[0]['status']='invalid';rows[0]['reason']=''
        with self.assertRaises(ValueError):self.summary(rows)


class CollectTest(unittest.TestCase):
    def fixture(self,root,attempts):
        batch=root/'batch';replay=root/'replay';batch.mkdir();replay.mkdir()
        ledger=dict(planned=320,source_head='synthetic',parameter_restore_exact=True,remaining_simulators=[],attempts=attempts)
        (batch/'ledger.json').write_text(json.dumps(ledger))
        (replay/'evidence.json').write_text(json.dumps(dict(success=True,flights_run=0,
            ledger_sha256=common.fingerprint(batch/'ledger.json'),commands=[])))
        return batch,replay

    def test_empty_ledger_not_flights(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(collect,'qualification',return_value=dict(source_head='synthetic')):
            paths=self.fixture(Path(tmp),[]);rows=collect.collect(*paths)
            self.assertEqual(len(rows),320);self.assertTrue(all(r['status']=='unattempted' for r in rows))

    def test_first_failure_remaining_unattempted(self):
        j=common.jobs()[0]
        a=dict(attempt=1,job=j,status='failed',directory='/tmp/synthetic-not-a-flight',error='synthetic safety stop')
        with tempfile.TemporaryDirectory() as tmp,patch.object(collect,'qualification',return_value=dict(source_head='synthetic')):
            rows=collect.collect(*self.fixture(Path(tmp),[a]))
            self.assertEqual(rows[0]['status'],'failed');self.assertEqual(sum(r['status']=='unattempted' for r in rows),319)

    def test_continued_after_failure_rejected(self):
        attempts=[dict(attempt=i+1,job=j,status='failed',directory='/tmp/synthetic',error='synthetic') for i,j in enumerate(common.jobs()[:2])]
        with tempfile.TemporaryDirectory() as tmp,patch.object(collect,'qualification',return_value=dict(source_head='synthetic')):
            paths=self.fixture(Path(tmp),attempts)
            with self.assertRaises(ValueError):collect.collect(*paths)

    def test_wrong_ledger_hash_rejected(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(collect,'qualification',return_value=dict(source_head='synthetic')):
            paths=self.fixture(Path(tmp),[]);(paths[0]/'ledger.json').write_text((paths[0]/'ledger.json').read_text()+'\n')
            with self.assertRaises(ValueError):collect.collect(*paths)
if __name__=='__main__':unittest.main()
