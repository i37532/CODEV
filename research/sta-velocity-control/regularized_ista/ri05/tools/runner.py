#!/usr/bin/env python3
"""RI05 XY then XYZ nine-attempt runner; dry-run unless explicitly qualified.

Transport, startup, unique setpoint publisher, takeoff/90s observation/landing,
incremental warmup and tail sealing are the frozen revision11 implementations.
Only new scope/qualification and MODE4 metadata are privately rebound.
"""
import argparse
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import re
import socket

import numpy as np

from bindings import (api, clone, digest, exact, HERE, KERNEL, local, OLD_RUNNER,
                      RAM_LOG, read, REPO, save)

historical = OLD_RUNNER.historical
BIN, ROOTFS = OLD_RUNNER.BIN, OLD_RUNNER.ROOTFS
active_simulators = OLD_RUNNER.active_simulators
append_event = OLD_RUNNER.append_event
restore_parameters = OLD_RUNNER.restore_parameters


def local_module(name):
    return api() if name == 'protocol' else local(name)


# Clone keeps all real startup/flight/tail code and owned-process shutdown.
# New __file__ makes result.runner_sha256 name THIS version, not the old file.
flight_main = clone(OLD_RUNNER.flight_main, local_module=local_module, __file__=__file__, ram_log=RAM_LOG)


def validate_scope(protocol):
    gate = protocol.get('gate')
    api().valid_gate(gate)
    required = dict(maximum_attempts=9, total_maximum_attempts=18,
                    historical_attempts=0, new_matrix_attempts=9)
    if protocol.get('revision') != 'ri05' or gate not in ('C', 'D') or protocol.get('stage') != api().stage(gate):
        raise RuntimeError('Only RI05 C=A/XY and D=B/XYZ are authorized')
    if any(type(protocol.get(k)) is not int or protocol[k] != v for k, v in required.items()):
        raise RuntimeError('Exact nine new attempts, no retained/retry budget')
    jobs = protocol['jobs']
    if len(jobs) != 9 or [j['id'] for j in jobs] != [j['id'] for j in api().jobs(gate)]:
        raise RuntimeError('Wrong exact nine-job identity/order')
    if jobs[0]['mode'] != 0 or len({j['seed'] for j in jobs}) != 3:
        raise RuntimeError('PID-first three paired seeds required')
    for job in jobs:
        local('analyzer').validate_job(job)
    for seed in {j['seed'] for j in jobs}:
        if sorted(j['mode'] for j in jobs if j['seed'] == seed) != [0, 3, 4]:
            raise RuntimeError('Exactly PID/RSTA/RISTA per seed; no old ESTA')


class Admission:
    def __init__(self, protocol, compare):
        validate_scope(protocol)
        self.jobs, self.compare = protocol['jobs'], compare
        self.accepted, self.by_seed, self.checked, self.last_pairs = [], {}, set(), []
        self.failed = False

    def before(self, job):
        if self.failed or len(self.accepted) >= 9 or not exact(self.jobs[len(self.accepted)], job):
            raise RuntimeError('Failed/exhausted/out-of-order batch; no retry')
        self.last_pairs = []

    def accept(self, job, metrics):
        self.before(job)
        if metrics.get('accepted') is not True or not exact(metrics.get('job'), job):
            self.failed = True
            raise RuntimeError('Required flight/log validity failed')
        block = self.by_seed.setdefault(job['seed'], {})
        block[job['mode']] = metrics
        if 0 in block:
            for mode in (3, 4):
                identity = job['seed'], mode
                if mode in block and identity not in self.checked:
                    pair = self.compare(block[0], block[mode])
                    self.last_pairs.append(pair)
                    if pair.get('accepted') is not True:
                        self.failed = True
                        raise RuntimeError('Frozen paired development-risk threshold failed')
                    self.checked.add(identity)
        self.accepted.append(job)
        return self.last_pairs


