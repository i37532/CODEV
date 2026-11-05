"""Actual RI05 parameter transaction and replay-copy wiring, all offline."""
import contextlib
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import numpy as np
import bindings
from test_tools import analyzer, runner, replay, job, metrics
p = bindings.api()

def protocol(root='/tmp/ri05-offline-placeholder'):
    value = p.load_protocol('C')
    value['artifacts']['new_run_root'] = str(Path(root)/'C/batch01')
    return value

class ParameterTransactionTests(unittest.TestCase):
    def backend(self, failure):
        with tempfile.TemporaryDirectory(prefix='ri05-offline-') as tmp:
            root = Path(tmp); rootfs = root / 'rootfs'; (rootfs / 'eeprom').mkdir(parents=True)
            binary = root / 'bin'; binary.mkdir(); (binary / 'px4').write_bytes(b'fake qualification binary; not executable')
            proto = protocol(root); proto.update(startup_overrides=copy.deepcopy(proto['jobs'][0]['parameters']),
                plugins=str(root / 'plugins'), execution_path=str(root / 'execution.json'), config_dir=str(root / 'config'))
            param = rootfs / 'eeprom/parameters_10016'
            original_values = {**proto['jobs'][0]['parameters'], 'SDLOG_PROFILE': 1, 'UNRELATED_USER': 7.5}
            table = {name: 'Int32' if type(value) is int else 'Float' for name, value in original_values.items()}
            original = runner.historical.encode_bson(original_values, table); param.write_bytes(original)
            definitions = root / 'build/px4_sitl_default/parameters.json'; definitions.parent.mkdir(parents=True)
            bindings.save(definitions, dict(parameters=[dict(name=k, type=table[k], default=v) for k, v in original_values.items()]))
            qualification = root / 'qualification/evidence.json'; qualification.parent.mkdir()
            qualified = dict(firmware_sha256=bindings.digest(binary / 'px4'))
            bindings.save(qualification, qualified); bindings.save(qualification.parent / 'authorization.json', dict(approved=True))
            fake_api = types.SimpleNamespace(require_qualification=lambda *args: qualified,
                valid_gate=p.valid_gate, stage=p.stage, jobs=p.jobs)
            calls = []
            class FakeChecks:
                def __init__(self, proto, expected, j, *args):
                    self.job = j; self.log_root = root / 'not-a-real-tmpfs-log'
            def fake_flight(run, checks, scenario):
                calls.append(checks.job['id']); run.mkdir()
                current = runner.historical.persisted_bson(param.read_bytes())
                self.assertEqual(current['UNRELATED_USER'], 7.5); self.assertEqual(current['SDLOG_PROFILE'], 3089)
                self.assertEqual(current['MPC_VC_MODE'], checks.job['mode'])
                if failure == 'backend': raise RuntimeError('synthetic startup failure')
                if failure == 'write': param.write_bytes(b'mutated by mocked PX4')
            def fake_analyze(run, proto, j):
                self.assertEqual(param.read_bytes(), original)
                result = metrics(j)
                if failure == 'analysis': result['accepted'] = False
                bindings.save(run / 'r03_metrics.json', result)
                return result
            safe_restore = bindings.clone(bindings.OLD_RUNNER.restore_parameters, active_simulators=lambda: [])
            fake_git = lambda *args: '' if args[0] == 'status' else 'a' * 40
            fake_noise = lambda run: np.array([float(proto['jobs'][int(run.name[3:]) - 1]['seed'])])
            with contextlib.ExitStack() as stack:
                for name, value in dict(ROOTFS=rootfs, BIN=binary, REPO=root, api=lambda: fake_api,
                    active_simulators=lambda: [], restore_parameters=safe_restore,
                    execution_checks_class=lambda: FakeChecks).items(): stack.enter_context(patch.object(runner, name, value))
                stack.enter_context(patch.object(runner, 'precheck', return_value=(qualified, dict(control_parameters=original_values), dict(accepted=True))))
                stack.enter_context(patch.object(runner.historical, 'git', side_effect=fake_git))
                stack.enter_context(patch.object(runner.historical, 'noise_prefix', side_effect=fake_noise))
                stack.enter_context(patch.object(runner.historical.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=30 * 1024**3)))
                stack.enter_context(patch.object(bindings.RAM_LOG, 'release_archived'))
                if failure in ('backend', 'analysis'):
                    with self.assertRaises(RuntimeError): runner._execute_gate(proto, 'a' * 40, qualification, single_flight=fake_flight, analyze=fake_analyze, compare=analyzer.compare)
                else:
                    self.assertTrue(runner._execute_gate(proto, 'a' * 40, qualification, single_flight=fake_flight, analyze=fake_analyze, compare=analyzer.compare)['success'])
            self.assertEqual(param.read_bytes(), original)
            ledger = bindings.read(Path(proto['artifacts']['new_run_root']) / 'ledger.json')
            self.assertTrue(ledger['parameter_restore_exact']); self.assertEqual(ledger['remaining_simulators'], [])
            self.assertEqual(len(calls), 1 if failure in ('backend', 'analysis') else 9)
            self.assertEqual(len(ledger['unattempted']), 8 if failure in ('backend', 'analysis') else 0)

    def test_actual_runtime_transaction_success(self): self.backend(None)
    def test_actual_runtime_startup_failure_stops_restores(self): self.backend('backend')
    def test_actual_runtime_analysis_failure_stops_restores(self): self.backend('analysis')
    def test_actual_runtime_rewrites_are_restored_each_attempt(self): self.backend('write')

    def test_active_owned_process_blocks_unsafe_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); param = root / 'parameters'; param.write_bytes(b'changed'); run = root / 'run001'; run.mkdir()
            restore = bindings.clone(bindings.OLD_RUNNER.restore_parameters, active_simulators=lambda: ['owned process still alive'])
            with self.assertRaises(RuntimeError): restore(param, b'original', run, root / 'backup', 'a' * 40, job())
            self.assertEqual(param.read_bytes(), b'changed')
            self.assertFalse(bindings.read(run / 'parameter_restore.json')['stopped_before_restore'])


