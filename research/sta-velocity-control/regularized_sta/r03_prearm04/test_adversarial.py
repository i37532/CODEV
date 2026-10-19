#!/usr/bin/env python3
"""Independent offline adversarial tests for persistent prearm warming.

Synthetic typed ULog bytes are passed through the new persistent reader and
the unchanged historical validators. These tests neither authorize flights
nor reassess an archived run. The older fixture module supplies only data and
encoding; its test cases are not counted or silently rerun here.
"""
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest

import numpy as np
from pyulog import ULog

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixture = load('prearm04_adversarial_frozen_fixture',
               HERE.parent/'r03_monitor02/test_integration.py')
integration = load('prearm04_adversarial_integration', HERE/'integration.py')
prearm = load('prearm04_adversarial_original_prearm',
              REPO/'research/sta-velocity-control/scripts/v04_prearm17.py')


def encoded(tables):
    header, packets = fixture.encode(tables)
    return header+b''.join(p[3] for p in packets)


def append(path, chunk):
    with path.open('ab') as stream:
        stream.write(chunk)


@contextmanager
def reader_context(initial):
    with tempfile.TemporaryDirectory(prefix='r03-prearm04-adversarial-') as temp:
        root = Path(temp)
        path = root/'synthetic.ulg'
        path.write_bytes(initial)
        reader = integration.OwnedWarmReader(path)
        yield root, path, reader


