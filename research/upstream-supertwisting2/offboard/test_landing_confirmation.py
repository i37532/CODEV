"""Offline final-receipt regression; never launches or qualifies a flight."""
import ast
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import analyze
import run
import runner_contract as rc
import test_analyze as analyzer_tests
from test_diagnostic_wiring import RecordedCLI, bind_runner, job_for
from test_runner_contract import state as flight_state


def terminal(timestamp=100000000, status_offset=0, land_offset=0):
    state = flight_state(timestamp=timestamp)
    state['position']['z'] = 0.
    state['status'].update(timestamp=timestamp + status_offset, arming_state=1, nav_state=18)
    state['land'].update(timestamp=timestamp + land_offset, landed=True, ground_contact=True)
    return state


class Clock:
    def __init__(self):
        self.now = 0.
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FinalReceiptTests(unittest.TestCase):
    def test_frozen_limit_and_analyzer_are_still_half_second(self):
        self.assertEqual(rc.FINAL_STATE_MAX_GAP_US, 500000)
        self.assertEqual(analyze.MAX_GAP_US, 500000)

    def test_fresh_snapshot_and_sequential_listener_future_receipts(self):
        for status, land in ((0, 0), (-32000, -20000), (50000, 10000)):
            self.assertTrue(rc.landing_confirmation_ready(terminal(status_offset=status, land_offset=land)))

    def test_each_exact_signed_boundary_and_neighbour(self):
        for topic in ('status', 'land'):
            for delta in (-500001, -500000, -499999, 499999, 500000, 500001):
                state = terminal()
                state[topic]['timestamp'] += delta
                with self.subTest(topic=topic, delta=delta):
                    self.assertEqual(rc.landing_confirmation_ready(state), abs(delta) <= 500000)

    def test_stale_land_status_or_both_mean_wait(self):
        for status, land in ((0, -904000), (-904000, 0), (-904000, -904000)):
            self.assertFalse(rc.landing_confirmation_ready(terminal(status_offset=status, land_offset=land)))

    def test_actual_b03_final_receipt_is_not_ready(self):
        self.assertFalse(rc.landing_confirmation_ready(terminal(103560000, -32000, -904000)))

    def test_uses_publication_not_sample_time(self):
        state = terminal(status_offset=-510000, land_offset=-510000)
        state['position']['timestamp_sample'] -= 20000
        self.assertFalse(rc.landing_confirmation_ready(state))
        state = terminal(status_offset=490000, land_offset=490000)
        state['position']['timestamp_sample'] -= 20000
        self.assertTrue(rc.landing_confirmation_ready(state))

    def test_disarmed_and_landed_required_in_same_snapshot(self):
        state = terminal()
        state['status']['arming_state'] = 2
        self.assertFalse(rc.landing_confirmation_ready(state))
        state['status']['arming_state'] = 1
        state['land']['landed'] = False
        self.assertFalse(rc.landing_confirmation_ready(state))

    def test_invalid_or_missing_publication_timestamps_are_errors(self):
        for topic in ('position', 'status', 'land'):
            for value in (None, 0, -1, True, '100000000', 1.5, float('nan'), float('inf')):
                state = terminal()
                state[topic]['timestamp'] = value
                with self.subTest(topic=topic, value=value), self.assertRaises(ValueError):
                    rc.landing_confirmation_ready(state)
            state = terminal()
            del state[topic]['timestamp']
            with self.subTest(topic=topic), self.assertRaises(ValueError):
                rc.landing_confirmation_ready(state)

    def test_invalid_position_sample_clock_is_not_hidden(self):
        for sample in (0, 100000001, float('nan')):
            state = terminal()
            state['position']['timestamp_sample'] = sample
            with self.assertRaises(ValueError):
                rc.landing_confirmation_ready(state)

    def test_missing_or_nonmapping_topic_is_error(self):
        for topic in ('position', 'status', 'land'):
            for value in (None, [], 1):
                state = terminal()
                state[topic] = value
                with self.subTest(topic=topic, value=value), self.assertRaises(ValueError):
                    rc.landing_confirmation_ready(state)

    def test_invalid_landed_and_arming_values_are_errors(self):
        for topic, field, values in (
                ('land', 'landed', (None, 'true', 2, -1, .5, float('nan'), float('inf'))),
                ('status', 'arming_state', (None, '1', True, -1, .5, float('nan'), float('inf')))):
            for value in values:
                state = terminal()
                state[topic][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    rc.landing_confirmation_ready(state)

    def test_no_input_mutation_or_timestamp_fabrication(self):
        state = terminal(103560000, -32000, -904000)
        original = copy.deepcopy(state)
        rc.landing_confirmation_ready(state)
        self.assertEqual(state, original)


class WaitLoopTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.record = Mock()
        self.addCleanup(patch.stopall)
        patch.object(run.time, 'monotonic', self.clock.monotonic).start()
        patch.object(run.time, 'sleep', self.clock.sleep).start()

    def test_fresh_first_sample_records_once_without_sleep(self):
        state = terminal()
        sample = Mock(return_value=state)
        self.assertIs(run.wait_for_landing_confirmation(sample, self.record), state)
        sample.assert_called_once_with('landing')
        self.record.assert_called_once_with('landed_disarmed', state)
        self.assertEqual(self.clock.sleeps, [])

    def test_waits_for_new_land_or_status_publication(self):
        for topic in ('land', 'status'):
            self.record.reset_mock()
            stale = terminal()
            stale[topic]['timestamp'] -= 904000
            fresh = terminal(100100000)
            sample = Mock(side_effect=[stale, stale, fresh])
            self.assertIs(run.wait_for_landing_confirmation(sample, self.record), fresh)
            self.assertEqual(sample.call_count, 3)
            self.record.assert_called_once_with('landed_disarmed', fresh)
        self.assertTrue(all(value == .1 for value in self.clock.sleeps))

    def test_bounce_rearm_and_stale_flags_are_not_latched(self):
        old = terminal(100000000, land_offset=-904000)
        airborne = terminal(100100000)
        airborne['land']['landed'] = False
        airborne['status']['arming_state'] = 2
        armed = terminal(100200000)
        armed['status']['arming_state'] = 2
        stale = terminal(100300000, status_offset=-600000)
        fresh = terminal(100400000)
        sample = Mock(side_effect=[old, airborne, armed, stale, fresh])
        self.assertIs(run.wait_for_landing_confirmation(sample, self.record), fresh)
        self.assertEqual(sample.call_count, 5)
        self.record.assert_called_once_with('landed_disarmed', fresh)

    def test_no_fresh_message_times_out_with_original_150_second_budget(self):
        sample = Mock(return_value=terminal(100000000, land_offset=-904000))
        with self.assertRaisesRegex(TimeoutError, 'fresh final state'):
            run.wait_for_landing_confirmation(sample, self.record)
        self.assertGreaterEqual(self.clock.now, 150)
        self.assertLess(self.clock.now, 150.11)
        self.record.assert_not_called()

    def test_still_armed_or_airborne_never_completes(self):
        for topic, field, value in (('status', 'arming_state', 2), ('land', 'landed', False)):
            self.clock.now = 0
            state = terminal()
            state[topic][field] = value
            with self.subTest(field=field), self.assertRaises(TimeoutError):
                run.wait_for_landing_confirmation(Mock(return_value=state), self.record)
        self.record.assert_not_called()

    def test_blocking_listener_cannot_accept_at_or_after_deadline(self):
        for finish in (150., 151.):
            self.clock.now = 0
            def sample(phase):
                self.clock.now = finish
                return terminal()
            with self.subTest(finish=finish), self.assertRaises(TimeoutError):
                run.wait_for_landing_confirmation(sample, self.record)
        self.record.assert_not_called()

    def test_sample_safety_simulator_or_clock_errors_propagate_without_retry(self):
        for error in (ValueError('Flight failsafe'), ValueError('Native simulation clock stopped'),
                      ValueError('Simulator/GCS monitor failed'), TimeoutError('listener')):
            sample = Mock(side_effect=error)
            with self.subTest(error=error), self.assertRaises(type(error)):
                run.wait_for_landing_confirmation(sample, self.record)
            sample.assert_called_once_with('landing')
        self.record.assert_not_called()
        self.assertEqual(self.clock.sleeps, [])

    def test_bad_state_and_record_failure_are_not_swallowed(self):
        state = terminal()
        state['land']['timestamp'] = float('nan')
        with self.assertRaises(ValueError):
            run.wait_for_landing_confirmation(Mock(return_value=state), self.record)
        self.record.assert_not_called()
        self.record.side_effect = OSError('event persistence failed')
        with self.assertRaises(OSError):
            run.wait_for_landing_confirmation(Mock(return_value=terminal()), self.record)
        self.record.assert_called_once()

    def test_real_execute_callsite_waits_before_end_verification_and_completion(self):
        tree = ast.parse(Path(run.__file__).read_text())
        execute = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'execute')
        block = next(n for n in execute.body if isinstance(n, ast.Try))
        start = next(i for i, n in enumerate(block.body) if isinstance(n, ast.Assign) and
                     isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) and
                     n.value.func.id == 'wait_for_landing_confirmation')
        # This is the real production end block, not a retyped approximation.
        module = ast.fix_missing_locations(ast.Module(body=block.body[start:], type_ignores=[]))
        stale, fresh = terminal(100000000, land_offset=-904000), terminal(100100000)
        order, result = [], {}
        sample = Mock(side_effect=[stale, fresh])
        env = dict(run.__dict__, sample=sample, result=result,
                   event=lambda name, state: order.append((name, state)),
                   verify_configuration=lambda name: order.append(('verify', name)))
        exec(compile(module, run.__file__, 'exec'), env)
        self.assertEqual(order, [('landed_disarmed', fresh), ('verify', 'end')])
        self.assertTrue(result['task_completed'])
        self.assertIs(env['state'], fresh)
        sample.reset_mock(side_effect=True)
        sample.side_effect = ValueError('safety failure while waiting')
        order.clear(); result.clear()
        with self.assertRaises(ValueError):
            exec(compile(module, run.__file__, 'exec'), env)
        self.assertEqual(order, [])
        self.assertEqual(result, {})

    def test_actual_collector_four_systems_two_tasks_waits_and_keeps_checks(self):
        for system in ('PID', 'STA2', 'RSTA', 'RISTA'):
            for task in ('position', 'velocity'):
                with self.subTest(system=system, task=task), tempfile.TemporaryDirectory() as directory:
                    self.clock.now = 0
                    cli = RecordedCLI(system)
                    cli.phase = 'landing'
                    job = job_for(system); job['task'] = task
                    cli.overrides = {
                        'vehicle_local_position': dict(timestamp=100000000, timestamp_sample=99990000),
                        'vehicle_status': dict(timestamp=99980000),
                        'vehicle_land_detected': dict(timestamp=99096000)}
                    bound, env = bind_runner(run.__file__, job, cli, Path(directory))
                    actual_sample = bound['sample']
                    observed = []
                    def sample(phase):
                        if observed:
                            cli.overrides['vehicle_land_detected']['timestamp'] = 100010000
                        state = actual_sample(phase)
                        observed.append(state)
                        return state
                    recorded = Mock()
                    final = run.wait_for_landing_confirmation(sample, recorded)
                    self.assertEqual(len(observed), 2)
                    self.assertIs(final, observed[-1])
                    recorded.assert_called_once_with('landed_disarmed', final)
                    required = rc.diagnostic_expectations(job)
                    for topic in (*required, 'vehicle_local_position', 'vehicle_status', 'vehicle_land_detected'):
                        self.assertEqual(cli.calls.count(('listener', topic, '-n', '1')), 2)
                    cli.overrides['vehicle_status']['failsafe'] = True
                    recorded.reset_mock()
                    with self.assertRaisesRegex(ValueError, 'failsafe'):
                        run.wait_for_landing_confirmation(actual_sample, recorded)
                    recorded.assert_not_called()


