#!/usr/bin/env python3
"""Run one unchanged-PID Iris baseline through the repository SITL launcher.

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
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
        "pid_parameters_modified": False,
        "success": False,
        "events": [],
    }
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

    def receiver():
        last_heartbeat = 0
        last_manual = 0
        with (output / "mavlink_events.jsonl").open("w") as stream:
            while not stop.is_set():
                msg = link.recv_match(blocking=True, timeout=0.1)
                if msg:
                    if msg.get_type() in ("HEARTBEAT", "STATUSTEXT", "EXTENDED_SYS_STATE"):
                        stream.write(json.dumps(msg.to_dict()) + "\n")
                        stream.flush()
                    telemetry[msg.get_type()] = msg
                if time.monotonic() - last_heartbeat > 0.5 and telemetry:
                    link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                                            mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                                            0, 0, mavutil.mavlink.MAV_STATE_ACTIVE)
                    last_heartbeat = time.monotonic()
                # Emulate a connected RC transmitter at neutral sticks. This
                # satisfies the existing RC-loss policy during AUTO_LOITER.
                # It does not publish attitude/rate/offboard setpoints.
                if time.monotonic() - last_manual > 0.1 and telemetry:
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
        data = {}
        for line in raw.splitlines():
            match = re.match(r"\s+(\w+):\s+([^\s]+)", line)
            if match:
                key, value = match.groups()
                if value in ("True", "False"):
                    data[key] = value == "True"
                else:
                    try:
                        data[key] = float(value)
                    except ValueError:
                        pass
        return data

    def sample(phase):
        state = {"phase": phase, "position": topic("vehicle_local_position"),
                 "status": topic("vehicle_status"), "land": topic("vehicle_land_detected")}
        sample_file.write(json.dumps(state) + "\n")
        sample_file.flush()
        return state

    def event(name, state):
        entry = {"name": name, "timestamp_us": state["position"]["timestamp"]}
        result["events"].append(entry)
        save(output / "result.json", result)
        print(json.dumps(entry), flush=True)

    env = os.environ.copy()
    env.pop("DONT_RUN", None)
    env.pop("NO_PXH", None)
    env.pop("PX4_SIM_SPEED_FACTOR", None)
    env["PX4_SITL_WORLD"] = str(REPO / "sitl/worlds/empty_grey.world")
    env["GAZEBO_MASTER_URI"] = "http://127.0.0.1:11345"
    result["explicit_environment"] = {k: env[k] for k in ("PX4_SITL_WORLD", "GAZEBO_MASTER_URI")}
    console = (output / "console.log").open("w")
    proc = subprocess.Popen(result["command"], cwd=REPO, env=env,
                            stdin=subprocess.PIPE, stdout=console, stderr=subprocess.STDOUT,
                            start_new_session=True)
    result["launcher_pid"] = proc.pid
    save(output / "result.json", result)
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
        (output / "params_all.txt").write_text(cli("param", "show", "-a"))
        cli("param", "save", str(output / "parameters.bson"))
        (output / "version.txt").write_text(cli("ver", "all"))
        (output / "mavlink_status.txt").write_text(cli("mavlink", "status"))
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            state = sample("warmup")
            p = state["position"]
            if p.get("timestamp", 0) > 30e6 and p.get("xy_global") and p.get("z_valid") and telemetry:
                break
            time.sleep(1)
        else:
            raise TimeoutError("Global estimator readiness timeout")
        event("ready", state)
        ground_z = state["position"]["z"]
        cli("commander", "takeoff")
        event("takeoff_command", state)
        deadline = time.monotonic() + 150
        stable_since = None
        hold_requested = False
        while time.monotonic() < deadline:
            state = sample("takeoff")
            p, s = state["position"], state["status"]
            if s.get("failsafe"):
                raise RuntimeError("Failsafe during takeoff")
            # This CODEV baseline intentionally finishes takeoff in POSCTL
            # (Commander.cpp), not AUTO_LOITER. Request Hold explicitly once.
            if s.get("nav_state") == 2 and s.get("arming_state") == 2 and not hold_requested:
                cli("commander", "mode", "auto:loiter")
                event("hold_command_after_takeoff", state)
                hold_requested = True
            stable = (s.get("nav_state") == 4 and s.get("arming_state") == 2
                      and not s.get("failsafe") and ground_z - p.get("z", ground_z) > 1.0
                      and abs(p.get("vz", 99)) < 0.2 and not state["land"].get("landed", True))
            if stable:
                stable_since = stable_since or p["timestamp"]
                if p["timestamp"] - stable_since >= 3e6:
                    break
            else:
                stable_since = None
            time.sleep(0.5)
        else:
            raise TimeoutError("Takeoff did not reach stable AUTO_LOITER")
        event("hover_start", state)
        (output / "perf_hover_start.txt").write_text(cli("perf"))
        hover_start = state["position"]["timestamp"]
        deadline = time.monotonic() + 240
        while state["position"]["timestamp"] - hover_start < 60e6:
            if time.monotonic() > deadline:
                raise TimeoutError("60 s simulation hover wall timeout")
            time.sleep(0.5)
            state = sample("hover")
            if (state["status"].get("failsafe") or state["status"].get("nav_state") != 4
                    or state["status"].get("arming_state") != 2 or state["land"].get("landed")):
                raise RuntimeError("Unexpected mode, failsafe, disarm or ground contact during hover")
        event("hover_end", state)
        (output / "perf_hover_end.txt").write_text(cli("perf"))
        cli("commander", "mode", "auto:land")
        event("land_command", state)
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            state = sample("landing")
            if state["land"].get("landed") and state["status"].get("arming_state") == 1:
                break
            time.sleep(0.5)
        else:
            raise TimeoutError("Landing/automatic disarm timeout")
        event("landed_disarmed", state)
        (output / "logger_status.txt").write_text(cli("logger", "status"))
        (output / "params_end.txt").write_text(cli("param", "show", "-a"))
        result["success"] = True
    except Exception as exc:
        result["error"] = repr(exc)
        print(result["error"], flush=True)
    finally:
        if proc.poll() is None:
            try:
                cli("shutdown", check=False)
                proc.wait(timeout=15)
            except (subprocess.TimeoutExpired, RuntimeError):
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=15)
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