def run_ordered(protocol, perform, compare, ledger, record):
    """Actual runner schedule, independently testable without flight/I/O edges."""
    admission = Admission(protocol, compare)
    for index, job in enumerate(protocol['jobs'], 1):
        admission.before(job)
        item = dict(attempt=index, job=job, directory=str(Path(protocol['artifacts']['new_run_root']) / job['id']), status='running')
        ledger['attempts'].append(item)
        record(dict(event='attempt', **item))
        try:
            metrics, details = perform(job, index)
            item.update(details)
            pairs = admission.accept(job, metrics)
            ledger['pairs'].extend(pairs)
            item['status'] = 'accepted'
            record(dict(event='accepted', job_id=job['id'], pairs=pairs))
        except BaseException as error:
            admission.failed = True
            item.update(status='failed', error=repr(error), paired_checks_at_stop=admission.last_pairs)
            record(dict(event='failed', job_id=job['id'], error=repr(error)))
            raise
        finally:
            ledger['unattempted'] = [j['id'] for j in protocol['jobs'][len(ledger['attempts']):]]
    ledger['success'] = len(admission.accepted) == 9 and len(admission.checked) == 6
    return ledger


def execution_checks_class():
    # Preserve prearm04 -> warmup10 -> position11 exact class composition.
    base = OLD_RUNNER.execution_checks_class()
    class Checks(base):
        def require_execution(self):
            api().require_execution_authority(self.job['gate'])
            qualified = api().require_qualification(self.job['gate'], self.source_head, self.qualification_path)
            if qualified.get('success') is not True or qualified.get('source_head') != self.source_head or qualified.get('gate') != self.job['gate']:
                raise RuntimeError('Wrong RI05 clean qualification')
            return qualified

        def configuration(self, cli, topic, output, phase):
            raw = cli('listener', 'velocity_ctrl_selection', '-n', '1')
            selection = OLD_RUNNER.scalars(raw)
            if 'div_req' not in selection:
                raise RuntimeError('Missing complete selection metadata')
            self.selection(selection)
            if selection.get('ri_version') != 1:
                raise RuntimeError('Missing RI02 diagnostic schema')
            for field in ('eps_req', 'eps_eff'):
                values = historical.base.arrays(raw, field)
                if len(values) != 3:
                    raise RuntimeError('Missing complete epsilon ' + field)
                selection[field] = values
            for axis, suffix in enumerate('XYZ'):
                expected = self.expected['MPC_VC_EPS_' + suffix]
                if not np.isfinite(selection['eps_req'][axis]) or abs(selection['eps_req'][axis] - expected) > 1e-7:
                    raise RuntimeError('Requested epsilon differs')
                effective = selection['eps_eff'][axis]
                if self.job['mode'] in (3, 4) and self.job['axes'] & (1 << axis):
                    if not np.isfinite(effective) or abs(effective - expected) > 1e-7:
                        raise RuntimeError('Effective epsilon differs')
                elif not np.isnan(effective):
                    raise RuntimeError('Unselected/PID epsilon must be NaN')
            historical.base.check_inner(topic('sta_rate_ctrl_status'))
            with (output / 'r03_configuration_checks.jsonl').open('a') as stream:
                stream.write(json.dumps(dict(phase=phase, selection=selection)) + '\n')

        def prepare_environment(self, output):
            qualified = self.require_execution()
            approval = read(self.qualification_path.parent / 'authorization.json')
            expected = dict(revision='ri05', stage=api().stage(self.job['gate']), gate=self.job['gate'], source_head=self.source_head,
                maximum_attempts=9, total_maximum_attempts=18, historical_attempts=0, new_matrix_attempts=9,
                qualification_sha256=digest(self.qualification_path),
                execution_authorized=True, flight_authorized=True, execution_ready=True)
            if approval.get('approved') is not True or any(not exact(approval.get(k), v) for k, v in expected.items()):
                raise RuntimeError('RI05 authorization receipt differs')
            save(output / 'authorization.json', approval)
            save(output / 'qualification.json', qualified)
            OLD_RUNNER.qualification_reference(output, self.qualification_path)
            save(output / 'run_protocol.json', self.p)
            (output / 'original_parameters.bson').write_bytes(self.backup.read_bytes())
            self.log_root = RAM_LOG.create()
            save(output / 'ram_log_root.json', dict(path=str(self.log_root), filesystem='tmpfs', owner=os.geteuid(),
                minimum_free_bytes=512 * 1024**2, volatile_before_archive=True, originals_retained_until_durable_archive=True))
            model_dir = output / 'models/iris'
            model_dir.mkdir(parents=True)
            original = REPO / 'Tools/sitl_gazebo/models/iris/iris.sdf'
            tree = historical.ET.ElementTree(historical.derive(historical.ET.parse(original).getroot()))
            imu = tree.getroot().find("model/plugin[@name='rotors_gazebo_imu_plugin']")
            if imu is None:
                raise RuntimeError('Missing original IMU plugin')
            imu.set('filename', str(self.plugins / 'libm10_imu.so'))
            tree.write(model_dir / 'iris.sdf', encoding='utf-8', xml_declaration=True)
            with (model_dir / 'iris.sdf').open('ab') as stream:
                stream.write(b'\n')
            historical.shutil.copyfile(model_dir / 'iris.sdf', model_dir / 'iris-gen.sdf')
            historical.shutil.copyfile(original.parent / 'model.config', model_dir / 'model.config')
            (model_dir / 'meshes').symlink_to(original.parent / 'meshes', target_is_directory=True)
            historical.verify_model(output, self.plugins)
            if digest(model_dir / 'iris.sdf') != self.frozen['derived_iris_sha256']:
                raise RuntimeError('Qualified derived contact/IMU asset differs')
            save(output / 'job.json', self.job)
            save(output / 'model_manifest.json', dict(original=digest(original), derived=digest(model_dir / 'iris.sdf'),
                only_change='Already-qualified compliant contact and original seeded IMU filename',
                seed_scope='IMU only; GPS/barometer/magnetometer/scheduling not independently seeded'))
            return dict(GAZEBO_MODEL_PATH=str(output / 'models') + ':' + str(REPO / 'Tools/sitl_gazebo/models'),
                GAZEBO_PLUGIN_PATH=str(REPO / 'build/px4_sitl_default/build_gazebo'), LD_LIBRARY_PATH='',
                M10_IMU_SEED=str(self.job['seed']), M10_IMU_LOG=str(output / 'imu_innovations.csv'),
                PX4_SIM_SPEED_FACTOR='1', PX4_SITL_LOG_DIR=str(self.log_root))
    return Checks