class ReplayTests(unittest.TestCase):
    def ledger(self):
        proto = protocol(); ledger = dict(stage='RI05-C', revision='ri05', gate='C', planned=9, total_budget=18,
            new_planned=9, prior_attempts=0, parameter_restore_exact=True, remaining_simulators=[],
            source_head='a' * 40, firmware_sha256='b' * 64, attempts=[], pairs=[], success=False)
        runner.run_ordered(proto, lambda j, i: (metrics(j), dict(metrics_sha256='c' * 64)), analyzer.compare, ledger, lambda e: None)
        return proto, ledger

    def test_complete_ledger_and_independent_six_pairs(self):
        proto, ledger = self.ledger(); replay.validate_ledger(ledger, proto)
        self.assertEqual(len(replay.recompute_pairs(ledger, {j['id']: metrics(j) for j in proto['jobs']})), 6)

    def test_incomplete_failed_reordered_or_forged_pair_rejected(self):
        for case in ('missing', 'failed', 'order', 'pair', 'cleanup', 'old_budget', 'old_mode'):
            proto, ledger = self.ledger()
            if case == 'missing': ledger['attempts'].pop()
            elif case == 'failed': ledger['attempts'][0]['status'] = 'failed'
            elif case == 'order': ledger['attempts'][0], ledger['attempts'][1] = ledger['attempts'][1], ledger['attempts'][0]
            elif case == 'pair': ledger['pairs'][0]['checks']['yaw'] = False
            elif case == 'cleanup': ledger['parameter_restore_exact'] = False
            elif case == 'old_budget': ledger['prior_attempts'] = 97
            else: ledger['attempts'][1]['job']['mode'] = 1
            with self.subTest(case=case), self.assertRaises((ValueError, RuntimeError)): replay.validate_ledger(ledger, proto)

    def test_replay_does_not_trust_stored_pair_success(self):
        proto, ledger = self.ledger(); data = {j['id']: metrics(j) for j in proto['jobs']}; data['run003']['yaw_rmse'] = 1.
        with self.assertRaises(ValueError): replay.recompute_pairs(ledger, data)

    def test_snapshot_read_only_and_byte_changes_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); (p / 'raw.ulg').write_bytes(b'fixture'); before = replay.snapshot(p)
            self.assertEqual(before, replay.snapshot(p)); (p / 'raw.ulg').write_bytes(b'changed')
            self.assertNotEqual(before, replay.snapshot(p))


