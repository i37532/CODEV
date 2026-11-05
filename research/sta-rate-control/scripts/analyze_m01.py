#!/usr/bin/env python3
"""Cross-check M01 selector telemetry against the actual ULog and M00 parameters."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from pyulog import ULog

from analyze_m00 import analyze, plain


def main(run):
    analyze(run)  # Common flight acceptance, raw hash check and hover metrics.
    result = json.loads((run / "result.json").read_text())
    log = ULog(result["logs"][0]["archive"])
    selection = log.get_dataset("rate_ctrl_selection").data
    if not (np.all(selection["effective_mode"] == 0) and np.all(selection["effective_axes"] == 0)):
        raise ValueError("Non-PID controller became effective")
    records = [json.loads(line) for line in (run / "selection_checks.jsonl").read_text().splitlines()]
    phases = {r["phase"] for r in records}
    if not {"preflight", "hover", "disarmed", "cleanup"}.issubset(phases):
        raise ValueError("Incomplete real parameter checks")
    verified = []
    for record in records:
        if record["phase"] not in ("preflight", "hover"):
            continue  # SDLOG_MODE=1 can stop before the final disarmed changes.
        mask = selection["timestamp"] == record["observed"]["timestamp"]
        for key, value in record["expected"].items():
            mask &= selection[key] == value
        if not np.any(mask):
            raise ValueError(f"Expected selection observation missing from ULog: {record}")
        verified.append(record)
    for mode in (1, 2):
        if not any(r["expected"]["requested_mode"] == mode and r["expected"]["request_status"] == 1
                   and r["phase"] == "hover" for r in verified):
            raise ValueError("Missing armed unsupported-mode test")
    baseline_path = Path(__file__).resolve().parents[1] / "baseline/pid_initial_parameters.json"
    baseline = json.loads(baseline_path.read_text())
    initial = log.initial_parameters
    differences = {k: {"M00": baseline.get(k), "M01": initial.get(k)}
                   for k in sorted(baseline.keys() | initial.keys()) if baseline.get(k) != initial.get(k)}
    allowed = {"MC_RTC_MODE", "MC_STA_AXES", "COM_FLIGHT_UUID", "LND_FLIGHT_T_LO", "LND_FLIGHT_T_HI"}
    if set(differences) - allowed:
        raise ValueError(f"Unexpected initial parameter differences: {differences}")
    if initial.get("MC_RTC_MODE") != 0 or initial.get("MC_STA_AXES") != 0:
        raise ValueError("PID selector defaults were not used at boot")
    unexpected_changes = [c for c in log.changed_parameters if c[1] not in ("MC_RTC_MODE", "MC_STA_AXES")]
    if unexpected_changes:
        raise ValueError(f"Unexpected runtime parameter changes: {unexpected_changes}")
    summary = {
        "success": True,
        "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "ulog_sha256": result["logs"][0]["sha256"],
        "selection_logged_samples": len(selection["timestamp"]),
        "all_logged_effective_modes_pid": True,
        "all_logged_effective_axes_zero": True,
        "cli_check_count": len(records),
        "preflight_hover_checks_verified_in_ulog": len(verified),
        "initial_parameter_differences_vs_M00": differences,
        "changed_parameters": log.changed_parameters,
        "disarmed_check_note": "Final disarm/cleanup checks use archived CLI observations; boot-to-disarm ULog may stop earlier.",
    }
    (run / "selection_analysis.json").write_text(json.dumps(summary, indent=2, default=plain) + "\n")
    print(json.dumps(summary, indent=2, default=plain))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    main(parser.parse_args().run)
