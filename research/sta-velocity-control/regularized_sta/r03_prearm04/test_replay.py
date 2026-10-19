#!/usr/bin/env python3
"""Offline replay plumbing tests. No simulator or original-log writes."""
import argparse
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('prearm04_replay_tested', HERE/'replay.py')
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


def packet(kind, body):
    return struct.pack('<HB', len(body), ord(kind))+body


HEADER = b'ULog\x01\x12\x35\x01'+struct.pack('<Q', 1)


def fixture(times=(100, 200, 300), schema='uint64_t timestamp;float value;'):
    raw = HEADER+packet('F', ('vehicle_local_position_log:'+schema).encode())
    raw += packet('A', struct.pack('<BH', 0, 9)+b'vehicle_local_position_log')
    for t in times:
        raw += packet('D', struct.pack('<HQf', 9, t, 1.25))
        raw += packet('I', b'\x0cchar[3] noteabc')
    return raw


class ScannerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='prearm04-replay-test-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'fixture.ulg'

    def scan(self, raw=None):
        self.path.write_bytes(fixture() if raw is None else raw)
        return replay.scan_anchors(self.path)

    def test_anchor_index_is_physical_continuous_prefix(self):
        raw = fixture(); index = self.scan(raw)
        self.assertEqual(index['times'], [100, 200, 300])
        self.assertEqual(index['bytes'], len(raw))
        self.assertEqual(index['records'][0][0], 16)
        self.assertTrue(all(a[1] == b[0] for a, b in zip(index['records'], index['records'][1:])))
        self.assertIn(b'char[3] noteabc', raw[:index['ends'][1]])

    def test_selects_last_anchor_not_future(self):
        index = self.scan()
        rows = replay.select_limits(index, [100, 199, 200, 1000])
        self.assertEqual([r['anchor_us'] for r in rows], [100, 100, 200, 300])
        self.assertEqual([r['raw_limit'] for r in rows], [index['ends'][i] for i in [0, 0, 1, 2]])

    def test_repeated_warmup_is_not_deduplicated(self):
        rows = replay.select_limits(self.scan(), [100]*4)
        self.assertEqual(len(rows), 4)

    def test_empty_warmup_rejected(self):
        with self.assertRaises(ValueError): replay.select_limits(self.scan(), [])

    def test_backwards_warmup_rejected(self):
        with self.assertRaises(ValueError): replay.select_limits(self.scan(), [200, 100])

    def test_no_causal_anchor_rejected(self):
        with self.assertRaises(ValueError): replay.select_limits(self.scan(), [99])

    def test_timestamp_schema_required(self):
        with self.assertRaisesRegex(ValueError, 'first uint64'): self.scan(fixture(schema='float value;uint64_t timestamp;'))

    def test_duplicate_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError, 'strictly'): self.scan(fixture((100, 100)))

    def test_backwards_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError, 'strictly'): self.scan(fixture((200, 100)))

    def test_unknown_subscription_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown'): self.scan(fixture()+packet('D', struct.pack('<HQ', 42, 500)))

    def test_truncated_record_header_rejected(self):
        with self.assertRaisesRegex(ValueError, 'header'): self.scan(fixture()+b'\x05')

    def test_truncated_record_body_rejected(self):
        with self.assertRaisesRegex(ValueError, 'body'): self.scan(fixture()[:-1])

    def test_invalid_header_rejected(self):
        with self.assertRaisesRegex(ValueError, 'header'): self.scan(b'bad!'+fixture()[4:])

    def test_no_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError, 'No position'): self.scan(HEADER)

    def test_partial_tail_probes_are_ordered_and_complete(self):
        index = self.scan(); limit = index['ends'][1]
        probes = replay.boundary_probes(index, limit)
        self.assertEqual([p[0] for p in probes], ['repeat', 'partial_header', 'partial_body', 'complete_tail_record'])
        self.assertEqual(probes[0][1], limit); self.assertEqual(probes[1][1], limit+1)
        self.assertEqual(probes[2][1]+1, probes[3][1])

    def test_non_boundary_probe_rejected(self):
        index = self.scan()
        with self.assertRaises(ValueError): replay.boundary_probes(index, index['ends'][0]+1)

    def original_commands(self, current=600000):
        rows = [dict(cmd=['px4-listener', 'vehicle_status', '-n', '1'], stdout='timestamp: 1\n'),
                dict(cmd=['px4-listener', 'vehicle_local_position', '-n', '1'], stdout=f'timestamp: {current}\n')]
        folder = Path(self.temp.name)
        (folder/'commands.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
        return folder

    def test_original_age_inclusive_500ms(self):
        folder = self.original_commands()
        (folder/'height_reference.json').write_text(json.dumps(dict(position=dict(timestamp=100000))))
        self.assertEqual(replay.historical_prearm(folder)['original_age_us'], 500000)

    def test_unknown_original_age_stays_unknown(self):
        result = replay.historical_prearm(self.original_commands())
        self.assertIsNone(result['original_age_us']); self.assertIsNone(result['original_exact_writer_cutoff_bytes'])

    def test_original_stale_age_not_relabelled(self):
        folder = self.original_commands(600001)
        (folder/'height_reference.json').write_text(json.dumps(dict(position=dict(timestamp=100000))))
        with self.assertRaises(ValueError): replay.historical_prearm(folder)

    def test_existing_output_rejected_before_any_reader(self):
        with self.assertRaisesRegex(ValueError, 'overwrite'): replay.run(Path(self.temp.name))


class ActualReaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        replay.load('prearm04_replay_fixture_runner', HERE.parent/'r03_revision03/runner.py')
        cls.integration = replay.load('prearm04_replay_actual_integration', HERE/'integration.py')
        cls.fixture = replay.load('prearm04_replay_full_fixture', HERE.parent/'r03_monitor02/test_integration.py')

    def test_complete_fixture_and_partial_tail_equal_all_readers(self):
        import position_live
        from v04_prearm17 import reference_row
        from v04_live_clock09 import sealed_time
        tables, _ = self.fixture.heading_tables()
        header, packets = self.fixture.encode(tables)
        raw = header+b''.join(p[3] for p in packets)
        with tempfile.TemporaryDirectory(prefix='prearm04-full-replay-') as name:
            path = Path(name)/'log.ulg'; path.write_bytes(raw)
            seam = replay.utils.PrefixPath(path)
            new = self.integration.OwnedWarmReader(path); new.path = seam
            frozen = self.integration.incremental.PositionLiveLog(path); frozen.path = seam
            seam.limit = 8
            self.assertIsNone(new.consume(allow_incomplete=True))
            for limit in [len(raw)-1, len(raw)-1, len(raw)]:
                seam.limit = limit
                a, b = frozen.read(), new.consume(allow_incomplete=True)
                replay.compare_views(a, b, reference_row, sealed_time)
                self.assertEqual(frozen.offset, new.offset)
            cold = position_live.PositionLiveLog(path)
            replay.compare_views(cold.read(), b, reference_row, sealed_time)
            self.assertEqual(new.decoder.pending, b'')

    def test_full_field_comparison_detects_changed_value(self):
        import numpy as np
        from types import SimpleNamespace
        def view(value):
            return SimpleNamespace(raw=SimpleNamespace(data_list=[SimpleNamespace(name='topic', multi_id=0,
                data={'value':np.array([value], dtype=np.float32)})]))
        with self.assertRaises(AssertionError):
            replay.compare_views(view(1), view(2), lambda _: None, lambda _: None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args, remaining = parser.parse_known_args()
    if args.output is None:
        unittest.main(argv=[__file__]+remaining)
    else:
        if args.output.exists(): raise ValueError('Refuse overwrite of test evidence')
        args.output.mkdir(parents=True)
        captured = io.StringIO()
        suite = unittest.defaultTestLoader.loadTestsFromModule(__import__('__main__'))
        result = unittest.TextTestRunner(stream=captured, verbosity=2).run(suite)
        text = captured.getvalue(); print(text, end='')
        with (args.output/'unittest.log').open('x') as stream: stream.write(text)
        receipt = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                       skipped=len(result.skipped), success=result.wasSuccessful(), new_flights=0,
                       test_sha256=replay.utils.sha(Path(__file__)), replay_sha256=replay.utils.sha(HERE/'replay.py'))
        with (args.output/'evidence.json').open('x') as stream: json.dump(receipt, stream, indent=2)
        raise SystemExit(0 if result.wasSuccessful() else 1)
