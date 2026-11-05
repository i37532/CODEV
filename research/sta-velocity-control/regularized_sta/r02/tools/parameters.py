"""Full archive transaction with explicit injected I/O; R02 has no device backend.

Uses unchanged run_v00 BSON encoder/decoder, CLI parser and tolerance checks.
The memory store in tests is the only supplied backend. Neither this module nor
the R02 runner discovers or opens the real EEPROM/CLI automatically.
"""
import hashlib
import math
import numbers
from config import validate
from legacy import parameter_io


class ParameterTransaction:
    def __init__(self, store, types, defaults, is_stopped):
        self.store, self.types, self.defaults = store, types, defaults
        self.is_stopped = is_stopped
        self.original = None
        self.expected = None
        self.receipt = {}

    def __enter__(self):
        if not self.is_stopped():
            raise RuntimeError('Full EEPROM transaction requires stopped simulator')
        self.original = bytes(self.store.read())
        self.receipt['original_sha256'] = hashlib.sha256(self.original).hexdigest()
        return self

    def apply(self, configuration):
        if self.original is None or not self.is_stopped():
            raise RuntimeError('No stopped-session backup; refusing write')
        p = configuration['parameters']
        validate(configuration['mode'], configuration['axes'], p)
        io = parameter_io()
        values = io.persisted_bson(self.original)
        self.expected = {**self.defaults, **values, **p}
        unknown = set(values) | set(p)
        if unknown - set(self.types):
            raise ValueError('Missing exact parameter types')
        # Preserve every persisted unrelated parameter and existing logger bits.
        profile = int(self.expected.get('SDLOG_PROFILE', 131)) | 16 | 1024
        if 'SDLOG_PROFILE' in values:
            profile |= int(values['SDLOG_PROFILE'])
        self.expected['SDLOG_PROFILE'] = profile
        encoded = io.encode_bson({**values, **p, 'SDLOG_PROFILE': profile}, self.types)
        self.store.write(encoded)
        if bytes(self.store.read()) != encoded:
            raise RuntimeError('Parameter archive write/readback mismatch')
        self.receipt['applied_sha256'] = hashlib.sha256(encoded).hexdigest()
        self.receipt['persisted_parameter_count'] = len(io.persisted_bson(encoded))
        return self.expected.copy()

    def verify_runtime(self, cli, topic):
        if self.expected is None:
            raise RuntimeError('No applied configuration')
        io = parameter_io()
        actual = io.parse_params(cli('param', 'show', '-a'))
        io.check_parameters(actual, self.expected)
        if topic('vehicle_status').get('arming_state') != 1 or not topic('vehicle_land_detected').get('landed'):
            raise RuntimeError('Runtime switching requires landed/disarmed')
        io.check_inner(topic('sta_rate_ctrl_status'))
        s = topic('velocity_ctrl_selection')
        for key, value in dict(requested_mode=self.expected['MPC_VC_MODE'], effective_mode=self.expected['MPC_VC_MODE'],
                               requested_axes=self.expected['MPC_VC_AXES'], effective_axes=self.expected['MPC_VC_AXES'],
                               div_req=1, div_eff=1, pending=0, reject=0).items():
            if s.get(key) != value:
                raise RuntimeError('Runtime configuration not effective: ' + key)
        mode = self.expected['MPC_VC_MODE']; axes = self.expected['MPC_VC_AXES']
        required = ('variant_req', 'variant_eff', 'sta_pending', 'sta_reject', 'sta_gen', 'eps_req', 'eps_eff')
        if any(key not in s for key in required):
            raise RuntimeError('Missing runtime STA configuration metadata')
        for key in ('sta_pending', 'sta_reject'):
            if not isinstance(s[key], (bool, int, float)) or s[key] not in (0, 1):
                raise RuntimeError('Invalid boolean runtime metadata: ' + key)
        generation = s['sta_gen']
        if isinstance(generation, bool) or not isinstance(generation, numbers.Integral) or generation < 0 or (mode != 0 and generation == 0):
            raise RuntimeError('Invalid runtime STA configuration generation')
        for key in ('eps_req', 'eps_eff'):
            if not isinstance(s[key], (list, tuple)) or len(s[key]) != 3:
                raise RuntimeError('Runtime epsilon metadata must contain exactly three axes')
        if s.get('variant_req') != mode or s.get('variant_eff') != mode or s.get('sta_pending'):
            raise RuntimeError('Runtime algorithm variant/pending mismatch')
        if mode and s.get('sta_reject'):
            raise RuntimeError('Runtime STA configuration rejected')
        for axis, suffix in enumerate('XYZ'):
            req = s['eps_req'][axis]
            eff = s['eps_eff'][axis]
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in (req, eff)):
                raise RuntimeError('Runtime epsilon fields must be numeric')
            expected = self.expected['MPC_VC_EPS_' + suffix]
            if not math.isclose(req, expected, rel_tol=0, abs_tol=1e-7):
                raise RuntimeError('Runtime requested epsilon mismatch')
            if mode == 3 and axes & (1 << axis):
                if not math.isclose(eff, expected, rel_tol=0, abs_tol=1e-7):
                    raise RuntimeError('Runtime effective epsilon mismatch')
            elif not math.isnan(eff):
                raise RuntimeError('Unused effective epsilon must remain NaN')
        self.receipt['runtime_verified'] = True

    def __exit__(self, exc_type, exc, traceback):
        if self.original is not None:
            if not self.is_stopped():
                self.receipt['restore_deferred_running'] = True
                raise RuntimeError('Simulator still running: retain original backup, do not overwrite live EEPROM') from exc
            self.store.write(self.original)
            self.receipt['restore_exact'] = bytes(self.store.read()) == self.original
            if not self.receipt['restore_exact']:
                raise RuntimeError('Full archive restoration failed') from exc
        return False
