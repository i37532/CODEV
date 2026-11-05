"""Landing-only raw reader; historical LiveLog and its topic filter stay unchanged."""
import io
import struct
from pathlib import Path
from pyulog import ULog
from v04_heading_stream import TOPICS as HEADING_TOPICS

from position_log import PositionLogView
TOPICS = HEADING_TOPICS + ["vehicle_command", "vehicle_command_ack", "vehicle_local_position_log"]

class PositionLiveLog:
    """Bounded transport, not a substitute for the final complete flight ULog.

    Logger writes >=4096-byte chunks; fsync cadence is not read visibility.
    Lack of a fresh complete prefix stops admission rather than forcing flushes.
    """
    def __init__(self, path):
        self.path = Path(path)
        self.last_size = 0
        self.inode = self.path.stat().st_ino
        self.offset = 0
        self.prefix = bytearray()
        self.ids = {}

    def read(self):
        stat = self.path.stat()
        if stat.st_ino != self.inode or stat.st_size < self.last_size:
            raise ValueError('Live log replaced/truncated')
        if stat.st_size > 128*1024*1024: raise ValueError('Unexpected oversized flight log')
        self.last_size = stat.st_size
        with self.path.open('rb') as source:
            source.seek(self.offset)
            raw = source.read(stat.st_size-self.offset)
        i = 0
        if self.offset == 0:
            if len(raw)<16 or raw[:7]!=b'ULog\x01\x12\x35': raise ValueError('Missing ULog header')
            self.prefix.extend(raw[:16]); i=16
        while i+3<=len(raw):
            size,kind=struct.unpack_from('<HB',raw,i)
            end=i+3+size
            if end>len(raw): break  # retain incomplete bytes in the original file
            if kind==ord('O'): raise ValueError('ULog dropout in live evidence')
            keep=True
            if kind==ord('A'):
                if size<4: raise ValueError('Malformed ULog subscription')
                msg_id=struct.unpack_from('<H',raw,i+4)[0]
                name=raw[i+6:end].decode('utf8')
                self.ids[msg_id]=name
            elif kind==ord('D'):
                if size<2: raise ValueError('Malformed ULog data')
                msg_id=struct.unpack_from('<H',raw,i+3)[0]
                if msg_id not in self.ids: raise ValueError('Unknown ULog message ID')
                keep=self.ids[msg_id] in TOPICS
            if keep: self.prefix.extend(raw[i:end])
            i=end
        self.offset+=i
        log = ULog(io.BytesIO(self.prefix), message_name_filter_list=TOPICS)
        if log.dropouts or log.file_corruption: raise ValueError('ULog dropout/corruption')
        return PositionLogView(log)
