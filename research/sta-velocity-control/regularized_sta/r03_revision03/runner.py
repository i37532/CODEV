#!/usr/bin/env python3
"""R03 revision03 execution; default dry-run, explicit qualified launch only.

Actual flight body derives from v08/protocol02/flight.py SHA-256
ed6901ce8203821943241bf4108f6b6a6d1768b80b2c6a4e65f687a6d1ed9cfb.
The modern process ownership/entry/landing/archive body is preserved verbatim;
only its old common/authorization/argparse entry is replaced by explicit R03
qualification and output arguments. Old modules/globals are never modified.
Offline qualification is not execution authority. A subsequent explicit version
must resolve permission before these already-tested gate-loop paths may run.
"""
import importlib.util
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
LEGACY = REPO / 'research/sta-velocity-control/axis_ablation/ax04'
if str(LEGACY) not in sys.path:
    sys.path.insert(0, str(LEGACY))

def local_module(name):
    if name not in ('protocol', 'analyzer'):
        raise ValueError('Unknown revision03 dependency')
    key = '_r03_revision03_' + name
    path = (HERE / (name + '.py')).resolve()
    if key in sys.modules:
        if Path(getattr(sys.modules[key], '__file__', '')).resolve() != path:
            raise RuntimeError('Private revision03 module path collision: ' + name)
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec); sys.modules[key] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[key]
        raise
    return module

spec = importlib.util.spec_from_file_location('_r03_revision03_unchanged_ax04_runner', LEGACY / 'run.py')
historical = importlib.util.module_from_spec(spec); spec.loader.exec_module(historical)

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
import fcntl
from contextlib import ExitStack
import numpy as np

from pymavlink import mavutil
from v04_task04 import scalars, entry_ok, EntryGate
from v04_entry14 import advance_entry
from handoff_capture import Handoff, local_xy_ok
import ram_log

REPO = Path(__file__).resolve().parents[4]
BIN = REPO / "build/px4_sitl_default/bin"
ROOTFS = REPO / "build/px4_sitl_default/tmp/rootfs"


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def qualification_reference(output, path):
    path = Path(path).resolve()
    reference = dict(path=str(path), sha256=digest(path))
    save(Path(output)/'qualification_reference.json', reference)
    return reference


def active_simulators():
    found = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                name = (entry / "comm").read_text().strip()
                if name in ("px4", "gzserver", "gzclient", "gazebo", "QGroundControl"):
                    found.append((entry.name, name))
            except (OSError, ProcessLookupError):
                pass
    return found


def shutdown_owned(proc, cli):
    """Only the session leader created by this invocation; never pkill by name."""
    if proc.poll() is not None: return
    try:
        cli('shutdown',check=False)
        proc.wait(timeout=15)
        return
    except (subprocess.TimeoutExpired,RuntimeError):
        pass
    if proc.poll() is not None: return
    if os.getpgid(proc.pid)!=proc.pid: raise RuntimeError('Owned launcher session identity changed')
    os.killpg(proc.pid,signal.SIGTERM)
    try: proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid,signal.SIGKILL)
        proc.wait(timeout=5)


