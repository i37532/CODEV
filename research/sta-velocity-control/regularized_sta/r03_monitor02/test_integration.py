#!/usr/bin/env python3
"""Offline actual-reader/actual-predicate integration; no flight or regrading.

Age-only tests mock the heading result, not the original monitor age guard.
Binary-stream tests call the unchanged full heading/position/landing predicates.
No old archive is written or replayed here; larger historical replay is separate.
"""
import ast
import copy
import importlib.util
import inspect
import io
import json
import math
from pathlib import Path
import struct
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from pyulog import ULog

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SCRIPTS = REPO/'research/sta-velocity-control/scripts'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Deliberately use the actual runner import chain, not a substitute Checks class.
runner = load('monitor02_integration_actual_runner', HERE.parent/'r03_revision01/runner.py')
integration = load('monitor02_integration_under_test', HERE/'integration.py')
inc = integration.incremental
# Imported historical modules can be loaded under a private name without a
# sys.modules entry. Their actual globals, not a generic module name, are used.
monitor_globals = runner.historical.LandingChecks.monitor.__globals__
landing = load('monitor02_unchanged_landing', inc.LEGACY/'landing.py')
position = load('monitor02_unchanged_position', inc.LEGACY/'position_log.py')
clock09 = load('monitor02_unchanged_clock09', SCRIPTS/'v04_live_clock09.py')
attitude_policy = clock09.AttitudeClockPolicy
old_fixture = load('monitor02_heading_fixture', SCRIPTS/'test_v04_protocol04.py')
old_landing_fixture = load('monitor02_landing_fixture',
                          REPO/'research/sta-velocity-control/v07/protocol07/test_landing.py')
cli_clock = load('monitor02_clock_receipt', inc.LEGACY/'cli_clock.py')


def record(kind, body):
    return struct.pack('<HB', len(body), ord(kind))+body


def encode(tables):
    """Typed synthetic ULog, including actual instances and raw row order.

    Cross-topic messages are ordered by publication time. Equal-key rows keep
    their original order; no row is deduplicated or interpolated.
    """
    tags = {'uint64': ('uint64_t', 'Q'), 'int64': ('int64_t', 'q'),
            'uint32': ('uint32_t', 'I'), 'int32': ('int32_t', 'i'),
            'uint8': ('uint8_t', 'B'), 'int8': ('int8_t', 'b'),
            'float32': ('float', 'f'), 'float64': ('double', 'd')}
    head = ULog.HEADER_BYTES+b'\x01'+struct.pack('<Q', 1)
    subscriptions, packets = [], []
    for ident, ((name, instance), table) in enumerate(tables.items(), 1):
        fields = ''.join(tags[str(v.dtype)][0]+' '+k+';' for k, v in table.items())
        head += record('F', (name+':'+fields).encode())
        subscriptions.append(record('A', struct.pack('<BH', instance, ident)+name.encode()))
        fmt = '<H'+''.join(tags[str(v.dtype)][1] for v in table.values())
        for index, timestamp in enumerate(table['timestamp']):
            body = struct.pack(fmt, ident, *(v[index].item() for v in table.values()))
            packets.append((int(timestamp), name, index, record('D', body)))
    packets.sort(key=lambda item: item[0])
    return head+b''.join(subscriptions), packets


def decode(tables):
    header, packets = encode(tables)
    decoder = inc.Decoder()
    decoder.feed(header+b''.join(p[3] for p in packets))
    return decoder.snapshot()


def heading_tables():
    """Old validated alignment fixture plus typed mirror/attitude payloads."""
    log, reference = old_fixture.fixture()
    tables = copy.deepcopy(log.tables)
    a = tables[('vehicle_attitude', 0)]
    for key, values in list(a.items()):
        a[key] = np.r_[values[0], values]
    a['timestamp'][0] = 990000
    a['timestamp_sample'] = a['timestamp'].copy()
    for i in range(4):
        a[f'q[{i}]'] = np.full(len(a['timestamp']), float(i == 0), np.float64)
    p = tables[('vehicle_local_position', 0)]
    for key in position.POSITION_FIELDS:
        if key not in p:
            p[key] = np.zeros(len(p['timestamp']), np.float64)
    mirror = {k: v.copy() for k, v in p.items()}
    mirror['log_seq'] = np.arange(1, len(p['timestamp'])+1, dtype=np.uint32)
    tables[(position.TOPIC, 0)] = mirror
    return tables, reference