class PersistentReaderTests(unittest.TestCase):
    """Real decoder/parser state is preserved; no recovery by cold rebuilding."""

    def test_partial_header_then_complete_prefix_uses_same_decoder(self):
        tables, _ = fixture.heading_tables()
        raw = encoded(tables)
        with reader_context(raw[:7]) as (_, path, reader):
            decoder = reader.decoder
            self.assertIsNone(reader.consume(allow_incomplete=True))
            self.assertFalse(reader.failed)
            self.assertFalse(decoder.header)
            self.assertEqual(decoder.pending, raw[:7])
            append(path, raw[7:])
            log = reader.read()
            self.assertIs(reader.decoder, decoder)
            self.assertTrue(decoder.header)
            self.assertEqual(reader.last_size, len(raw))
            self.assertEqual(reader.last_timing['new_bytes'], len(raw)-7)
            self.assertEqual(prearm.reference_row(log)['timestamp'], 3990000)

    def test_empty_header_cannot_be_used_as_prearm_reference(self):
        with reader_context(b'') as (_, path, reader):
            self.assertIsNone(reader.consume(allow_incomplete=True))
            self.assertFalse(reader.failed)
            with self.assertRaises(ValueError):
                reader.read()
            self.assertTrue(reader.failed)
            append(path, ULog.HEADER_BYTES+b'\x01'+struct.pack('<Q', 1))
            with self.assertRaisesRegex(ValueError, 'latched'):
                reader.read()

    def test_valid_header_without_position_evidence_does_not_pass_reference(self):
        raw = ULog.HEADER_BYTES+b'\x01'+struct.pack('<Q', 1)
        with reader_context(raw) as (_, _, reader):
            reader.consume(allow_incomplete=True)
            log = reader.read()
            with self.assertRaises((KeyError, ValueError, IndexError)):
                prearm.reference_row(log)

    def test_bad_header_is_not_reclassified_as_pending(self):
        with reader_context(b'not-a-ULog-file!!') as (_, _, reader):
            with self.assertRaisesRegex(ValueError, 'header'):
                reader.consume(allow_incomplete=True)
            self.assertTrue(reader.failed)
            with self.assertRaisesRegex(ValueError, 'latched'):
                reader.consume(allow_incomplete=True)

    def test_old_snapshot_immutable_and_new_snapshot_contains_all_rows(self):
        tables, reference = fixture.heading_tables()
        header, packets = fixture.encode(tables)
        cut = next(i for i, p in enumerate(packets) if p[0] > 3000000)
        first = header+b''.join(p[3] for p in packets[:cut])
        tail = b''.join(p[3] for p in packets[cut:])
        with reader_context(first) as (_, path, reader):
            reader.consume(allow_incomplete=True)
            before = reader.read()
            old = before.get_dataset('vehicle_attitude').data['timestamp'].copy()
            initial = fixture.clock09.replay(before, reference, allow_pending=True)
            decoder = reader.decoder
            old_records = decoder.records
            append(path, tail)
            after = reader.read()
            self.assertIs(reader.decoder, decoder)
            np.testing.assert_array_equal(before.get_dataset('vehicle_attitude').data['timestamp'], old)
            self.assertGreater(len(after.get_dataset('vehicle_attitude').data['timestamp']), len(old))
            self.assertEqual(reader.last_timing['new_records'], decoder.records-old_records)
            self.assertEqual(reader.last_timing['new_bytes'], len(tail))
            result = fixture.clock09.replay(after, reference, frozen=initial['freeze_candidate'])
            expected = fixture.clock09.replay(
                fixture.position.PositionLogView(ULog(io.BytesIO(first+tail))),
                reference, frozen=initial['freeze_candidate'])
            self.assertEqual(result, expected)
            self.assertEqual(result['position_samples'], 300)

    def test_incomplete_tail_is_decoded_once_when_completed(self):
        tables, _ = fixture.heading_tables()
        header, packets = fixture.encode(tables)
        last = packets[-1][3]
        raw = header+b''.join(p[3] for p in packets[:-1])+last[:-1]
        with reader_context(raw) as (_, path, reader):
            reader.consume(allow_incomplete=True)
            count = reader.decoder.records
            self.assertEqual(reader.decoder.pending, last[:-1])
            reader.read()
            self.assertEqual(reader.decoder.records, count)
            append(path, last[-1:])
            reader.read()
            self.assertEqual(reader.decoder.records, count+1)
            self.assertEqual(reader.decoder.pending, b'')
            reader.read()
            self.assertEqual(reader.decoder.records, count+1)
            self.assertEqual(reader.last_timing['new_records'], 0)

    def assert_suffix_rejected_and_latched(self, suffix, pattern):
        tables, _ = fixture.heading_tables()
        with reader_context(encoded(tables)) as (_, path, reader):
            reader.consume(allow_incomplete=True)
            decoder = reader.decoder
            append(path, suffix)
            with self.assertRaisesRegex((ValueError, KeyError), pattern):
                reader.read()
            self.assertIs(reader.decoder, decoder)
            self.assertTrue(reader.failed)
            with self.assertRaisesRegex(ValueError, 'latched'):
                reader.consume(allow_incomplete=True)

    def test_dropout_after_warmup_is_permanent_failure(self):
        self.assert_suffix_rejected_and_latched(fixture.record('O', struct.pack('<H', 1)), 'dropout')

    def test_bad_subscription_after_warmup_is_permanent_failure(self):
        self.assert_suffix_rejected_and_latched(fixture.record('A', b'\x00\x01'), 'subscription')

    def test_replaced_subscription_after_warmup_is_permanent_failure(self):
        body = struct.pack('<BH', 0, 1)+b'vehicle_local_position'
        self.assert_suffix_rejected_and_latched(fixture.record('A', body), 'Repeated/replaced')

    def test_unknown_subscription_data_after_warmup_is_permanent_failure(self):
        self.assert_suffix_rejected_and_latched(fixture.record('D', struct.pack('<H', 65535)), 'Unknown')

    def test_schema_change_after_warmup_is_permanent_failure(self):
        self.assert_suffix_rejected_and_latched(
            fixture.record('F', b'new_topic:uint64_t timestamp;'), 'format changed')

    def test_replaced_file_after_warmup_does_not_construct_new_reader(self):
        tables, _ = fixture.heading_tables()
        raw = encoded(tables)
        with reader_context(raw) as (root, path, reader):
            reader.consume(allow_incomplete=True)
            identity = reader.inode
            path.rename(root/'original.ulg')
            path.write_bytes(raw)
            self.assertNotEqual(path.stat().st_ino, identity)
            with self.assertRaisesRegex(ValueError, 'replaced/truncated'):
                reader.read()
            self.assertEqual(reader.inode, identity)
            self.assertTrue(reader.failed)

    def test_truncated_file_after_warmup_does_not_restart_decoder(self):
        tables, _ = fixture.heading_tables()
        with reader_context(encoded(tables)) as (_, path, reader):
            reader.consume(allow_incomplete=True)
            decoder = reader.decoder
            with path.open('r+b') as stream:
                stream.truncate(16)
            with self.assertRaisesRegex(ValueError, 'replaced/truncated'):
                reader.read()
            self.assertIs(reader.decoder, decoder)
            self.assertTrue(reader.failed)