class ReplayAuthorityWiringTests(unittest.TestCase):
    """Real copying + real full-engine provenance, stop before ULog science.

    Fake qualification/prearm services isolate this offline test from real
    frozen flight admission. The real composed analyze body is executed until
    its existing verify_model call, AFTER provenance, then deliberately stops.
    No opaque fixture bytes are presented as successfully decoded ULogs.
    """
    @contextlib.contextmanager
    def archive(self):
        with tempfile.TemporaryDirectory(prefix='ri05-replay-wiring-') as tmp:
            root = Path(tmp); canonical = protocol(root); j = canonical['jobs'][2]
            source = Path(canonical['artifacts']['new_run_root']) / j['id']; source.mkdir(parents=True)
            destination = root / 'C/replay01' / j['id']
            qpath = root / 'C/qualification01/evidence.json'; qpath.parent.mkdir()
            config = root / 'config'; config.mkdir(); bindings.save(config / 'frozen.json', {})
            execution = root / 'execution.json'; bindings.save(execution, {})
            canonical.update(qualification_path=str(qpath), config_dir=str(config), execution_path=str(execution),
                plugins=str(root / 'plugins'), startup_overrides=canonical['jobs'][0]['parameters'])
            saved = {**canonical, 'startup_overrides': {**canonical['startup_overrides'], **j['parameters']}}
            qualified = dict(revision='ri05', stage='RI05-C', gate='C', source_head='a' * 40,
                firmware_sha256='b' * 64, execution_sha256=bindings.digest(execution),
                frozen_sha256=bindings.digest(config / 'frozen.json'), maximum_attempts=9,
                new_matrix_attempts=9, historical_attempts=0, total_maximum_attempts=18,
                execution_authorized=True, flight_authorized=True, execution_ready=True)
            bindings.save(qpath, qualified)
            approval = dict(qualified, approved=True, qualification_sha256=bindings.digest(qpath))
            bindings.save(qpath.parent / 'authorization.json', approval)
            bindings.save(source / 'authorization.json', approval)
            bindings.save(source / 'qualification.json', qualified)
            bindings.save(source / 'qualification_reference.json', dict(path=str(qpath), sha256=bindings.digest(qpath)))
            bindings.save(source / 'run_protocol.json', saved); bindings.save(source / 'job.json', j)
            raw = source / 'opaque_fixture.ulg'; raw.write_bytes(b'NOT A REAL ULOG: stop before decoding')
            record = dict(source_head='a' * 40, binary_sha256='b' * 64,
                runner_sha256=bindings.digest(Path(runner.__file__)), scenario_sha256=bindings.digest(execution),
                scenario_path=str(execution), branch='research/ista-velocity-regularized', success=False,
                logs=[dict(archive=str(raw), bytes=raw.stat().st_size, sha256=bindings.digest(raw))])
            bindings.save(source / 'result.json', record)
            backup = source / 'original_parameters.bson'; backup.write_bytes(b'offline opaque parameter snapshot')
            bindings.save(source / 'parameter_restore.json', dict(parameter_restore_exact=True, remaining_simulators=[],
                stopped_before_restore=True, source_head='a' * 40, gate='C', job_id=j['id'],
                original_parameter_sha256=bindings.digest(backup), restored_parameter_sha256=bindings.digest(backup)))
            (source / 'commands.jsonl').write_text('{}\n')
            calls = []
            def qualified_read(gate, head, path):
                self.assertEqual((gate, head, path), ('C', 'a' * 40, qpath))
                calls.append('archive_qualification')
                return bindings.read(path)
            fake_api = types.SimpleNamespace(load_protocol=lambda gate: canonical,
                require_execution_authority=lambda gate: calls.append('authority_binding_only'),
                archive_qualification=qualified_read)
            actual_full = analyzer.full_analysis
            def stop_after_provenance(*args, **kwargs):
                calls.append('actual_full_engine_after_provenance')
                raise ValueError('OFFLINE_STOP_AFTER_REAL_PROVENANCE_BEFORE_ULOG')
            def real_engine(provenance):
                return bindings.clone(actual_full(provenance), verify_model=stop_after_provenance)
            with patch.object(analyzer, 'api', return_value=fake_api), \
                 patch.object(analyzer, 'full_analysis', side_effect=real_engine), \
                 patch.object(bindings.FINAL, 'prearm_evidence', return_value=dict(valid=True)), \
                 patch.object(bindings.FINAL, 'warmup_evidence', return_value=dict(valid=True)):
                yield types.SimpleNamespace(source=source, destination=destination, job=j, protocol=saved,
                    qpath=qpath, calls=calls, root=root)

    def copy(self, f):
        bindings.FINAL._handoff.copy_sidecars(f.source, f.destination)
        bindings.FINAL._handoff.copied_input_binding(f.source, f.destination)
        return bindings.digest(f.source / 'authorization.json')

    def provenance(self, f, sha):
        return analyzer.provenance(f.destination, f.protocol, f.job,
            original_source=f.source, authorization_sha256=sha)

    def test_real_copy_excludes_authority_live_and_replay_binding_identical(self):
        with self.archive() as f:
            live = analyzer.provenance(f.source, f.protocol, f.job)
            sha = self.copy(f)
            self.assertFalse((f.destination / 'authorization.json').exists())
            self.assertEqual(live, self.provenance(f, sha))
            self.assertEqual(live['authorization_receipt_sha256'], sha)

    def test_actual_replay_new_actual_full_engine_provenance_without_copying_authority(self):
        with self.archive() as f:
            original = analyzer.analyze(f.source, f.protocol, f.job)
            self.assertEqual(original['error'], 'OFFLINE_STOP_AFTER_REAL_PROVENANCE_BEFORE_ULOG')
            before = replay.snapshot(f.source)
            repeated = analyzer.replay_new(f.source, f.destination)
            self.assertEqual(repeated, original)
            self.assertEqual(f.calls.count('actual_full_engine_after_provenance'), 2)
            self.assertFalse(repeated['accepted'])
            self.assertEqual(before, replay.snapshot(f.source))
            self.assertFalse((f.destination / 'authorization.json').exists())
            self.assertFalse((f.destination / 'gate_pass.json').exists())

    def test_copy_completeness_checked_before_full_engine_output(self):
        with self.archive() as f:
            sha = self.copy(f); (f.destination / 'commands.jsonl').write_text('tampered\n')
            with self.assertRaisesRegex(ValueError, 'sidecar copy'):
                analyzer.analyze(f.destination, f.protocol, f.job, original_source=f.source, authorization_sha256=sha)
            self.assertNotIn('actual_full_engine_after_provenance', f.calls)
            self.assertFalse((f.destination / 'r03_metrics.json').exists())

    def test_missing_extra_changed_sidecar_rejected(self):
        for kind in ('missing', 'extra', 'changed', 'symlink'):
            with self.archive() as f:
                sha = self.copy(f)
                if kind == 'missing': (f.destination / 'commands.jsonl').unlink()
                elif kind == 'extra': (f.destination / 'extra.txt').write_text('extra')
                elif kind == 'changed': (f.destination / 'commands.jsonl').write_text('changed')
                else: (f.destination / 'foreign').symlink_to('/tmp/nonexistent-ri05-offline-fixture')
                with self.subTest(kind=kind), self.assertRaises(ValueError): self.provenance(f, sha)

    def test_missing_tampered_original_authorization_rejected(self):
        for kind in ('missing', 'changed', 'symlink'):
            with self.archive() as f:
                sha = self.copy(f); auth = f.source / 'authorization.json'
                if kind == 'missing': auth.unlink()
                elif kind == 'changed': auth.write_text('{}\n')
                else:
                    auth.unlink(); auth.symlink_to(f.qpath.parent / 'authorization.json')
                with self.subTest(kind=kind), self.assertRaises(ValueError): self.provenance(f, sha)

    def test_fake_destination_authority_and_gate_receipts_rejected(self):
        for name in ('authorization.json', 'gate_pass.json'):
            with self.archive() as f:
                sha = self.copy(f); bindings.save(f.destination / name, dict(approved=True, accepted=True))
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'authority'):
                    self.provenance(f, sha)

    def test_other_source_and_missing_fingerprint_rejected(self):
        with self.archive() as f:
            sha = self.copy(f)
            with self.assertRaisesRegex(ValueError, 'canonical'):
                analyzer.provenance(f.destination, f.protocol, f.job,
                    original_source=f.source.parent / 'run004', authorization_sha256=sha)
            with self.assertRaisesRegex(ValueError, 'fingerprint'):
                analyzer.provenance(f.destination, f.protocol, f.job, original_source=f.source)
            with self.assertRaisesRegex(ValueError, 'canonical'):
                analyzer.provenance(f.destination, f.protocol, f.job)

    def test_qualification_authorization_substitution_rejected(self):
        with self.archive() as f:
            sha = self.copy(f)
            approval = bindings.read(f.qpath.parent / 'authorization.json'); approval['source_head'] = 'c' * 40
            bindings.save(f.qpath.parent / 'authorization.json', approval)
            with self.assertRaisesRegex(ValueError, 'Original authorization changed'):
                self.provenance(f, sha)

    def test_replay_new_detects_copy_hook_tampering_before_science(self):
        with self.archive() as f:
            original_copy = bindings.FINAL._handoff.copy_sidecars
            def changed(source, dest):
                result = original_copy(source, dest)
                (dest / 'commands.jsonl').write_text('tampered')
                return result
            with patch.object(bindings.FINAL._handoff, 'copy_sidecars', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'sidecar copy'): analyzer.replay_new(f.source, f.destination)
            self.assertNotIn('actual_full_engine_after_provenance', f.calls)

    def test_authorization_changed_during_replay_is_not_silently_accepted(self):
        with self.archive() as f:
            original_copy = bindings.FINAL._handoff.copy_sidecars
            def changed(source, dest):
                result = original_copy(source, dest)
                (source / 'authorization.json').write_text('{}\n')
                return result
            with patch.object(bindings.FINAL._handoff, 'copy_sidecars', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'Original replay inputs changed'):
                    analyzer.replay_new(f.source, f.destination)



if __name__=='__main__':unittest.main()
