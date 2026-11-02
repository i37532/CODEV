"""Read-only admission, state and receipt checks for the eight Offboard attempts."""

import importlib.util
import json
import math
from collections.abc import Mapping
from pathlib import Path
import re
from heading_check import POLICY as HEADING_POLICY, STRICT as STRICT_HEADING_POLICY

from task_contract import (BATCH_ORDER, ENTRY_LIMITS, MAX_ATTEMPTS, PHASE_DURATION_S,
                           SAFETY_LIMITS, STABLE_REQUIRED_S, STABLE_TIMEOUT_S, Phase)


_legacy_spec = importlib.util.spec_from_file_location(
    '_offboard_legacy_hover_contract', Path(__file__).resolve().parents[1] / 'tools/run_hover.py')
_legacy = importlib.util.module_from_spec(_legacy_spec)
_legacy_spec.loader.exec_module(_legacy)
check_envelope = _legacy.check_envelope

SCORED_PHASES = frozenset(('hover', 'step_up', 'step_down', 'velocity'))
ACTIVE_PHASES = frozenset(phase.value for phase in Phase) - {'prestream'}
ALL_PHASES = ACTIVE_PHASES | {'prestream', 'warmup', 'landing'}
_LABELS = {'PID': 'PID', 'STA2': 'Upstream STA2', 'RSTA': 'RSTA', 'RISTA': 'RISTA'}
_OLD_ROOT = Path('/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-HOVER-20261102')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _finite(value, name):
    _require(not isinstance(value, bool) and isinstance(value, (int, float)), name + ' must be numeric')
    try:
        value = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(name + ' must be finite') from exc
    _require(math.isfinite(value), name + ' must be finite')
    return value


def _timestamp(value, name):
    value = _finite(value, name)
    _require(value > 0 and value.is_integer(), name + ' must be positive integer microseconds')
    return value


def _mapping(value, name):
    _require(isinstance(value, Mapping), name + ' must be a mapping')
    return value


def diagnostic_expectations(job, scored=False):
    """One selection rule for admission, collection and checking.

    Only an absent scored override inherits the base configuration. An explicit
    empty/null override is invalid, not permission to stop reading diagnostics.
    Empty field maps are valid (STA2 requires the topic and its timestamp).
    """
    _mapping(job, 'job')
    base = _mapping(job.get('diagnostic_expectations'), 'diagnostic_expectations')
    selected = base
    configurations = [('diagnostic_expectations', base)]
    if 'hover_diagnostic_expectations' in job:
        hover = _mapping(job['hover_diagnostic_expectations'], 'hover_diagnostic_expectations')
        configurations.append(('hover_diagnostic_expectations', hover))
        if scored:
            selected = hover
    for name, configuration in configurations:
        _require(bool(configuration), 'Actual controller diagnostics are required: ' + name)
        for topic, fields in configuration.items():
            _require(isinstance(topic, str) and re.fullmatch(r'[a-z][a-z0-9_]*', topic),
                     'Invalid diagnostic topic')
            _mapping(fields, 'diagnostic fields ' + topic)
            for field, value in fields.items():
                _require(isinstance(field, str) and bool(field), 'Invalid diagnostic field')
                if not isinstance(value, bool):
                    _finite(value, 'expected diagnostic value ' + topic + '.' + field)
    return {topic: dict(fields) for topic, fields in selected.items()}


def check_diagnostics(diagnostics, expectations):
    """Validate a freshly collected snapshot using the selected requirements."""
    _mapping(diagnostics, 'diagnostics')
    _require(bool(expectations), 'Actual controller diagnostics are required')
    for topic, expected in expectations.items():
        actual = _mapping(diagnostics.get(topic), 'diagnostic ' + topic)
        _timestamp(actual.get('timestamp'), topic + ' timestamp')
        for field, value in expected.items():
            _require(field in actual and actual[field] == value, 'Wrong diagnostic ' + topic + '.' + field)


def _absolute(value, name):
    _require(isinstance(value, str) and value, name + ' must be an absolute path')
    path = Path(value)
    _require(path.is_absolute() and '..' not in path.parts, name + ' must be an absolute path without traversal')
    return path


def _same_mapping(actual, expected, name):
    # JSON roundtrips turn tuple limits into lists; canonicalize only that shape.
    def numbers_only(value):
        if isinstance(value, Mapping):
            return all(numbers_only(item) for item in value.values())
        if isinstance(value, (list, tuple)):
            return all(numbers_only(item) for item in value)
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    _require(numbers_only(actual), 'Invalid ' + name)
    _require(json.loads(json.dumps(actual, allow_nan=False)) ==
             json.loads(json.dumps(dict(expected), allow_nan=False)), 'Changed ' + name)


