#!/usr/bin/env python3
"""Synthetic owned-log and real prearm predicates; no flight authorization."""
import ast
import importlib.util
import inspect
import json
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixture = load('prearm04_original_fixtures', HERE.parent/'r03_monitor02/test_integration.py')
runner = load('prearm04_current_runner', HERE.parent/'r03_revision03/runner.py')
integration = load('prearm04_integration_under_test', HERE/'integration.py')


class PreparedFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='r03-prearm04-integration-')
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        self.root = self.out/'owned'
        self.root.mkdir()
        self.path = self.root/'sess001/log001.ulg'
        self.path.parent.mkdir()
        self.cls = integration.make_checks(runner.Checks)
        self.check = self.cls.__new__(self.cls)
        self.check.log_root = self.root
        self.check.logs_before = set()
        self.check.reference = None
        tables, _ = fixture.heading_tables()
        header, packets = fixture.encode(tables)
        self.raw = header+b''.join(p[3] for p in packets)
        self.header = header
        self.packets = packets

    def write(self, data=None):
        self.path.write_bytes(self.raw if data is None else data)

    def warmup(self):
        # The adapter's parent monitor is observed, not replaced globally.
        # Real complete-history prearm functions are always executed below.
        with patch.object(runner.Checks, 'monitor', autospec=True) as parent:
            self.check.monitor('warmup', None, lambda _: {}, self.out, {})
        self.assertEqual(parent.call_count, 1)

    def start(self, age=10000, arming=1):
        def topic(name):
            if name == 'vehicle_status':
                return {'arming_state': arming, 'timestamp': 3990000+age}
            self.assertEqual(name, 'vehicle_local_position')
            return {'timestamp': 3990000+age}
        return self.check.start_heading(topic, self.out)

    def receipts(self):
        return [json.loads(line) for line in (self.out/integration.RECEIPT).read_text().splitlines()]


