#!/usr/bin/env python3
"""Synthetic framing, byte equivalence and fail-closed reader regression."""
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from pyulog import ULog

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('incremental_under_test', HERE/'incremental.py')
inc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inc)


def record(kind, body):
    return struct.pack('<HB', len(body), ord(kind))+body


HEADER = ULog.HEADER_BYTES+b'\x01'+struct.pack('<Q', 1)
FORMAT = record('F', b'test:uint64_t timestamp;float value;uint8_t flag;')
ADD = record('A', struct.pack('<BH', 0, 17)+b'test')


def payload(t=1000, v=1.25, flag=2, ident=17):
    return record('D', struct.pack('<HQfB', ident, t, v, flag))


def fixture():
    return HEADER+FORMAT+ADD+payload()


def equal(a, b):
    assert [(d.name, d.multi_id) for d in a.data_list] == [(d.name, d.multi_id) for d in b.data_list]
    for x, y in zip(a.data_list, b.data_list):
        assert set(x.data) == set(y.data)
        for k in x.data:
            assert x.data[k].dtype == y.data[k].dtype
            assert x.data[k].shape == y.data[k].shape
            assert x.data[k].tobytes() == y.data[k].tobytes()


class IncrementalTest(unittest.TestCase):
    def decode(self, raw, topics=('test',)):
        d = inc.Decoder(topics)
        d.feed(raw)
        return d

    def rejects(self, raw):
        d = inc.Decoder(('test',))
        with self.assertRaises((ValueError, KeyError, IndexError, struct.error)):
            d.feed(raw)
        self.assertTrue(d.failed)
        with self.assertRaisesRegex(ValueError, 'latched'):
            d.feed(fixture())

    def test_every_split_matches_reference(self):
        raw = fixture()+payload(1000, -0.0)+payload(2000, float('nan'))
        expected = ULog(io.BytesIO(raw))
        for split in range(len(raw)+1):
            with self.subTest(split=split):
                d = inc.Decoder(('test',))
                d.feed(raw[:split]); d.feed(raw[split:])
                equal(d.snapshot(), expected)
                self.assertEqual(d.complete_bytes, len(raw))
                self.assertEqual(d.records, 5)

    def test_bytewise_feed(self):
        d = inc.Decoder(('test',))
        for x in fixture():
            d.feed(bytes([x]))
        equal(d.snapshot(), ULog(io.BytesIO(fixture())))

    def test_no_new_bytes_do_not_redecode(self):
        d = self.decode(fixture())
        before = d.records
        d.feed(b''); d.snapshot(); d.feed(b'')
        self.assertEqual(d.records, before)

    def test_complete_boundary_partial_tail(self):
        raw = fixture(); tail = payload(2000)
        d = self.decode(raw+tail[:-1])
        self.assertEqual(d.complete_bytes, len(raw))
        self.assertEqual(len(d.pending), len(tail)-1)
        self.assertEqual(len(d.snapshot().get_dataset('test').data['timestamp']), 1)
        d.feed(tail[-1:])
        self.assertEqual(d.complete_bytes, len(raw+tail))

    def test_old_snapshot_unchanged_by_append(self):
        d = self.decode(fixture()); old = d.snapshot()
        d.feed(payload(2000, 2.0)); new = d.snapshot()
        self.assertEqual(len(old.get_dataset('test').data['timestamp']), 1)
        self.assertEqual(len(new.get_dataset('test').data['timestamp']), 2)
        with self.assertRaises(ValueError):
            old.get_dataset('test').data['value'][0] = 9

    def test_duplicate_timestamp_is_preserved_not_deduped(self):
        d = self.decode(fixture()+payload())
        self.assertEqual(d.snapshot().get_dataset('test').data['timestamp'].tolist(), [1000, 1000])

    def test_backward_timestamp_not_sorted_or_repaired(self):
        d = self.decode(fixture()+payload(900))
        self.assertEqual(d.snapshot().get_dataset('test').data['timestamp'].tolist(), [1000, 900])

    def test_signed_zero_and_nan_bits_preserved(self):
        raw = fixture()+record('D', struct.pack('<HQ', 17, 2000)+b'\x34\x12\xc0\x7f\x00')+payload(3000, -0.0)
        equal(self.decode(raw).snapshot(), ULog(io.BytesIO(raw)))

    def test_nested_arrays_and_instances_match(self):
        raw = HEADER+record('F', b'child:float[2] xy;')
        raw += record('F', b'test:uint64_t timestamp;child c;uint8_t flag;')
        raw += ADD+record('A', struct.pack('<BH', 2, 18)+b'test')
        for ident in (17, 18):
            raw += record('D', struct.pack('<HQffB', ident, 1000, 1, -2, 3))
        equal(self.decode(raw).snapshot(), ULog(io.BytesIO(raw)))

    def test_filtered_topic_not_materialized(self):
        self.assertEqual(self.decode(fixture(), topics=('other',)).snapshot().data_list, [])

    def test_valid_flags(self):
        raw = HEADER+record('B', bytes(40))+FORMAT+ADD+payload()
        equal(self.decode(raw).snapshot(), ULog(io.BytesIO(raw)))

    def test_valid_sync(self):
        raw = fixture()+record('S', ULog.SYNC_BYTES)
        equal(self.decode(raw).snapshot(), ULog(io.BytesIO(raw)))

    def test_incomplete_header_cannot_snapshot(self):
        d = self.decode(HEADER[:15])
        with self.assertRaises(ValueError): d.snapshot()

    def test_missing_schema_fails(self): self.rejects(HEADER+ADD)
    def test_bad_header_fails(self): self.rejects(b'X'+fixture()[1:])
    def test_bad_version_fails(self): self.rejects(HEADER[:7]+b'\x02'+fixture()[8:])
    def test_unknown_id_fails(self): self.rejects(fixture()+payload(ident=18))
    def test_dropout_fails(self): self.rejects(fixture()+record('O', b'\x01\x00'))
    def test_unknown_type_fails(self): self.rejects(fixture()+record('Z', b'x'))
    def test_empty_record_fails(self): self.rejects(fixture()+record('D', b''))
    def test_oversized_record_fails(self): self.rejects(fixture()+struct.pack('<HB', 10001, ord('D')))
    def test_short_data_fails(self): self.rejects(fixture()+record('D', b'\x11\x00\x01'))
    def test_large_payload_fails(self): self.rejects(fixture()+record('D', struct.pack('<HQfBH', 17, 2000, 1, 1, 1)))
    def test_duplicate_subscription_fails(self): self.rejects(fixture()+ADD)
    def test_duplicate_name_instance_fails(self): self.rejects(fixture()+record('A', struct.pack('<BH', 0, 18)+b'test'))
    def test_remove_subscription_fails(self): self.rejects(fixture()+record('R', b'\x11\x00'))
    def test_late_format_fails(self): self.rejects(fixture()+FORMAT)
    def test_repeated_format_fails(self): self.rejects(HEADER+FORMAT+FORMAT)
    def test_bad_sync_fails(self): self.rejects(fixture()+record('S', b'12345678'))
    def test_late_flags_fails(self): self.rejects(fixture()+record('B', bytes(40)))
    def test_bad_flags_size_fails(self): self.rejects(HEADER+record('B', bytes(39)))
    def test_incompatible_flags_fails(self): self.rejects(HEADER+record('B', bytes(8)+b'\x01'+bytes(31)))
    def test_appended_offsets_fails(self): self.rejects(HEADER+record('B', bytes(16)+struct.pack('<QQQ', 100, 0, 0)))

    def test_dependency_fingerprint_fails_closed(self):
        with patch.object(inc, 'PYULOG_SHA256', '0'*64):
            with self.assertRaisesRegex(ValueError, 'frozen pyulog'): inc.Decoder()

    def test_total_bound_fails_closed(self):
        with patch.object(inc, 'MAX_BYTES', 16): self.rejects(fixture())

    def test_instances_are_isolated(self):
        a, b = self.decode(fixture()), self.decode(fixture())
        a.feed(payload(2000))
        self.assertEqual(b.selected_records, 1)


class FileReaderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='r03-monitor-test-')
        self.path = Path(self.tmp.name)/'test.ulg'
        self.path.write_bytes(fixture())
        self.reader = inc.PositionLiveLog(self.path)

    def tearDown(self): self.tmp.cleanup()

    def test_reader_zero_growth(self):
        self.reader.read(); count = self.reader.decoder.records
        self.reader.read()
        self.assertEqual(self.reader.last_timing['new_bytes'], 0)
        self.assertEqual(self.reader.decoder.records, count)

    def test_reader_append_is_incremental(self):
        self.reader.read()
        with self.path.open('ab') as stream: stream.write(payload(2000))
        self.reader.read()
        self.assertEqual(self.reader.last_timing['new_records'], 1)
        self.assertEqual(self.reader.last_timing['new_bytes'], len(payload(2000)))

    def test_reader_retains_partial_record(self):
        self.reader.read()
        with self.path.open('ab') as stream: stream.write(payload(2000)[:-1])
        self.reader.read()
        self.assertEqual(self.reader.offset, len(fixture()))
        with self.path.open('ab') as stream: stream.write(payload(2000)[-1:])
        self.reader.read()
        self.assertEqual(self.reader.offset, len(fixture()+payload(2000)))

    def test_reader_truncation_latches(self):
        self.reader.read(); self.path.write_bytes(HEADER)
        with self.assertRaisesRegex(ValueError, 'truncated'): self.reader.read()
        self.path.write_bytes(fixture())
        with self.assertRaisesRegex(ValueError, 'latched'): self.reader.read()

    def test_reader_replacement_latches(self):
        self.reader.read(); other = self.path.with_name('replacement')
        other.write_bytes(fixture()); other.replace(self.path)
        with self.assertRaisesRegex(ValueError, 'replaced'): self.reader.read()


class ReplayReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('monitor_replay_report', HERE/'replay.py')
        cls.report = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.report)

    def test_nonfinite_bits_are_json_safe(self):
        value = {'nested': [float('nan'), float('inf'), -float('inf')]}
        encoded = self.report.report_value(value)
        json.dumps(encoded, allow_nan=False)
        self.assertEqual(encoded['nested'][1]['__float64_bits__'], '7ff0000000000000')
        self.assertEqual(encoded['nested'][2]['__float64_bits__'], 'fff0000000000000')
        self.assertIsInstance(value['nested'][0], float)

    def test_distinct_nan_payloads_not_equal(self):
        a = struct.unpack('>d', bytes.fromhex('7ff8000000000001'))[0]
        b = struct.unpack('>d', bytes.fromhex('7ff8000000000002'))[0]
        self.assertTrue(self.report.same(a, a)); self.assertFalse(self.report.same(a, b))

    def test_signed_zero_not_erased_in_report(self):
        self.assertFalse(self.report.same(-0.0, 0.0))

    def test_only_first_cold_poll_excluded(self):
        result = self.report.benchmark_summary([{'timing': {'total_s': t}} for t in (3., .02, .03)])
        self.assertEqual(result['warm_polls'], 2)
        self.assertEqual(result['warm_max_s'], .03)
        self.assertTrue(result['offline_headroom_pass'])

    def test_slow_or_boundary_poll_never_discarded(self):
        for t in (.25, .251, 2.):
            result = self.report.benchmark_summary([{'timing': {'total_s': x}} for x in (3., .02, t, .03)])
            self.assertFalse(result['offline_headroom_pass'])
            self.assertEqual(result['warm_polls'], 3)

    def test_empty_or_only_cold_cannot_pass(self):
        for rows in ([], [{'timing': {'total_s': .01}}]):
            with self.assertRaises(ValueError): self.report.benchmark_summary(rows)

    def test_nonfinite_or_negative_time_rejected(self):
        for t in (float('nan'), float('inf'), -.1):
            with self.assertRaises(ValueError):
                self.report.benchmark_summary([{'timing': {'total_s': x}} for x in (0., t)])


if __name__ == '__main__':
    unittest.main(verbosity=2)