def validate_manifest(manifest, job_id):
    """Validate only a fully frozen new batch; never reuse the old hover results."""
    manifest = _mapping(manifest, 'manifest')
    _require(manifest.get('flight_qualified') is True, 'Manifest is not flight qualified')
    _require(type(manifest.get('max_attempts')) is int and manifest['max_attempts'] == MAX_ATTEMPTS,
             'Exactly eight attempts are authorized')
    for name, expected in (('stop_on_first_failure', True), ('automatic_retry', False), ('retuning', False)):
        _require(manifest.get(name) is expected, 'Wrong batch policy ' + name)
    for name in ('pid_addition', 'preserved_results', 'prior_results'):
        _require(name not in manifest, 'Old task bookkeeping is forbidden: ' + name)
    root = _absolute(manifest.get('data_root'), 'data_root').resolve()
    old = _OLD_ROOT.resolve()
    _require(root != old and not root.is_relative_to(old) and not old.is_relative_to(root),
             'New attempts cannot share the old hover data tree')
    _same_mapping(manifest.get('phase_duration_s'), PHASE_DURATION_S, 'phase durations')
    _same_mapping(manifest.get('safety_limits'), SAFETY_LIMITS, 'safety limits')
    _same_mapping(manifest.get('entry_limits'), ENTRY_LIMITS, 'entry limits')
    jobs = manifest.get('jobs')
    _require(isinstance(jobs, list) and len(jobs) == MAX_ATTEMPTS, 'Require eight new jobs')
    # Revision must be explicit and uniform; old frozen manifests remain strict.
    heading_policy = manifest.get('heading_reset_policy', STRICT_HEADING_POLICY)
    _require(heading_policy in (STRICT_HEADING_POLICY, HEADING_POLICY), 'Unknown heading reset policy')
    ids = ['O%03d' % index for index in range(1, MAX_ATTEMPTS + 1)]
    _require(manifest.get('order') == ids and job_id in ids, 'Invalid order or requested job')
    by_system = {}
    for index, (job, (task, system)) in enumerate(zip(jobs, BATCH_ORDER)):
        _mapping(job, 'job')
        _require(job.get('heading_reset_policy', STRICT_HEADING_POLICY) == heading_policy,
                 'Mixed/undeclared heading reset policy')
        _require(job.get('id') == ids[index] and job.get('task') == task and job.get('system') == system,
                 'Job identity or task order changed')
        _require(job.get('label') == _LABELS[system], 'Wrong system label')
        for field in ('result_path', 'result', 'results', 'logs', 'events', 'success', 'independent_replay_passed'):
            _require(field not in job, 'Old attempt evidence is forbidden in jobs: ' + field)
        _require(job.get('status', 'unattempted') == 'unattempted', 'Job already records an attempt')
        for field in ('repo', 'bin', 'rootfs'):
            _absolute(job.get(field), field)
        _require(isinstance(job.get('launch_command'), list) and job['launch_command'] and
                 all(isinstance(x, str) and x for x in job['launch_command']), 'Launch requires argv')
        _mapping(job.get('launch_env'), 'launch_env')
        _require(re.fullmatch(r'[0-9a-f]{64}', str(job.get('firmware_sha256', ''))) is not None,
                 'Missing frozen firmware digest')
        _require(re.fullmatch(r'[0-9a-f]{40}', str(job.get('source_head', ''))) is not None,
                 'Missing frozen source HEAD')
        parameters = _mapping(job.get('parameters'), 'parameters')
        expected = _mapping(job.get('expected_parameters'), 'expected_parameters')
        for mapping in (parameters, expected):
            for key, value in mapping.items():
                _require(isinstance(key, str), 'Parameter names must be strings')
                _finite(value, 'parameter ' + key)
        _require(all(key in expected and expected[key] == value for key, value in parameters.items()),
                 'Expected parameters do not cover configured parameters exactly')
        _require(parameters.get('MIS_TAKEOFF_ALT') == 2.5 and parameters.get('SDLOG_MODE') == 1,
                 'Explicit 2.5 m task and prearm logging required')
        _require(parameters.get('MPC_VCT_TEST', 0) == 0 and parameters.get('MC_RATT_TEST', 0) == 0,
                 'Internal task generators must remain disabled')
        if system != 'STA2':
            required = dict(MPC_VC_MODE={'PID': 0, 'RSTA': 3, 'RISTA': 4}[system],
                            MPC_VC_AXES=0 if system == 'PID' else 7, MPC_VC_DIV=1,
                            MC_RTC_MODE=0, MC_STA_AXES=0, MC_RTC_DIV=1, MC_RATT_TEST=0, MPC_VCT_TEST=0)
            _require(all(parameters.get(key) == value for key, value in required.items()),
                     'Wrong algorithm, axes, divisor or internal task configuration: ' + system)
        for scored in (False, True):
            diagnostic_expectations(job, scored)
        if system in by_system:
            previous = by_system[system]
            for field in ('parameters', 'expected_parameters', 'firmware_sha256', 'source_head',
                          'repo', 'bin', 'rootfs'):
                _require(job[field] == previous[field], 'System changed between tasks: ' + field)
            for scored in (False, True):
                _require(diagnostic_expectations(job, scored) == diagnostic_expectations(previous, scored),
                         'System diagnostics changed between tasks')
        else:
            by_system[system] = job
    runtime = _mapping(manifest.get('runtime'), 'runtime')
    _require(isinstance(runtime.get('launcher'), list) and runtime['launcher'] and
             all(isinstance(x, str) and x for x in runtime['launcher']), 'Runtime launcher must be argv')
    _absolute(runtime.get('preflight'), 'runtime preflight')
    _mapping(runtime.get('environment'), 'runtime environment')
    assets = _mapping(manifest.get('assets'), 'assets')
    _require(bool(assets), 'Frozen assets are required')
    for path, digest in assets.items():
        _absolute(path, 'asset')
        _require(re.fullmatch(r'[0-9a-f]{64}', str(digest)) is not None, 'Invalid asset digest')
    return jobs[ids.index(job_id)]


