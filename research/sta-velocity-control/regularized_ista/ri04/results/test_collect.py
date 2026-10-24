#!/usr/bin/env python3
"""Result-only regression; never launches a simulator or writes old evidence."""
import copy
import math
import unittest
from unittest.mock import patch

import collect


class StoppedCollectionTest(unittest.TestCase):
    def setUp(self):
        self.ledger = {'pairs': [{'accepted': True}]}
        self.replay = dict(success=True, stage_accepted=False, gate_pass_generated=False,
            gate_pass_absent=True, source_head=collect.SOURCE, replayed=2, pair_count=1, new_flights=0,
            source_inputs_unchanged=True, original_input_sha256_before={'one': 'a'},
            original_input_sha256_after={'one': 'a'}, commands=[{'exit_code': 0}, {'exit_code': 0}],
            single_pair={'accepted': True})

    def test_partial_replay_is_not_acceptance(self):
        collect.validate_replay(self.ledger, self.replay)

    def test_reject_gate_pass_or_extra_flight(self):
        for key, value in [('stage_accepted', True), ('gate_pass_generated', True),
                           ('gate_pass_absent', False), ('new_flights', 1), ('pair_count', 6), ('replayed', 9)]:
            changed = copy.deepcopy(self.replay)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                collect.validate_replay(self.ledger, changed)

    def test_reject_changed_inputs_or_subprocess_failure(self):
        for change in [('source_inputs_unchanged', False), ('original_input_sha256_after', {'one': 'b'}),
                       ('commands', [{'exit_code': 0}, {'exit_code': 1}]), ('source_head', 'wrong')]:
            changed = copy.deepcopy(self.replay)
            changed[change[0]] = change[1]
            with self.subTest(key=change[0]), self.assertRaises(ValueError):
                collect.validate_replay(self.ledger, changed)

    def test_pair_cannot_change(self):
        self.replay['single_pair'] = {'accepted': 1}
        with self.assertRaises(ValueError):
            collect.validate_replay(self.ledger, self.replay)

    def test_missing_results_are_not_zero_filled(self):
        jobs = [dict(id='run%03d' % i, seed=82001 + (i-1)//3,
                     candidate='C', mode=4, axes=4) for i in range(1, 10)]
        attempts = [dict(job=j, status='accepted' if i < 2 else 'failed') for i, j in enumerate(jobs[:3])]
        runs = [dict(id=j['id'], airborne=True, accepted=i < 2) for i, j in enumerate(jobs[:3])]
        rows = collect.outcomes(jobs, attempts, runs)
        self.assertEqual([r['metrics_available'] for r in rows], [True, True] + [False]*7)
        self.assertEqual([r['status'] for r in rows], ['accepted', 'accepted', 'failed'] + ['unattempted']*6)
        self.assertTrue(all('rmse' not in r for r in rows))
        with self.assertRaises(ValueError):
            collect.outcomes(jobs[:8], attempts, runs)

    def test_diagnostic_infinity_is_tagged_not_zero(self):
        self.assertEqual(collect.view.json_view(math.inf), {'nonfinite_float': 'Infinity'})
        with self.assertRaises(AssertionError):
            collect.view.check_nonfinite({'rmse': math.inf}, diagnostic=True)
        collect.view.check_nonfinite({'height_task': {'reference': {'position': {'vxy_max': math.inf}}}},
                                     diagnostic=True)

    def test_replay_process_and_log_binding(self):
        repeated = dict(result_script_sha256='hash', commands=[dict(
            argv=['python3', '-B', str(collect.HERE.parent/'tools/analyzer.py'), str(collect.BATCH/id),
                  '--output', str(collect.REPLAY/id)], cwd=str(collect.replay_stopped.bindings.REPO),
            log=str(collect.REPLAY/(id+'.log')), log_sha256='hash') for id in ('run001','run002')])
        with patch.object(collect.view, 'digest', return_value='hash'):
            collect.validate_replay_files(repeated)
            for key, value in [('log_sha256', 'bad'), ('cwd', '/elsewhere'), ('argv', ['python3', 'fake.py'])]:
                changed = copy.deepcopy(repeated)
                changed['commands'][0][key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    collect.validate_replay_files(changed)

    def test_failure_audit_requires_identity_and_real_airborne_evidence(self):
        result = dict(success=False, source_head=collect.SOURCE)
        raw = {str(collect.BATCH/'run003'/name): dict(bytes=12, sha256=name) for name in ('one.ulg','two.ulg')}
        records = {collect.Path(p).name: dict(type='regular', **v) for p, v in raw.items()}
        audit = dict(success=True, audit_completed=True, source_inputs_unchanged=True,
            airborne_confirmed=True, original_failure_preserved=True, stage_accepted=False, flight_accepted=False,
            new_flights=0, retries=0, budget_added=0, source_head=collect.SOURCE, original_result=result,
            main_task={'started': False}, preservation=dict(identical=True, before=records, after=records,
                decoded_ulog_count=2, original_ulog_count=2),
            raw_ulog_fingerprints={p: dict(before=records[collect.Path(p).name], after=records[collect.Path(p).name])
                                  for p in raw})
        collect.validate_failure_audit(audit, result, raw)
        for key, value in [('success', False), ('airborne_confirmed', False), ('stage_accepted', True),
                           ('source_head', 'other'), ('new_flights', 1), ('original_result', {}),
                           ('raw_ulog_fingerprints', {})]:
            changed = copy.deepcopy(audit)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                collect.validate_failure_audit(changed, result, raw)

        changed = copy.deepcopy(audit)
        changed['raw_ulog_fingerprints'][next(iter(raw))]['after']['sha256'] = 'bad'
        with self.assertRaises(ValueError):
            collect.validate_failure_audit(changed, result, raw)

    def test_empty_failure_audit_cannot_prove_airborne(self):
        with self.assertRaises(ValueError):
            collect.validate_failure_audit({}, {'success': False}, {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