def precheck(protocol, source_head, qualification_path):
    validate_scope(protocol)
    gate = protocol['gate']
    api().require_execution_authority(gate)
    qualified = api().require_qualification(gate, source_head, Path(qualification_path))
    if historical.git('branch', '--show-current') != 'research/ista-velocity-regularized' or historical.git('rev-parse', 'HEAD') != source_head:
        raise RuntimeError('Wrong RI05 branch/source')
    if historical.git('status', '--porcelain') or historical.git('submodule', 'foreach', '--recursive', '--quiet', 'git status --porcelain'):
        raise RuntimeError('Dirty main/submodule workspace')
    if any(x[:1] in ('+', '-', 'U') for x in historical.git('submodule', 'status', '--recursive').splitlines()):
        raise RuntimeError('Recursive submodule mismatch')
    if active_simulators():
        raise RuntimeError('Conflicting simulator; no launch')
    if historical.shutil.disk_usage(ROOTFS).free < 12 * 1024**3:
        raise RuntimeError('Less than inherited 12GiB batch reserve')
    if (ROOTFS / 'etc/logging/logger_topics.txt').exists():
        raise RuntimeError('Custom logging override')
    if any((REPO / 'Tools/sitl_gazebo/models/iris').glob('*-gen.sdf')):
        raise RuntimeError('Unexpected generated model override')
    for port in (14550, 11345):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM if port == 14550 else socket.SOCK_STREAM) as sock:
            sock.bind(('127.0.0.1', port))
    frozen = read(Path(protocol['config_dir']) / 'frozen.json')
    for name, expected in frozen['assets'].items():
        if digest(REPO / name) != expected:
            raise RuntimeError('Changed frozen source/asset: ' + name)
    for name, expected in frozen['external_assets'].items():
        if digest(Path(name)) != expected:
            raise RuntimeError('Changed external asset: ' + name)
    historical.require_passive(REPO / 'research/sta-velocity-control/v06/soft_landing/offline03/evidence.json')
    historical.require_qualification(REPO / 'research/sta-velocity-control/v06/soft_landing/qualified_contact.json')
    historical.validate_receiver_profile()
    for name, expected in read(Path(protocol['plugins']) / 'manifest.json').items():
        if digest(Path(name)) != expected:
            raise RuntimeError('Changed plugin: ' + name)
    seeds = api().fresh_seeds(gate)
    if seeds.get('accepted') is not True:
        raise RuntimeError('Seed history scan failed')
    output = Path(protocol['artifacts']['new_run_root']).resolve()
    if output.exists() or any((api().DATA_ROOT/gate).glob('batch*')):
        raise RuntimeError('Prior/partial/unknown batch; no retry or replacement')
    if source_head not in (REPO / 'build/px4_sitl_default/src/lib/version/build_git_version.h').read_text():
        raise RuntimeError('Firmware not built at this clean source')
    if digest(BIN / 'px4') != qualified['firmware_sha256']:
        raise RuntimeError('Wrong qualified firmware')
    return qualified, frozen, seeds


