#!/usr/bin/env python3
"""Derive baseline hover metrics from the archived ULog, not console samples."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import numpy as np
from pyulog import ULog


def plain(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def analyze(run, log_index=None):
    result = json.loads((run / "result.json").read_text())
    if not result["success"] or (log_index is None and len(result["logs"]) != 1):
        raise ValueError("Run must pass and have exactly one ULog")
    selected_log = result["logs"][0 if log_index is None else log_index]
    path = Path(selected_log["archive"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != selected_log["sha256"]:
        raise ValueError("ULog checksum mismatch")
    log = ULog(str(path))
    events = {entry["name"]: entry["timestamp_us"] for entry in result["events"]}
    start, end = events["hover_start"], events["hover_end"]
    if end - start < 60e6:
        raise ValueError("Hover shorter than 60 s")

    def topic(name):
        return log.get_dataset(name, 0).data

    def window(data, a=start, b=end):
        t = data["timestamp"]
        return (t >= a) & (t <= b)

    def vectors(data, keys):
        return np.column_stack([data[key] for key in keys])

    def hold(data, times, keys):
        indices = np.searchsorted(data["timestamp"], times, side="right") - 1
        if np.any(indices < 0):
            raise ValueError("No prior setpoint for alignment")
        return vectors(data, keys)[indices]

    def stats(values):
        if not np.all(np.isfinite(values)):
            raise ValueError("Nonfinite samples in metric input")
        return {"rmse": np.sqrt(np.mean(values**2, axis=0)),
                "mean": np.mean(values, axis=0),
                "std": np.std(values, axis=0),
                "max_abs": np.max(np.abs(values), axis=0)}

    def rate(data):
        t = data["timestamp"][window(data)].astype(np.float64) * 1e-6
        dt = np.diff(t)
        return {"count": len(t), "logged_hz": (len(t)-1)/(t[-1]-t[0]),
                "logged_dt_min_s": dt.min(), "logged_dt_max_s": dt.max(),
                "logged_dt_mean_s": dt.mean(), "logged_dt_std_s": dt.std()}

    rates = topic("vehicle_angular_velocity")
    mask = window(rates)
    t = rates["timestamp"][mask]
    r = vectors(rates, ["xyz[0]", "xyz[1]", "xyz[2]"])[mask]
    rsp = hold(topic("vehicle_rates_setpoint"), t, ["roll", "pitch", "yaw"])
    pos = topic("vehicle_local_position")
    pm = window(pos)
    p = vectors(pos, ["x", "y", "z"])[pm]
    psp = hold(topic("vehicle_local_position_setpoint"), pos["timestamp"][pm], ["x", "y", "z"])
    att = topic("vehicle_attitude")
    q = vectors(att, ["q[0]", "q[1]", "q[2]", "q[3]"])[window(att)]
    tilt = np.rad2deg(np.arccos(np.clip(1 - 2*(q[:, 1]**2+q[:, 2]**2), -1, 1)))
    yaw = np.arctan2(2*(q[:, 0]*q[:, 3]+q[:, 1]*q[:, 2]),
                     1-2*(q[:, 2]**2+q[:, 3]**2))
    yaw_drift = np.rad2deg(np.unwrap(yaw)-np.unwrap(yaw)[0])
    act = topic("actuator_controls_0")
    controls = vectors(act, [f"control[{i}]" for i in range(4)])[window(act)]
    status = topic("vehicle_status")
    sm = window(status)
    land = topic("vehicle_land_detected")
    lm = window(land)
    # Cross-check the available ULog state history, not only runner polling.
    checks = {
        "hover_60s": end-start >= 60e6,
        "hover_auto_loiter_only": bool(np.all(status["nav_state"][sm] == 4)),
        "hover_armed": bool(np.all(status["arming_state"][sm] == 2)),
        "hover_no_failsafe": not bool(np.any(status["failsafe"][sm])),
        "hover_not_landed": not bool(np.any(land["landed"][lm])),
        "logged_landed_disarmed": bool(status["arming_state"][-1] == 1 and land["landed"][-1]),
    }
    flight = window(status, events["takeoff_command"], events["landed_disarmed"])
    flight_armed = flight & (status["arming_state"] == 2)
    checks["armed_flight_no_failsafe"] = not bool(np.any(status["failsafe"][flight_armed]))
    checks["armed_flight_no_failure_detector"] = not bool(np.any(
        status["failure_detector_status"][flight_armed]))
    checks["hover_controls_finite"] = bool(np.all(np.isfinite(controls)))
    # On-change topics may have no sample inside the window: include last prior.
    for key, field, required in (("hover_auto_loiter_only", "nav_state", 4),
                                 ("hover_armed", "arming_state", 2),
                                 ("hover_no_failsafe", "failsafe", 0)):
        initial = hold(status, np.array([start]), [field])[0, 0]
        checks[key] = checks[key] and initial == required
    checks["hover_not_landed"] = checks["hover_not_landed"] and not hold(
        land, np.array([start]), ["landed"])[0, 0]
    if not all(checks.values()):
        raise ValueError(f"ULog acceptance failed: {checks}")
    output = {
        "run": run.name,
        "ulog_sha256": selected_log["sha256"],
        "hover_start_us": start, "hover_end_us": end,
        "hover_duration_s": (end-start)*1e-6,
        "acceptance": {key: bool(value) for key, value in checks.items()},
        "rate_error_rad_s": stats(rsp-r),
        "position_error_m": stats(psp-p),
        "position_displacement_from_hover_start_m": stats(p-p[0]),
        "tilt_deg": stats(tilt),
        "yaw_drift_from_hover_start_deg": stats(yaw_drift),
        "control_roll_pitch_yaw_throttle": {
            "rms": np.sqrt(np.mean(controls**2, axis=0)),
            "min": controls.min(axis=0), "max": controls.max(axis=0),
            "logged_sample_tv_not_full_rate": np.abs(np.diff(controls, axis=0)).sum(axis=0)},
        "logged_rates": {name: rate(topic(name)) for name in (
            "vehicle_angular_velocity", "vehicle_rates_setpoint", "actuator_controls_0",
            "vehicle_local_position", "vehicle_attitude")},
        "ulog_reported_dropout_count": len(log.dropouts),
        "ulog_reported_dropout_total_ms": sum(d.duration for d in log.dropouts),
        "dropout_note": "Absence of logger dropouts does not prove full-rate uORB capture.",
        "parameter_changes_count": len(log.changed_parameters),
    }
    ground_mask = window(rates, 20e6, events["takeoff_command"])
    if np.count_nonzero(ground_mask) > 10:
        output["stationary_filtered_gyro_std_rad_s"] = np.std(
            vectors(rates, ["xyz[0]", "xyz[1]", "xyz[2]"])[ground_mask], axis=0)
    # The default profile only records raw sensor topics at about 1 Hz.
    # Report sample count and bandwidth limitation instead of inferring a PSD.
    output["stationary_raw_sensor_samples"] = []
    for dataset in log.data_list:
        if dataset.name not in ("sensor_gyro", "sensor_accel"):
            continue
        d = dataset.data
        m = window(d, 20e6, events["takeoff_command"])
        if np.count_nonzero(m) >= 2:
            output["stationary_raw_sensor_samples"].append({
                "topic": dataset.name, "instance": dataset.multi_id,
                "unit": "rad/s" if dataset.name == "sensor_gyro" else "m/s^2",
                "count": int(np.count_nonzero(m)),
                "statistics": stats(vectors(d, ["x", "y", "z"])[m]),
                "note": "Sparse preflight samples, not full-rate noise or independent IMUs."})
    groundtruth = topic("vehicle_local_position_groundtruth")
    gp = vectors(groundtruth, ["x", "y", "z"])[window(groundtruth)]
    output["groundtruth_position_displacement_m"] = stats(gp-gp[0])
    # perf PC_ELAPSED reports execution counts independent of ULog decimation.
    counts = []
    for suffix in ("start", "end"):
        text = (run / f"perf_hover_{suffix}.txt").read_text()
        match = re.search(r"mc_rate_control: cycle:\s*(\d+) events", text)
        counts.append(int(match.group(1)) if match else None)
    if any(c is None for c in counts):
        # On this PX4 version perf prints to daemon stdout, not client stdout.
        console_counts = re.findall(r"mc_rate_control: cycle:\s*(\d+) events",
                                    (run / "console.log").read_text())
        if len(console_counts) == 2:
            counts = [int(c) for c in console_counts]
            output["module_perf_counter_source"] = "two ordered perf calls in console.log"
    if all(c is not None for c in counts):
        output["module_perf_callback_count_delta"] = counts[1]-counts[0]
        output["module_perf_approx_callback_hz"] = (counts[1]-counts[0])/output["hover_duration_s"]
    (run / "metrics.json").write_text(json.dumps(output, indent=2, default=plain) + "\n")
    (run / "ulog_initial_parameters.json").write_text(
        json.dumps(log.initial_parameters, sort_keys=True, indent=2, default=plain) + "\n")
    (run / "ulog_topic_inventory.json").write_text(json.dumps([
        {"topic": d.name, "instance": d.multi_id, "samples": len(d.data["timestamp"])}
        for d in log.data_list], indent=2) + "\n")
    print(json.dumps(output, indent=2, default=plain))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    analyze(parser.parse_args().run)