class CompleteHistoryTests(unittest.TestCase):
    """Use the original replay window, never reset reference to hide a fault.

    Startup coordinate/heading changes *before* a newly selected prearm
    reference are not retroactively forbidden. These cases exercise the fixed
    reference's later window, including the first predecessor/boundary rows.
    """

    def assert_rejected_after_tail(self, tables, reference, pattern):
        header, packets = fixture.encode(tables)
        cut = next(i for i, p in enumerate(packets) if p[0] > 3000000)
        initial = header+b''.join(p[3] for p in packets[:cut])
        tail = b''.join(p[3] for p in packets[cut:])
        with reader_context(initial) as (_, path, reader):
            reader.consume(allow_incomplete=True)
            first = fixture.clock09.replay(reader.read(), reference, allow_pending=True)
            self.assertTrue(first['ready'])
            append(path, tail[:-1])
            reader.consume(allow_incomplete=True)
            append(path, tail[-1:])
            log = reader.read()
            with self.assertRaisesRegex(ValueError, pattern):
                fixture.clock09.replay(log, reference, frozen=first['freeze_candidate'], allow_pending=True)

    def test_single_sample_controller_fault_not_hidden_by_later_good_rows(self):
        tables, reference = fixture.heading_tables()
        d = tables[('sta_velocity_ctrl_status', 0)]
        d['first_fail'][d['timestamp'] == 3200000] = 1
        self.assert_rejected_after_tail(tables, reference, 'Controller')

    def test_single_sample_estimator_fault_not_hidden_by_later_good_rows(self):
        tables, reference = fixture.heading_tables()
        d = tables[('estimator_status', 1)]
        d['filter_fault_flags'][d['timestamp'] == 3200000] = 1
        self.assert_rejected_after_tail(tables, reference, 'Filter fault')

    def test_coordinate_reset_in_preserved_history_rejected(self):
        tables, reference = fixture.heading_tables()
        for name in ('vehicle_local_position', fixture.position.TOPIC):
            d = tables[(name, 0)]
            d['z_reset_counter'][d['timestamp'] >= 3200000] += 1
        self.assert_rejected_after_tail(tables, reference, 'Coordinate/reset')

    def test_repeated_heading_reset_in_preserved_history_rejected(self):
        tables, reference = fixture.heading_tables()
        for name in ('vehicle_local_position', fixture.position.TOPIC):
            d = tables[(name, 0)]
            d['heading_reset_counter'][d['timestamp'] >= 3200000] += 1
        self.assert_rejected_after_tail(tables, reference, 'Repeated')

    def test_consumed_sample_not_silently_reassociated(self):
        tables, reference = fixture.heading_tables()
        d = tables[('sta_velocity_ctrl_status', 0)]
        d['timestamp_sample'][d['timestamp'] == 3200000] += 1
        self.assert_rejected_after_tail(tables, reference, 'Consumed')

    def test_signed_zero_mirror_corruption_remains_bitwise_checked(self):
        tables, reference = fixture.heading_tables()
        d = tables[(fixture.position.TOPIC, 0)]
        d['x'][d['timestamp'] == 3200000] = -0.
        self.assert_rejected_after_tail(tables, reference, 'payload mismatch')

    def test_mirror_sequence_gap_not_filled(self):
        tables, reference = fixture.heading_tables()
        d = tables[(fixture.position.TOPIC, 0)]
        d['log_seq'][d['timestamp'] >= 3200000] += 1
        self.assert_rejected_after_tail(tables, reference, 'sequence')

    def test_non_attitude_duplicate_not_whitelisted(self):
        tables, reference = fixture.heading_tables()
        d = tables[('sta_velocity_ctrl_status', 0)]
        index = int(np.flatnonzero(d['timestamp'] == 3200000)[0])
        for key, values in list(d.items()):
            d[key] = np.insert(values, index, values[index])
        self.assert_rejected_after_tail(tables, reference, 'nonmonotonic')

    @contextmanager
    def tied_tail(self, mutation=None):
        tables, reference = fixture.heading_tables()
        a = tables[('vehicle_attitude', 0)]
        index = int(np.flatnonzero(a['timestamp'] == 3000000)[0])
        for key, values in list(a.items()):
            a[key] = np.insert(values, index+1, values[index])
        a['timestamp_sample'][index] = 2996000
        if mutation:
            mutation(a, index+1)
        header, packets = fixture.encode(tables)
        cut = next(i for i, p in enumerate(packets)
                   if p[1] == 'vehicle_attitude' and p[2] == index+1)
        with reader_context(header+b''.join(p[3] for p in packets[:cut])) as (_, path, reader):
            reader.consume(allow_incomplete=True)
            first = reader.read()
            self.assertEqual(fixture.clock09.sealed_time(first), 2990000)
            self.assertTrue(fixture.clock09.replay(first, reference, allow_pending=True)['ready'])
            append(path, b''.join(p[3] for p in packets[cut:]))
            yield reader.read(), reference

    def test_same_publication_late_row_is_retained_and_not_claimed_consumed(self):
        with self.tied_tail() as (log, reference):
            attitude = fixture.attitude_policy().data(log)
            self.assertEqual(attitude['timestamp_sample'][attitude['timestamp'] == 3000000].tolist(),
                             [2996000, 3000000])
            with self.assertRaisesRegex(ValueError, 'Ambiguous'):
                fixture.attitude_policy().unique_index(attitude, 3000000)
            self.assertTrue(fixture.clock09.replay(log, reference)['ready'])

    def test_late_same_publication_tilt_violation_not_dropped(self):
        def mutation(a, i):
            a['q[0]'][i] = math.cos(.2)
            a['q[1]'][i] = math.sin(.2)
        with self.tied_tail(mutation) as (log, reference):
            with self.assertRaisesRegex(ValueError, 'tilt'):
                fixture.clock09.replay(log, reference)

    def test_late_same_publication_quaternion_reset_not_dropped(self):
        def mutation(a, i):
            a['quat_reset_counter'][i] = 4
        with self.tied_tail(mutation) as (log, reference):
            with self.assertRaisesRegex(ValueError, 'Repeated'):
                fixture.clock09.replay(log, reference)

    def test_late_same_publication_duplicate_sample_not_repaired(self):
        def mutation(a, i):
            a['timestamp_sample'][i] = 2996000
        with self.tied_tail(mutation) as (log, reference):
            with self.assertRaisesRegex(ValueError, 'Nonunique'):
                fixture.clock09.replay(log, reference)

    def test_late_same_publication_nan_not_repaired(self):
        def mutation(a, i):
            a['q[0]'][i] = np.nan
        with self.tied_tail(mutation) as (log, reference):
            with self.assertRaisesRegex(ValueError, 'Nonfinite'):
                fixture.clock09.replay(log, reference)

    def test_original_boundary_predecessor_requirement_survives_warming(self):
        tables, reference = fixture.heading_tables()
        a = tables[('vehicle_attitude', 0)]
        mask = a['timestamp'] >= reference['position']['timestamp']
        for key, values in list(a.items()):
            a[key] = values[mask].copy()
        with reader_context(encoded(tables)) as (_, _, reader):
            reader.consume(allow_incomplete=True)
            with self.assertRaisesRegex(ValueError, 'boundary predecessor'):
                fixture.clock09.replay(reader.read(), reference)