def execute_gate(protocol, source_head, qualification_path, *, single_flight=flight_main, analyze=None, compare=None):
    gate = protocol['gate']
    api().require_execution_authority(gate)
    canonical = api().load_protocol(gate)
    qp = str(Path(qualification_path).resolve())
    if not exact({**protocol, 'qualification_path': qp}, {**canonical, 'qualification_path': qp}):
        raise RuntimeError('Caller protocol differs from canonical RI05 manifest')
    api().require_qualification(gate, source_head, Path(qp))
    # Coordinate with prior runners without changing any old lockfile bytes.
    old_api = OLD_RUNNER.local_module('protocol')
    old_locks = [Path(row['root']) / '.runner.lock' for row in old_api.retained_failure()['batches']]
    old_locks.append(old_api.EXTERNAL / old_api.DATA_STAGE / '.runner.lock')
    api().DATA_ROOT.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        for path in dict.fromkeys(p.resolve() for p in old_locks):
            stream = stack.enter_context(path.open('r'))
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError('Another historical/new runner owns shared EEPROM') from error
        stream = stack.enter_context((api().DATA_ROOT / '.runner.lock').open('a'))
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _execute_gate(protocol, source_head, Path(qp), single_flight=single_flight, analyze=analyze, compare=compare)


def _execute_gate(protocol, source_head, qualification_path, *, single_flight=flight_main, analyze=None, compare=None):
    gate = protocol['gate']
    qualified, frozen, seeds = precheck(protocol, source_head, qualification_path)
    protocol = {**protocol, 'qualification_path': str(qualification_path.resolve())}
    analyze, compare = analyze or local('analyzer').analyze, compare or local('analyzer').compare
    output = Path(protocol['artifacts']['new_run_root']).resolve()
    param = ROOTFS / 'eeprom/parameters_10016'
    original = param.read_bytes()
    values = historical.persisted_bson(original)
    definitions = read(REPO / 'build/px4_sitl_default/parameters.json')['parameters']
    defaults = {p['name']: p['default'] for p in definitions}
    types = {p['name']: p['type'] for p in definitions}
    historical.check_parameters({**defaults, **values}, frozen['control_parameters'])
    profile = int(values.get('SDLOG_PROFILE', defaults.get('SDLOG_PROFILE', 131))) | 16 | 1024 | 2048
    if profile != 3089:
        raise RuntimeError('Original-plus-raw-gyro profile differs from inherited 3089')
    output.mkdir(parents=True, exist_ok=False)
    backup = output / 'original_parameters.bson'
    with backup.open('xb') as stream:
        stream.write(original)
        stream.flush()
        os.fsync(stream.fileno())
    save(output / 'seed_audit_before_launch.json', seeds)
    save(output / 'qualification.json', qualified)
    OLD_RUNNER.qualification_reference(output, qualification_path)
    save(output / 'protocol.json', protocol)
    save(output / 'authorization.json', read(qualification_path.parent / 'authorization.json'))
    ledger = dict(stage=api().stage(gate), gate=gate, revision='ri05', source_head=source_head,
        planned=9, total_budget=18, new_planned=9, prior_attempts=0, attempts=[], pairs=[], success=False,
        firmware_sha256=qualified['firmware_sha256'], original_parameter_sha256=digest(backup),
        original_parameter_backup=str(backup), applied_profile=profile)
    journal = output / 'journal.jsonl'
    prefixes = {}
    def record(event):
        append_event(journal, event)
        save(output / 'ledger.json', ledger)
    def perform(job, index):
        api().require_qualification(gate, source_head, qualification_path)
        if active_simulators() or historical.git('status', '--porcelain') or historical.git('rev-parse', 'HEAD') != source_head:
            raise RuntimeError('Source/process changed before attempt')
        resources = dict(disk_free_bytes=historical.shutil.disk_usage(ROOTFS).free,
                         tmpfs_free_bytes=historical.shutil.disk_usage('/dev/shm').free)
        if resources['disk_free_bytes'] < 10 * 1024**3 or resources['tmpfs_free_bytes'] < 512 * 1024**2:
            raise RuntimeError('Insufficient original per-attempt disk/tmpfs reserve')
        if param.read_bytes() != original:
            raise RuntimeError('Previous parameters not restored')
        run = output / job['id']
        p = {**protocol, 'startup_overrides': {**protocol['startup_overrides'], **job['parameters']}}
        applied = {**values, **p['startup_overrides'], 'SDLOG_PROFILE': profile}
        if set(applied) - set(types) or any(types[k] not in ('Int32', 'Float') for k in applied):
            raise RuntimeError('Incomplete exact parameter type table')
        encoded = historical.encode_bson(applied, types)
        try:
            param.write_bytes(encoded)
            if param.read_bytes() != encoded:
                raise RuntimeError('Full BSON write/readback differs')
            expected = {**frozen['control_parameters'], **p['startup_overrides'], 'SYS_AUTOSTART': 10016, 'SDLOG_PROFILE': profile}
            checks = execution_checks_class()(p, expected, job, Path(protocol['plugins']), qualification_path, source_head, backup)
            checks.execution_permitted = True
            checks.pid_parameters_modified = True
            single_flight(run, checks, Path(protocol['execution_path']))
        finally:
            restored = restore_parameters(param, original, run, backup, source_head, job)
            record(dict(event='restore', **restored))
        RAM_LOG.release_archived(run, checks.log_root)
        if digest(BIN / 'px4') != qualified['firmware_sha256']:
            raise RuntimeError('Qualified firmware changed during attempt')
        metrics = analyze(run, p, job)
        if metrics.get('accepted') is not True:
            raise RuntimeError('Complete ULog acceptance failed: ' + str(metrics.get('error')))
        prefix = historical.noise_prefix(run)
        for seed, other in prefixes.items():
            difference = float(np.max(np.abs(prefix - other)))
            if seed == job['seed'] and difference >= 1e-10:
                raise RuntimeError('Paired IMU innovations differ')
            if seed != job['seed'] and difference <= 1e-6:
                raise RuntimeError('Distinct registered seeds not distinct')
        prefixes[job['seed']] = prefix
        return metrics, dict(metrics_sha256=digest(run / 'r03_metrics.json'), resource_capacity=resources)
    save(output / 'ledger.json', ledger)
    try:
        run_ordered(protocol, perform, compare, ledger, record)
    finally:
        if not active_simulators():
            param.write_bytes(original)
        ledger['parameter_restore_exact'] = param.read_bytes() == original
        ledger['remaining_simulators'] = active_simulators()
        ledger['unattempted'] = [j['id'] for j in protocol['jobs'][len(ledger['attempts']):]]
        record(dict(event='gate_end', success=ledger['success'], attempts=len(ledger['attempts']),
                    parameter_restore_exact=ledger['parameter_restore_exact'], remaining_simulators=ledger['remaining_simulators']))
    if not ledger['success'] or not ledger['parameter_restore_exact'] or ledger['remaining_simulators']:
        raise RuntimeError('Nine attempts/pairs/cleanup incomplete')
    return ledger


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate', choices=('C', 'D'), default='C')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--source-head', default='')
    parser.add_argument('--qualification', type=Path)
    args = parser.parse_args(argv)
    api().validate_manifest()
    protocol = api().load_protocol(args.gate)
    validate_scope(protocol)
    print(json.dumps(dict(stage=protocol['stage'], planned=9, maximum_attempts=9,
        jobs=[{k: j[k] for k in ('id', 'task', 'seed', 'candidate', 'mode', 'axes', 'divisor', 'main_duration_s')}
              for j in protocol['jobs']]), indent=2), flush=True)
    if not args.execute:
        print('DRY RUN: no process, parameter, output directory or flight changed.')
        return 0
    if re.fullmatch('[0-9a-f]{40}', args.source_head) is None or args.qualification is None:
        raise RuntimeError('Explicit full qualified source SHA and qualification required')
    execute_gate(protocol, args.source_head, args.qualification)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
