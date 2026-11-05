"""Offline archive/real-runner/real-seed-scanner wiring; zero flight attempts."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import archive_stdout as archive

HERE = Path(__file__).resolve().parent
STAGE = HERE.parents[1]
REPO = STAGE.parents[3]
TOOLS = STAGE / 'tools'
sys.path.insert(0, str(TOOLS))
import bindings

p = bindings.api()
runner = bindings.local('runner')
REGISTRATION = {STAGE / name: (STAGE / name).read_bytes()
                for name in (*p.REGISTRATION_NAMES, 'seed_reservations.json')}


def fixture_stdout(gate='D'):
    jobs = p.jobs(gate)
    summary = dict(stage=p.stage(gate), planned=9, maximum_attempts=9,
                   jobs=[{key: row[key] for key in archive.JOB_FIELDS} for row in jobs])
    return (json.dumps(summary, indent=2) + archive.TRAILER).encode()


class StdoutContractTests(unittest.TestCase):
    def setUp(self):
        self.jobs = p.jobs('D')
        self.raw = fixture_stdout()

    def validate(self, raw):
        return archive.validate_stdout(raw, frozen_jobs=self.jobs, stage='RI05-D')

    def test_exact_summary_and_trailer(self):
        parsed = self.validate(self.raw)
        self.assertEqual(parsed['planned'], 9)
        self.assertEqual(parsed['jobs'][0]['seed'], 83101)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(self.raw)  # Mixed stdout is deliberately NOT a JSON document.

    def test_missing_changed_or_extra_trailer_rejected(self):
        for raw in (self.raw[:-1], self.raw + b'\n', self.raw + b'{}',
                    self.raw.replace(b'DRY RUN:', b'EXECUTED:'),
                    self.raw.replace(b'\n', b'\r\n'), self.raw.split(b'\nDRY RUN:')[0]):
            with self.subTest(raw=raw[-90:]), self.assertRaises(ValueError):
                self.validate(raw)

    def test_unknown_or_tampered_jobs_order_and_fields_rejected(self):
        summary = self.validate(self.raw)
        for kind in ('seed', 'order', 'mode', 'axes', 'task', 'budget', 'stage', 'extra', 'numeric_type'):
            altered = copy.deepcopy(summary)
            if kind == 'seed': altered['jobs'][0]['seed'] += 100
            elif kind == 'order': altered['jobs'].reverse()
            elif kind == 'mode': altered['jobs'][2]['mode'] = 1
            elif kind == 'axes': altered['jobs'][2]['axes'] = 3
            elif kind == 'task': altered['jobs'][0]['task'] = 'H'
            elif kind == 'budget': altered['planned'] = 10
            elif kind == 'stage': altered['stage'] = 'RI05-C'
            elif kind == 'extra': altered['flight_authorized'] = True
            else: altered['planned'] = 9.0
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.validate((json.dumps(altered) + archive.TRAILER).encode())

    def test_duplicate_keys_nonfinite_prefix_and_bad_utf8_rejected(self):
        for raw in (self.raw.replace(b'"planned": 9', b'"planned": 9, "planned": 9'),
                    self.raw.replace(b'"planned": 9', b'"planned": NaN'),
                    b'\xef\xbb\xbf' + self.raw, b'\xff' + self.raw, b'\n' + self.raw):
            with self.subTest(raw=raw[:45]), self.assertRaises((ValueError, UnicodeError)):
                self.validate(raw)

    def test_raw_bytes_complete_nine_jobs_and_known_stage_required(self):
        with self.assertRaises(TypeError): self.validate(self.raw.decode())
        for jobs, stage in ((self.jobs[:8], 'RI05-D'), (self.jobs, 'RI05-X'), ([{}] * 9, 'RI05-D')):
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                archive.validate_stdout(self.raw, frozen_jobs=jobs, stage=stage)

    def test_log_exclusive_readback_and_sha_preserve_raw_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'dry_run.log'
            receipt = archive.archive_stdout(self.raw, destination, frozen_jobs=self.jobs, stage='RI05-D')
            self.assertEqual(destination.read_bytes(), self.raw)
            self.assertEqual(receipt['sha256'], hashlib.sha256(self.raw).hexdigest())
            self.assertEqual(receipt['bytes'], len(self.raw)); self.assertEqual(receipt['new_flights'], 0)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

    def test_json_and_other_extensions_refused_without_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            for suffix in ('.json', '.jsonl', '.txt', '.LOG', ''):
                destination = Path(tmp) / ('dry_run' + suffix)
                with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                    archive.archive_stdout(self.raw, destination, frozen_jobs=self.jobs, stage='RI05-D')
                self.assertFalse(destination.exists())

    def test_existing_file_and_hard_link_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / 'original.log'; original.write_bytes(b'KEEP original evidence')
            linked = Path(tmp) / 'hardlink.log'; os.link(original, linked)
            for destination in (original, linked):
                with self.subTest(path=str(destination)), self.assertRaises(FileExistsError):
                    archive.archive_stdout(self.raw, destination, frozen_jobs=self.jobs, stage='RI05-D')
                self.assertEqual(destination.read_bytes(), b'KEEP original evidence')

    def test_leaf_and_parent_symlinks_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); target = root / 'target.log'; target.write_bytes(b'KEEP')
            linked = root / 'link.log'; linked.symlink_to(target)
            dangling = root / 'dangling.log'; dangling.symlink_to(root / 'missing.log')
            real_directory = root / 'real'; real_directory.mkdir()
            link_directory = root / 'linked'; link_directory.symlink_to(real_directory, target_is_directory=True)
            for destination in (linked, dangling, link_directory / 'new.log'):
                with self.subTest(path=str(destination)), self.assertRaises(OSError):
                    archive.archive_stdout(self.raw, destination, frozen_jobs=self.jobs, stage='RI05-D')
            self.assertEqual(target.read_bytes(), b'KEEP')
            self.assertFalse((root / 'missing.log').exists()); self.assertEqual(list(real_directory.iterdir()), [])

    def test_bad_payload_rejected_before_any_archive_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'dry.log'
            with self.assertRaises(ValueError):
                archive.archive_stdout(self.raw + b'tampered', destination, frozen_jobs=self.jobs, stage='RI05-D')
            self.assertFalse(destination.exists())

    def test_relative_traversal_missing_parent_and_directory_destinations_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); directory = root / 'folder.log'; directory.mkdir()
            for destination in (Path('relative.log'), root / '..' / 'escape.log', root / 'absent' / 'new.log', directory):
                with self.subTest(path=str(destination)), self.assertRaises((ValueError, OSError)):
                    archive.archive_stdout(self.raw, destination, frozen_jobs=self.jobs, stage='RI05-D')

    def test_io_exception_keeps_new_original_bytes_instead_of_deleting_or_retrying(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'dry.log'
            with patch.object(archive.os, 'fsync', side_effect=OSError('synthetic offline fsync error')):
                with self.assertRaises(OSError):
                    archive.archive_stdout(self.raw, destination, frozen_jobs=self.jobs, stage='RI05-D')
            self.assertEqual(destination.read_bytes(), self.raw)
            with self.assertRaises(FileExistsError):
                archive.archive_stdout(self.raw, destination, frozen_jobs=self.jobs, stage='RI05-D')


class ActualRunnerTests(unittest.TestCase):
    def invoke(self, argv, gate):
        captured = io.StringIO()
        # Run the real main/manifest/scope/printing path, fail if execution or a
        # process launch is ever attempted. This is not a mocked flight result.
        with patch.object(runner, 'execute_gate', side_effect=AssertionError('dry-run attempted execution')) as execute, \
                patch.object(subprocess, 'Popen', side_effect=AssertionError('dry-run launched process')), \
                contextlib.redirect_stdout(captured):
            self.assertEqual(runner.main(argv), 0)
        execute.assert_not_called()
        raw = captured.getvalue().encode()
        archive.validate_stdout(raw, frozen_jobs=p.jobs(gate), stage=p.stage(gate))
        self.assertEqual(raw, fixture_stdout(gate))

    def test_real_default_runner_is_c_dry_run_without_execution(self): self.invoke([], 'C')

    def test_real_d_runner_is_dry_run_without_execution(self): self.invoke(['--gate', 'D'], 'D')

    def test_real_cli_stdout_format_matches_archive_contract(self):
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([sys.executable, str(TOOLS / 'runner.py'), '--gate', 'D'],
                                cwd=REPO, env=environment, capture_output=True, check=False, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.assertEqual(result.stdout, fixture_stdout('D'))
        archive.validate_stdout(result.stdout, frozen_jobs=p.jobs('D'), stage='RI05-D')


class ActualSeedAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ri05-archive-seed-wiring-')
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'; self.research = self.repo / 'research'
        self.experiments = self.root / 'experiments'; self.plan = self.root / 'plan'
        for directory in (self.research, self.experiments, self.plan): directory.mkdir(parents=True)
        (self.research / 'baseline.json').write_text('{"unrelated": 17}\n')
        spec = importlib.util.spec_from_file_location('_recovery_actual_seed_audit',
                    REPO / 'research/sta-velocity-control/scripts/check_v04_protocol02.py')
        self.audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.audit)
        self.audit.REPO = self.repo; self.audit.CONFIG = self.root / 'not_an_exemption'
        real_path = Path
        replacements = {'/home/yr/Desktop/codev doc/experiments': self.experiments,
                        '/home/yr/Desktop/codev doc/plan': self.plan}
        self.audit.Path = lambda value: replacements.get(str(value), real_path(value))

    def tearDown(self): self.temp.cleanup()

    def scan(self):
        # Real rg --files -g '*.json', JSON parsing, recursion and collision
        # detection. Only the three filesystem roots point to isolated fixtures.
        return self.audit.seed_audit([83101, 83102, 83103])

    def test_mixed_stdout_json_is_rejected_by_actual_scanner(self):
        path = self.experiments / 'dry_run.json'; path.write_bytes(fixture_stdout())
        result = self.scan()
        self.assertFalse(result['accepted']); self.assertEqual(result['invalid_json'], [str(path)])

    def test_pure_json_stdout_still_collides_with_reserved_seeds(self):
        data = archive.validate_stdout(fixture_stdout(), frozen_jobs=p.jobs('D'), stage='RI05-D')
        path = self.experiments / 'dry_run.json'; path.write_text(json.dumps(data))
        result = self.scan()
        self.assertFalse(result['accepted']); self.assertEqual(result['invalid_json'], [])
        self.assertEqual({match['path'] for match in result['matches']}, {str(path)})
        self.assertEqual({seed for match in result['matches'] for seed in match['seeds']}, {83101, 83102, 83103})

    def test_log_is_not_a_json_scan_input(self):
        before = self.scan()
        archive.archive_stdout(fixture_stdout(), self.experiments / 'dry_run.log',
                               frozen_jobs=p.jobs('D'), stage='RI05-D')
        after = self.scan()
        self.assertTrue(after['accepted']); self.assertEqual(after, before)

    def test_log_does_not_hide_other_malformed_json_or_real_seed_collision(self):
        archive.archive_stdout(fixture_stdout(), self.experiments / 'dry_run.log',
                               frozen_jobs=p.jobs('D'), stage='RI05-D')
        bad = self.plan / 'other_bad.json'; bad.write_bytes(b'not JSON')
        collision = self.research / 'old_actual_run.json'; collision.write_text('{"imu_seed": 83101}')
        result = self.scan()
        self.assertFalse(result['accepted']); self.assertEqual(result['invalid_json'], [str(bad)])
        self.assertEqual(result['matches'], [dict(path=str(collision), field='imu_seed', seeds=[83101])])

    def registered_fixture(self):
        here = self.research / 'ri05'; here.mkdir()
        for name in p.REGISTRATION_NAMES: (here / name).write_bytes(REGISTRATION[STAGE / name])
        reservations = {str(here / name): hashlib.sha256((here / name).read_bytes()).hexdigest()
                        for name in p.REGISTRATION_NAMES}
        (here / 'seed_reservations.json').write_text(json.dumps(reservations))
        return here, reservations

    def fresh(self, here):
        with patch.object(p, 'HERE', here), patch.object(p, 'load_file', return_value=self.audit):
            return p.fresh_seeds('D')

    def test_real_four_registration_filter_unchanged_and_log_adds_no_exception(self):
        here, reservations = self.registered_fixture()
        before = self.fresh(here); self.assertTrue(before['accepted'])
        self.assertGreater(len(before['design_registrations']), 0)
        archive.archive_stdout(fixture_stdout(), self.experiments / 'dry_run.log',
                               frozen_jobs=p.jobs('D'), stage='RI05-D')
        self.assertEqual(self.fresh(here), before)
        self.assertEqual(json.loads((here / 'seed_reservations.json').read_text()), reservations)
        self.assertEqual(set(reservations), {str(here / name) for name in p.REGISTRATION_NAMES})
        for path, raw in REGISTRATION.items(): self.assertEqual(path.read_bytes(), raw)

    def test_other_registration_collision_is_not_exempted(self):
        here, _ = self.registered_fixture()
        collision = self.plan / 'actual_run.json'; collision.write_text('{"seed": 83102}')
        result = self.fresh(here)
        self.assertFalse(result['accepted']); self.assertEqual(result['invalid_json'], [])
        self.assertEqual(result['matches'], [dict(path=str(collision), field='seed', seeds=[83102])])

    def test_expanding_four_registration_allowlist_is_rejected(self):
        here, reservations = self.registered_fixture()
        extra = here / 'extra.json'; extra.write_text('{"seed": 83101}')
        reservations[str(extra)] = hashlib.sha256(extra.read_bytes()).hexdigest()
        (here / 'seed_reservations.json').write_text(json.dumps(reservations))
        with self.assertRaisesRegex(ValueError, 'Only four exact'): self.fresh(here)

    def test_original_registration_tampering_is_rejected(self):
        here, _ = self.registered_fixture()
        (here / 'seed_audit_initial.json').write_text('{}\n')
        with self.assertRaisesRegex(ValueError, 'reservation changed'): self.fresh(here)


if __name__ == '__main__':
    unittest.main(verbosity=2)
