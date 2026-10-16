"""Opt-in append-only ULog decoder; preserves every selected row and its bits.

Only framing/decoding is incremental. The existing PositionLogView and complete
heading/landing history checks still run on every returned immutable snapshot.
No time rule, watermark, safety limit, controller or archived log is changed.
The pinned local pyulog supplies the schema flattening and payload decoder.
"""
import copy
import hashlib
import importlib.util
from pathlib import Path
import struct
import time
from types import SimpleNamespace

from pyulog import ULog
import pyulog.core

PYULOG_SHA256 = '130187f7676dd53582f984085a8659f6a2c0545fb627c7a683e7609807a6f2ef'
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
LEGACY = REPO/'research/sta-velocity-control/v08/protocol02'
TOPICS = ('vehicle_local_position', 'vehicle_attitude', 'trajectory_setpoint',
          'vehicle_status', 'vehicle_land_detected', 'estimator_selector_status',
          'estimator_status', 'estimator_status_flags', 'estimator_event_flags',
          'sta_velocity_ctrl_status', 'vehicle_command', 'vehicle_command_ack',
          'vehicle_local_position_log')
MAX_BYTES = 128*1024*1024


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pinned_pyulog():
    if hashlib.sha256(Path(pyulog.core.__file__).read_bytes()).hexdigest() != PYULOG_SHA256:
        raise ValueError('Incremental decoder requires the frozen pyulog implementation')


class Decoder:
    """One framing pass per complete record, with an unconsumed partial tail.

    The supported live session is fixed-schema/append-only. Dynamic formats,
    subscription replacement/removal and appended-data offsets fail closed;
    there is no parser recovery, resync, filtering of faults or deduplication.
    """
    def __init__(self, topics=TOPICS):
        pinned_pyulog()
        self.topics = frozenset(topics)
        self.state = ULog(None)
        self.subscriptions = {}
        self.names = set()
        self.pending = b''
        self.header = False
        self.data_started = False
        self.failed = False
        self.complete_bytes = 0
        self.received_bytes = 0
        self.records = 0
        self.data_records = 0
        self.selected_records = 0
        self.message = ULog._MessageData()
        self._snapshots = {}

    def feed(self, chunk):
        if self.failed:
            raise ValueError('Incremental decoder latched')
        try:
            self.received_bytes += len(chunk)
            if self.received_bytes > MAX_BYTES:
                raise ValueError('Unexpected oversized flight log')
            raw = self.pending + bytes(chunk)
            i = 0
            if not self.header:
                if len(raw) < 16:
                    self.pending = raw
                    return
                if raw[:7] != ULog.HEADER_BYTES or raw[7] not in (0, 1):
                    raise ValueError('Missing/unsupported ULog header')
                self.state._start_timestamp = struct.unpack_from('<Q', raw, 8)[0]
                self.header = True
                i = 16
            while i+3 <= len(raw):
                size, kind = struct.unpack_from('<HB', raw, i)
                end = i+3+size
                if not 0 < size <= 10000:
                    raise ValueError('Malformed ULog message size')
                if end > len(raw):
                    break
                header = SimpleNamespace(msg_size=size, msg_type=kind)
                self._record(raw[i+3:end], header)
                self.records += 1
                i = end
            self.complete_bytes += i
            self.pending = raw[i:]
        except Exception:
            self.failed = True
            raise

    def _record(self, body, header):
        kind = header.msg_type
        if kind == ord('F'):
            if self.data_started:
                raise ValueError('Live format changed after data')
            item = ULog.MessageFormat(body, header)
            if item.name in self.state._message_formats:
                raise ValueError('Repeated live ULog format')
            self.state._message_formats[item.name] = item
        elif kind == ord('A'):
            if len(body) < 4:
                raise ValueError('Malformed ULog subscription')
            item = ULog._MessageAddLogged(body, header, self.state._message_formats)
            key = (item.message_name, item.multi_id)
            if item.msg_id in self.subscriptions or key in self.names:
                raise ValueError('Repeated/replaced live ULog subscription')
            self.names.add(key)
            self.subscriptions[item.msg_id] = item
            if item.message_name in self.topics:
                self.state._subscriptions[item.msg_id] = item
            else:
                self.state._filtered_message_ids.add(item.msg_id)
        elif kind == ord('D'):
            self.data_started = True
            if len(body) < 2:
                raise ValueError('Malformed ULog data')
            msg_id = struct.unpack_from('<H', body)[0]
            if msg_id not in self.subscriptions:
                raise ValueError('Unknown ULog message ID')
            self.data_records += 1
            if self.message.initialize(body, header, self.state._subscriptions, self.state):
                raise ValueError('ULog payload corruption')
            if msg_id in self.state._subscriptions:
                self.selected_records += 1
                self.state._last_timestamp = max(self.state._last_timestamp, self.message.timestamp)
        elif kind == ord('B'):
            if self.records != 0 or len(body) != 40:
                raise ValueError('Unexpected ULog flags position/length')
            flags = ULog._MessageFlagBits(body, header)
            if any(flags.incompat_flags) or flags.appended_offsets:
                raise ValueError('Unsupported incompatible/appended live ULog')
        elif kind == ord('O'):
            raise ValueError('ULog dropout in live evidence')
        elif kind == ord('R'):
            raise ValueError('Live subscription removal is unsupported')
        elif kind == ord('S'):
            if body != ULog.SYNC_BYTES:
                raise ValueError('Invalid ULog sync')
        elif kind in (ord('I'), ord('P')):
            ULog._MessageInfo(body, header)
        elif kind == ord('M'):
            ULog._MessageInfo(body, header, is_info_multiple=True)
        elif kind == ord('Q'):
            ULog._MessageParameterDefault(body, header)
        elif kind == ord('L'):
            ULog.MessageLogging(body, header)
        elif kind == ord('C'):
            ULog.MessageLoggingTagged(body, header)
        else:
            raise ValueError('Unknown live ULog message type')

    def snapshot(self):
        if self.failed or not self.header:
            raise ValueError('Incomplete/latched incremental decoder')
        # Never export a buffer view of a mutable bytearray: a consumer may keep
        # the old snapshot while the next feed appends data.
        rows = []
        for ident, sub in self.state._subscriptions.items():
            if not sub.buffer:
                continue
            cached = self._snapshots.get(ident)
            if cached is None or cached[0] != len(sub.buffer):
                frozen = copy.copy(sub)
                frozen.buffer = bytes(sub.buffer)
                item = ULog.Data(frozen)
                cached = (len(sub.buffer), item)
                self._snapshots[ident] = cached
            rows.append(cached[1])
        result = ULog(None)
        result._start_timestamp = self.state._start_timestamp
        result._last_timestamp = self.state._last_timestamp
        result._data_list = sorted(rows, key=lambda x: (x.name, x.multi_id))
        return result