def flight_main(output, checks, scenario_path):
    """Execute one already-ledgered R03 attempt; no implicit authority."""
    if checks is None or not getattr(checks, 'execution_permitted', False):
        raise RuntimeError('Qualified R03 batch required before mutation')
    local_module('protocol').require_execution_authority(checks.job['gate'])
    checks.require_execution()
    if Path(scenario_path).resolve() != Path(checks.p['execution_path']).resolve():
        raise RuntimeError('Wrong R03 execution manifest binding')
    output = Path(output).resolve()
    # Opt-in M10 only; prior milestones retain exactly the original timing.
    speed = float(getattr(checks, 'simulation_speed', 1))
    if not 1 <= speed <= 10:
        raise ValueError('Simulation speed must be within [1,10]')
    if active_simulators():
        raise RuntimeError(f"Refusing conflicting instances: {active_simulators()}")
    output.mkdir(parents=True, exist_ok=False)
    old_eeprom = ROOTFS / "eeprom/parameters_10016"
    if old_eeprom.exists():
        (output / "startup_parameters.bson").write_bytes(old_eeprom.read_bytes())
    result = {
        "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip(),
        "binary_sha256": digest(BIN / "px4"),
        "runner_sha256": digest(Path(__file__)),
        "command": ["./sitl/run.sh", "--headless", "--backend", "gazebo", "--model", "iris"],
        "pid_parameters_modified": bool(getattr(checks, 'pid_parameters_modified', False)),
        "success": False,
        "events": [],
    }
    if scenario_path is not None:
        result["scenario_sha256"] = digest(scenario_path)
        result["scenario_path"] = str(scenario_path.resolve())
    (output / "worktree_status.txt").write_text(
        subprocess.check_output(["git", "status", "--short"], cwd=REPO, text=True))
    (output / "tracked_diff.patch").write_bytes(
        subprocess.check_output(["git", "diff", "HEAD"], cwd=REPO))
    command_file = (output / "commands.jsonl").open("w")
    sample_file = (output / "samples.jsonl").open("w")
    stop = threading.Event()
    link = mavutil.mavlink_connection("udpin:127.0.0.1:14550",
                                     source_system=255, source_component=190)
    telemetry = {}
    acknowledgements = []
    wire_lock = threading.Lock()

    def receiver():
        last_heartbeat = 0
        last_manual = 0
        with (output / "mavlink_events.jsonl").open("w") as stream:
            while not stop.is_set():
                msg = link.recv_match(blocking=True, timeout=0.1/speed)
                if msg:
                    if msg.get_type() in ("HEARTBEAT", "STATUSTEXT", "EXTENDED_SYS_STATE"):
                        stream.write(json.dumps(msg.to_dict()) + "\n")
                        stream.flush()
                    telemetry[msg.get_type()] = msg
                    if msg.get_type() == 'COMMAND_ACK':
                        record = dict(message=msg.to_dict(), system=msg.get_srcSystem(),
                                      component=msg.get_srcComponent(), received_monotonic=time.monotonic())
                        acknowledgements.append(record)
                        stream.write(json.dumps(record)+'\n'); stream.flush()
                if time.monotonic() - last_heartbeat > 0.5/speed and telemetry:
                    with wire_lock:
                        link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                                                mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                                                0, 0, mavutil.mavlink.MAV_STATE_ACTIVE)
                    last_heartbeat = time.monotonic()
                # Emulate a connected RC transmitter at neutral sticks. This
                # satisfies the existing RC-loss policy during AUTO_LOITER.
                # It does not publish attitude/rate/offboard setpoints.
                if time.monotonic() - last_manual > 0.1/speed and telemetry:
                    with wire_lock:
                        link.mav.manual_control_send(1, 0, 0, 500, 0, 0)
                    last_manual = time.monotonic()

    worker = threading.Thread(target=receiver, daemon=True)
    worker.start()

    from cli_clock import receipt
    clock_receipts = {}

    def cli(module, *arguments, check=True):
        cmd = [str(BIN / ("px4-" + module)), *map(str, arguments)]
        started = time.monotonic_ns()
        proc = subprocess.run(cmd, cwd=ROOTFS, text=True, capture_output=True, timeout=10)
        finished = time.monotonic_ns()
        record = {"cmd": cmd, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr,
                  "host_start_ns": started, "host_end_ns": finished, "host_elapsed_ns": finished-started}
        try:
            timing = receipt(module, list(map(str, arguments)), proc.stdout, started, finished) if proc.returncode == 0 else None
            record['clock'] = timing
        except ValueError as exc:
            record['clock_error'] = str(exc)
            command_file.write(json.dumps(record)+'\n'); command_file.flush()
            raise
        command_file.write(json.dumps(record) + "\n")
        command_file.flush()
        if module == 'listener' and arguments:
            clock_receipts[arguments[0]] = timing
        if check and proc.returncode:
            raise RuntimeError(f"CLI failed: {module} {arguments}: {proc.stdout} {proc.stderr}")
        return proc.stdout

    def topic(name):
        raw = cli("listener", name, "-n", "1")
        data = scalars(raw)
        clock = clock_receipts.pop(name, None)
        if clock is not None: data['_clock'] = clock
        return data

    def sample(phase):
        state = {"phase": phase, "position": topic("vehicle_local_position"),
                 "status": topic("vehicle_status"), "land": topic("vehicle_land_detected")}
        sample_file.write(json.dumps(state) + "\n")
        sample_file.flush()
        # Opt-in research monitor. Raising preserves failure evidence and enters
        # the existing local-instance shutdown path; it never commands fallback.
        if checks is not None and hasattr(checks, "monitor"):
            checks.monitor(phase, cli, topic, output, state)
        return state

    def event(name, state):
        entry = {"name": name, "timestamp_us": state["position"]["timestamp"]}
        result["events"].append(entry)
        save(output / "result.json", result)
        print(json.dumps(entry), flush=True)

    console = None
    proc = None
    try:
        env = os.environ.copy()
        env.pop("DONT_RUN", None)
        env.pop("NO_PXH", None)
        env.pop("PX4_SIM_SPEED_FACTOR", None)
        env["PX4_SITL_WORLD"] = str(REPO / "sitl/worlds/empty_grey.world")
        env["GAZEBO_MASTER_URI"] = "http://127.0.0.1:11345"
        if checks is not None and hasattr(checks, 'prepare_environment'):
            env.update(checks.prepare_environment(output))
            env['PX4_SIM_SPEED_FACTOR'] = str(speed)
            result['simulation_speed_requested'] = speed
        result["explicit_environment"] = {k: env[k] for k in ("PX4_SITL_WORLD", "GAZEBO_MASTER_URI", "PX4_SITL_LOG_DIR")}
        console = (output / "console.log").open("w")
        proc = subprocess.Popen(result["command"], cwd=REPO, env=env,
                                stdin=subprocess.PIPE, stdout=console, stderr=subprocess.STDOUT,
                                start_new_session=True)
        result["launcher_pid"] = proc.pid
        save(output / "result.json", result)
    except BaseException:
        if proc is not None:
            shutdown_owned(proc,cli)
        stop.set(); worker.join(timeout=2); link.close()
        if console is not None: console.close()
        command_file.close(); sample_file.close()
        raise
    try:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError("SITL exited during startup")
            if "Startup script returned successfully" in (output / "console.log").read_text():
                break
            time.sleep(0.5)
        else:
            raise TimeoutError("Startup timeout")
        # The project launcher invokes make and may rebuild before starting PX4.
        actual_binary = digest(BIN / "px4")
        if actual_binary != result["binary_sha256"]:
            result["prelaunch_binary_sha256"] = result["binary_sha256"]
            result["binary_sha256"] = actual_binary
        (output / "params_all.txt").write_text(cli("param", "show", "-a"))
        cli("param", "save", str(output / "parameters.bson"))
        (output / "version.txt").write_text(cli("ver", "all"))
        (output / "mavlink_status.txt").write_text(cli("mavlink", "status"))
        if checks is not None:
            checks("preflight", cli, topic, output)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            state = sample("warmup")
            p = state["position"]
            if p.get("timestamp", 0) > 30e6 and p.get("xy_global") and p.get("z_valid") and telemetry:
                break
            time.sleep(1/speed)
        else:
            raise TimeoutError("Global estimator readiness timeout")
        event("ready", state)
        ref = checks.start_heading(topic, output)
        checks.reference = ref
        save(output / "height_reference.json", ref)
        state['position'] = ref['position']
        cli("commander", "takeoff")
        event("takeoff_command", state)
        deadline = time.monotonic() + 150
        gate = EntryGate()
        handoff = Handoff()
        readback = False
        candidates = []
        while time.monotonic() < deadline:
            state = sample("takeoff")
            p, status = state["position"], state["status"]
            if status.get("failsafe"):
                raise RuntimeError("Failsafe during takeoff")
            if (status.get("nav_state") == 2 and status.get("arming_state") == 2
                    and not state["land"].get("landed", True) and handoff.sent is None and checks.task_yaw_ready):
                # Preserve raw source provenance, not the already-cleared Navigator triplet.
                (output / "triplet_before.txt").write_text(cli("listener", "position_setpoint_triplet", "-n", "1"))
                source_log = checks.live.read()
                # Query current CLI time after tail snapshot to avoid a fabricated future-source error.
                state['position'] = topic('vehicle_local_position')
                p = state['position']
                def record_attempt(target_record, wall, sample):
                    save(output / "handoff_target.json", target_record)
                    save(output / "reposition_command.json", dict(sent_monotonic=wall,
                         timestamp_us=sample, message="COMMAND_INT", wire=target_record["wire"], maximum_sends=1))
                with wire_lock:
                    handoff.start(link.mav, source_log, ref, checks.frozen_yaw,
                                  p["timestamp"], time.monotonic(), on_attempt=record_attempt)
                event("reposition_command", state)
            if handoff.sent is not None:
                raw = cli("listener", "position_setpoint_triplet", "-n", "1")
                (output / "triplet_after.txt").write_text(raw)
                was_ready = handoff.ready
                readback = handoff.poll(time.monotonic(), acknowledgements, raw, status.get("nav_state"))
                if handoff.ack is not None:
                    save(output / "reposition_ack.json", handoff.ack)
                with (output / "handoff_pending.jsonl").open("a") as stream:
                    stream.write(json.dumps(dict(timestamp_us=p["timestamp"], ready=readback, raw=raw))+"\n")
                if readback and not was_ready:
                    state['position'] = topic('vehicle_local_position')
                    p = state['position']
                    event("handoff_ready", state)
            target = topic("trajectory_setpoint")
            diagnostic = checks.latest_diagnostic
            valid = readback and local_xy_ok(target, handoff.target) and entry_ok(p, status, state["land"], target, ref)
            candidates.append(dict(position=p, status=status, land=state["land"],
                                   target=target, diagnostic=diagnostic, valid=bool(valid)))
            save(output / "entry_candidates.json", candidates)
            readiness = advance_entry(gate, p["timestamp_sample"], valid, diagnostic,
                                      checks.live.read, ref, p["timestamp"])
            with (output / "entry_raw_gate.jsonl").open("a") as stream:
                stream.write(json.dumps(readiness) + "\n")
            if readiness["ready"]:
                checks("hover", cli, topic, output)
                break
            time.sleep(0.25/speed)
        else:
            raise TimeoutError("Takeoff/explicit 2.5m target entry timeout")
        event("hover_start", state)
        (output / "perf_hover_start.txt").write_text(cli("perf"))
        hover_start = state["position"]["timestamp"]
        if checks is not None:
            checks("hover", cli, topic, output)
        deadline = time.monotonic() + 240
        while state["position"]["timestamp"] - hover_start < 90e6:
            if time.monotonic() > deadline:
                raise TimeoutError("90 s simulation observation wall timeout")
            time.sleep(0.5/speed)
            state = sample("hover")
            handoff.poll(time.monotonic(), acknowledgements,
                         cli("listener", "position_setpoint_triplet", "-n", "1"), state['status']['nav_state'])
            if not local_xy_ok(topic('trajectory_setpoint'), handoff.target):
                raise RuntimeError('Local XY hold target lost during observation')
            if (state["status"].get("failsafe") or state["status"].get("nav_state") != 4
                    or state["status"].get("arming_state") != 2 or state["land"].get("landed")):
                raise RuntimeError("Unexpected mode, failsafe, disarm or ground contact during hover")
        event("hover_end", state)
        (output / "perf_hover_end.txt").write_text(cli("perf"))
        checks.observation_completed = True
        landing_lower = topic("vehicle_local_position")["timestamp"]
        cli("commander", "mode", "auto:land")
        checks.planned_landing = True
        checks.begin_landing(hover_start, state["position"]["timestamp"], landing_lower, output)
        event("land_command", state)
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            state = sample("landing")
            if (state["land"].get("landed") and state["status"].get("arming_state") == 1
                    and checks.landing_complete()):
                break
            time.sleep(0.1/speed)
        else:
            raise TimeoutError("Landing/automatic disarm timeout")
        event("landed_disarmed", state)
        if checks is not None:
            checks("disarmed", cli, topic, output)
            checks.collect_landing_tail(topic, output, result["events"])
        # M06 explicitly closes its constant-configuration flight log before
        # disarmed transition checks. "not running" is expected only then.
        (output / "logger_status.txt").write_text(cli("logger", "status",
            check=not getattr(checks, "flight_logger_stopped", False)))
        (output / "params_end.txt").write_text(cli("param", "show", "-a"))
        result["success"] = True
    except Exception as exc:
        result["error"] = repr(exc)
        print(result["error"], flush=True)
    finally:
        if proc.poll() is None:
            if checks is not None:
                try:
                    checks("cleanup", cli, topic, output)
                except Exception as exc:
                    result["cleanup_error"] = repr(exc)
                    result["success"] = False
            try:
                shutdown_owned(proc,cli)
            except Exception as exc:
                result['shutdown_error']=repr(exc)
                result['success']=False
        result["launcher_returncode"] = proc.returncode
        stop.set()
        worker.join(timeout=2)
        link.close()
        console.close()
        command_file.close()
        sample_file.close()
        result["logs"] = []
        try:
            for path in checks.log_paths():
                result["logs"].append(ram_log.archive(path,output/path.name,checks.log_root))
        except Exception as exc:
            result["archive_error"]=repr(exc)
            result["success"]=False
        result["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save(output / "result.json", result)
    if not result["success"]:
        raise SystemExit(1)
    print(f"PASS: {output}", flush=True)


class Checks(historical.Checks):
    """Original live safeguards, with explicit R03 parameter/model provenance."""
    def __init__(self, protocol, expected, job, plugins, qualification_path, source_head, backup):
        super().__init__(protocol, expected, job, plugins)
        self.qualification_path = Path(qualification_path)
        self.source_head = source_head
        self.backup = Path(backup)
        self.frozen = json.loads((Path(protocol['config_dir']) / 'frozen.json').read_text())
        self.execution_permitted = False

    def require_execution(self):
        local_module('protocol').require_execution_authority(self.job['gate'])
        q = local_module('protocol').require_qualification(self.job['gate'], self.source_head, self.qualification_path)
        if q.get('success') is not True or q.get('source_head') != self.source_head or q.get('gate') != self.job['gate']:
            raise RuntimeError('Wrong R03 qualified source/gate')
        return q

    def selection(self, data):
        # Status and selection share these fields; both are checked whenever read.
        for key, value in dict(requested_mode=self.job['mode'], effective_mode=self.job['mode'],
                               requested_axes=self.job['axes'], effective_axes=self.job['axes'], pending=0, reject=0).items():
            if data.get(key) != value:
                raise RuntimeError('R03 requested/effective selection mismatch ' + key)
        if 'div_req' in data:
            for key, value in dict(div_req=1, div_eff=1, div_pending=0, div_reject=0, control_fault=0,
                                   variant_req=self.job['mode'], variant_eff=self.job['mode'], sta_pending=0).items():
                if data.get(key) != value:
                    raise RuntimeError('R03 cadence/variant mismatch ' + key)
            generation = data.get('sta_gen', float('nan'))
            if isinstance(generation, bool) or not isinstance(generation, (int, float)) or not np.isfinite(generation) or generation < 0 or generation != int(generation) or (self.job['mode'] and generation == 0):
                raise RuntimeError('Missing/invalid STA configuration generation')
            if data.get('sta_reject') not in (0, 1) or (self.job['mode'] and data['sta_reject']):
                raise RuntimeError('Missing/rejected STA parameters')

    def configuration(self, cli, topic, output, phase):
        raw = cli('listener', 'velocity_ctrl_selection', '-n', '1')
        selection = scalars(raw)
        # Unlike status callbacks, this is specifically the selection topic;
        # absence of the cadence discriminator must not skip its metadata.
        if 'div_req' not in selection:
            raise RuntimeError('Missing complete velocity selection metadata')
        self.selection(selection)
        for field in ('eps_req', 'eps_eff'):
            values = historical.base.arrays(raw, field)
            if len(values) != 3:
                raise RuntimeError('Missing complete epsilon array ' + field)
            selection[field] = values
        for axis, suffix in enumerate('XYZ'):
            expected = self.expected['MPC_VC_EPS_' + suffix]
            if not np.isfinite(selection['eps_req'][axis]) or abs(selection['eps_req'][axis] - expected) > 1e-7:
                raise RuntimeError('Requested epsilon does not match frozen gate')
            effective = selection['eps_eff'][axis]
            if self.job['mode'] == 3 and self.job['axes'] & (1 << axis):
                if not np.isfinite(effective) or abs(effective - expected) > 1e-7:
                    raise RuntimeError('Effective epsilon does not match frozen gate')
            elif not np.isnan(effective):
                raise RuntimeError('Unused effective epsilon not NaN')
        historical.base.check_inner(topic('sta_rate_ctrl_status'))
        with (output / 'r03_configuration_checks.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(phase=phase, selection=selection)) + '\n')

    def prepare_environment(self, output):
        qualified = self.require_execution()
        authorization = json.loads((self.qualification_path.parent / 'authorization.json').read_text())
        if (authorization.get('approved') is not True or authorization.get('source_head') != self.source_head
                or authorization.get('stage') != self.p['stage'] or authorization.get('maximum_attempts') != 9
                or authorization.get('total_maximum_attempts') != 44
                or authorization.get('new_matrix_attempts') != 36
                or authorization.get('historical_attempts') != 8
                or authorization.get('revision') != 'r03_revision03'
                or authorization.get('historical_budget') != self.p['historical_budget']
                or not local_module('protocol').exact(authorization.get('seed_migration'),self.p['seed_migration'])
                or any(authorization.get(k) is not True for k in ('execution_authorized','flight_authorized','execution_ready'))
                or authorization.get('qualification_sha256') != digest(self.qualification_path)):
            raise RuntimeError('R03 continuous-authorization receipt mismatch')
        save(output / 'authorization.json', authorization)
        save(output / 'qualification.json', qualified)
        qualification_reference(output, self.qualification_path)
        save(output / 'run_protocol.json', self.p)
        (output / 'original_parameters.bson').write_bytes(self.backup.read_bytes())
        self.log_root = ram_log.create()
        save(output / 'ram_log_root.json', dict(path=str(self.log_root), filesystem='tmpfs', owner=os.geteuid(),
            minimum_free_bytes=512*1024**2, volatile_before_archive=True,
            originals_retained_until_durable_archive=True))
        model_dir = output / 'models/iris'; model_dir.mkdir(parents=True)
        original = REPO / 'Tools/sitl_gazebo/models/iris/iris.sdf'
        tree = historical.ET.ElementTree(historical.derive(historical.ET.parse(original).getroot()))
        imu = tree.getroot().find("model/plugin[@name='rotors_gazebo_imu_plugin']")
        if imu is None: raise RuntimeError('Missing original IMU plugin')
        imu.set('filename', str(self.plugins / 'libm10_imu.so'))
        tree.write(model_dir / 'iris.sdf', encoding='utf-8', xml_declaration=True)
        with (model_dir / 'iris.sdf').open('ab') as stream: stream.write(b'\n')
        historical.shutil.copyfile(model_dir / 'iris.sdf', model_dir / 'iris-gen.sdf')
        historical.shutil.copyfile(original.parent / 'model.config', model_dir / 'model.config')
        (model_dir / 'meshes').symlink_to(original.parent / 'meshes', target_is_directory=True)
        historical.verify_model(output, self.plugins)
        if digest(model_dir / 'iris.sdf') != self.frozen['derived_iris_sha256']:
            raise RuntimeError('R03 qualified contact/IMU asset mismatch')
        save(output / 'job.json', self.job)
        save(output / 'model_manifest.json', dict(original=digest(original), derived=digest(model_dir / 'iris.sdf'),
            only_change='Already-qualified compliant contact and original seeded IMU filename',
            seed_scope='IMU only; no independence claim for GPS/barometer/magnetometer/scheduling'))
        return dict(GAZEBO_MODEL_PATH=str(output/'models')+':'+str(REPO/'Tools/sitl_gazebo/models'),
            GAZEBO_PLUGIN_PATH=str(REPO/'build/px4_sitl_default/build_gazebo'), LD_LIBRARY_PATH='',
            M10_IMU_SEED=str(self.job['seed']), M10_IMU_LOG=str(output/'imu_innovations.csv'),
            PX4_SIM_SPEED_FACTOR='1', PX4_SITL_LOG_DIR=str(self.log_root))

    def __call__(self, phase, cli, topic, output):
        if phase == 'preflight':
            self.logs_before = set(self.log_paths())
            if topic('vehicle_status').get('arming_state') != 1:
                raise RuntimeError('R03 must begin disarmed')
            parameters = historical.parse_params(cli('param', 'show', '-a'))
            historical.check_parameters(parameters, self.expected)
            save(output / 'runtime_parameters_start.json', parameters)
            console = (output / 'console.log').read_text()
            if 'Using: ' + str(output/'models/iris/iris.sdf') not in console:
                raise RuntimeError('Qualified Iris was not loaded')
            if 'M10_IMU_SEED_ACCEPTED=' + str(self.job['seed']) not in console:
                raise RuntimeError('Registered seed was not consumed')
            qualified = self.require_execution()
            if digest(BIN / 'px4') != qualified['firmware_sha256']:
                raise RuntimeError('Launcher rebuilt an unqualified binary; no takeoff')
            pid = json.loads((output / 'result.json').read_text())['launcher_pid']
            world = REPO / 'sitl/worlds/empty_grey.world'
            evidence = historical.snapshot(pid, world)
            save(output / 'world_process.json', evidence)
            historical.validate_world(evidence['servers'], pid, evidence['launcher_sid'], world, 'http://127.0.0.1:11345')
            if evidence['world_sha256'] != self.frozen['assets'][str(world.relative_to(REPO))]:
                raise RuntimeError('Qualified world changed')
            (output/'uorb_start.txt').write_text(cli('uorb', 'status'))
            historical.restart_logger(cli)
        else:
            historical.base.Checks.__call__(self, phase, cli, topic, output)
        if phase in ('preflight', 'hover', 'disarmed'):
            self.configuration(cli, topic, output, phase)


def execution_checks_class():
    """Opt-in private class; importing this runner never changes old globals."""
    path = HERE.parent/'r03_monitor02/integration.py'
    spec = importlib.util.spec_from_file_location('_r03_revision03_monitor_integration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.make_checks(Checks)


def append_event(path, record):
    """Durable append-only audit; mutable ledger.json is merely its summary."""
    with Path(path).open('a') as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        stream.flush(); os.fsync(stream.fileno())


class Admission:
    def __init__(self, protocol, compare):
        self.jobs = protocol['jobs']; self.compare = compare
        required = dict(maximum_attempts=9, total_maximum_attempts=44,
                        historical_attempts=8, new_matrix_attempts=36)
        if (len(self.jobs) != 9 or protocol.get('revision') != 'r03_revision03'
                or any(type(protocol.get(k)) is not int or protocol[k] != v for k, v in required.items())
                or any(j.get('revision') != 'r03_revision03' for j in self.jobs)):
            raise RuntimeError('R03 revision03 exactly nine new attempts per gate, 36 new plus eight retained')
        if self.jobs[0]['mode'] != 0:
            raise RuntimeError('First PID is the budgeted safety gate')
        if len({j['id'] for j in self.jobs}) != 9 or len({j['seed'] for j in self.jobs}) != 3:
            raise RuntimeError('Duplicate job or wrong paired-seed count')
        for seed in {j['seed'] for j in self.jobs}:
            if sorted(j['mode'] for j in self.jobs if j['seed'] == seed) != [0, 1, 3]:
                raise RuntimeError('Each seed needs exactly PID/ESTA/RSTA')
        self.accepted = []; self.by_seed = {}; self.checked = set(); self.failed = False; self.last_pairs = []

    def before(self, job):
        if self.failed or len(self.accepted) >= 9 or self.jobs[len(self.accepted)] != job:
            raise RuntimeError('Failed/exhausted/out-of-order gate; no retry')
        self.last_pairs = []

    def accept(self, job, metrics):
        self.before(job)
        if metrics.get('accepted') is not True or metrics.get('job') != job:
            self.failed = True; raise RuntimeError('Required flight/log validity failed')
        block = self.by_seed.setdefault(job['seed'], {})
        block[job['mode']] = metrics
        if 0 in block:
            for mode in (1, 3):
                identity = (job['seed'], mode)
                if mode in block and identity not in self.checked:
                    pair = self.compare(block[0], block[mode]); self.last_pairs.append(pair)
                    if pair.get('accepted') is not True:
                        self.failed = True; raise RuntimeError('Frozen paired development-risk threshold failed')
                    self.checked.add(identity)
        self.accepted.append(job)
        return self.last_pairs


def retained_budget(protocol, api):
    """Read-only exact binding: all eight historical attempts stay consumed."""
    retained = api.retained_failure()
    actual = json.dumps(retained, sort_keys=True, separators=(',', ':'), allow_nan=False)
    expected = json.dumps(protocol.get('historical_budget'), sort_keys=True, separators=(',', ':'), allow_nan=False)
    if actual != expected:
        raise RuntimeError('Retained historical failure binding changed')
    counts = dict(attempts=8, accepted=6, failed=2, accepted_for_new_matrix=0)
    if any(type(retained.get(key)) is not int or retained[key] != value for key,value in counts.items()):
        raise RuntimeError('All eight historical attempts, six accepted and two failed must remain separate')
    return retained


def verify_prior_budget(root, gate, api, protocol):
    """All old/new attempts count; unknown, partial or replacement batches fail."""
    retained_budget(protocol, api)
    if gate not in 'ABCD' or len(gate) != 1:
        raise RuntimeError('Unknown budget gate')
    root = Path(root).resolve()
    expected_gates = list('ABCD')[:list('ABCD').index(gate)]
    expected_paths = {str((root/g/'batch01/ledger.json').resolve()) for g in expected_gates}
    actual_paths = {str(path.resolve()) for path in root.glob('*/batch*/ledger.json')}
    batch_dirs = {str(path.resolve()) for path in root.glob('*/batch*') if path.is_dir()}
    expected_dirs = {str(Path(path).parent) for path in expected_paths}
    if actual_paths != expected_paths or batch_dirs != expected_dirs:
        raise RuntimeError('Unknown, missing, duplicate or replacement revision03 batch')
    attempts = 8
    for name in expected_gates:
        path = root/name/'batch01/ledger.json'
        ledger = json.loads(path.read_text())
        previous = api.load_protocol(name)
        required = dict(stage='R03-revision03-'+name, gate=name, revision='r03_revision03',
            planned=9, total_budget=44, retained_invalid_attempts=2, retained_accepted_attempts=6, retained_attempts=8, new_planned=36,
            prior_attempts=attempts, success=True, parameter_restore_exact=True,
            remaining_simulators=[], historical_budget=protocol['historical_budget'])
        # Strict JSON preserves the distinction among true, 1 and 1.0.
        for key, value in required.items():
            if json.dumps(ledger.get(key), sort_keys=True, allow_nan=False) != json.dumps(value, sort_keys=True, allow_nan=False):
                raise RuntimeError('Previous revision03 gate failed/incomplete: ' + key)
        records = ledger.get('attempts', [])
        if len(records) != 9 or any(item.get('status') != 'accepted' for item in records):
            raise RuntimeError('Previous revision03 gate needs exactly nine accepted attempts')
        recorded = [item.get('job') for item in records]
        if json.dumps(recorded, sort_keys=True, allow_nan=False) != json.dumps(previous['jobs'], sort_keys=True, allow_nan=False):
            raise RuntimeError('Previous revision03 jobs/order changed')
        attempts += len(records)
    if attempts + 9 > 44:
        raise RuntimeError('R03 44-attempt total budget would be exceeded')
    return attempts


def restore_parameters(param, original, run, backup, source_head, job):
    remaining = active_simulators(); stopped = not remaining
    if stopped: param.write_bytes(original)
    actual = param.read_bytes()
    record = dict(source_head=source_head, gate=job['gate'], job_id=job['id'],
        original_parameter_sha256=hashlib.sha256(original).hexdigest(),
        restored_parameter_sha256=hashlib.sha256(actual).hexdigest(),
        parameter_restore_exact=actual == original, remaining_simulators=remaining,
        backup_path=str(backup), stopped_before_restore=stopped)
    target = run/'parameter_restore.json' if run.is_dir() else run.parent/(job['id']+'_parameter_restore.json')
    save(target, record)
    if not stopped or not record['parameter_restore_exact']:
        raise RuntimeError('Unsafe/inexact full parameter restoration; backup retained')
    return record


def execute_gate(protocol, source_head, qualification_path, *, single_flight=flight_main, analyze=None, compare=None):
    """Serialize qualified batches, including separate gates, before mutation."""
    api = local_module('protocol')
    api.require_execution_authority(protocol['gate'])
    canonical = api.load_protocol(protocol['gate'])
    # The CLI uses this same canonical document. Programmatic callers receive
    # no extra authority to alter jobs, gains, order, output roots or budgets.
    bound_path = str(Path(qualification_path).resolve())
    try:
        actual_json = json.dumps({**protocol, 'qualification_path': bound_path},
                                 sort_keys=True, separators=(',', ':'), allow_nan=False)
        expected_json = json.dumps({**canonical, 'qualification_path': bound_path},
                                   sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RuntimeError('Invalid noncanonical JSON protocol') from exc
    if actual_json != expected_json:
        raise RuntimeError('Caller protocol differs from frozen canonical gate')
    retained_budget(protocol, api)
    api.require_qualification(protocol['gate'], source_head, Path(qualification_path))
    root = Path(protocol['artifacts']['new_run_root']).resolve().parent.parent
    root.mkdir(parents=True, exist_ok=True)
    # Share the historical R03 process lock too: a different revision cannot
    # concurrently mutate the same SITL EEPROM or own the same ports.
    historical_locks = [Path(batch['root']) / '.runner.lock' for batch in protocol['historical_budget']['batches']]
    with ExitStack() as locks:
        for path in (*historical_locks, root / '.runner.lock'):
            lock = locks.enter_context(path.open('a'))
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError('Another R03 gate owns the runner lock') from exc
        return _execute_gate(protocol, source_head, qualification_path,
                             single_flight=single_flight, analyze=analyze, compare=compare)


def _execute_gate(protocol, source_head, qualification_path, *, single_flight=flight_main, analyze=None, compare=None):
    """Exact, one-shot gate loop. Tests replace only external process/I/O edges."""
    api = local_module('protocol'); gate = protocol['gate']
    api.require_execution_authority(gate)
    qualification_path = Path(qualification_path)
    qualified = api.require_qualification(gate, source_head, qualification_path)
    # A second offline qualification is a different immutable receipt; do not
    # silently analyze against the default first (possibly failed) attempt.
    protocol = {**protocol, 'qualification_path': str(qualification_path.resolve())}
    analysis = local_module('analyzer') if analyze is None or compare is None else None
    analyze = analyze or analysis.analyze; compare = compare or analysis.compare
    admission = Admission(protocol, compare)
    output = Path(protocol['artifacts']['new_run_root']).resolve()
    if output.exists(): raise RuntimeError('R03 output already exists; no overwrite/resume/retry')
    if historical.git('branch', '--show-current') != 'research/sta-velocity-regularized' or historical.git('rev-parse', 'HEAD') != source_head:
        raise RuntimeError('Wrong R03 branch/source')
    if historical.git('status', '--porcelain') or historical.git('submodule', 'foreach', '--recursive', '--quiet', 'git status --porcelain'):
        raise RuntimeError('Dirty main/submodule worktree')
    if any(s[:1] in ('+', '-', 'U') for s in historical.git('submodule', 'status', '--recursive').splitlines()):
        raise RuntimeError('Recursive submodule mismatch')
    if active_simulators(): raise RuntimeError('Conflicting simulator; no process started')
    if historical.shutil.disk_usage(ROOTFS).free < 12*1024**3:
        raise RuntimeError('Insufficient gate archive/replay capacity plus system reserve (12 GiB)')
    if (ROOTFS/'etc/logging/logger_topics.txt').exists(): raise RuntimeError('Custom logging override')
    if any((REPO/'Tools/sitl_gazebo/models/iris').glob('*-gen.sdf')): raise RuntimeError('Unexpected model override')
    for port in (14550, 11345):
        with historical.socket.socket(historical.socket.AF_INET,
             historical.socket.SOCK_DGRAM if port == 14550 else historical.socket.SOCK_STREAM) as sock:
            sock.bind(('127.0.0.1', port))
    frozen = json.loads((Path(protocol['config_dir'])/'frozen.json').read_text())
    for rel, value in frozen['assets'].items():
        if digest(REPO/rel) != value: raise RuntimeError('Frozen source/asset changed: ' + rel)
    for name, value in frozen.get('external_assets', {}).items():
        if digest(Path(name)) != value: raise RuntimeError('Frozen external dependency changed: ' + name)
    historical.require_passive(REPO/'research/sta-velocity-control/v06/soft_landing/offline03/evidence.json')
    historical.require_qualification(REPO/'research/sta-velocity-control/v06/soft_landing/qualified_contact.json')
    historical.validate_receiver_profile()
    plugins = Path(protocol['plugins'])
    for name, value in json.loads((plugins/'manifest.json').read_text()).items():
        if digest(Path(name)) != value: raise RuntimeError('Plugin changed: ' + name)
    seed_audit = api.fresh_seeds(gate)
    if not seed_audit.get('accepted'): raise RuntimeError('Seed history check failed')
    previous_attempts = verify_prior_budget(output.parent.parent, gate, api, protocol)
    if source_head not in (REPO/'build/px4_sitl_default/src/lib/version/build_git_version.h').read_text():
        raise RuntimeError('Firmware not built at this clean source')
    if digest(BIN/'px4') != qualified['firmware_sha256']: raise RuntimeError('Wrong qualified firmware')
    param = ROOTFS/'eeprom/parameters_10016'; original = param.read_bytes()
    values = historical.persisted_bson(original)
    definitions = json.loads((REPO/'build/px4_sitl_default/parameters.json').read_text())['parameters']
    defaults = {p['name']: p['default'] for p in definitions}; types = {p['name']: p['type'] for p in definitions}
    historical.check_parameters({**defaults, **values}, frozen['control_parameters'])
    profile = int(values.get('SDLOG_PROFILE', defaults.get('SDLOG_PROFILE', 131))) | 16 | 1024
    output.mkdir(parents=True, exist_ok=False)
    backup = output/'original_parameters.bson'; backup.write_bytes(original)
    with backup.open('rb') as stream: os.fsync(stream.fileno())
    save(output/'seed_audit_before_launch.json', seed_audit)
    save(output/'qualification.json', qualified)
    qualification_reference(output, qualification_path)
    save(output/'protocol.json', protocol)
    authorization = json.loads((qualification_path.parent/'authorization.json').read_text())
    save(output/'authorization.json', authorization)
    ledger = dict(stage=protocol['stage'], gate=gate, revision='r03_revision03',
        source_head=source_head, planned=9, total_budget=44, retained_invalid_attempts=2, retained_accepted_attempts=6, retained_attempts=8,
        new_planned=36, historical_budget=protocol['historical_budget'],seed_migration=protocol['seed_migration'],
        prior_attempts=previous_attempts, attempts=[], pairs=[], success=False,
        firmware_sha256=qualified['firmware_sha256'], original_parameter_sha256=digest(backup),
        original_parameter_backup=str(backup), applied_profile=profile)
    journal = output/'journal.jsonl'; save(output/'ledger.json', ledger)
    prefixes = {}
    try:
        for index, job in enumerate(protocol['jobs'], 1):
            admission.before(job)
            retained_budget(protocol, api)
            api.require_qualification(gate, source_head, qualification_path)
            if active_simulators() or historical.git('status', '--porcelain') or historical.git('rev-parse', 'HEAD') != source_head:
                raise RuntimeError('Source/process changed before attempt')
            resources = dict(disk_free_bytes=historical.shutil.disk_usage(ROOTFS).free,
                             tmpfs_free_bytes=historical.shutil.disk_usage('/dev/shm').free)
            if resources['disk_free_bytes'] < 10*1024**3 or resources['tmpfs_free_bytes'] < 512*1024**2:
                raise RuntimeError('Insufficient per-attempt disk/tmpfs reserve; no launch')
            if param.read_bytes() != original: raise RuntimeError('Previous parameters were not restored')
            run = output/job['id']
            item = dict(attempt=index, job=job, directory=str(run), status='running', resource_capacity=resources)
            ledger['attempts'].append(item); append_event(journal, dict(event='attempt', **item)); save(output/'ledger.json', ledger)
            try:
                p = {**protocol, 'startup_overrides': {**protocol['startup_overrides'], **job['parameters']}}
                applied = {**values, **p['startup_overrides'], 'SDLOG_PROFILE': profile}
                param.write_bytes(historical.encode_bson(applied, types))
                expected = {**frozen['control_parameters'], **p['startup_overrides'], 'SYS_AUTOSTART': 10016, 'SDLOG_PROFILE': profile}
                checks = execution_checks_class()(p, expected, job, plugins, qualification_path, source_head, backup)
                checks.execution_permitted = True; checks.pid_parameters_modified = True
                try:
                    single_flight(run, checks, Path(protocol['execution_path']))
                finally:
                    restored = restore_parameters(param, original, run, backup, source_head, job)
                    append_event(journal, dict(event='restore', **restored))
                ram_log.release_archived(run, checks.log_root)
                if digest(BIN/'px4') != qualified['firmware_sha256']:
                    raise RuntimeError('Qualified firmware changed during attempt')
                metrics = analyze(run, p, job)
                if metrics.get('accepted') is not True: raise RuntimeError('Full ULog acceptance failed')
                item['metrics_sha256'] = digest(run/'r03_metrics.json')
                prefix = historical.noise_prefix(run)
                for seed, other in prefixes.items():
                    difference = float(np.max(np.abs(prefix-other)))
                    if seed == job['seed'] and difference >= 1e-10: raise RuntimeError('Paired IMU innovations differ')
                    if seed != job['seed'] and difference <= 1e-6: raise RuntimeError('Distinct registered seeds not distinct')
                prefixes[job['seed']] = prefix
                pairs = admission.accept(job, metrics); ledger['pairs'].extend(pairs)
                save(run/'paired_checks.json', pairs)
                item['status'] = 'accepted'
                append_event(journal, dict(event='accepted', job_id=job['id'], metrics_sha256=item['metrics_sha256'], pairs=pairs))
                print(json.dumps(dict(attempt=index, planned=9, gate=gate, mode=job['mode'], seed=job['seed'], status='accepted')), flush=True)
            except BaseException as exc:
                admission.failed = True
                item.update(status='failed', error=repr(exc))
                save(output/(job['id']+'_paired_checks_at_stop.json'), admission.last_pairs)
                append_event(journal, dict(event='failed', job_id=job['id'], error=repr(exc)))
                raise
            finally:
                if not active_simulators() and param.read_bytes() != original: param.write_bytes(original)
                save(output/'ledger.json', ledger)
        ledger['success'] = len(admission.accepted) == 9 and len(admission.checked) == 6
    finally:
        if not active_simulators(): param.write_bytes(original)
        ledger['parameter_restore_exact'] = param.read_bytes() == original
        ledger['remaining_simulators'] = active_simulators()
        ledger['unattempted'] = [j['id'] for j in protocol['jobs'][len(ledger['attempts']):]]
        append_event(journal, dict(event='gate_end', success=ledger['success'], parameter_restore_exact=ledger['parameter_restore_exact'],
                                  attempts=len(ledger['attempts']), remaining_simulators=ledger['remaining_simulators']))
        save(output/'ledger.json', ledger)
    if not ledger['success'] or not ledger['parameter_restore_exact'] or ledger['remaining_simulators']:
        raise RuntimeError('R03 gate/cleanup not complete')
    return ledger


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate', choices=list('ABCD'), default='A')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--source-head', default='')
    parser.add_argument('--qualification', type=Path)
    args = parser.parse_args(argv)
    api = local_module('protocol'); api.validate_manifest()
    protocol = api.load_protocol(args.gate)
    print(json.dumps(dict(stage=protocol['stage'], planned=len(protocol['jobs']), total_budget=44,
        status=protocol['status'],**{k:protocol[k] for k in ('execution_authorized','flight_authorized','execution_ready')},
        retained_invalid_attempts=2, retained_accepted_attempts=6, retained_attempts=8, new_planned=36, revision='r03_revision03',
        execution_path=protocol['execution_path'],
        jobs=[{k:j[k] for k in ('id','task','seed','candidate','mode','axes','divisor','main_duration_s')}
              for j in protocol['jobs']]), indent=2), flush=True)
    if not args.execute:
        print('DRY RUN: no files, parameters, simulator processes or flights changed.')
        return 0
    if not args.source_head: raise RuntimeError('Explicit qualified source SHA required')
    path = args.qualification or Path(protocol['qualification_path'])
    execute_gate(protocol, args.source_head, path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