def landing_tables(*, disarmed=False, offset=0):
    log, context = old_landing_fixture.fixture()
    tables = copy.deepcopy(log.tables)
    if disarmed:
        d = tables[('sta_velocity_ctrl_status', 0)]
        for key, values in list(d.items()):
            value = 91112000 if key == 'timestamp' else 0 if key in ('armed', 'excitation_fault') else values[-1]
            d[key] = np.append(values, value)
    for table in tables.values():
        for key in ('timestamp', 'nav_state_timestamp'):
            if key in table:
                table[key] = (table[key]+offset).astype(np.uint64)
    for key in ('hover_start_us', 'hover_end_us', 'command_lower_us'):
        context[key] += offset
    return tables, context


def last_diagnostic(log):
    return {k: v[-1].item() for k, v in log.get_dataset('sta_velocity_ctrl_status').data.items()}


def with_receipt(data, topic):
    raw = f"TOPIC: {topic}\n timestamp: {data['timestamp']}  (0.000000 seconds ago)\n"
    return {**data, '_clock': cli_clock.receipt('listener', [topic, '-n', '1'], raw, 1, 1001)}


class BindingTests(unittest.TestCase):
    def test_exactly_one_import_ast_replaced_and_other_nodes_identical(self):
        original = runner.Checks.start_heading
        tree = ast.parse(textwrap.dedent(inspect.getsource(original)))
        imported = [node for node in tree.body[0].body
                    if isinstance(node, ast.ImportFrom) and node.module == 'position_live']
        self.assertEqual(len(imported), 1)
        tree.body[0].body.remove(imported[0])
        with patch.object(integration, 'compile', wraps=compile, create=True) as compiling:
            bound = integration.bind_start_heading(original)
        self.assertEqual(compiling.call_count, 1)
        self.assertEqual(ast.dump(compiling.call_args.args[0]), ast.dump(tree))
        self.assertIs(bound.__globals__['PositionLiveLog'], inc.PositionLiveLog)

    def test_inherited_predicates_and_parent_globals_never_replaced(self):
        original = runner.Checks.start_heading
        saved = dict(original.__globals__)
        monitor_saved = dict(monitor_globals)
        cls = integration.make_checks(runner.Checks)
        self.assertIsSubclass(cls, runner.Checks)
        for name in ('selection', '_base_monitor', '_phase_monitor', 'begin_landing', 'landing_complete', 'collect_landing_tail'):
            self.assertIs(getattr(cls, name), getattr(runner.Checks, name))
        self.assertEqual(saved.keys(), original.__globals__.keys())
        self.assertTrue(all(original.__globals__[key] is value for key, value in saved.items()))
        self.assertEqual(monitor_saved.keys(), monitor_globals.keys())
        self.assertTrue(all(monitor_globals[key] is value for key, value in monitor_saved.items()))
        self.assertIsNot(cls.start_heading.__globals__, original.__globals__)
        self.assertIs(cls.start_heading.__globals__['replay'], original.__globals__['replay'])

    def assertIsSubclass(self, child, parent):
        self.assertTrue(issubclass(child, parent))

    def test_unexpected_function_source_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unexpected inherited heading'):
            integration.bind_start_heading(self.test_unexpected_function_source_rejected)

    def test_import_absence_duplication_alias_and_extra_name_rejected(self):
        original = runner.Checks.start_heading
        source = textwrap.dedent(inspect.getsource(original))
        token = 'from position_live import PositionLiveLog'
        for replacement in ('pass', token+'\n    '+token,
                            token+' as OtherReader', token+', OtherReader'):
            with self.subTest(replacement=replacement), patch.object(
                    integration.inspect, 'getsource', return_value=source.replace(token, replacement)):
                with self.assertRaisesRegex(ValueError, 'Unexpected inherited reader'):
                    integration.bind_start_heading(original)

    def test_actual_start_heading_uses_new_reader_and_preserves_base_globals(self):
        tables, _ = heading_tables()
        header, packets = encode(tables)
        cls = integration.make_checks(runner.Checks)
        check = cls.__new__(cls)
        check.log_root = '/synthetic-owned-log'; check.logs_before = set()
        base_globals = dict(runner.Checks.start_heading.__globals__)
        with tempfile.TemporaryDirectory(prefix='r03-monitor02-start-') as temp:
            out = Path(temp); path = out/'synthetic.ulg'
            path.write_bytes(header+b''.join(p[3] for p in packets))
            topics = {'vehicle_status': {'arming_state': 1},
                      'vehicle_local_position': {'timestamp': 4000000}}
            with patch.dict(cls.start_heading.__globals__, {'owned_log': lambda *_: path}):
                reference = check.start_heading(topics.__getitem__, out)
            self.assertIsInstance(check.live, inc.PositionLiveLog)
            self.assertIs(check.live, check.landing_live)
            self.assertEqual(reference['position']['timestamp'], 3990000)
            evidence = json.loads((out/'live_log.json').read_text())
            self.assertEqual(evidence['transport_max_age_us'], 500000)
            self.assertEqual(evidence['position_evidence']['sequence_gaps'], 0)
        self.assertTrue(all(runner.Checks.start_heading.__globals__[key] is value
                            for key, value in base_globals.items()))

    def test_actual_prearm_500ms_boundary_and_future_guard_unchanged(self):
        tables, _ = heading_tables()
        header, packets = encode(tables)
        for age in (499999, 500000, 500001, -1):
            cls = integration.make_checks(runner.Checks)
            check = cls.__new__(cls)
            check.log_root = '/synthetic-owned-log'; check.logs_before = set()
            with self.subTest(age=age), tempfile.TemporaryDirectory(prefix='r03-monitor02-prearm-age-') as temp:
                out = Path(temp); path = out/'synthetic.ulg'
                path.write_bytes(header+b''.join(p[3] for p in packets))
                topics = {'vehicle_status': {'arming_state': 1},
                          'vehicle_local_position': {'timestamp': 3990000+age}}
                with patch.dict(cls.start_heading.__globals__, {'owned_log': lambda *_: path}):
                    if 0 <= age <= 500000:
                        self.assertEqual(check.start_heading(topics.__getitem__, out)['position']['timestamp'], 3990000)
                    else:
                        with self.assertRaisesRegex(RuntimeError, 'Stale prearm ULog'):
                            check.start_heading(topics.__getitem__, out)


