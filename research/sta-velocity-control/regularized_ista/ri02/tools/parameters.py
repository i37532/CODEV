"""Full BSON transaction with explicit injected I/O and durable exact backup.

There is no simulator discovery or live-device backend. FileStore accepts only
an explicit sandbox root, and refuses the real PX4 rootfs. Tests use a new
temporary directory. A later flight stage must supply its owned-session guard.
"""
import hashlib
import json
import math
import os
from pathlib import Path

from configuration import validate
from dependencies import REPO, parameter_io


class FileStore:
    def __init__(self, path, sandbox):
        self.path, self.sandbox = Path(path).resolve(), Path(sandbox).resolve()
        if self.sandbox not in self.path.parents or REPO / 'build' in self.path.parents:
            raise ValueError('Explicit offline archive outside real build/rootfs required')

    def read(self):
        return self.path.read_bytes()

    def write(self, value):
        # Existing explicit file only: do not silently create a real EEPROM.
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        temporary = self.path.with_name(self.path.name + '.ri02-tmp')
        with temporary.open('xb') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)


class ParameterTransaction:
    def __init__(self, store, types, defaults, stopped, backup_directory):
        self.store, self.types, self.defaults = store, dict(types), dict(defaults)
        self.stopped = stopped
        self.backup_directory = Path(backup_directory)
        self.original = self.expected = None
        self.receipt = dict(offline=True, flight_authorized=False)

    def __enter__(self):
        if not self.stopped():
            raise RuntimeError('Archive transaction requires stopped owned session')
        self.backup_directory.mkdir(parents=True, exist_ok=False)
        self.original = bytes(self.store.read())
        # Validate BEFORE any write; malformed originals are never overwritten.
        parameter_io().persisted_bson(self.original)
        backup = self.backup_directory / 'original.bson'
        with backup.open('xb') as stream:
            stream.write(self.original)
            stream.flush()
            os.fsync(stream.fileno())
        self.receipt.update(original_sha256=hashlib.sha256(self.original).hexdigest(),
                            backup_path=str(backup.resolve()))
        return self

    def apply(self, configuration):
        if self.original is None or not self.stopped():
            raise RuntimeError('No stopped-session backup')
        mode, axes, parameters = configuration['mode'], configuration['axes'], configuration['parameters']
        validate(mode, axes, parameters)
        io = parameter_io()
        persisted = io.persisted_bson(self.original)
        if (set(persisted) | set(parameters) | {'SDLOG_PROFILE'}) - set(self.types):
            raise ValueError('Complete parameter type table required')
        if any(self.types[k] not in ('Int32', 'Float') for k in set(persisted) | set(parameters) | {'SDLOG_PROFILE'}):
            raise ValueError('Exact PX4 Int32/Float parameter types required')
        requested = {**persisted, **parameters}
        requested['SDLOG_PROFILE'] = int(persisted.get('SDLOG_PROFILE', 0)) | int(parameters.get('SDLOG_PROFILE', 0)) | 16 | 1024
        self.expected = {**self.defaults, **requested}
        encoded = io.encode_bson(requested, self.types)
        self.store.write(encoded)
        if bytes(self.store.read()) != encoded:
            raise RuntimeError('Full archive write/readback differs')
        self.receipt.update(applied_sha256=hashlib.sha256(encoded).hexdigest(),
                            persisted_parameter_count=len(io.persisted_bson(encoded)))
        return self.expected.copy()

    def verify_readback(self, cli, topic, *, expected_rejected_mode4=False, retained_configuration=None):
        if self.expected is None:
            raise RuntimeError('No applied profile')
        io = parameter_io()
        io.check_parameters(io.parse_params(cli('param', 'show', '-a')), self.expected)
        if topic('vehicle_status').get('arming_state') != 1 or not topic('vehicle_land_detected').get('landed'):
            raise RuntimeError('Must be landed and disarmed')
        io.check_inner(topic('sta_rate_ctrl_status'))
        q = topic('velocity_ctrl_selection')
        mode, axes = self.expected['MPC_VC_MODE'], self.expected['MPC_VC_AXES']
        common = dict(requested_mode=mode, requested_axes=axes, div_req=1, div_eff=1,
                      pending=0, div_pending=0, div_reject=0, control_fault=0, sta_pending=0)
        if any(q.get(k) != v for k, v in common.items()):
            raise RuntimeError('Wrong requested configuration or cadence')
        if mode == 4:
            if not expected_rejected_mode4 or q.get('effective_mode') == 4 or not int(q.get('reject', 0)) & 2:
                raise RuntimeError('MODE4 must be explicitly unavailable in RI02')
            if q.get('ri_valid') or q.get('ri_commit_axes'):
                raise RuntimeError('Rejected MODE4 cannot produce new candidates/commits')
        elif expected_rejected_mode4 or q.get('effective_mode') != mode or q.get('effective_axes') != axes or q.get('reject'):
            raise RuntimeError('Effective existing mode differs')
        if q.get('variant_req') != mode or q.get('ri_version') != 1:
            raise RuntimeError('Missing/wrong variant/schema')
        effective_mode, effective_axes = q.get('effective_mode'), q.get('effective_axes')
        if effective_mode not in (0, 3) or q.get('variant_eff') != effective_mode:
            raise RuntimeError('Wrong actual effective variant')
        if type(effective_axes) is not int or (effective_axes != 0 if effective_mode == 0 else effective_axes not in (1, 3, 4, 7)):
            raise RuntimeError('Wrong actual effective axes')
        if q.get('sta_reject') not in (False, True, 0, 1) or (effective_mode == 3 and q.get('sta_reject')):
            raise RuntimeError('Rejected/missing effective STA configuration')
        effective_parameters = self.expected
        if mode == 4 and effective_mode == 3:
            if retained_configuration is None:
                raise RuntimeError('Explicit previously verified retained configuration required')
            validate(retained_configuration['mode'], retained_configuration['axes'], retained_configuration['parameters'])
            if retained_configuration['mode'] != effective_mode or retained_configuration['axes'] != effective_axes:
                raise RuntimeError('Retained effective configuration differs')
            effective_parameters = retained_configuration['parameters']
        for key in ('eps_req', 'eps_eff'):
            if not isinstance(q.get(key), (list, tuple)) or len(q[key]) != 3:
                raise RuntimeError('Three requested/effective epsilon values required')
        generation = q.get('sta_gen')
        if type(generation) is not int or generation < 0 or (effective_mode == 3 and generation == 0):
            raise RuntimeError('Invalid configuration generation')
        for i, axis in enumerate('XYZ'):
            value = q.get('eps_req', [])[i]
            if type(value) not in (float, int) or not math.isclose(value, self.expected['MPC_VC_EPS_' + axis], rel_tol=0, abs_tol=1e-7):
                raise RuntimeError('Wrong complete requested epsilon profile')
            effective = q['eps_eff'][i]
            if type(effective) not in (float, int):
                raise RuntimeError('Invalid effective epsilon value')
            if effective_mode == 3 and effective_axes & (1 << i):
                if not math.isclose(effective, effective_parameters['MPC_VC_EPS_' + axis], rel_tol=0, abs_tol=1e-7):
                    raise RuntimeError('Wrong effective epsilon profile')
            elif not math.isnan(effective):
                raise RuntimeError('Unselected/PID axis claims effective epsilon')
        self.receipt['runtime_verified'] = True
        self.receipt['mode4_rejection_verified'] = mode == 4

    def __exit__(self, exc_type, exc, traceback):
        try:
            if self.original is not None:
                if not self.stopped():
                    self.receipt['restore_deferred_running'] = True
                    raise RuntimeError('Session running: durable backup retained; no unsafe live restore') from exc
                self.store.write(self.original)
                self.receipt['restore_exact'] = bytes(self.store.read()) == self.original
                if not self.receipt['restore_exact']:
                    raise RuntimeError('Full archive restoration failed') from exc
        finally:
            (self.backup_directory / 'receipt.json').write_text(json.dumps(self.receipt, indent=2) + '\n')
        return False
