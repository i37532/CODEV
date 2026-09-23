"""Synthetic ULog format round-trip, NOT evidence of a new flight or logger run."""
from pathlib import Path
import re
import struct
import tempfile
import unittest
from pyulog import ULog


class RepairMessageTest(unittest.TestCase):
    def test_generated_format_and_first_failure_survive_ulog_decode(self):
        repo = Path(__file__).resolve().parents[3]
        source = (repo/'build/px4_sitl_default/msg/topics_sources/sta_velocity_ctrl_status.cpp').read_text()
        fields = re.search(r'__orb_sta_velocity_ctrl_status_fields\[\] = "([^"]+)"', source)[1]
        format_bytes = ('sta_velocity_ctrl_status:' + fields).encode()
        self.assertLess(len(format_bytes) + 1, 1500)
        codes = dict(uint64_t='Q', uint32_t='I', uint16_t='H', uint8_t='B', int32_t='i', int8_t='b', bool='B', float='f')
        expected = dict(timestamp=1000000, timestamp_sample=1000000, first_fail=8,
                        first_input=(3<<6)|(7<<9)|(7<<12), retry_result=1,
                        excitation_fault=4, pid_calls=2, valid=1)
        data = bytearray()
        for field in fields.split(';'):
            if not field: continue
            dtype, count, name = re.fullmatch(r'(\w+)(?:\[(\d+)\])? (\w+)', field).groups()
            if name.startswith('_padding'): continue  # logger writes o_size_no_padding
            n = int(count or 1)
            data.extend(struct.pack('<'+codes[dtype]*n, *([expected.get(name, 0)]*n)))
        def message(kind, value): return struct.pack('<HB', len(value), ord(kind)) + value
        blob = ULog.HEADER_BYTES + b'\x01' + struct.pack('<Q', 0)
        blob += message('F', format_bytes)
        blob += message('A', struct.pack('<BH', 0, 1) + b'sta_velocity_ctrl_status')
        blob += message('D', struct.pack('<H', 1) + data)
        with tempfile.TemporaryDirectory(prefix='v04-ulog-format-') as temp:
            path = Path(temp)/'synthetic.ulg'; path.write_bytes(blob)
            decoded = ULog(str(path)).get_dataset('sta_velocity_ctrl_status').data
            for name, value in expected.items(): self.assertEqual(decoded[name].tolist(), [value])


if __name__ == '__main__': unittest.main()