class AnalyzerAgreementTests(unittest.TestCase):
    def test_all_four_systems_two_tasks_use_same_terminal_receipt_rule(self):
        # The unchanged full analyzer independently checks the new gate's rule.
        for system in ('PID', 'STA2', 'RSTA', 'RISTA'):
            for task in ('position', 'velocity'):
                for delta in (-500001, -500000, 500000, 500001):
                    f = analyzer_tests.fixture(task, system)
                    end = f['events'][-1]['timestamp_us']
                    for topic, field in (('vehicle_status', 'status_timestamp_us'),
                                         ('vehicle_land_detected', 'land_timestamp_us')):
                        f['topics'][topic]['timestamp'][-1] = end + delta
                        f['events'][-1][field] = end + delta
                    state = terminal(end, delta, delta)
                    case = analyzer_tests.AuditTests()
                    case.setUp()
                    try:
                        with self.subTest(system=system, task=task, delta=delta):
                            if abs(delta) <= 500000:
                                self.assertTrue(rc.landing_confirmation_ready(state))
                                self.assertTrue(case.audit(f)['accepted'])
                            else:
                                self.assertFalse(rc.landing_confirmation_ready(state))
                                with self.assertRaisesRegex(ValueError, 'Stale final state receipts'):
                                    case.audit(f)
                    finally:
                        case.doCleanups()


if __name__ == '__main__':
    unittest.main()
