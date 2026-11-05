#!/usr/bin/env python3
"""Read-only RI05 result collection after a gate has stopped; never flies.

This result layer does not alter frozen acceptance or recompute ULog metrics.
It verifies archived bytes, retains partial/failed outcomes, and summarizes
accepted per-run statistics. An incomplete gate is not an execution error:
exit 0 means evidence collection succeeded, NOT that the gate passed.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys

DEFAULT_ROOT = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI05')
CANDIDATES = ('PID', 'RSTA', 'RISTA')
MISSING = object()
NOTES = [
    'C is milestone A/XY/TEST6; D is milestone B/XYZ/TEST8. Separate source/firmware and statistics per gate.',
    'Main consumed-velocity window is 64 s; first/second halves are 32 s each. J is the arithmetic mean of the three axis RMSEs.',
    'Position RMSE is published position target matched to preceding measurement (<=20 ms) over the observation window (~90-92 s), not same-sample consumed position error or only the 64 s main window.',
    'Height is deviation from nominal 2.5 m and includes intentional task-V vertical motion. Task Z velocity error and position-target Z error are separate.',
    'Target waveform/FF consistency error is not aircraft tracking error. Shared external reference does not imply identical internally synthesized v_sp.',
    'Groups average accepted per-run statistics, not pooled high-rate samples. n<=3 paired development; no significance or superiority claim.',
    'Failed/missing runs are retained and excluded from accepted-only means, never imputed as zero. Selection bias and incomplete pairs remain visible.',
    'TV uses genuine updates and is not energy. Common-band spectrum is correction acceleration, not velocity error.',
    'host_cost outer keys path_ns/module_ns contain microsecond quantiles; mean of per-run quantiles is not a pooled quantile, board CPU cost or WCET.',
    'p/ideal-nu/output peaks are not precomputed frozen metrics. Raw ULog fields remain indexed; no new numerical acceptance threshold is introduced.',
    'Airborne is confirmed only by recorded armed, not-landed, local-height>0.5 m monitor samples, not merely a takeoff command. No Gazebo truth is inferred.',
    'Protected applied output/state is not claimed to satisfy the ideal implicit equations. a_proxy is not measured acceleration.',
    'XYZ pid_axes=0 expresses no idle PID normal output; pid_calls=1 is the update invocation count.',
    'Replay hashes/receipts are checked without launching another decoder. A reported pass additionally requires the existing full replay and gate_pass receipt.',
]


def view(value):
    if isinstance(value, float) and not math.isfinite(value):
        return {'nonfinite_float': 'NaN' if math.isnan(value) else ('Infinity' if value > 0 else '-Infinity')}
    if isinstance(value, dict):
        return {key: view(item) for key, item in value.items()}
    if isinstance(value, list):
        return [view(item) for item in value]
    return value


def exact(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(exact(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    return a == b


def get(data, path, default=MISSING):
    for key in path.split('.'):
        if not isinstance(data, dict) or key not in data:
            return default
        data = data[key]
    return data


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def numeric(value):
    return finite(value) or (isinstance(value, list) and len(value) == 3 and all(finite(x) for x in value))


class Evidence:
    def __init__(self):
        self.files = {}
        self.issues = []

    def check(self, condition, message):
        if not condition:
            self.issues.append(message)
        return bool(condition)

    @staticmethod
    def signature(path):
        s = path.stat()
        return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)

    def ref(self, path):
        path = Path(os.path.abspath(path))
        key = str(path)
        try:
            before = self.signature(path)
            if key in self.files:
                self.check(before == self.files[key]['signature'], 'Input changed while collecting: ' + key)
                return self.files[key]['reference']
            h = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(chunk)
            self.check(before == self.signature(path), 'Input changed while hashing: ' + key)
            result = dict(path=key, bytes=before[2], sha256=h.hexdigest())
            if path.is_symlink():
                result.update(symlink=os.readlink(path), resolved_target=str(path.resolve()))
            self.files[key] = dict(signature=before, reference=result)
            return result
        except OSError as error:
            self.issues.append('Missing/unreadable input ' + key + ': ' + repr(error))
            return dict(path=key, missing=True)

    def read(self, path, *, required=False):
        path = Path(path)
        if not path.exists():
            if required:
                self.issues.append('Missing required JSON: ' + str(path))
            return None
        ref = self.ref(path)
        try:
            raw = path.read_bytes()
            self.check(hashlib.sha256(raw).hexdigest() == ref.get('sha256'), 'JSON changed: ' + str(path))
            return json.loads(raw)
        except (OSError, ValueError) as error:
            self.issues.append('Unreadable JSON ' + str(path) + ': ' + repr(error))
            return None

    def tree(self, root):
        root = Path(root)
        files, links = {}, {}
        if not root.exists():
            return dict(files=files, links=links)
        for path in sorted(root.rglob('*')):
            if path.is_symlink():
                links[str(path)] = os.readlink(path)
            if path.is_file():
                ref = self.ref(path)
                if 'sha256' in ref:
                    files[str(path)] = ref['sha256']
            elif path.is_symlink() and not path.exists():
                self.issues.append('Broken evidence link: ' + str(path))
        return dict(files=files, links=links)

    def unchanged(self):
        for path, item in self.files.items():
            try:
                self.check(self.signature(Path(path)) == item['signature'], 'Input changed after collection: ' + path)
            except OSError:
                self.issues.append('Input disappeared after collection: ' + path)


def metric_paths():
    paths = ['position_rmse', 'height.rmse', 'height.mean', 'height.std', 'height.max_abs', 'yaw_rmse',
             'spectral_summary.update_hz', 'spectral_summary.common_0_7hz_rms',
             'flight.sample_hz', 'observation.sample_hz', 'lifecycle.hte_shift_count', 'lifecycle.hte_shift_max_abs']
    for prefix in ('diagnostic', 'diagnostic.windows.first_half', 'diagnostic.windows.second_half'):
        paths.extend(prefix + '.' + item for item in (
            'error.rmse', 'error.mean', 'error.variance', 'error.std', 'error.max_abs',
            'J', 'seconds', 'samples', 'actual_updates', 'iae_m',
            'correction_tv', 'correction_tv_per_second', 'acceleration_tv', 'acceleration_tv_per_second',
            'normalized_thrust_tv', 'normalized_thrust_tv_per_second',
            'constraint_fraction', 'maximum_continuous_constraint_s', 'nu_peak.X', 'nu_peak.Y', 'nu_peak.Z'))
    for field in ('path_ns', 'module_ns'):
        paths.extend('host_cost.' + field + '.' + stat for stat in ('median_us', 'p95_us', 'p99_us', 'max_us'))
    return paths


def statistics_view(metrics, issues):
    values = {}
    for path in metric_paths():
        value = get(metrics, path)
        if value is MISSING:
            continue
        vector = ('.error.' in path or path in ('position_rmse', 'spectral_summary.common_0_7hz_rms')
                  or path.endswith(('_tv', '_tv_per_second', '.iae_m')))
        shape_ok = isinstance(value, list) and len(value) == 3 if vector else finite(value)
        if shape_ok and numeric(value):
            values[path] = value
        else:
            issues.append('Invalid/nonfinite statistic: ' + path)
    for path in ('diagnostic.error.rmse', 'diagnostic.J', 'position_rmse', 'yaw_rmse',
                 'diagnostic.windows.first_half.error.rmse', 'diagnostic.windows.second_half.error.rmse'):
        if path not in values:
            issues.append('Missing required statistic: ' + path)
    return values


def airborne_evidence(path, evidence):
    if not path.exists():
        return dict(confirmed=None, reason='samples.jsonl missing; takeoff command alone is insufficient')
    evidence.ref(path)
    ground_z, count = None, 0
    try:
        with path.open() as stream:
            for line in stream:
                sample = json.loads(line)
                count += 1
                position = sample.get('position', {})
                z = position.get('z')
                if ground_z is None and finite(z):
                    ground_z = z
                if (ground_z is not None and finite(z) and ground_z - z > .5
                        and sample.get('status', {}).get('arming_state') == 2
                        and sample.get('land', {}).get('landed') is False):
                    return dict(confirmed=True, first_confirmed_row=count, timestamp_us=position.get('timestamp'),
                                height_above_initial_local_z_m=ground_z-z,
                                source='samples.jsonl onboard monitor; not Gazebo truth')
    except (ValueError, OSError) as error:
        evidence.issues.append('Unreadable monitor samples ' + str(path) + ': ' + repr(error))
    return dict(confirmed=None, rows_read=count, reason='No confirmed airborne sample; not proof of zero flight')


def group_summary(rows):
    result = {}
    for candidate in CANDIDATES:
        all_rows = [r for r in rows if r.get('candidate') == candidate]
        chosen = [r for r in all_rows if r.get('included_in_accepted_means')]
        stats = {}
        for path in metric_paths():
            present = [r for r in chosen if path in r.get('statistics', {})]
            if not present:
                continue
            values = [r['statistics'][path] for r in present]
            if isinstance(values[0], list):
                mean = [statistics.mean(v[a] for v in values) for a in range(3)]
                sd = [statistics.stdev(v[a] for v in values) for a in range(3)] if len(values) > 1 else None
            else:
                mean = statistics.mean(values)
                sd = statistics.stdev(values) if len(values) > 1 else None
            stats[path] = dict(n=len(values), mean=mean, between_run_sd=sd,
                missing_accepted_ids=[r['id'] for r in chosen if path not in r.get('statistics', {})])
        result[candidate] = dict(planned=len(all_rows), attempted=sum(r['attempted'] for r in all_rows),
            declared_accepted=sum(r.get('declared_status') == 'accepted' for r in all_rows),
            accepted_for_descriptive_means=len(chosen), accepted_ids=[r['id'] for r in chosen], statistics=stats)
    return result


def pair_risk(pid, candidate):
    checks = {}
    for axis, margin in enumerate((.02, .02, .01)):
        checks['velocity_' + str(axis)] = candidate['diagnostic']['error']['rmse'][axis] <= 1.25*pid['diagnostic']['error']['rmse'][axis]+margin
        checks['position_' + str(axis)] = candidate['position_rmse'][axis] <= 1.25*pid['position_rmse'][axis]+.05
    for half in ('first_half', 'second_half'):
        for axis, margin in enumerate((.02, .02, .01)):
            checks[half + '_velocity_' + str(axis)] = candidate['diagnostic']['windows'][half]['error']['rmse'][axis] <= 1.25*pid['diagnostic']['windows'][half]['error']['rmse'][axis]+margin
    checks['yaw'] = candidate['yaw_rmse'] <= 1.25*pid['yaw_rmse']+.02
    return dict(accepted=all(checks.values()), checks=checks, seed=pid['job']['seed'], gate=pid['job']['gate'],
                candidate=candidate['job']['candidate'], criterion='Inherited development risk, not a requirement to beat PID or another STA')


def descriptive_pairs(rows):
    out = []
    for seed in sorted({r['seed'] for r in rows}):
        block = {r['candidate']: r for r in rows if r['seed'] == seed and r.get('included_in_accepted_means')}
        if not {'RSTA', 'RISTA'} <= block.keys():
            out.append(dict(seed=seed, complete=False, missing_candidates=[c for c in ('RSTA', 'RISTA') if c not in block]))
            continue
        left = block['RSTA']['statistics']['diagnostic.error.rmse']
        right = block['RISTA']['statistics']['diagnostic.error.rmse']
        out.append(dict(seed=seed, complete=True, rsta_rmse=left, rista_rmse=right,
                        rista_minus_rsta=[b-a for a,b in zip(left,right)],
                        relative_change_percent=[100*(b-a)/a if a != 0 else None for a,b in zip(left,right)]))
    return out


def read_run(item, expected, ledger, evidence, logs):
    run = Path(item['directory'])
    issues_before = len(evidence.issues)
    row = dict(id=expected['id'], seed=expected['seed'], candidate=expected['candidate'], attempted=True,
               declared_status=item.get('status'), directory=str(run), included_in_accepted_means=False)
    local_issues = []
    evidence.check(exact(item.get('job'), expected), 'Attempt job differs: ' + row['id'])
    result = evidence.read(run/'result.json', required=item.get('status') == 'accepted')
    metrics = evidence.read(run/'r03_metrics.json', required=item.get('status') == 'accepted')
    restore = evidence.read(run/'parameter_restore.json', required=item.get('status') == 'accepted')
    row.update(result=result, metrics=metrics, parameter_restore=restore,
               airborne=airborne_evidence(run/'samples.jsonl', evidence), error=item.get('error'),
               paired_checks_at_stop=item.get('paired_checks_at_stop'))
    if result is not None:
        evidence.check(result.get('source_head') == ledger.get('source_head') and
                       result.get('binary_sha256') == ledger.get('firmware_sha256'), 'Run source/firmware mismatch: ' + row['id'])
        row['takeoff_commanded'] = any(e.get('name') == 'takeoff_command' for e in result.get('events', []))
        row['landed_disarmed_observed'] = any(e.get('name') == 'landed_disarmed' for e in result.get('events', []))
        seen_logs = set()
        for entry in result.get('logs', []):
            archive = Path(entry.get('archive', ''))
            ref = evidence.ref(archive)
            verified = (ref.get('sha256') == entry.get('sha256') and ref.get('bytes') == entry.get('bytes')
                        and entry.get('durable_copy_verified') is True and 'sha256' in ref)
            evidence.check(verified, 'ULog digest/size/archive verification mismatch: ' + str(archive))
            evidence.check(str(archive) not in seen_logs, 'Duplicate result ULog: ' + str(archive))
            seen_logs.add(str(archive))
            logs.append(dict(gate=expected['gate'], job_id=row['id'], seed=row['seed'], candidate=row['candidate'],
                source_head=ledger.get('source_head'), firmware_sha256=ledger.get('firmware_sha256'),
                recorded=entry, actual=ref, verified=verified))
    if metrics is not None:
        evidence.check(exact(metrics.get('job'), expected), 'Metrics job differs: ' + row['id'])
        binding = metrics.get('binding', {})
        evidence.check(binding.get('source_head') == ledger.get('source_head')
                       and binding.get('firmware_sha256') == ledger.get('firmware_sha256')
                       and binding.get('stage') == ledger.get('stage') and binding.get('revision') == 'ri05',
                       'Metrics qualification binding differs: ' + row['id'])
        if item.get('metrics_sha256'):
            evidence.check(evidence.ref(run/'r03_metrics.json').get('sha256') == item['metrics_sha256'], 'Metrics SHA changed: ' + row['id'])
        row['statistics'] = statistics_view(metrics, local_issues)
    if item.get('status') == 'accepted':
        evidence.check(result is not None and result.get('success') is True and bool(result.get('logs')), 'Accepted run lacks successful result/logs: ' + row['id'])
        evidence.check(metrics is not None and metrics.get('accepted') is True and bool(item.get('metrics_sha256')), 'Accepted run lacks accepted metrics/SHA: ' + row['id'])
        evidence.check(restore is not None and restore.get('parameter_restore_exact') is True
                       and restore.get('remaining_simulators') == [] and restore.get('stopped_before_restore') is True
                       and restore.get('original_parameter_sha256') == restore.get('restored_parameter_sha256') == ledger.get('original_parameter_sha256')
                       and restore.get('source_head') == ledger.get('source_head') and restore.get('job_id') == row['id'],
                       'Accepted run parameter restore mismatch: ' + row['id'])
        evidence.check(row['airborne']['confirmed'] is True and row.get('landed_disarmed_observed') is True,
                       'Accepted run lacks monitored flight/landing evidence: ' + row['id'])
    evidence.issues.extend(row['id'] + ': ' + item for item in local_issues)
    row['evidence_issues'] = evidence.issues[issues_before:]
    row['included_in_accepted_means'] = item.get('status') == 'accepted' and not row['evidence_issues']
    return row


def verify_replay(replay_dir, ledger, rows, evidence, batch_snapshot):
    path = replay_dir/'summary.json'
    summary = evidence.read(path)
    if summary is None:
        return dict(present=False, verified=False, replayed=0)
    if summary.get('success') is not True:
        return dict(present=True, verified=False, replayed=summary.get('replayed', 0),
                    summary_reference=evidence.ref(path), summary=summary,
                    note='Incomplete/failed independent replay is retained, not relabelled as complete')
    before = len(evidence.issues)
    expected = dict(stage=ledger['stage'], revision='ri05', gate=ledger['gate'], source_head=ledger['source_head'],
                    qualified_firmware_sha256=ledger['firmware_sha256'], success=True, new_flights=0,
                    replayed=9, source_inputs_unchanged=True)
    for key, value in expected.items():
        evidence.check(exact(summary.get(key), value), 'Replay field differs: ' + key)
    evidence.check(summary.get('ledger_sha256') == evidence.ref(replay_dir.parent/'batch01/ledger.json').get('sha256'), 'Replay ledger SHA differs')
    evidence.check(exact(summary.get('original_input_sha256_before'), summary.get('original_input_sha256_after'))
                   and exact(summary.get('original_input_sha256_after'), batch_snapshot), 'Replay input inventory changed')
    commands = summary.get('commands', [])
    evidence.check(len(commands) == 9, 'Replay requires nine decoder commands')
    replayed = 0
    for row, command in zip([r for r in rows if r['attempted']], commands):
        run = Path(row['directory'])
        dest = replay_dir/row['id']
        argv = command.get('argv', [])
        valid_command = (len(argv) == 6 and argv[1] == '-B' and argv[2].endswith('/ri05/tools/analyzer.py')
                         and argv[3:] == [str(run), '--output', str(dest)] and command.get('returncode') == 0)
        evidence.check(valid_command, 'Replay command mismatch: ' + row['id'])
        if command.get('log'):
            evidence.check(evidence.ref(Path(command['log'])).get('sha256') == command.get('log_sha256'), 'Replay command log SHA mismatch: ' + row['id'])
        else:
            evidence.issues.append('Replay log path absent: ' + row['id'])
        repeated = evidence.read(dest/'r03_metrics.json', required=True)
        same = exact(row.get('metrics'), repeated) and repeated is not None
        evidence.check(same, 'Replayed metrics differ: ' + row['id'])
        evidence.check(evidence.ref(run/'spectra.json').get('sha256') == evidence.ref(dest/'spectra.json').get('sha256'), 'Replayed spectra differ: ' + row['id'])
        replayed += bool(valid_command and same)
    evidence.check(exact(summary.get('pairs'), ledger.get('pairs')), 'Replay/ledger paired decisions differ')
    return dict(present=True, verified=len(evidence.issues) == before, replayed=replayed,
                summary_reference=evidence.ref(path), summary=summary)


def save_new(path, value):
    with path.open('x') as stream:
        json.dump(view(value), stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def collect(gate, output, data_root=DEFAULT_ROOT):
    if gate not in ('C', 'D'):
        raise ValueError('Only RI05 gates C/D')
    root, output = Path(data_root).resolve(), Path(output).resolve()
    if output.exists() or output == root or root in output.parents or output in root.parents:
        raise ValueError('Output must be a NEW directory outside the input data tree')
    base, batch = root/gate, root/gate/'batch01'
    evidence = Evidence()
    ledger = evidence.read(batch/'ledger.json', required=True)
    protocol = evidence.read(batch/'protocol.json', required=True)
    if not isinstance(ledger, dict) or not isinstance(protocol, dict):
        raise ValueError('Cannot collect without readable frozen batch protocol and ledger')
    if any(r.get('status') == 'running' for r in ledger.get('attempts', [])) or 'remaining_simulators' not in ledger:
        raise ValueError('Gate still running/unfinalized: refuse large hashing during flight')
    if ledger.get('remaining_simulators'):
        raise ValueError('Simulator cleanup not complete: stop collection until processes stop')
    jobs = protocol.get('jobs', [])
    expected_axes, expected_task, expected_test = (3, 'H', 6) if gate == 'C' else (7, 'V', 8)
    evidence.check(len(jobs) == 9 and len({j.get('id') for j in jobs}) == 9, 'Protocol must contain nine unique gate jobs')
    evidence.check(ledger.get('stage') == 'RI05-'+gate and ledger.get('revision') == 'ri05' and ledger.get('gate') == gate, 'Wrong ledger scope')
    for key, value in dict(planned=9, total_budget=18, new_planned=9, prior_attempts=0).items():
        evidence.check(type(ledger.get(key)) is int and ledger[key] == value, 'Wrong budget: ' + key)
    for index, job in enumerate(jobs):
        mode = {'PID': 0, 'RSTA': 3, 'RISTA': 4}.get(job.get('candidate'))
        block, slot = divmod(index, 3)
        order = ('PID', 'RISTA', 'RSTA') if block == 1 else CANDIDATES
        evidence.check(mode is not None and job.get('gate') == gate and job.get('task') == expected_task
                       and job.get('mode') == mode and job.get('axes') == (0 if mode == 0 else expected_axes)
                       and job.get('divisor') == 1 and job.get('main_duration_s') == 64
                       and job.get('parameters', {}).get('MPC_VCT_TEST') == expected_test
                       and job.get('id') == f'run{index+1+(9 if gate=="D" else 0):03d}'
                       and job.get('candidate') == order[slot]
                       and job.get('seed') == (83001 if gate == 'C' else 83101)+block,
                       'Wrong job scope/seed/order: ' + str(job.get('id')))
    attempts = ledger.get('attempts', [])
    evidence.check(len(attempts) <= len(jobs), 'Attempts exceed frozen finite budget')
    rows, logs = [], []
    for index, job in enumerate(jobs):
        if index >= len(attempts):
            rows.append(dict(id=job['id'], seed=job['seed'], candidate=job['candidate'], attempted=False,
                             declared_status='unattempted', included_in_accepted_means=False))
            continue
        item = attempts[index]
        evidence.check(item.get('attempt') == index+1 and Path(item['directory']).resolve() == batch/job['id'], 'Attempt order/directory differs')
        rows.append(read_run(item, job, ledger, evidence, logs))
    evidence.check(ledger.get('unattempted') == [r['id'] for r in rows if not r['attempted']], 'Ledger missing/unattempted inventory differs')
    batch_snapshot = evidence.tree(batch)
    gate_receipt = evidence.read(base/'gate_pass.json')
    replay_dir = Path(gate_receipt['replay_summary_path']).parent if gate_receipt and gate_receipt.get('replay_summary_path') else base/'replay01'
    if replay_dir.parent != base or replay_dir == batch:
        evidence.issues.append('Replay path outside gate/inside original batch')
        replay_dir = base/'replay01'
    evidence.tree(replay_dir)
    replay = verify_replay(replay_dir, ledger, rows, evidence, batch_snapshot)
    qualification_reference = evidence.read(batch/'qualification_reference.json')
    qualification = None
    if qualification_reference:
        qpath = Path(qualification_reference['path'])
        evidence.check(evidence.ref(qpath).get('sha256') == qualification_reference.get('sha256'), 'Qualification reference SHA differs')
        qualification = evidence.read(qpath, required=True)
        if qualification:
            evidence.check(qualification.get('source_head') == ledger.get('source_head') and qualification.get('firmware_sha256') == ledger.get('firmware_sha256')
                           and qualification.get('success') is True and qualification.get('approved') is True
                           and bool(qualification.get('commands')) and all(c.get('exit_code') == 0 for c in qualification['commands']), 'Qualification evidence differs')
    else:
        evidence.issues.append('Missing qualification reference')
    accepted = [r for r in rows if r.get('included_in_accepted_means')]
    blocks = {}
    for row in accepted:
        blocks.setdefault(row['seed'], {})[row['candidate']] = row['metrics']
    pairs = []
    for row in accepted:
        block = blocks[row['seed']]
        if row['candidate'] != 'PID' and 'PID' in block:
            pairs.append(pair_risk(block['PID'], row['metrics']))
    if ledger.get('success'):
        evidence.check(exact(pairs, ledger.get('pairs')) and len(pairs) == 6 and all(p['accepted'] for p in pairs), 'Complete ledger paired risk differs')
    if gate_receipt:
        expected = dict(stage='RI05-'+gate, revision='ri05', gate=gate, accepted=True, planned=9,
                        attempts=9, accepted_runs=9, independent_replays=9, paired_checks=6, missing=0,
                        source_head=ledger.get('source_head'), firmware_sha256=ledger.get('firmware_sha256'),
                        ledger_sha256=evidence.ref(batch/'ledger.json').get('sha256'),
                        parameter_restore_exact=True, new_flights_by_replay=0)
        for key, value in expected.items():
            evidence.check(exact(gate_receipt.get(key), value), 'Gate receipt differs: ' + key)
        evidence.check(gate_receipt.get('replay_summary_sha256') == evidence.ref(replay_dir/'summary.json').get('sha256'), 'Gate replay SHA differs')
    prior_gate = None
    if gate == 'D':
        prior_gate = evidence.read(root/'C/gate_pass.json', required=True)
        prior_ledger = evidence.read(root/'C/batch01/ledger.json', required=True)
        if prior_gate and prior_ledger:
            prior_replay_path = Path(prior_gate.get('replay_summary_path', str(root/'C/replay01/summary.json')))
            evidence.check(prior_replay_path.parent.parent == root/'C', 'Prior C replay path outside gate')
            evidence.check(prior_gate.get('accepted') is True and prior_gate.get('accepted_runs') == 9
                           and prior_gate.get('independent_replays') == 9 and prior_gate.get('paired_checks') == 6
                           and prior_gate.get('missing') == 0 and prior_gate.get('parameter_restore_exact') is True
                           and prior_gate.get('source_head') == prior_ledger.get('source_head')
                           and prior_gate.get('firmware_sha256') == prior_ledger.get('firmware_sha256')
                           and prior_gate.get('ledger_sha256') == evidence.ref(root/'C/batch01/ledger.json').get('sha256')
                           and prior_gate.get('replay_summary_sha256') == evidence.ref(prior_replay_path).get('sha256'),
                           'D result lacks bound prior C acceptance receipt')
    evidence.unchanged()
    passed = (not evidence.issues and len(accepted) == 9 and ledger.get('success') is True
              and ledger.get('parameter_restore_exact') is True and ledger.get('unattempted') == []
              and replay['verified'] and gate_receipt is not None and qualification is not None)
    summary = dict(stage='RI05-'+gate, milestone_gate='A' if gate == 'C' else 'B', gate=gate,
        source_head=ledger.get('source_head'), firmware_sha256=ledger.get('firmware_sha256'),
        status='passed' if passed else ('evidence_inconsistent' if evidence.issues else 'partial_or_not_finalized'),
        gate_passed=passed, collection_ok=not evidence.issues, new_flights=0, new_ulog_decodes=0,
        counts=dict(planned=len(jobs), attempted=len(attempts),
            takeoff_commanded=sum(r.get('takeoff_commanded') is True for r in rows),
            airborne_confirmed=sum(r.get('airborne', {}).get('confirmed') is True for r in rows),
            airborne_unknown=sum(r['attempted'] and r.get('airborne', {}).get('confirmed') is not True for r in rows),
            declared_accepted=sum(r.get('declared_status') == 'accepted' for r in rows),
            accepted_verified=len(accepted), failed=sum(r.get('declared_status') == 'failed' for r in rows),
            unattempted=sum(not r['attempted'] for r in rows), missing_accepted=len(jobs)-len(accepted),
            independent_replays=replay['replayed'], paired_risk_checks=len(pairs)),
        groups=group_summary(rows), rista_vs_rsta_descriptive_pairs=descriptive_pairs(rows),
        runs=rows, stored_pairs=ledger.get('pairs', []), independent_numeric_pairs=pairs,
        parameter_restore_exact=ledger.get('parameter_restore_exact'), remaining_simulators=ledger.get('remaining_simulators'),
        qualification=qualification, replay=replay, gate_receipt=gate_receipt, prior_gate_receipt=prior_gate, ledger=ledger,
        issues=evidence.issues, notes=NOTES,
        invocation=dict(script=str(Path(__file__).resolve()), data_root=str(root), gate=gate),
        nonfinite_display='Explicit nonfinite_float tags preserve raw diagnostic values; no imputation or source writes')
    script_ref = evidence.ref(Path(__file__))
    output.mkdir(parents=True, exist_ok=False)
    save_new(output/'summary.json', summary)
    save_new(output/'ulog_index.json', dict(log_count=len(logs), verified_count=sum(x['verified'] for x in logs), files=logs))
    save_new(output/'evidence_index.json', dict(scope=str(base), source_files_unchanged=not any('changed' in x or 'disappeared' in x for x in evidence.issues),
        files=[item['reference'] for _, item in sorted(evidence.files.items())], batch_snapshot=batch_snapshot,
        script=script_ref, exclusions=['Collector output directory is outside input tree; no input file is rewritten']))
    text = '# RI05 ' + gate + ' 结果摘要\n\n状态：`' + summary['status'] + '`；整门通过：' + str(passed) + '。\n\n'
    text += '仅汇总既有证据；退出码 0 不代表实验门已通过。\n\n'
    text += '| 算法 | 接受数/计划数 | X RMSE | Y RMSE | Z RMSE |\n|---|---:|---:|---:|---:|\n'
    for name, group in summary['groups'].items():
        values = group['statistics'].get('diagnostic.error.rmse', {}).get('mean')
        cells = [format(v, '.8g') for v in values] if values is not None else ['缺失']*3
        text += '| ' + name + ' | ' + str(group['accepted_for_descriptive_means']) + '/' + str(group['planned']) + ' | ' + ' | '.join(cells) + ' |\n'
    text += '\n速度单位 m/s；均值仅含逐轮接受且证据一致的运行。完整计数、失败、半窗、指标口径、配对风险与指纹见 JSON。\n'
    with (output/'SUMMARY_CN.md').open('x') as stream:
        stream.write(text)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate', choices=('C', 'D'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, default=DEFAULT_ROOT, help='Read-only evidence root; override for isolated fixtures')
    args = parser.parse_args()
    try:
        summary = collect(args.gate, args.output, args.data_root)
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps(dict(collection_ok=False, error=repr(error)), ensure_ascii=False))
        return 2
    print(json.dumps({k: summary[k] for k in ('stage','status','gate_passed','collection_ok','counts','issues')}, ensure_ascii=False, indent=2))
    return 0 if summary['collection_ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
