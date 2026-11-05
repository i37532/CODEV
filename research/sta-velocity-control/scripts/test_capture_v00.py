"""Offline tests for the parameter archive decoder (not controller tests)."""
import struct
import unittest

from capture_v00 import persisted_bson


def document(payload):
    return struct.pack('<i', len(payload) + 5) + payload + b'\0'


class CaptureTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(persisted_bson(document(b'')), {})

    def test_scalar_types(self):
        data = (b'\x10MODE\0' + struct.pack('<i', 0)
                + b'\x01GAIN\0' + struct.pack('<d', 0.4)
                + b'\x12COUNT\0' + struct.pack('<q', 12345678901)
                + b'\x08BOOL\0\x01')
        self.assertEqual(persisted_bson(document(data)),
                         dict(MODE=0, GAIN=0.4, COUNT=12345678901, BOOL=True))

    def test_trailing_old_document_not_consumed(self):
        first = document(b'\x10MODE\0' + struct.pack('<i', 0))
        second = document(b'\x10MODE\0' + struct.pack('<i', 3))
        self.assertEqual(persisted_bson(first + second), {'MODE': 0})

    def test_bad_length_and_terminator(self):
        for data in (b'', b'\0' * 5, struct.pack('<i', 99) + b'\0', b'\x05\0\0\0x'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                persisted_bson(data)

    def test_duplicate_or_unsupported_field(self):
        field = b'\x10MODE\0' + struct.pack('<i', 0)
        for data in (document(field + field), document(b'\x02TEXT\0')):
            with self.subTest(data=data), self.assertRaises(ValueError):
                persisted_bson(data)

    def test_truncated_scalar(self):
        with self.assertRaises((ValueError, struct.error)):
            persisted_bson(document(b'\x10MODE\0\x01'))


if __name__ == '__main__':
    unittest.main()