class MonitorGuardTests(unittest.TestCase):
    """Exercise the real runner MRO/age comparisons, not a copied predicate."""
    def fixture(self, now=91112000):
        tables, context = landing_tables(disarmed=True, offset=now-91112000)
        raw = decode(tables)
        cls = integration.make_checks(runner.Checks)
        check = cls.__new__(cls)
        check.job = {'mode': 0, 'axes': 0, 'divisor': 1}
        check.last_seq = None; check.ground = [0, 0, 0]
        check.reference = {'synthetic': True}; check.frozen_yaw = None
        check.task_yaw_ready = True
        check.planned_landing = check.observation_completed = True
        check.landing = landing.LandingMonitor(clock=lambda: 0.)
        check.landing.begin(**context)
        calls = []
        def read():
            calls.append('read')
            return raw
        check.live = check.landing_live = SimpleNamespace(read=read, last_size=123,
            offset=123, last_timing={'new_records': 1, 'total_records': 20})
        diag = last_diagnostic(raw)
        diag.update(requested_mode=0, requested_axes=0, effective_mode=0, effective_axes=0, pending=0, reject=0)
        rate = dict(timestamp=now, publish_seq=1, requested_mode=0, requested_axes=0,
            effective_mode=0, effective_axes=0, div_req=1, div_eff=1,
            fault=0, abort_requested=0, termination=0)
        topics = {'sta_rate_ctrl_status': with_receipt(rate, 'sta_rate_ctrl_status'),
                  'sta_velocity_ctrl_status': with_receipt(diag, 'sta_velocity_ctrl_status'),
                  'vehicle_local_position': {'timestamp': now}}
        state = dict(position={'timestamp': now}, status={'arming_state': 1, 'nav_state': 18})
        def topic(name):
            calls.append(name)
            return topics[name]
        return check, raw, state, topics, topic, calls

    def age(self, phase, age, *, now=91112000):
        check, raw, state, topics, topic, calls = self.fixture(now)
        def replay(*args, **kwargs):
            self.assertIs(args[0], raw)
            self.assertIs(args[1], check.reference)
            self.assertEqual(kwargs, {'frozen': None, 'allow_pending': True})
            calls.append('replay')
            return {'through_us': now-age, 'ready': False}
        original = monitor_globals['replay']
        with tempfile.TemporaryDirectory(prefix='r03-monitor02-age-') as temp:
            out = Path(temp)
            with patch.dict(monitor_globals, {'replay': replay}):
                if 0 <= age <= 500000:
                    check.monitor(phase, None, topic, out, state)
                else:
                    with self.assertRaisesRegex((ValueError, RuntimeError), 'Live ULog transport stale/future'):
                        check.monitor(phase, None, topic, out, state)
            timing = json.loads((out/'r03_monitor_timing.jsonl').read_text())
            self.assertEqual(timing['actual_position_cli_timestamps'], [now])
            self.assertEqual(timing['transport_max_age_us'], 500000)
            self.assertGreaterEqual(timing['host_elapsed_s'], 0)
            self.assertEqual(timing['error'] is None, 0 <= age <= 500000)
            self.assertLess(calls.index('read'), calls.index('replay'))
            self.assertLess(calls.index('replay'), calls.index('vehicle_local_position'))
            if phase == 'landing' and 0 <= age <= 500000:
                self.assertFalse(check.landing.last_evidence['pending'])
                self.assertEqual(check.landing.last_evidence['evidence']['classification']['expected_planned_landing_gate'], 2)
        self.assertIs(monitor_globals['replay'], original)

    def test_landing_499999_accepted(self): self.age('landing', 499999)
    def test_landing_500000_accepted(self): self.age('landing', 500000)
    def test_landing_500001_rejected(self): self.age('landing', 500001)
    def test_landing_future_rejected(self): self.age('landing', -1)
    def test_nonlanding_499999_accepted(self): self.age('warmup', 499999)
    def test_nonlanding_500000_accepted(self): self.age('warmup', 500000)
    def test_nonlanding_500001_rejected(self): self.age('warmup', 500001)
    def test_nonlanding_future_rejected(self): self.age('warmup', -1)

    def test_run007_recorded_now_and_watermark_remain_540ms_rejection(self):
        self.assertEqual(147876000-147336000, 540000)
        self.age('landing', 540000, now=147876000)

    def test_actual_selection_inner_fault_and_cli_receipt_rejected(self):
        for kind in ('mode', 'inner', 'receipt'):
            check, _, state, topics, topic, _ = self.fixture()
            if kind == 'mode': topics['sta_velocity_ctrl_status']['effective_mode'] = 3
            elif kind == 'inner': topics['sta_rate_ctrl_status']['fault'] = 1
            else: topics['sta_velocity_ctrl_status'].pop('_clock')
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(prefix='r03-monitor02-live-negative-') as temp:
                with self.assertRaises(RuntimeError):
                    check.monitor('landing', None, topic, Path(temp), state)
                timing = json.loads((Path(temp)/'r03_monitor_timing.jsonl').read_text())
                self.assertIsNotNone(timing['error'])


