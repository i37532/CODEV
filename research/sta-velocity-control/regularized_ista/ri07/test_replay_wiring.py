"""Real formal provenance/replay-copy wiring; opaque fixtures never count as ULogs."""
import contextlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent/'tools'))
import bindings
p=bindings.api()
analyzer=bindings.local('analyzer');runner=bindings.local('runner');replay=bindings.local('replay')
def protocol(root):
    value=p.load_protocol()
    value['artifacts']['new_run_root']=str(Path(root)/'C/batch01')
    return value

class ReplayAuthorityWiringTests(unittest.TestCase):
    """Real copying + real full-engine provenance, stop before ULog science.

    Fake qualification/prearm services isolate this offline test from real
    frozen flight admission. The real composed analyze body is executed until
    its existing verify_model call, AFTER provenance, then deliberately stops.
    No opaque fixture bytes are presented as successfully decoded ULogs.
    """
    @contextlib.contextmanager
    def archive(self):
        with tempfile.TemporaryDirectory(prefix='ri07-replay-wiring-') as tmp:
            root = Path(tmp); canonical = protocol(root); j = canonical['jobs'][2]
            source = Path(canonical['artifacts']['new_run_root']) / j['id']; source.mkdir(parents=True)
            destination = root / 'C/replay01' / j['id']
            qpath = root / 'C/qualification01/evidence.json'; qpath.parent.mkdir()
            config = root / 'config'; config.mkdir(); bindings.save(config / 'frozen.json', {})
            execution = root / 'execution.json'; bindings.save(execution, {})
            canonical.update(qualification_path=str(qpath), config_dir=str(config), execution_path=str(execution),
                plugins=str(root / 'plugins'), startup_overrides=canonical['jobs'][0]['parameters'])
            saved = p.job_protocol(canonical,j)
            qualified = dict(revision='ri07', stage='RI07-FORMAL', gate='FORMAL', source_head='a' * 40,
                firmware_sha256='b' * 64, execution_sha256=bindings.digest(execution),
                frozen_sha256=bindings.digest(config / 'frozen.json'), maximum_attempts=200,
                new_matrix_attempts=200, historical_attempts=0, total_maximum_attempts=200,
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
                stopped_before_restore=True, source_head='a' * 40, gate='FORMAL', job_id=j['id'],
                original_parameter_sha256=bindings.digest(backup), restored_parameter_sha256=bindings.digest(backup)))
            (source / 'commands.jsonl').write_text('{}\n')
            calls = []
            def qualified_read(gate, head, path):
                self.assertEqual((gate, head, path), ('FORMAL', 'a' * 40, qpath))
                calls.append('archive_qualification')
                return bindings.read(path)
            fake_api = types.SimpleNamespace(load_protocol=lambda gate: canonical,
                require_execution_authority=lambda gate: calls.append('authority_binding_only'),
                archive_qualification=qualified_read, budget=p.budget, valid_gate=p.valid_gate,
                candidate_parameters=p.candidate_parameters, jobs=p.jobs, job_protocol=p.job_protocol)
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
                else: (f.destination / 'foreign').symlink_to('/tmp/nonexistent-ri07-offline-fixture')
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
