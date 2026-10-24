"""Result-only safeguards; zero flight and no original archive modification."""
import copy
import unittest

import replay_stopped as subject

fixture = subject.bindings.load('ri04_result_fixtures', subject.TOOLS / 'test_tools.py')


def stopped():
    protocol = fixture.protocol()
    ledger = dict(stage='RI04-B', revision='ri04', gate='B', planned=9, total_budget=9,
        new_planned=9, prior_attempts=0, parameter_restore_exact=True, remaining_simulators=[],
        source_head=subject.SOURCE_HEAD, firmware_sha256='b' * 64, attempts=[], pairs=[], success=False)
    def perform(job, index):
        if index == 3:
            raise RuntimeError('offline fixture first mandatory failure')
        return fixture.metrics(job), dict(metrics_sha256='c' * 64)
    try:
        subject.runner.run_ordered(protocol, perform, fixture.analyzer.compare, ledger, lambda event: None)
    except RuntimeError:
        pass
    return protocol, ledger


class StoppedReplayTests(unittest.TestCase):
    def test_exact_stopped_ledger_only_two_replays(self):
        protocol, ledger = stopped()
        self.assertEqual(len(subject.validate_stopped(ledger, protocol)), 2)
        self.assertFalse(ledger['success'])
        self.assertEqual(len(ledger['unattempted']), 6)

    def test_cannot_relabel_failed_attempt_as_accepted_or_resume(self):
        for change in ('passed', 'accepted', 'missing_failure', 'additional', 'wrong_mode', 'missing_unattempted'):
            protocol, ledger = stopped()
            if change == 'passed': ledger['success'] = True
            elif change == 'accepted': ledger['attempts'][2]['status'] = 'accepted'
            elif change == 'missing_failure': ledger['attempts'].pop()
            elif change == 'additional': ledger['attempts'].append(copy.deepcopy(ledger['attempts'][2]))
            elif change == 'wrong_mode': ledger['attempts'][2]['job']['mode'] = 3
            else: ledger['unattempted'].pop()
            with self.subTest(change=change), self.assertRaises(ValueError): subject.validate_stopped(ledger, protocol)

    def test_original_identity_budget_and_cleanup_required(self):
        for field, value in (('source_head', 'a' * 40), ('planned', 8), ('prior_attempts', 1),
                             ('parameter_restore_exact', False), ('remaining_simulators', ['owned'])):
            protocol, ledger = stopped(); ledger[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): subject.validate_stopped(ledger, protocol)

    def test_one_independent_pair_has_thirteen_checks(self):
        protocol, ledger = stopped()
        data = {job['id']: fixture.metrics(job) for job in protocol['jobs'][:2]}
        self.assertEqual(len(subject.single_pair(ledger, data)['checks']), 13)
        self.assertFalse(ledger['success'])

    def test_original_pair_bool_not_trusted(self):
        protocol, ledger = stopped()
        data = {job['id']: fixture.metrics(job) for job in protocol['jobs'][:2]}
        data['run002']['diagnostic']['error']['rmse'][2] = 1.
        with self.assertRaises(ValueError): subject.single_pair(ledger, data)

    def test_no_failed_run_fill_or_partial_pair(self):
        for case in ('missing', 'fill'):
            protocol, ledger = stopped()
            data = {job['id']: fixture.metrics(job) for job in protocol['jobs'][:2]}
            if case == 'missing': del data['run002']
            else: data['run003'] = fixture.metrics(protocol['jobs'][2])
            with self.subTest(case=case), self.assertRaises(ValueError): subject.single_pair(ledger, data)

    def test_type_strict_metrics_comparison(self):
        self.assertFalse(subject.bindings.exact({'x': 1}, {'x': 1.}))
        self.assertFalse(subject.bindings.exact({'x': True}, {'x': 1}))


if __name__ == '__main__':
    unittest.main(verbosity=2)