class LifecycleTests(PreparedFixture):
    def test_real_revision03_warmup_monitor_consumes_reader(self):
        old, _, state, _, topic, calls = fixture.MonitorGuardTests().fixture()
        self.check.__dict__.update(old.__dict__)
        self.check.reference = None
        self.check.log_root = self.root
        self.check.logs_before = set()
        self.write()
        self.check.monitor('warmup', None, topic, self.out, state)
        self.assertEqual(self.check._prearm04['warmup_reads'], 1)
        self.assertEqual(self.check._prearm04['reader'].last_size, len(self.raw))
        self.assertIn('sta_rate_ctrl_status', calls)
        self.assertIn('sta_velocity_ctrl_status', calls)
        self.assertEqual(self.receipts()[-1]['error'], None)

    def test_missing_file_preparation_not_acceptance(self):
        self.warmup()
        self.assertEqual(self.receipts()[-1]['preparation_pending'], 'owned_file_not_created')
        with self.assertRaisesRegex(RuntimeError, 'no completed warmup'):
            self.start()
        self.assertTrue(self.receipts()[-1]['failure_latched'])
        self.write()
        with self.assertRaisesRegex(RuntimeError, 'latched'):
            self.warmup()

    def test_no_warmup_cannot_decode_cold_even_if_file_complete(self):
        self.write()
        with self.assertRaisesRegex(RuntimeError, 'no completed warmup'):
            self.start()
        self.assertIsNone(self.check._prearm04['reader'])
        self.assertEqual(self.receipts()[-1]['raw_reader'], {})

    def test_partial_header_preparation_then_append_and_same_reader(self):
        self.write(self.raw[:7])
        self.warmup()
        reader = self.check._prearm04['reader']
        self.assertEqual(self.receipts()[-1]['preparation_pending'], 'incomplete_first_header')
        self.assertEqual(reader.last_size, 7)
        self.assertEqual(reader.offset, 0)
        with self.path.open('ab') as stream:
            stream.write(self.raw[7:])
        self.warmup()
        self.assertIs(reader, self.check._prearm04['reader'])
        self.assertEqual(reader.last_timing['new_bytes'], len(self.raw)-7)
        result = self.start()
        self.assertEqual(result['position']['timestamp'], 3990000)
        self.assertIs(self.check.live, reader)
        self.assertIs(self.check.landing_live, reader)
        self.assertEqual(reader.last_timing['new_bytes'], 0)

    def test_prearm_reads_only_appended_tail_after_completed_warmup(self):
        cut = next(i for i, row in enumerate(self.packets) if row[0] > 3000000)
        first = self.header+b''.join(p[3] for p in self.packets[:cut])
        tail = b''.join(p[3] for p in self.packets[cut:])
        self.write(first)
        self.warmup()
        reader = self.check._prearm04['reader']
        decoder = reader.decoder
        with self.path.open('ab') as stream:
            stream.write(tail)
        self.start()
        self.assertIs(reader.decoder, decoder)
        self.assertEqual(reader.last_timing['new_bytes'], len(tail))
        self.assertEqual(reader.last_size, len(self.raw))
        self.assertEqual(reader.offset, len(self.raw))
        self.assertGreater(reader.decoder.records, reader.last_timing['new_records'])

    def test_two_files_ambiguous_is_not_pending(self):
        self.write()
        (self.path.parent/'log002.ulg').write_bytes(self.raw)
        with self.assertRaisesRegex(RuntimeError, 'exactly one'):
            self.warmup()
        self.assertTrue(self.receipts()[-1]['failure_latched'])

    def test_missing_ownership_not_pending(self):
        self.check.log_root = None
        with self.assertRaisesRegex(RuntimeError, 'ownership'):
            self.warmup()

    def test_new_owned_path_never_rebinds(self):
        self.write()
        self.warmup()
        self.path.rename(self.path.parent/'log002.ulg')
        with self.assertRaisesRegex(RuntimeError, 'logfile changed'):
            self.warmup()

    def test_reader_truncation_latches_and_finally_records(self):
        self.write()
        self.warmup()
        self.write(self.raw[:16])
        with self.assertRaisesRegex(ValueError, 'replaced/truncated'):
            self.start()
        item = self.receipts()[-1]
        self.assertTrue(item['read_attempted'])
        self.assertIn('truncated', item['raw_reader']['error'])
        self.assertEqual(item['actual_cli'], [])
        self.assertTrue(item['failure_latched'])

    def test_repeated_start_never_redecodes_or_arms(self):
        self.write()
        self.warmup()
        self.start()
        reader = self.check.live
        with patch.object(reader, 'read', wraps=reader.read) as reading:
            with self.assertRaisesRegex(RuntimeError, 'Repeated prearm'):
                self.start()
            self.assertEqual(reading.call_count, 0)
        self.assertTrue(self.receipts()[-1]['failure_latched'])

    def test_warmup_after_start_rejected(self):
        self.write()
        self.warmup()
        self.start()
        with self.assertRaisesRegex(RuntimeError, 'Warmup after'):
            self.warmup()

    def test_parent_monitor_failure_receipted_without_swallow_or_read(self):
        self.write()
        with patch.object(runner.Checks, 'monitor', side_effect=RuntimeError('original safety')):
            with self.assertRaisesRegex(RuntimeError, 'original safety'):
                self.check.monitor('warmup', None, lambda _: {}, self.out, {})
        item = self.receipts()[-1]
        self.assertFalse(item['read_attempted'])
        self.assertIsNone(self.check._prearm04['reader'])
        self.assertIn('original safety', item['error'])
        self.assertGreaterEqual(item['segments']['parent_monitor_s'], 0)

    def test_later_parent_owned_read_failure_receipted(self):
        self.write()
        self.warmup()
        self.start()
        self.check.reference = {'prepared': True}
        self.write(self.raw[:16])
        with patch.object(runner.Checks, 'monitor', side_effect=lambda *a: self.check.live.read()):
            with self.assertRaisesRegex(ValueError, 'truncated'):
                self.check.monitor('landing', None, lambda _: {}, self.out, {})
        item = self.receipts()[-1]
        self.assertTrue(item['read_attempted'])
        self.assertIn('truncated', item['raw_reader']['error'])

    def test_invalid_header_latches_during_warmup(self):
        self.write(b'not a valid ULog header')
        with self.assertRaisesRegex(ValueError, 'header'):
            self.warmup()
        self.assertTrue(self.check._prearm04['reader'].failed)
        self.assertIn('header', self.receipts()[-1]['raw_reader']['error'])