def check_order(manifest, job_id):
    """Read previous receipts, refusing reruns, skipped jobs and failed replay."""
    validate_manifest(manifest, job_id)
    root = Path(manifest['data_root']).resolve()
    index = manifest['order'].index(job_id)
    outputs = []
    for job in manifest['jobs']:
        path = root / 'runs' / job['id']
        _require(not path.is_symlink() and path.resolve().is_relative_to(root), 'Unsafe attempt output path')
        outputs.append(path)
    _require(not outputs[index].exists(), 'Attempt already exists; no retry or replacement')
    for previous_job, output in zip(manifest['jobs'][:index], outputs[:index]):
        path = output / 'result.json'
        _require(path.is_file() and not path.is_symlink(), 'Previous attempt has no result; stop batch')
        try:
            result = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise ValueError('Unreadable previous result; stop batch') from exc
        _mapping(result, 'previous result')
        _require(all(result.get(key) == previous_job[key] for key in ('id', 'task', 'system')),
                 'Previous receipt belongs to a different task or system')
        _require(result.get('success') is True and result.get('independent_replay_passed') is True,
                 'Previous attempt failed or lacks independent replay; stop batch')
    _require(all(not path.exists() for path in outputs[index + 1:]), 'Later attempt already exists')
    return outputs[index]


def position_time_us(state):
    position = _mapping(state.get('position'), 'position')
    publication = _timestamp(position.get('timestamp'), 'position timestamp')
    sample = _timestamp(position.get('timestamp_sample', publication), 'position sample timestamp')
    _require(sample <= publication, 'Position sample timestamp is ahead of publication')
    return sample


def _airborne(state):
    status, land, takeoff = (state.get(key, {}) for key in ('status', 'land', 'takeoff'))
    return (status.get('nav_state') == 14 and status.get('arming_state') == 2 and
            status.get('failsafe') == 0 and not status.get('failure_detector_status', 0) and
            land.get('landed') == 0 and land.get('ground_contact') == 0 and
            land.get('maybe_landed', False) == 0 and takeoff.get('takeoff_state') == 5)