class BinaryHeadingTests(unittest.TestCase):
    def prefix(self, tables, reference, split_us=3000000):
        header, packets = encode(tables)
        index = next(i for i, p in enumerate(packets) if p[0] > split_us)
        decoder = inc.Decoder()
        decoder.feed(header+b''.join(p[3] for p in packets[:index]))
        initial = position.PositionLogView(decoder.snapshot())
        result = clock09.replay(initial, reference, allow_pending=True)
        self.assertTrue(result['ready'])
        return decoder, b''.join(p[3] for p in packets[index:]), result['freeze_candidate']

    def reject_later(self, tables, reference, pattern):
        decoder, tail, frozen = self.prefix(tables, reference)
        # Fragmenting a record must neither erase nor prematurely decode it.
        decoder.feed(tail[:-1]); decoder.feed(tail[-1:])
        view = position.PositionLogView(decoder.snapshot())
        with self.assertRaisesRegex(ValueError, pattern):
            clock09.replay(view, reference, frozen=frozen, allow_pending=True)

    def test_full_binary_heading_after_multiple_chunks_matches_original_parser(self):
        tables, reference = heading_tables()
        header, packets = encode(tables)
        raw = header+b''.join(p[3] for p in packets)
        decoder, tail, frozen = self.prefix(tables, reference)
        for start in range(0, len(tail), 1237): decoder.feed(tail[start:start+1237])
        actual = clock09.replay(position.PositionLogView(decoder.snapshot()), reference, frozen=frozen)
        expected = clock09.replay(position.PositionLogView(ULog(io.BytesIO(raw))), reference, frozen=frozen)
        self.assertEqual(actual, expected)
        self.assertEqual(actual['position_samples'], 300)

    def test_fault_between_polls_not_hidden_by_later_recovery(self):
        for name, instance, field, value in (
                ('sta_velocity_ctrl_status', 0, 'first_fail', 1),
                ('sta_velocity_ctrl_status', 0, 'inner_mode', 1),
                ('vehicle_status', 0, 'failsafe', 1),
                ('estimator_status', 1, 'filter_fault_flags', 1),
                ('estimator_status_flags', 1, 'fs_bad_hdg', 1),
                ('estimator_selector_status', 0, 'primary_instance', 2)):
            tables, reference = heading_tables()
            d = tables[(name, instance)]; d[field][d['timestamp'] == 3200000] = value
            with self.subTest(topic=name, field=field):
                self.reject_later(tables, reference, 'Controller|failure|fault|Forbidden|switch')

    def test_second_heading_reset_cross_chunk_rejected(self):
        tables, reference = heading_tables()
        for name in ('vehicle_local_position', position.TOPIC):
            d = tables[(name, 0)]; d['heading_reset_counter'][d['timestamp'] >= 3200000] += 1
        self.reject_later(tables, reference, 'Repeated')

    def test_position_frame_reset_cross_chunk_rejected(self):
        tables, reference = heading_tables()
        for name in ('vehicle_local_position', position.TOPIC):
            d = tables[(name, 0)]; d['z_reset_counter'][d['timestamp'] >= 3200000] += 1
        self.reject_later(tables, reference, 'Coordinate/reset')

    def test_consumed_publication_or_sample_mismatch_cross_chunk(self):
        for key in ('input_timestamp', 'timestamp_sample'):
            tables, reference = heading_tables()
            d = tables[('sta_velocity_ctrl_status', 0)]; d[key][d['timestamp'] == 3200000] += 1
            with self.subTest(key=key): self.reject_later(tables, reference, 'consumed|Consumed')

    def test_position_mirror_payload_and_signed_zero_cross_chunk(self):
        for value in (1., -0.):
            tables, reference = heading_tables()
            d = tables[(position.TOPIC, 0)]; d['x'][d['timestamp'] == 3200000] = value
            with self.subTest(value=value): self.reject_later(tables, reference, 'payload mismatch')

    def test_position_mirror_sequence_gap_cross_chunk(self):
        tables, reference = heading_tables()
        d = tables[(position.TOPIC, 0)]; d['log_seq'][d['timestamp'] >= 3200000] += 1
        self.reject_later(tables, reference, 'sequence')

    def test_duplicate_position_sample_clock_preserved_then_rejected(self):
        tables, reference = heading_tables()
        d = tables[(position.TOPIC, 0)]; d['timestamp_sample'][d['timestamp'] == 3200000] = 3190000
        self.reject_later(tables, reference, 'Invalid position clock')

    def test_duplicate_nonattitude_publication_not_whitelisted(self):
        tables, reference = heading_tables()
        d = tables[('sta_velocity_ctrl_status', 0)]
        index = int(np.flatnonzero(d['timestamp'] == 3200000)[0])
        for key, values in list(d.items()): d[key] = np.insert(values, index, values[index])
        self.reject_later(tables, reference, 'nonmonotonic')

    def tied_tail(self, mutation=None):
        tables, reference = heading_tables()
        a = tables[('vehicle_attitude', 0)]
        index = int(np.flatnonzero(a['timestamp'] == 3000000)[0])
        for key, values in list(a.items()): a[key] = np.insert(values, index+1, values[index])
        a['timestamp_sample'][index] = 2996000
        if mutation: mutation(a, index+1)
        header, packets = encode(tables)
        cut = next(i for i, p in enumerate(packets) if p[1] == 'vehicle_attitude' and p[2] == index+1)
        decoder = inc.Decoder(); decoder.feed(header+b''.join(p[3] for p in packets[:cut]))
        first = position.PositionLogView(decoder.snapshot())
        self.assertEqual(clock09.sealed_time(first), 2990000)
        self.assertTrue(clock09.replay(first, reference, allow_pending=True)['ready'])
        return decoder, b''.join(p[3] for p in packets[cut:]), reference

    def test_cross_chunk_same_publication_group_retained_and_ambiguous(self):
        decoder, tail, reference = self.tied_tail()
        decoder.feed(tail)
        log = position.PositionLogView(decoder.snapshot())
        a = attitude_policy().data(log)
        self.assertEqual(a['timestamp_sample'][a['timestamp'] == 3000000].tolist(), [2996000, 3000000])
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            attitude_policy().unique_index(a, 3000000)
        self.assertTrue(clock09.replay(log, reference)['ready'])

    def test_late_tied_attitude_tilt_violation_is_not_discarded(self):
        def bad(a, i):
            a['q[0]'][i] = math.cos(.2); a['q[1]'][i] = math.sin(.2)
        decoder, tail, reference = self.tied_tail(bad)
        decoder.feed(tail)
        with self.assertRaisesRegex(ValueError, 'tilt'):
            clock09.replay(position.PositionLogView(decoder.snapshot()), reference)

    def test_late_tied_quaternion_reset_is_not_discarded(self):
        decoder, tail, reference = self.tied_tail(lambda a, i: a['quat_reset_counter'].__setitem__(i, 4))
        decoder.feed(tail)
        with self.assertRaisesRegex(ValueError, 'Repeated'):
            clock09.replay(position.PositionLogView(decoder.snapshot()), reference)

    def test_late_tied_sample_duplicate_or_nan_is_not_repaired(self):
        for key, value, pattern in [('timestamp_sample', 2996000, 'Nonunique'), ('q[0]', np.nan, 'Nonfinite')]:
            decoder, tail, reference = self.tied_tail(lambda a, i: a[key].__setitem__(i, value))
            decoder.feed(tail)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, pattern):
                clock09.replay(position.PositionLogView(decoder.snapshot()), reference)


