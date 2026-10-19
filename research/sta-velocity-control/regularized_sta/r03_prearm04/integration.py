"""Offline-only opt-in preparation of the existing complete-history reader.

This factory grants no execution authority and changes no historical module.
It moves decoding into ordinary warmup calls, not the safety clock: prearm
still obtains CLI time after its one bounded tail snapshot/reference read.
Missing files and an incomplete first header are preparation states, never
acceptance. Parser/identity/safety failures latch, with no recovery or retry.
"""
import ast
import importlib.util
import inspect
import json
import math
import numbers
import os
from pathlib import Path
import textwrap
import time

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    'r03_prearm04_frozen_incremental', HERE.parent/'r03_monitor02/incremental.py')
incremental = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(incremental)
RECEIPT = 'r03_prearm04_timing.jsonl'


def evidence_value(value):
    """Represent invalid telemetry in the receipt without masking its failure.

    This conversion is for JSON evidence only; no value passed to a historical
    predicate is altered, nor is a NaN silently turned into zero or null.
    """
    if isinstance(value, dict):
        return {key: evidence_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [evidence_value(item) for item in value]
    if isinstance(value, numbers.Integral):
        return value if isinstance(value, bool) else int(value)
    if isinstance(value, numbers.Real):
        return float(value) if math.isfinite(value) else {'invalid_numeric': repr(float(value))}
    return value


class OwnedWarmReader(incremental.PositionLiveLog):
    """Same decoder/history, with explicit incomplete-header preparation.

Each call reads only through its initial fstat boundary, once; appended bytes
are left for the next scheduled monitor call. No tail chasing, truncation,
filtering or cold re-opening is used. The original 128 MiB session cap remains.
"""
    def consume(self, *, allow_incomplete=False):
        began = time.monotonic()
        timing = dict(read_s=0., decode_s=0., snapshot_s=0., new_bytes=0,
                      new_records=0, error=None, completed=False)
        self.last_timing = timing
        try:
            if self.failed:
                raise ValueError('Incremental live reader latched')
            stat = self.path.stat()
            if ((stat.st_ino, stat.st_dev) != (self.inode, self.device)
                    or stat.st_size < self.last_size):
                raise ValueError('Live log replaced/truncated')
            if stat.st_size > incremental.MAX_BYTES:
                raise ValueError('Unexpected oversized flight log')
            timing['snapshot_end_bytes'] = stat.st_size
            previous = self.last_size
            with self.path.open('rb') as stream:
                opened = os.fstat(stream.fileno())
                if (opened.st_ino, opened.st_dev) != (self.inode, self.device):
                    raise ValueError('Live log changed during open')
                stream.seek(previous)
                chunk = stream.read(stat.st_size-previous)
            timing['new_bytes'] = len(chunk)
            timing['read_s'] = time.monotonic()-began
            if len(chunk) != stat.st_size-previous:
                raise ValueError('Live log shortened during read')
            decode_begin = time.monotonic()
            records = self.decoder.records
            try:
                self.decoder.feed(chunk)
            finally:
                timing['decode_s'] = time.monotonic()-decode_begin
                timing['new_records'] = self.decoder.records-records
            self.last_size = stat.st_size
            self.offset = self.decoder.complete_bytes
            if not self.decoder.header and allow_incomplete:
                timing['preparation_pending'] = 'incomplete_first_header'
                return None
            snapshot_begin = time.monotonic()
            try:
                result = self.view(self.decoder.snapshot())
            finally:
                timing['snapshot_s'] = time.monotonic()-snapshot_begin
            timing['completed'] = True
            return result
        except BaseException as exc:
            self.failed = True
            timing['error'] = repr(exc)
            raise
        finally:
            timing.update(raw_bytes=self.last_size, raw_offset=self.offset,
                          received_bytes=self.decoder.received_bytes,
                          complete_bytes=self.decoder.complete_bytes,
                          pending_bytes=len(self.decoder.pending),
                          total_records=self.decoder.records,
                          host_elapsed_s=time.monotonic()-began)

    def read(self):
        return self.consume()


def bind_start_heading(function):
    """Preserve original safety expressions/order; bind three measured hooks.

    The only semantic replacement is constructor+read -> the already warmed
    reader's one tail read. Reference selection/replay wrappers call exactly
    the imported original functions, unchanged. No earlier 'now' is supplied.
    """
    source = Path(inspect.getsourcefile(function)).resolve()
    expected = incremental.REPO/'research/sta-velocity-control/axis_ablation/ax04/run.py'
    if source != expected:
        raise ValueError('Unexpected inherited heading implementation')
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    body = tree.body[0].body
    substitutions = (
        ('from position_live import PositionLiveLog', None),
        ('self.live=PositionLiveLog(owned_log(self.log_root,self.logs_before))', None),
        ('log=self.live.read()', 'log=self._prearm_log()'),
        ('p=reference_row(log)', 'p=self._prearm_reference(log,reference_row)'),
        ('replay(log,ref)', 'self._prearm_replay(log,ref,replay)'),
    )
    for before, after in substitutions:
        needle = ast.dump(ast.parse(before).body[0])
        indices = [i for i, node in enumerate(body) if ast.dump(node) == needle]
        if len(indices) != 1:
            raise ValueError('Unexpected inherited prearm statement: '+before)
        index = indices[0]
        if after is None:
            body.pop(index)
        else:
            body[index] = ast.parse(after).body[0]
    namespace = dict(function.__globals__)
    exec(compile(ast.fix_missing_locations(tree), str(source), 'exec'), namespace)
    return namespace[function.__name__]


def make_checks(base_cls):
    original = base_cls.start_heading
    start = bind_start_heading(original)
    owned_log = original.__globals__['owned_log']

    class PrearmPreparedChecks(base_cls):
        """Opt-in class only; base execution/qualification methods are inherited."""
        def _prearm_state(self):
            if not hasattr(self, '_prearm04'):
                self._prearm04 = dict(reader=None, warmup_reads=0,
                                     started=False, failed=False, call=None)
            return self._prearm04

        def _prearm_record(self, output, phase, action):
            state = self._prearm_state()
            began = time.monotonic()
            receipt = dict(phase=phase, error=None, host_started=began,
                           actual_cli=[], reference_timestamp_us=None,
                           sealed_watermark_us=None, warmup_reads=state['warmup_reads'],
                           transport_max_age_us=500000, execution_authority_granted=False,
                           segments={}, read_attempted=False)
            state['call'] = receipt
            try:
                if state['failed']:
                    raise RuntimeError('Prearm preparation failure latched')
                return action(receipt)
            except BaseException as exc:
                state['failed'] = True
                receipt['error'] = repr(exc)
                raise
            finally:
                reader = state['reader']
                receipt.update(host_elapsed_s=time.monotonic()-began,
                               warmup_reads=state['warmup_reads'],
                               failure_latched=state['failed'],
                               reader_path=str(reader.path) if reader else None,
                               reader_inode=reader.inode if reader else None,
                               reader_device=reader.device if reader else None,
                               raw_reader=dict(reader.last_timing) if reader and receipt['read_attempted'] else {})
                state['call'] = None
                with (Path(output)/RECEIPT).open('a') as stream:
                    stream.write(json.dumps(evidence_value(receipt), allow_nan=False)+'\n')

        def _prearm_owned_reader(self, *, preparation):
            state = self._prearm_state()
            if self.log_root is None or not hasattr(self, 'logs_before'):
                raise RuntimeError('Prearm logger ownership was not prepared')
            # Zero files is permitted only before the first reader exists;
            # ambiguity/wrong path/previously bound file loss is never pending.
            paths = set(Path(self.log_root).glob('**/*.ulg'))-self.logs_before
            if not paths and state['reader'] is None and preparation:
                state['call']['preparation_pending'] = 'owned_file_not_created'
                return None
            path = owned_log(self.log_root, self.logs_before)
            if state['reader'] is None:
                if not preparation:
                    raise RuntimeError('Prearm reader was not warmed')
                state['reader'] = OwnedWarmReader(path)
            elif Path(path) != state['reader'].path:
                raise RuntimeError('Owned prearm logfile changed')
            return state['reader']

        def _prearm_warmup(self):
            state = self._prearm_state()
            if state['started']:
                raise RuntimeError('Warmup after prearm start is forbidden')
            reader = self._prearm_owned_reader(preparation=True)
            if reader is None:
                return
            state['call']['read_attempted'] = True
            log = reader.consume(allow_incomplete=True)
            if log is not None:
                state['warmup_reads'] += 1
            else:
                state['call']['preparation_pending'] = 'incomplete_first_header'

        def _prearm_log(self):
            state = self._prearm_state()
            if state['warmup_reads'] < 1:
                raise RuntimeError('Prearm reader has no completed warmup read')
            reader = self._prearm_owned_reader(preparation=False)
            state['call']['read_attempted'] = True
            self.live = reader
            return reader.read()

        def _prearm_reference(self, log, function):
            receipt = self._prearm_state()['call']
            began = time.monotonic()
            try:
                value = function(log)
                receipt['reference_timestamp_us'] = value['timestamp']
                # This is the same deterministic watermark used by the
                # original reference_row. Obtain it before CLI time; record
                # it even when the subsequent unchanged freshness guard fails.
                receipt['sealed_watermark_us'] = function.__globals__['sealed_time'](log)
                return value
            finally:
                receipt['segments']['reference_s'] = time.monotonic()-began

        def _prearm_replay(self, log, ref, function):
            receipt = self._prearm_state()['call']
            began = time.monotonic()
            try:
                value = function(log, ref)
                receipt['sealed_watermark_us'] = value.get('through_us')
                return value
            finally:
                receipt['segments']['history_replay_s'] = time.monotonic()-began

        def _prearm_topic(self, topic, receipt):
            def observed(name, *args, **kwargs):
                began = time.monotonic()
                row = dict(topic=name, started_monotonic=began,
                           timestamp_us=None, receipt=None, error=None)
                receipt['actual_cli'].append(row)
                try:
                    value = topic(name, *args, **kwargs)
                    row['timestamp_us'] = value.get('timestamp')
                    row['receipt'] = value.get('_clock')
                    return value
                except BaseException as exc:
                    row['error'] = repr(exc)
                    raise
                finally:
                    row['host_elapsed_s'] = time.monotonic()-began
            return observed

        def start_heading(self, topic, output):
            def action(receipt):
                state = self._prearm_state()
                if state['started']:
                    raise RuntimeError('Repeated prearm start is forbidden')
                state['started'] = True
                return start(self, self._prearm_topic(topic, receipt), output)
            return self._prearm_record(output, 'prearm', action)

        def monitor(self, phase, cli, topic, output, state):
            def action(receipt):
                began = time.monotonic()
                reader = self._prearm_state()['reader']
                previous_timing = reader.last_timing if reader else None
                try:
                    result = super(PrearmPreparedChecks, self).monitor(
                        phase, cli, self._prearm_topic(topic, receipt), output, state)
                finally:
                    receipt['segments']['parent_monitor_s'] = time.monotonic()-began
                    if reader and reader.last_timing is not previous_timing:
                        # Subsequent heading/landing methods call the same
                        # owned reader themselves. Include their successful
                        # or failed reads without changing their predicates.
                        receipt['read_attempted'] = True
                if phase == 'warmup' and not getattr(self, 'reference', None):
                    self._prearm_warmup()
                return result
            return self._prearm_record(output, phase, action)

    return PrearmPreparedChecks