def stable_entry_ok(state, origin):
    """The inherited height/speed gate, with actual airborne Offboard state."""
    position = _mapping(state.get('position'), 'position')
    height = _finite(origin.get('z'), 'origin.z') - _finite(position.get('z'), 'position.z')
    speed = abs(_finite(position.get('vz'), 'position.vz'))
    return bool(_airborne(state) and
                all(position.get(key) == 1 for key in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid')) and
                abs(height - 2.5) <= 0.3 and speed < 0.2)


def stable_gate(state, origin, started_us, stable_since_us=None):
    """Return (stable_since, ready); caller preserves this state between samples."""
    now = position_time_us(state)
    started = _timestamp(started_us, 'gate start')
    _require(now >= started, 'Stable gate clock regressed before its start')
    if stable_since_us is not None:
        stable_since_us = _timestamp(stable_since_us, 'stable_since_us')
        _require(started <= stable_since_us <= now, 'Invalid stable gate history')
    elapsed = (now - started) * 1e-6
    if elapsed > STABLE_TIMEOUT_S:
        raise TimeoutError('Stable gate exceeded 15 simulation seconds')
    since = (now if stable_since_us is None else stable_since_us) if stable_entry_ok(state, origin) else None
    ready = since is not None and now - since >= STABLE_REQUIRED_S * 1e6
    if elapsed >= STABLE_TIMEOUT_S and not ready:
        raise TimeoutError('Stable gate did not satisfy three continuous seconds')
    return since, ready


def _check_diagnostics(state, job, scored):
    check_diagnostics(state.get('diagnostics'), diagnostic_expectations(job, scored))


def check_active_state(state, job, phase, origin):
    """Apply inherited full-flight limits and phase-appropriate actual state gates."""
    _require(phase in ALL_PHASES, 'Unknown runner phase')
    for key in ('position', 'status', 'land', 'attitude', 'takeoff', 'diagnostics'):
        _mapping(state.get(key), key)
    position_time_us(state)
    status = state['status']
    _require(status.get('failsafe') == 0 and not status.get('failure_detector_status', 0), 'Flight failsafe or detector fault')
    height = check_envelope(state['position'], state['attitude'], origin, phase)
    if phase in ACTIVE_PHASES:
        _require(status.get('nav_state') == 14 and status.get('arming_state') == 2,
                 'Active task left armed Offboard mode')
    if phase in SCORED_PHASES:
        _require(_airborne(state), 'Scored phase is not fully airborne')
    if phase == 'landing' and status.get('arming_state') == 1:
        _require(state['land'].get('landed') == 1, 'Disarmed without landed confirmation')
    _check_diagnostics(state, job, phase in SCORED_PHASES)
    return height


def receipt_ready(receipt, generation, phase, before_sent_count, now_wall_s, min_new_sent=1):
    """Use actual sent-generation evidence; control-file phase is not a receipt."""
    receipt = _mapping(receipt, 'bridge receipt')
    for value, name, minimum in ((generation, 'generation', 0), (before_sent_count, 'before_sent_count', 0),
                                 (min_new_sent, 'min_new_sent', 1)):
        _require(type(value) is int and value >= minimum, 'Invalid ' + name)
    _require(phase in tuple(item.value for item in Phase), 'Unknown receipt phase')
    _require(receipt.get('status') == 'running' and receipt.get('dry_run') is False,
             'Bridge is not actually running')
    age = _finite(now_wall_s, 'now_wall_s') - _finite(receipt.get('wall_stamp'), 'receipt wall stamp')
    _require(-0.001 <= age <= 0.5, 'Stale or future bridge receipt')
    for field in ('telemetry_age', 'native_clock_age'):
        value = _finite(receipt.get(field), field)
        _require(0 <= value <= 0.5, 'Stale native stream: ' + field)
    _require(receipt.get('publisher_count') == 1 and receipt.get('subscriber_count', 0) >= 1,
             'ROS graph does not contain the target path')
    sent = receipt.get('sent_count')
    _require(type(sent) is int and sent >= before_sent_count, 'Sent count regressed')
    actual_generation = receipt.get('last_sent_generation')
    if actual_generation is None:
        _require(sent == 0, 'Sent targets lack generation evidence')
        return False
    _require(type(actual_generation) is int and actual_generation >= 0, 'Invalid last sent generation')
    _require(actual_generation <= generation, 'Receipt is from a future generation')
    if actual_generation < generation:
        return False
    _require(receipt.get('last_sent_phase') == phase, 'Actual sent phase disagrees with requested phase')
    seq = receipt.get('last_sent_seq')
    _require(type(seq) is int and seq >= sent and seq > 0, 'Missing actual ROS send sequence')
    sent_time = _timestamp(receipt.get('last_sent_sim_us'), 'last_sent_sim_us')
    native_time = _timestamp(receipt.get('latest_native_sim_us'), 'latest_native_sim_us')
    _require(0 <= native_time - sent_time <= 500000, 'Last sent target references stale or future native time')
    return sent - before_sent_count >= min_new_sent
