#!/usr/bin/env python3
"""Freeze small baseline summaries and checksum ALL archived trial evidence."""
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DATA = Path("/home/yr/Desktop/codev doc/experiments/M00-20260912")
TARGET = REPO / "research/sta-rate-control/baseline"


def read(path):
    return json.loads(path.read_text())


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def main():
    results, metrics, parameters = [], [], []
    for run in sorted(DATA.glob("run[0-9][0-9]")):
        r = read(run / "result.json")
        for artifact in r["logs"]:
            p = Path(artifact["archive"])
            assert hashlib.sha256(p.read_bytes()).hexdigest() == artifact["sha256"], p
        results.append({"run": run.name, "result": r})
        if r["success"]:
            m = read(run / "metrics.json")
            assert all(m["acceptance"].values()), run
            assert m["hover_duration_s"] >= 60, run
            metrics.append(m)
            parameters.append((run.name, read(run / "ulog_initial_parameters.json")))
    assert len(metrics) == 3, "M00 requires exactly three accepted repetitions"
    accepted = [r["result"] for r in results if r["result"]["success"]]
    for key in ("source_head", "binary_sha256", "runner_sha256", "explicit_environment"):
        assert all(r[key] == accepted[0][key] for r in accepted), key
    base_name, base = parameters[0]
    differences = {}
    for name, params in parameters[1:]:
        differences[name] = {key: {base_name: base.get(key), name: params.get(key)}
                             for key in sorted(base.keys() | params.keys())
                             if base.get(key) != params.get(key)}
        unexpected = set(differences[name]) - {"COM_FLIGHT_UUID", "LND_FLIGHT_T_LO", "LND_FLIGHT_T_HI"}
        assert not unexpected, f"Unreviewed configuration differences in {name}: {unexpected}"
    save(TARGET / "pid_initial_parameters.json", base)
    save(TARGET / "parameter_differences.json", differences)
    save(TARGET / "plan_snapshot_hashes.json", {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((TARGET.parent / "plan").glob("*.md"))})
    save(TARGET / "metrics.json", metrics)
    save(TARGET / "runs.json", {
        "data_root": str(DATA), "all_attempt_count": len(results),
        "accepted_count": len(metrics), "runs": results,
        "note": "Includes setup failures; same-configuration repeats, not independent seeded trials."})
    paths = sorted((DATA / "build").glob("*.log"))
    paths += sorted(p for run in DATA.glob("run[0-9][0-9]") for p in run.rglob("*") if p.is_file())
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p}" for p in paths]
    (TARGET / "artifacts.sha256").write_text("\n".join(lines) + "\n")
    print(json.dumps({"attempts": len(results), "accepted": len(metrics),
                      "artifact_count": len(paths), "parameter_differences": differences}, indent=2))


if __name__ == "__main__":
    main()