def input_fingerprints():
    paths = [Path(__file__).resolve(), HERE/'integration.py',
             HERE.parent/'r03_monitor02/incremental.py',
             HERE.parent/'r03_monitor02/integration.py',
             HERE.parent/'r03_monitor02/test_integration.py',
             REPO/'research/sta-velocity-control/axis_ablation/ax04/run.py',
             REPO/'research/sta-velocity-control/v08/protocol02/position_log.py',
             REPO/'research/sta-velocity-control/scripts/v04_prearm17.py',
             REPO/'research/sta-velocity-control/scripts/v04_live_clock09.py',
             REPO/'research/sta-velocity-control/scripts/v04_attitude_clock09.py',
             REPO/'research/sta-velocity-control/scripts/v04_heading_stream.py']
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt-dir', type=Path)
    args = parser.parse_args()
    if args.receipt_dir:
        args.receipt_dir.mkdir(parents=True, exist_ok=False)
    before = input_fingerprints()
    output = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    after = input_fingerprints()
    unchanged = before == after
    exit_code = 0 if result.wasSuccessful() and unchanged else 1
    text = output.getvalue()
    print(text, end='')
    if args.receipt_dir:
        (args.receipt_dir/'tests.log').write_text(text)
        (args.receipt_dir/'evidence.json').write_text(json.dumps(dict(
            command=[sys.executable, *sys.argv], tests=result.testsRun,
            failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
            exit_code=exit_code, success=exit_code == 0, input_sha256_before=before,
            input_sha256_after=after, input_sha256_unchanged=unchanged,
            new_flights=0, new_flight_authorizations=0,
            historical_acceptance_unchanged=True,
            scope='Synthetic binary streams and unchanged historical predicates; not flight acceptance.'),
            indent=2)+'\n')
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
