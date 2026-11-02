"""Finite quick-stage gates, unchanged flight limits, and full hover analysis."""
import copy
import json
import tempfile
from pathlib import Path
import unittest
import numpy as np
from contact import aligned_tail

import analyze
import runner_contract as rc
from test_runner_contract import manifest
from test_analyze import fixture, ORIGIN
from ros_bridge import canonical_json


def quick(stage='contact_gate', root='/tmp/codev-quick-test'):
    m = manifest(root)
    m.update(quick_stage=stage, revision='imu_fix_quick_v1', total_new_attempts_ceiling=5)
    m['jobs'] = [m['jobs'][1]] if stage == 'contact_gate' else m['jobs'][:4]
    for i, j in enumerate(m['jobs'], 1):
        j.update(id='O%03d' % i, task='hover')
        if j['system'] == 'STA2':
            j.update(variant='original_control_with_sim_imu_fix',
                     repo='/home/yr/Desktop/Codev-SuperTwisting2-imu-fix')
    m['max_attempts'] = len(m['jobs'])
    m['order'] = [j['id'] for j in m['jobs']]
    return m


class QuickTests(unittest.TestCase):
    def test_causal_contact_tail_and_independent_origins(self):
        t=np.arange(1000000,2020000,20000,dtype=np.int64)
        lp=dict(timestamp=t,z=np.full(len(t),-.01),vz=np.zeros(len(t)))
        gt=dict(timestamp=t,z=np.full(len(t),-488.),vz=np.zeros(len(t)))
        self.assertTrue(aligned_tail(lp,gt,2000000,0.,1000000)['accepted'])
        lp['z'][:]=-.5
        self.assertFalse(aligned_tail(lp,gt,2000000,0.,1000000)['accepted'])

    def test_missing_or_stale_truth_and_tail_rejected(self):
        t=np.arange(1000000,2020000,20000,dtype=np.int64)
        data=dict(timestamp=t,z=np.zeros(len(t)),vz=np.zeros(len(t)))
        for gt in [dict(timestamp=t[:20],z=np.zeros(20),vz=np.zeros(20)),
                   dict(timestamp=t+21000,z=np.zeros(len(t)),vz=np.zeros(len(t)))]:
            with self.assertRaises(ValueError): aligned_tail(data,gt,2000000,0.,1000000)
        with self.assertRaises(ValueError): aligned_tail(data,data,2100000,0.,1000000)

    def test_gate_exactly_one_repaired_sta2(self):
        self.assertEqual(rc.validate_manifest(quick(), 'O001')['system'], 'STA2')

    def test_comparison_exact_order_four(self):
        m = quick('comparison')
        self.assertEqual([rc.validate_manifest(m, j)['system'] for j in m['order']],
                         ['PID', 'STA2', 'RSTA', 'RISTA'])

    def test_budget_scope_and_threshold_mutations_rejected(self):
        for mutate in [lambda m: m.update(max_attempts=2),
                       lambda m: m.update(total_new_attempts_ceiling=6),
                       lambda m: m.update(quick_stage='other'),
                       lambda m: m['jobs'][0].update(task='position'),
                       lambda m: m['jobs'][0].update(repo='/home/yr/Desktop/Codev-SuperTwisting2-original'),
                       lambda m: m['safety_limits'].update(vertical_speed_m_s=4),
                       lambda m: m.update(automatic_retry=True)]:
            m = quick(); mutate(m)
            with self.assertRaises(ValueError): rc.validate_manifest(m, 'O001')

    def test_comparison_requires_contact_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            m = quick('comparison', d)
            p = Path(d) / 'gate.json'
            p.write_text(json.dumps(dict(success=True, independent_replay_passed=True, contact_audit_passed=False)))
            m['contact_gate_receipt'] = str(p)
            with self.assertRaisesRegex(ValueError, 'Contact gate not accepted'):
                rc.check_order(m, 'O001')

    def test_gate_no_rerun(self):
        with tempfile.TemporaryDirectory() as d:
            m = quick(root=d)
            (Path(d) / 'runs/O001').mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'already exists'): rc.check_order(m, 'O001')

    def test_full_hover_analysis_all_systems(self):
        for system in ('PID', 'STA2', 'RSTA', 'RISTA'):
            f = fixture('hover', system, array_layout=system == 'STA2')
            with tempfile.TemporaryDirectory() as d:
                for name, rows in [('sent.jsonl', f['sent']), ('ros_published.jsonl', f['published'])]:
                    (Path(d) / name).write_text(''.join(canonical_json(r)+'\n' for r in rows))
                a = analyze.audit_native_log('not-flight', f['events'], ORIGIN, f['job'], Path(d)/'sent.jsonl',
                                             ulog_class=lambda *args, **kw: f['log'])
                self.assertTrue(a['accepted'])
                self.assertEqual([r['phase'] for r in a['phase_metrics']], ['hover'])


if __name__ == '__main__': unittest.main()
