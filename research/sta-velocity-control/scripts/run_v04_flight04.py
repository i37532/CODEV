#!/usr/bin/env python3
"""Protocol04 isolated height-target flight; original project SITL launcher.

Use local-only MAVLink GCS heartbeats; commands use the local PX4 instance-0
client binaries. Refuse to start if another simulator/flight process is active.
All time windows are measured in PX4 simulation time, with wall-time timeouts.
"""
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

from pymavlink import mavutil
from v04_task04 import (scalars, current_triplet, freeze_reference, command_params,
                       check_readback, accepted_ack, entry_ok, EntryGate)

REPO = Path(__file__).resolve().parents[3]
BIN = REPO / "build/px4_sitl_default/bin"
ROOTFS = REPO / "build/px4_sitl_default/tmp/rootfs"


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def main(checks=None, scenario_path=None):
    if checks is None or not getattr(checks, "execution_permitted", False):
        raise RuntimeError("Batch authorization required before any process or file mutation")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    # Opt-in M10 only; prior milestones retain exactly the original timing.
    speed = float(getattr(checks, 'simulation_speed', 1))
    if not 1 <= speed <= 10:
        raise ValueError('Simulation speed must be within [1,10]')
    if active_simulators():
        raise RuntimeError(f"Refusing conflicting instances: {active_simulators()}")
    output.mkdir(parents=True, exist_ok=False)
    old_logs = set(ROOTFS.glob("log/**/*.ulg"))
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

    def cli(module, *arguments, check=True):
        cmd = [str(BIN / ("px4-" + module)), *map(str, arguments)]
        proc = subprocess.run(cmd, cwd=ROOTFS, text=True, capture_output=True, timeout=10)
        command_file.write(json.dumps({"cmd": cmd, "returncode": proc.returncode,
                                       "stdout": proc.stdout, "stderr": proc.stderr}) + "\n")
        command_file.flush()
        if check and proc.returncode:
            raise RuntimeError(f"CLI failed: {module} {arguments}: {proc.stdout} {proc.stderr}")
        return proc.stdout

    def topic(name):
        raw = cli("listener", name, "-n", "1")
        return scalars(raw)

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
        result["explicit_environment"] = {k: env[k] for k in ("PX4_SITL_WORLD", "GAZEBO_MASTER_URI")}
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
        sent = None
        before = None
        ack = None
        readback = False
        candidates = []
        while time.monotonic() < deadline:
            state = sample("takeoff")
            p, status = state["position"], state["status"]
            if status.get("failsafe"):
                raise RuntimeError("Failsafe during takeoff")
            if (status.get("nav_state") == 2 and status.get("arming_state") == 2
                    and not state["land"].get("landed", True) and sent is None and checks.task_yaw_ready):
                state['position'] = topic('vehicle_local_position')
                p = state['position']
                raw = cli("listener", "position_setpoint_triplet", "-n", "1")
                (output / "triplet_before.txt").write_text(raw)
                before = current_triplet(raw)
                sent = time.monotonic()
                save(output / "reposition_command.json", dict(sent_monotonic=sent,
                     parameters=command_params(ref), timestamp_us=p["timestamp"],
                     target_system=1, target_component=1, command=192, confirmation=0, maximum_sends=1))
                with wire_lock:
                    link.mav.command_long_send(1, 1, 192, 0, *command_params(ref))
                event("reposition_command", state)
            if sent is not None:
                fresh = [r for r in acknowledgements if r["received_monotonic"] >= sent
                         and r["system"] == 1 and r["component"] == 1
                         and r["message"].get("command") == 192]
                if fresh:
                    if not accepted_ack(fresh[0], sent): raise RuntimeError("Reposition rejected")
                    ack = fresh[0]
                    save(output / "reposition_ack.json", ack)
                if ack is None and time.monotonic()-sent > 5:
                    raise TimeoutError("Reposition ACK timeout; no retry")
                if status.get("nav_state") == 4 and ack is not None:
                    raw = cli("listener", "position_setpoint_triplet", "-n", "1")
                    (output / "triplet_after.txt").write_text(raw)
                    check_readback(before, current_triplet(raw), ref)
                    readback = True
            target = topic("trajectory_setpoint")
            diagnostic = checks.latest_diagnostic
            valid = readback and entry_ok(p, status, state["land"], target, ref)
            candidates.append(dict(position=p, status=status, land=state["land"],
                                   target=target, diagnostic=diagnostic, valid=bool(valid)))
            save(output / "entry_candidates.json", candidates)
            if gate.update(p["timestamp_sample"], valid, diagnostic):
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
        while state["position"]["timestamp"] - hover_start < 60e6:
            if time.monotonic() > deadline:
                raise TimeoutError("60 s simulation hover wall timeout")
            time.sleep(0.5/speed)
            state = sample("hover")
            if (state["status"].get("failsafe") or state["status"].get("nav_state") != 4
                    or state["status"].get("arming_state") != 2 or state["land"].get("landed")):
                raise RuntimeError("Unexpected mode, failsafe, disarm or ground contact during hover")
        event("hover_end", state)
        (output / "perf_hover_end.txt").write_text(cli("perf"))
        checks.observation_completed = True
        cli("commander", "mode", "auto:land")
        checks.planned_landing = True
        event("land_command", state)
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            state = sample("landing")
            if state["land"].get("landed") and state["status"].get("arming_state") == 1:
                break
            time.sleep(0.5/speed)
        else:
            raise TimeoutError("Landing/automatic disarm timeout")
        event("landed_disarmed", state)
        if checks is not None:
            checks("disarmed", cli, topic, output)
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
        for path in sorted(set(ROOTFS.glob("log/**/*.ulg")) - old_logs):
            dest = output / path.name
            dest.write_bytes(path.read_bytes())
            result["logs"].append({"source": str(path), "archive": str(dest),
                                   "sha256": digest(dest), "bytes": dest.stat().st_size})
        result["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save(output / "result.json", result)
    if not result["success"]:
        raise SystemExit(1)
    print(f"PASS: {output}", flush=True)


if __name__ == "__main__":
    main()
