"""Offline only: real libc printing, archived CLI/raw pair, and unchanged raw gates."""
import copy
import ctypes
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from pyulog import ULog
from v04_task04 import REFERENCE, check_reference, check_cli_reference, entry_ok, freeze_reference, scalars
from v04_heading_stream import data, replay, row
from v04_protocol04 import CONFIG, REPO, load_protocol
from test_v04_protocol04 import fixture


def printed(value, digits):
    """Use the C printf implementation, not the production Python formatter."""
    buffer = ctypes.create_string_buffer(128)
    count = ctypes.CDLL(None).snprintf(buffer, ctypes.c_size_t(len(buffer)),
                                     ('%.'+str(digits)+'f').encode(), ctypes.c_double(value))
    if not 0 < count < len(buffer):
        raise ValueError('snprintf failed')
    return buffer.value.decode()


def cli_position(raw):
    fields = []
    for key, value in raw.items():
        if key in ('ref_lat', 'ref_lon'):
            rendered = printed(value, 6)
        elif key in ('ref_alt', 'x', 'y', 'z', 'vx', 'vy', 'vz', 'heading'):
            rendered = printed(value, 4)
        else:
            rendered = str(value)
        fields.append('\t'+key+': '+rendered)
    return scalars('\n'.join(fields))


class CliReferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads((CONFIG.parent/'results04/run01.json').read_text())
        cls.source = Path(cls.record['logs'][-1]['archive'])
        if hashlib.sha256(cls.source.read_bytes()).hexdigest() != cls.record['logs'][-1]['sha256']:
            raise ValueError('Historical ULog fingerprint changed')
        cls.log = ULog(str(cls.source))
        cls.ref = json.loads((cls.source.parent/'height_reference.json').read_text())
        cls.sample = json.loads((cls.source.parent/'samples.jsonl').read_text().splitlines()[-1])

    def test_generated_printer_contract(self):
        text = (REPO/'build/px4_sitl_default/msg/topics_sources/vehicle_local_position.cpp').read_text()
        for field, spec in [('ref_lat', '%.6f'), ('ref_lon', '%.6f'), ('ref_alt', '%.4f')]:
            self.assertIn(field+': '+spec, text)

    def test_archived_cli_failure_fixed_without_mutating_reference(self):
        ref = copy.deepcopy(self.ref)
        with self.assertRaisesRegex(ValueError, 'ref_lat'):
            check_reference(self.sample['position'], ref)
        check_cli_reference(self.sample['position'], ref)
        self.assertEqual(ref, self.ref)
        p = data(self.log, 'vehicle_local_position')
        i = int(np.flatnonzero(p['timestamp'] == self.sample['position']['timestamp'])[0])
        c = cli_position(row(p, i))
        for field in REFERENCE:
            self.assertEqual(c[field], self.sample['position'][field])
        self.assertFalse(replay(self.log, ref, allow_pending=True)['ready'])
        self.assertFalse(self.record['success'])

    def test_signed_boundaries_and_neighboring_values_match_libc(self):
        for value in (0., -0., 47.3977508, 8.5456073, -47.3977508, -8.5456073,
                      1.2345675, -1.2345675, 0.0000005, -0.0000005):
            for neighbor in (value, np.nextafter(value, -math.inf), np.nextafter(value, math.inf)):
                ref = copy.deepcopy(self.ref)
                ref['position'].update(ref_lat=float(neighbor), ref_lon=float(-neighbor), ref_alt=float(neighbor))
                with self.subTest(value=neighbor):
                    check_cli_reference(cli_position(ref['position']), ref)

    def test_one_printed_unit_change_is_rejected(self):
        for field, step in [('ref_lat', 1e-6), ('ref_lon', 1e-6), ('ref_alt', 1e-4)]:
            for sign in (-1, 1):
                p = cli_position(self.ref['position']); p[field] += sign*step
                with self.subTest(field=field, sign=sign), self.assertRaises(ValueError):
                    check_cli_reference(p, self.ref)

    def test_missing_nonfinite_raw_and_cli_rejected(self):
        for field in REFERENCE:
            for value in (math.nan, math.inf, -math.inf, None):
                for which in ('cli', 'raw'):
                    p = cli_position(self.ref['position']); ref = copy.deepcopy(self.ref)
                    target = p if which == 'cli' else ref['position']
                    if value is None: del target[field]
                    else: target[field] = value
                    with self.subTest(field=field, value=value, which=which), self.assertRaises(ValueError):
                        check_cli_reference(p, ref)

    def test_counters_and_reference_timestamp_remain_exact(self):
        for field in set(REFERENCE)-{'ref_lat', 'ref_lon', 'ref_alt'}:
            p = cli_position(self.ref['position']); p[field] += 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                check_cli_reference(p, self.ref)

    def test_raw_sub_print_resolution_changes_never_accepted(self):
        for field in ('ref_lat', 'ref_lon', 'ref_alt'):
            log, ref = fixture(); p = data(log, 'vehicle_local_position')
            p[field] = np.full(len(p['timestamp']), self.ref['position'][field], dtype=float)
            ref = freeze_reference(row(p, 0))
            p[field][100] = np.nextafter(p[field][100], math.inf)
            # A single double-ULP change is invisible in CLI, but raw replay rejects it.
            check_cli_reference(cli_position(row(p, 100)), ref)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'Coordinate/reset changed'):
                replay(log, ref)

    def test_missing_raw_sample_or_field_still_rejected(self):
        log, ref = fixture(); p = data(log, 'vehicle_local_position')
        log.tables[('vehicle_local_position', 0)] = {k:np.delete(v, 100) for k,v in p.items()}
        with self.assertRaises(ValueError): replay(log, ref)
        log, ref = fixture(); del data(log, 'vehicle_local_position')['ref_lat']
        with self.assertRaises(KeyError): replay(log, ref)

    def test_real_monitor_reaches_raw_gate_and_does_not_freeze_yaw(self):
        from run_v04_protocol04 import Checks
        protocol = load_protocol(); checks = Checks(protocol, {}, protocol['jobs'][0], Path('/unused'))
        checks.reference = copy.deepcopy(self.ref)
        checks.live = type('ReadOnlyLog', (), {'read': lambda _: self.log})()
        diag = row(data(self.log, 'sta_velocity_ctrl_status'), -1)
        latest = row(data(self.log, 'vehicle_local_position'), -1)
        def topic(name):
            return diag if name == 'sta_velocity_ctrl_status' else latest
        with tempfile.TemporaryDirectory(prefix='v04-cli-monitor-') as tmp, \
                patch('run_v04_protocol04.base.Checks.monitor'), \
                patch('run_v04_protocol04.replay', wraps=replay) as raw_gate:
            checks.monitor('takeoff', None, topic, Path(tmp), copy.deepcopy(self.sample))
            raw_gate.assert_called_once()
            self.assertFalse(checks.task_yaw_ready)
            self.assertFalse((Path(tmp)/'task_yaw.json').exists())
            self.assertTrue((Path(tmp)/'heading_live.jsonl').exists())
            with patch('run_v04_protocol04.replay', side_effect=ValueError('raw reference changed')):
                with self.assertRaisesRegex(ValueError, 'raw reference changed'):
                    checks.monitor('takeoff', None, topic, Path(tmp), copy.deepcopy(self.sample))

    def test_height_entry_uses_cli_semantics_not_old_comparison(self):
        ref = copy.deepcopy(self.ref)
        p = cli_position({**ref['position'], 'z':ref['target_z'], 'vz':0.})
        target = dict(z=ref['target_z'], vz=0., yaw=ref['yaw'])
        self.assertTrue(entry_ok(p, dict(arming_state=2, nav_state=4, failsafe=0),
                                 dict(landed=False, ground_contact=False), target, ref))
        p['ref_lon'] += 1e-6
        with self.assertRaises(ValueError):
            entry_ok(p, {}, {}, target, ref)


if __name__ == '__main__':
    unittest.main()