class BinaryLandingTests(unittest.TestCase):
    def test_full_landing_predicate_matches_original_parser(self):
        tables, context = landing_tables()
        header, packets = encode(tables); raw = header+b''.join(p[3] for p in packets)
        decoder = inc.Decoder()
        for start in range(0, len(raw), 17): decoder.feed(raw[start:start+17])
        a = landing.replay(decoder.snapshot(), context, 91108000, final=True)
        b = landing.replay(ULog(io.BytesIO(raw)), context, 91108000, final=True)
        self.assertEqual(a, b)
        self.assertEqual(a['classification']['expected_planned_landing_gate'], 2)

    def test_late_past_equal_status_resolves_pending_but_future_does_not(self):
        for delta, accepted in ((0, True), (1, False)):
            tables, context = landing_tables()
            status = tables[('vehicle_status', 0)]
            status['timestamp'][-1] += delta; status['nav_state_timestamp'][-1] += delta
            header, packets = encode(tables)
            delayed = [p for p in packets if p[1] == 'vehicle_status' and p[2] == 1]
            initial = [p for p in packets if p not in delayed]
            decoder = inc.Decoder(); decoder.feed(header+b''.join(p[3] for p in initial))
            with self.assertRaises(landing.LandingPending):
                landing.replay(decoder.snapshot(), context, 91108000)
            decoder.feed(b''.join(p[3] for p in delayed))
            if accepted:
                self.assertEqual(landing.replay(decoder.snapshot(), context, 91108000)['classification']['expected_planned_landing_gate'], 2)
            else:
                with self.assertRaisesRegex(ValueError, 'past/equal'):
                    landing.replay(decoder.snapshot(), context, 91108000)

    def test_transient_raw_faults_remain_rejected_after_recovery(self):
        for key in ('first_fail', 'fault', 'timing', 'inner_mode'):
            tables, context = landing_tables()
            tables[('sta_velocity_ctrl_status', 0)][key][2] = 1
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'diagnostic failure'):
                landing.replay(decode(tables), context, 91108000)

    def test_duplicate_command_and_leaving_auto_land_remain_rejected(self):
        for kind in ('command', 'status'):
            tables, context = landing_tables()
            if kind == 'command':
                d = tables[('vehicle_command', 0)]
                for key, values in list(d.items()): d[key] = np.append(values, values[-1]+1 if key == 'timestamp' else values[-1])
            else:
                d = tables[('vehicle_status', 0)]
                for key, values in list(d.items()): d[key] = np.append(values, 91106000 if key in ('timestamp', 'nav_state_timestamp') else 4 if key == 'nav_state' else 0)
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'Repeated|Left planned'):
                landing.replay(decode(tables), context, 91108000)

    def test_pending_repoll_does_not_restart_host_timeout_and_failure_latches(self):
        tables, context = landing_tables()
        tables[('vehicle_status', 0)] = {k: v[:1] for k, v in tables[('vehicle_status', 0)].items()}
        raw = decode(tables); diagnostic = last_diagnostic(raw)
        wall = [0.]; monitor = landing.LandingMonitor(clock=lambda: wall[0]); monitor.begin(**context)
        self.assertTrue(monitor.update(raw, diagnostic, 91108000)['pending'])
        origin = monitor.pending_since
        for elapsed in (.1, .5):
            wall[0] = elapsed
            self.assertTrue(monitor.update(raw, diagnostic, 91108000)['pending'])
            self.assertEqual(monitor.pending_since, origin)
        wall[0] = .500001
        with self.assertRaisesRegex(ValueError, 'pending timeout'): monitor.update(raw, diagnostic, 91108000)
        self.assertTrue(monitor.failed)
        with self.assertRaisesRegex(ValueError, 'latched'): monitor.update(raw, diagnostic, 91108000)

    def test_raw_transport_500ms_boundary_and_future_guard_unchanged(self):
        tables, context = landing_tables(); raw = decode(tables)
        for age in (499999, 500000, 500001, -1):
            monitor = landing.LandingMonitor(clock=lambda: 0.); monitor.begin(**context)
            diagnostic = last_diagnostic(raw)
            now = 91108000+age
            # Current CLI sample intentionally stays fresh: exercise the raw
            # history age guard rather than its preceding diagnostic age guard.
            diagnostic['timestamp'] = now
            with self.subTest(age=age):
                if 0 <= age <= 500000:
                    self.assertFalse(monitor.update(raw, diagnostic, now)['pending'])
                else:
                    with self.assertRaisesRegex(ValueError, 'raw transport stale/future'):
                        monitor.update(raw, diagnostic, now)
                    self.assertTrue(monitor.failed)


if __name__ == '__main__':
    unittest.main(verbosity=2)
