#!/usr/bin/env python3
"""Read-only, descriptive native-ULog comparison of three or four controller systems.

Never grants flight acceptance or replaces the runner's result. Missing/failed
runs are retained and never filled using earlier experiments. The only figures
are actual estimator velocity and position relative to takeoff, separately.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


EVENT_NAMES = ("takeoff_command", "hover_start", "hover_end", "land_command", "landed_disarmed")
TOPICS = ("vehicle_local_position", "vehicle_local_position_setpoint", "vehicle_attitude",
          "vehicle_status", "vehicle_land_detected")
COLORS = ("#264d83", "#d46a26", "#288566", "#9146b5")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read_json(path):
    def invalid(value):
        raise ValueError("Non-standard JSON value: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=invalid)


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def event_times(events):
    result = {}
    for event in events:
        name = event["name"]
        if name in EVENT_NAMES:
            require(name not in result, "Ambiguous repeated event: " + name)
            value = event["timestamp_us"]
            require(isinstance(value, int) and not isinstance(value, bool) and value > 0,
                    "Invalid event clock: " + name)
            result[name] = value
    require(all(name in result for name in EVENT_NAMES), "Missing task event(s)")
    a, b, c, d, e = (result[name] for name in EVENT_NAMES)
    require(a < b < c <= d < e, "Task events not strictly ordered")
    return result


def clock(data, strict=True):
    name = "timestamp_sample" if "timestamp_sample" in data else "timestamp"
    raw = np.asarray(data[name])
    require(raw.ndim == 1 and len(raw) > 1 and np.isfinite(raw).all(), "Invalid " + name)
    require(np.all(raw > 0) and np.all(raw <= np.iinfo(np.int64).max), "Out-of-range " + name)
    t = raw.astype(np.int64)
    require(np.all(raw == t), "Non-integer " + name)
    if strict:
        require(np.all(np.diff(t) > 0), "Non-increasing " + name + "; no silent sorting/deduplication")
    return t, name


def clock_statistics(data):
    result = {}
    for name in ("timestamp", "timestamp_sample"):
        if name not in data:
            continue
        t = np.asarray(data[name]).astype(np.int64)
        dt = np.diff(t)
        positive = dt[dt > 0] * 1e-6
        median = float(np.median(positive)) if len(positive) else None
        result[name] = dict(samples=len(t), zero_timestamp_count=int(np.sum(t == 0)),
            repeated_intervals=int(np.sum(dt == 0)), backwards_intervals=int(np.sum(dt < 0)),
            median_interval_s=median, maximum_positive_interval_s=float(positive.max()) if len(positive) else None,
            p95_positive_interval_s=float(np.percentile(positive, 95)) if len(positive) else None,
            median_frequency_hz=1.0 / median if median else None,
            intervals_over_twice_median=int(np.sum(positive > 2 * median)) if median else None,
            note="Long intervals are observed gaps, not a proven count of dropped messages.")
    return result


def window_weights(t, start, end):
    t = np.asarray(t, dtype=np.int64)
    require(len(t) > 1 and np.all(np.diff(t) > 0), "Non-increasing metric sample time")
    require(start < end and t[0] <= start and t[-1] >= end, "Missing full requested metric window")
    idx = np.flatnonzero((t[:-1] < end) & (t[1:] > start))
    require(len(idx) > 0, "Empty metric window")
    weights = (np.minimum(t[idx + 1], end) - np.maximum(t[idx], start)) * 1e-6
    require(np.all(weights > 0) and abs(float(weights.sum()) - (end - start) * 1e-6) < 1e-9,
            "Metric window coverage mismatch")
    return idx, weights


def weighted_rms(values, weights):
    values = np.asarray(values, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    require(values.shape[0] == len(weights) and np.isfinite(values).all(), "Invalid RMS samples")
    require(np.isfinite(weights).all() and np.all(weights > 0), "Invalid RMS weights")
    return np.sqrt(np.sum(values * values * weights.reshape((-1,) + (1,) * (values.ndim - 1)), axis=0)
                   / weights.sum()).tolist()


def vectors(data, names, finite=True):
    result = np.column_stack([data[name] for name in names]).astype(np.float64)
    if finite:
        require(np.isfinite(result).all(), "Nonfinite native measurement: " + ",".join(names))
    return result


def reset_evidence(data, full):
    result = {}
    for name in ("xy_reset_counter", "z_reset_counter", "vxy_reset_counter", "vz_reset_counter"):
        if name in data:
            v = np.asarray(data[name])[full]
            result[name] = dict(changes=int(np.count_nonzero(np.diff(v.astype(np.int64)))),
                                observed_values=np.unique(v).astype(int).tolist())
    return result


def compute_metrics(position, attitude, events, hover_s, takeoff_alt_m):
    """Exact-window ZOH metrics on raw samples; no interpolation or time warping."""
    t, name = clock(position)
    p = vectors(position, ("x", "y", "z"), finite=False)
    v = vectors(position, ("vx", "vy", "vz"), finite=False)
    takeoff, hs, he, land, end = (events[key] for key in EVENT_NAMES)
    require(t[0] <= takeoff < end <= t[-1], "Missing complete takeoff-to-disarm position coverage")
    hover_end = hs + int(round(hover_s * 1e6))
    require(hover_s > 0 and he >= hover_end, "Missing full requested hover duration")
    idx, weights = window_weights(t, hs, hover_end)
    origin_idx = int(np.searchsorted(t, takeoff, side="right") - 1)
    origin = p[origin_idx]
    full = (t >= takeoff) & (t <= end)
    require(int(full.sum()) > 1, "Missing flight samples")
    require(np.isfinite(p[full]).all() and np.isfinite(v[full]).all() and np.isfinite(origin).all(),
            "Nonfinite native measurement within flight/origin window")
    for validity in ("xy_valid", "z_valid", "v_xy_valid", "v_z_valid"):
        if validity in position:
            require(np.all(np.asarray(position[validity])[full]), "Invalid estimator flag in flight: " + validity)
    displacement = p - origin
    h = -displacement[:, 2]
    drift = np.linalg.norm(displacement[idx, :2], axis=1)
    height_error = h[idx] - takeoff_alt_m
    metrics = dict(hover_window_us=[hs, hover_end], hover_samples=len(idx),
        hover_seconds=float(weights.sum()), source_clock=name,
        velocity_rms_xyz_m_s=weighted_rms(v[idx], weights),
        horizontal_displacement_rms_m=weighted_rms(drift, weights),
        maximum_horizontal_displacement_m=float(drift.max()),
        nominal_height_error_rms_m=weighted_rms(height_error, weights),
        maximum_absolute_nominal_height_error_m=float(np.max(np.abs(height_error))),
        nominal_height_m=takeoff_alt_m,
        takeoff_to_hover_s=(hs - takeoff) * 1e-6,
        takeoff_to_disarm_s=(end - takeoff) * 1e-6,
        landing_command_to_disarm_s=(end - land) * 1e-6,
        origin_position_ned_m=origin.tolist(), origin_sample_us=int(t[origin_idx]),
        origin_age_at_takeoff_s=(takeoff - int(t[origin_idx])) * 1e-6,
        reset_evidence=reset_evidence(position, full),
        position_sampling=clock_statistics(position),
        hover_maximum_bracketing_interval_s=float(np.max(t[idx + 1] - t[idx])) * 1e-6,
        maximum_tilt_deg=None, attitude_note="Missing vehicle_attitude; no tilt metric")
    if attitude is not None:
        at, ac = clock(attitude, strict=False)
        mask = (at >= takeoff) & (at <= end)
        require(mask.any(), "No attitude samples in flight window")
        require(at.min() <= takeoff and at.max() >= end, "Missing full attitude time coverage")
        q = vectors(attitude, tuple("q[%d]" % i for i in range(4)), finite=False)[mask]
        require(np.isfinite(q).all(), "Nonfinite flight attitude")
        norm = np.linalg.norm(q, axis=1)
        require(np.all(norm > 0), "Zero attitude quaternion")
        unit_q = q / norm[:, None]
        tilt = np.degrees(np.arccos(np.clip(1 - 2 * (unit_q[:, 1] ** 2 + unit_q[:, 2] ** 2), -1, 1)))
        metrics.update(maximum_tilt_deg=float(tilt.max()), attitude_clock=ac,
                       maximum_quaternion_norm_deviation=float(np.max(abs(norm - 1))),
                       attitude_sampling=clock_statistics(attitude),
                       attitude_note="Quaternion-normalized tilt; native messages not reordered or deduplicated.")
    metrics["coordinate_reset_warning"] = any(item["changes"] for item in metrics["reset_evidence"].values())
    metrics["metric_definition"] = ("Time-weighted RMS of measured estimator velocity, NOT tracking RMSE. "
        "Position is relative to the last native sample at/before takeoff. "
        "Reset-induced coordinate jumps are not silently corrected. NED Z is positive down.")
    trace = dict(time_s=(t[full] - takeoff) * 1e-6, velocity=v[full], displacement=displacement[full])
    return metrics, trace


def resolve_result(data_root, job):
    if "result_path" in job:
        path = Path(job["result_path"])
        return path if path.is_absolute() else data_root / path
    candidates = [data_root / job["id"] / "result.json", data_root / "runs" / job["id"] / "result.json",
                  data_root / "batch01" / job["id"] / "result.json"]
    existing = [p for p in candidates if p.exists()]
    require(len(existing) <= 1, "Ambiguous result location for " + job["id"])
    return existing[0] if existing else candidates[0]


def verify_archives(items, result_path):
    require(isinstance(items, list) and items, "Missing original ULog archive list")
    records = []
    for item in items:
        p = Path(item["archive"])
        if not p.is_absolute():
            p = result_path.parent / p
        p = p.resolve()
        require(p.is_file(), "Missing ULog: " + str(p))
        require(p.stat().st_size == item["bytes"], "ULog byte count changed: " + str(p))
        require(digest(p) == item["sha256"], "ULog SHA-256 changed: " + str(p))
        records.append(dict(archive=str(p), sha256=item["sha256"], bytes=item["bytes"]))
    require(len({r["archive"] for r in records}) == len(records), "Duplicate ULog archive")
    return records


def dataset(log, name):
    matches = [d for d in log.data_list if d.name == name and d.multi_id == 0]
    require(len(matches) <= 1, "Ambiguous native topic " + name)
    return matches[0].data if matches else None


def dropout_evidence(log):
    values = []
    for dropout in log.dropouts:
        values.append(dict(timestamp_us=int(dropout.timestamp), duration_ms=int(dropout.duration)))
    return dict(records=values, count=len(values), total_duration_ms=sum(v["duration_ms"] for v in values),
                file_corruption=bool(getattr(log, "file_corruption", False)),
                note="ULog dropout messages only; absence does not prove full upstream topic delivery.")


def analyze_job(manifest, job, manifest_path, ulog_class=None):
    if ulog_class is None:
        from pyulog import ULog
        ulog_class = ULog
    root = Path(manifest["data_root"])
    if not root.is_absolute():
        root = manifest_path.parent / root
    row = dict(job=job, runner_success=None, analysis_valid=False, attempted=False, errors=[])
    trace = None
    try:
        result_path = resolve_result(root, job)
        row["result_path"] = str(result_path)
        if not result_path.exists():
            row["status"] = "unattempted_or_missing_result"
            row["errors"].append("No result.json; not replaced by a historical flight")
            return row, None
        result = read_json(result_path)
        row.update(attempted=True, runner_success=result.get("success") is True,
                   result_sha256=digest(result_path), source_result=result)
        row["status"] = "runner_passed" if row["runner_success"] else "runner_failed"
        archives = verify_archives(result.get("logs"), result_path)
        row["verified_logs"] = archives
        events = event_times(result.get("events", []))
        row["events"] = events
        complete = []
        archive_audit = []
        for record in archives:
            log = ulog_class(record["archive"], message_name_filter_list=list(TOPICS))
            evidence = dict(ulog=record, dropouts=dropout_evidence(log),
                topics={name: clock_statistics(dataset(log, name)) for name in TOPICS if dataset(log, name) is not None})
            archive_audit.append(evidence)
            position = dataset(log, "vehicle_local_position")
            if position is None:
                continue
            try:
                metrics, candidate_trace = compute_metrics(position, dataset(log, "vehicle_attitude"), events,
                    float(manifest["hover_s"]), float(manifest["takeoff_alt_m"]))
                complete.append((record, evidence, metrics, candidate_trace))
            except (ValueError, KeyError) as error:
                evidence["analysis_error"] = str(error)
        row["archive_audit"] = archive_audit
        require(len(complete) == 1, "Need exactly one complete native ULog window; got " + str(len(complete)))
        record, evidence, metrics, trace = complete[0]
        row.update(ulog=record, metrics=metrics)
        require(not evidence["dropouts"]["file_corruption"], "ULog reports corruption")
        # No new dropout/gap threshold is invented by this descriptive tool.
        # The runner's frozen rules determine flight acceptance independently.
        row["analysis_valid"] = True
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        row["errors"].append(str(error))
        row["status"] = "analysis_missing_or_invalid" if row["runner_success"] else row.get("status", "missing")
        trace = None
    return row, trace


def summarize(rows):
    failures = [r["job"]["id"] for r in rows if r["attempted"] and not r["runner_success"]]
    accepted = [r["job"]["id"] for r in rows if r["runner_success"] and r["analysis_valid"]]
    first_failure = failures[0] if failures else None
    after_failure = []
    if first_failure:
        index = next(i for i, r in enumerate(rows) if r["job"]["id"] == first_failure)
        after_failure = [r["job"]["id"] for r in rows[index + 1:] if r["attempted"]]
    return dict(planned=len(rows), attempted=sum(r["attempted"] for r in rows),
        runner_passed=sum(bool(r["runner_success"]) for r in rows),
        comparable_runs=accepted, failed=failures, first_runner_failure=first_failure,
        attempted_after_first_failure=after_failure,
        complete_three_system_comparison=len(rows) == len(accepted) == 3 and not failures,
        complete_comparison=len(rows) in (3, 4) and len(rows) == len(accepted) and not failures,
        missing=[r["job"]["id"] for r in rows if r["job"]["id"] not in accepted],
        interpretation="n=1 per system; descriptive system comparison, not a pure velocity-controller experiment.")


def draw(rows, traces, quantity, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    require(quantity in ("velocity", "displacement"), "Unknown figure quantity")
    count = len(rows)
    require(count in (3, 4) and count == len(traces) and all(t is not None for t in traces), "No incomplete comparison plots")
    fig, axes = plt.subplots(3, 1, figsize=(11.5, 8.4), sharex=True, constrained_layout=True)
    fig.suptitle("Takeoff / 10 s hover / landing: actual " + quantity + "\n%d controller systems, one flight each" % count)
    for i, (row, trace) in enumerate(zip(rows, traces)):
        for axis, ax in enumerate(axes):
            ax.plot(trace["time_s"], trace[quantity][:, axis], label=row["job"]["label"], color=COLORS[i], lw=1.1)
    for axis, ax in enumerate(axes):
        ax.set_ylabel("%s (%s) / %s" % ("XYZ"[axis], ("north", "east", "down")[axis], "m/s" if quantity == "velocity" else "m"))
        ax.grid(alpha=.2)
        require(len(ax.lines) == count, "Unexpected extra plot lines")
    axes[0].legend(loc="best", ncol=count)
    axes[-1].set_xlabel("Time since each takeoff command / s (no time scaling)")
    files = []
    for extension in ("png", "svg"):
        path = out / (quantity + "." + extension)
        fig.savefig(path, dpi=170)
        files.append(dict(path=path.name, sha256=digest(path)))
    plt.close(fig)
    return files


def write_readme(out, summary, rows):
    names = "、".join(r['job']['label'] for r in rows)
    lines = ["# " + names + " 简易系统对比", "",
        "这是不同完整控制系统的描述性对比，不是只替换速度环的公平算法消融。每个系统最多一轮（n=1），不能据此给出统计显著性、最优性或实机结论。", "",
        "## 本次数据", "", f"计划 {summary['planned']} 轮；实际有结果 {summary['attempted']} 轮；运行器通过 {summary['runner_passed']} 轮；完整可对比 {len(summary['comparable_runs'])} 轮。",
        "本次比较使用的运行器结果、失败、缺失和 ULog SHA-256 保留在 metrics.json；本分析器不改判飞行结果。PID 扩展保留本实验已经完成的三轮，只新增一轮 PID，没有借用其他任务的飞行补样本。", "",
        "速度是机载估计 vx/vy/vz；位移是估计位置减去各自起飞前最近样本，不是 Gazebo 真值或跟踪误差。NED 坐标：X北、Y东、Z向下。按起飞命令对齐，不平移峰值、不拉伸时间、不平滑。", ""]
    if summary["complete_comparison"]:
        lines += ["![各系统实际速度](velocity.png)", "", "![各系统相对起飞位置](displacement.png)", "",
            f"速度与位移分图，每图 XYZ 三个子图，每轴仅 {len(rows)} 条系统实测曲线，无目标虚线。SVG 为可缩放版本。", ""]
    else:
        lines += ["**比较清单尚未全部完成，因此不生成看似完整的比较曲线。**", ""]
    lines += ["## 10 秒悬停指标", "", "速度 RMS 是相对零速度的波动量，不是相对各控制器内部目标的跟踪 RMSE。按实际采样间隔加权；高度偏差相对本轮起飞原点上方的约定高度。", "",
        "|系统|运行器结果|X速度RMS|Y速度RMS|Z速度RMS|水平位移RMS|高度偏差RMS|最大倾角|", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        m = row.get("metrics") if row["analysis_valid"] else None
        status = "通过" if row["runner_success"] else ("失败" if row["attempted"] else "未执行/缺失")
        values = (m["velocity_rms_xyz_m_s"] + [m["horizontal_displacement_rms_m"], m["nominal_height_error_rms_m"], m["maximum_tilt_deg"]]) if m else [None] * 6
        lines.append("|" + row["job"]["label"] + "|" + status + "|" + "|".join("missing" if v is None else "%.6f" % v for v in values) + "|")
    lines += ["", "速度单位 m/s，位移/高度单位 m，倾角单位度。倾角取完整起降区间；其余表内指标使用明确的10秒悬停窗。", "",
        "metrics.json 另列起飞至悬停、起飞至上锁、降落命令至上锁耗时，以及原生消息双时钟、重复/倒退时刻、采样间隔、记录器 dropout 和 reset。间隔偏大不直接等同于已知丢失条数；没有 dropout 记录也不证明上游无漏采样。", "",
        "若存在估计器位置/速度 reset，表内 coordinate_reset_warning 会标明；不偷偷补偿坐标跳变。缺少完整窗口时指标标记 missing。未新增安全阈值，也未将本次任务与历史正式统计合并。", ""]
    (out / "README_CN.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    manifest = read_json(manifest_path)
    jobs = manifest["jobs"]
    require(len(jobs) in (3, 4) and len({j["id"] for j in jobs}) == len(jobs) and len({j["label"] for j in jobs}) == len(jobs),
            "Protocol requires three or four distinct systems, at most one flight each")
    require(float(manifest["hover_s"]) == 10 and float(manifest["takeoff_alt_m"]) > 0, "Unexpected task contract")
    out = args.output.resolve()
    require(not out.exists(), "Refusing to overwrite output")
    analyzed = [analyze_job(manifest, job, manifest_path) for job in jobs]
    rows, traces = [r[0] for r in analyzed], [r[1] for r in analyzed]
    summary = summarize(rows)
    out.mkdir(parents=True)
    figures = []
    if summary["complete_comparison"]:
        for quantity in ("velocity", "displacement"):
            figures += draw(rows, traces, quantity, out)
    payload = dict(manifest_path=str(manifest_path), manifest_sha256=digest(manifest_path),
        analyzer_sha256=digest(__file__), summary=summary, runs=rows, figures=figures)
    save_json(out / "metrics.json", payload)
    write_readme(out, summary, rows)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["complete_comparison"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