class SafetyBoundaryTests(PreparedFixture):
    def age(self, age, accepted):
        self.write()
        self.warmup()
        if accepted:
            self.start(age)
        else:
            with self.assertRaisesRegex(RuntimeError, 'Stale prearm ULog'):
                self.start(age)
        item = self.receipts()[-1]
        self.assertEqual(item['reference_timestamp_us'], 3990000)
        self.assertEqual(item['sealed_watermark_us'], 3990000)
        self.assertEqual(item['actual_cli'][-1]['timestamp_us'], 3990000+age)
        self.assertEqual(item['transport_max_age_us'], 500000)
        self.assertEqual(item['failure_latched'], not accepted)
        self.assertEqual(item['raw_reader']['new_bytes'], 0)
        self.assertFalse(item['execution_authority_granted'])

    def test_age_499999(self): self.age(499999, True)
    def test_age_500000(self): self.age(500000, True)
    def test_age_500001(self): self.age(500001, False)
    def test_future_minus1(self): self.age(-1, False)

    def test_armed_reference_still_rejected_before_position_now(self):
        self.write()
        self.warmup()
        with self.assertRaisesRegex(RuntimeError, 'must be prearm'):
            self.start(arming=2)
        self.assertEqual(len(self.receipts()[-1]['actual_cli']), 1)

    def test_cli_exception_receipted_and_latched(self):
        self.write()
        self.warmup()
        with self.assertRaisesRegex(RuntimeError, 'CLI unavailable'):
            self.check.start_heading(lambda _: (_ for _ in ()).throw(RuntimeError('CLI unavailable')), self.out)
        item = self.receipts()[-1]
        self.assertIn('CLI unavailable', item['actual_cli'][0]['error'])
        self.assertGreaterEqual(item['actual_cli'][0]['host_elapsed_s'], 0)

    def test_nonfinite_cli_timestamp_preserves_original_guard_failure(self):
        self.write()
        self.warmup()
        with self.assertRaisesRegex(RuntimeError, 'Stale prearm ULog'):
            self.start(float('nan'))
        item = self.receipts()[-1]
        self.assertEqual(item['actual_cli'][-1]['timestamp_us'], {'invalid_numeric': 'nan'})
        self.assertIn('Stale prearm ULog', item['error'])

    def test_clock_sampled_after_reader_and_reference(self):
        self.write()
        self.warmup()
        calls = []
        original = self.check._prearm_reference
        def reference(*args):
            calls.append('reference')
            return original(*args)
        def topic(name):
            calls.append(name)
            return {'arming_state': 1, 'timestamp': 4000000}
        with patch.object(self.check, '_prearm_reference', side_effect=reference):
            self.check.start_heading(topic, self.out)
        self.assertEqual(calls, ['reference', 'vehicle_status', 'vehicle_local_position'])
        item = self.receipts()[-1]
        self.assertGreaterEqual(item['segments']['history_replay_s'], 0)


class IsolationTests(unittest.TestCase):
    def test_production_authority_methods_inherited_and_globals_unchanged(self):
        original = runner.Checks.start_heading
        before = dict(original.__globals__)
        cls = integration.make_checks(runner.Checks)
        for name in ('require_execution', 'prepare_environment', 'configuration', 'selection',
                     '_phase_monitor', '_base_monitor', 'begin_landing', 'landing_complete'):
            self.assertIs(getattr(cls, name), getattr(runner.Checks, name))
        self.assertEqual(before.keys(), original.__globals__.keys())
        self.assertTrue(all(original.__globals__[key] is value for key, value in before.items()))

    def test_ast_only_exact_reader_and_observer_replacements(self):
        original = runner.Checks.start_heading
        tree = ast.parse(textwrap.dedent(inspect.getsource(original)))
        replacements = {
            'from position_live import PositionLiveLog': None,
            'self.live=PositionLiveLog(owned_log(self.log_root,self.logs_before))': None,
            'log=self.live.read()': 'log=self._prearm_log()',
            'p=reference_row(log)': 'p=self._prearm_reference(log,reference_row)',
            'replay(log,ref)': 'self._prearm_replay(log,ref,replay)',
        }
        bodies = {ast.dump(ast.parse(key).body[0]): value for key, value in replacements.items()}
        expected = []
        for node in tree.body[0].body:
            key = ast.dump(node)
            if key not in bodies:
                expected.append(node)
            elif bodies[key] is not None:
                expected.append(ast.parse(bodies[key]).body[0])
        tree.body[0].body = expected
        with patch.object(integration, 'compile', wraps=compile, create=True) as compiling:
            integration.bind_start_heading(original)
        self.assertEqual(ast.dump(compiling.call_args.args[0]), ast.dump(tree))

    def test_unexpected_function_refused(self):
        with self.assertRaisesRegex(ValueError, 'Unexpected inherited'):
            integration.bind_start_heading(self.test_unexpected_function_refused)

    def test_missing_or_duplicated_ast_statement_refused(self):
        original = runner.Checks.start_heading
        source = textwrap.dedent(inspect.getsource(original))
        for token in ('from position_live import PositionLiveLog', 'p=reference_row(log)', 'replay(log,ref)'):
            for changed in (source.replace(token, 'pass'), source.replace(token, token+';'+token)):
                with self.subTest(token=token), patch.object(integration.inspect, 'getsource', return_value=changed):
                    with self.assertRaisesRegex(ValueError, 'Unexpected inherited prearm statement'):
                        integration.bind_start_heading(original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