class PositionLiveLog:
    """Drop-in raw reader with original complete-history position validation."""
    def __init__(self, path):
        self.path = Path(path)
        stat = self.path.stat()
        self.inode, self.device = stat.st_ino, stat.st_dev
        self.offset = self.last_size = 0
        self.decoder = Decoder()
        self.failed = False
        self.last_timing = {}
        self.view = load('r03_monitor02_frozen_position_view', LEGACY/'position_log.py').PositionLogView

    def read(self):
        if self.failed:
            raise ValueError('Incremental live reader latched')
        start = time.monotonic()
        try:
            stat = self.path.stat()
            if (stat.st_ino, stat.st_dev) != (self.inode, self.device) or stat.st_size < self.last_size:
                raise ValueError('Live log replaced/truncated')
            if stat.st_size > MAX_BYTES:
                raise ValueError('Unexpected oversized flight log')
            previous = self.last_size
            with self.path.open('rb') as stream:
                opened = __import__('os').fstat(stream.fileno())
                if (opened.st_ino, opened.st_dev) != (self.inode, self.device):
                    raise ValueError('Live log changed during open')
                stream.seek(previous)
                chunk = stream.read(stat.st_size-previous)
            if len(chunk) != stat.st_size-previous:
                raise ValueError('Live log shortened during read')
            read_end = time.monotonic()
            records = self.decoder.records
            self.decoder.feed(chunk)
            self.last_size = stat.st_size
            self.offset = self.decoder.complete_bytes
            parse_end = time.monotonic()
            result = self.view(self.decoder.snapshot())
            self.last_timing = dict(read_s=read_end-start, decode_s=parse_end-read_end,
                snapshot_s=time.monotonic()-parse_end, new_bytes=len(chunk), raw_bytes=self.last_size,
                raw_offset=self.offset, pending_bytes=len(self.decoder.pending),
                new_records=self.decoder.records-records, total_records=self.decoder.records)
            return result
        except Exception:
            self.failed = True
            raise
