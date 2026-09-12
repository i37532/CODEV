#!/usr/bin/env python3
"""Archive M01 evidence summaries; raw ULog and build output stay outside Git."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REPO = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main(run):
    result = read(run / "result.json")
    metrics = read(run / "metrics.json")
    selection = read(run / "selection_analysis.json")
    if not (result["success"] and all(metrics["acceptance"].values()) and selection["success"]):
        raise ValueError("M01 evidence is not accepted")
    if sha(Path(result["logs"][0]["archive"])) != result["logs"][0]["sha256"]:
        raise ValueError("ULog changed since analysis")
    target = REPO / "research/sta-rate-control/m01"
    target.mkdir(exist_ok=True)
    assets = ["sitl/run.sh", "sitl/worlds/empty_grey.world", "Tools/sitl_gazebo/models/iris/iris.sdf",
              "ROMFS/px4fmu_common/init.d-posix/airframes/10016_iris",
              "ROMFS/px4fmu_common/mixers/quad_w.main.mix",
              "src/modules/mc_rate_control/RateControl/RateControl.cpp",
              "src/modules/mc_rate_control/RateControl/RateControl.hpp"]
    summary = {
        "scope": "M01: PID-only selector, host tests and one Iris Gazebo Classic flight smoke",
        "run": result, "hover_metrics": metrics, "selection_validation": selection,
        "tested_worktree_patch_sha256": sha(run / "tracked_diff.patch"),
        "tested_worktree_status_sha256": sha(run / "worktree_status.txt"),
        "assets_sha256": {p: sha(REPO / p) for p in assets},
        "submodules": subprocess.check_output(["git", "submodule", "status", "--recursive"], cwd=REPO, text=True),
        "submodule_worktrees": subprocess.check_output(
            ["git", "submodule", "foreach", "--recursive", "--quiet", "git status --porcelain"], cwd=REPO, text=True),
        "observed_build_and_test_exits": {
            "ratecontrol_tests.log": {"exit": 2, "reason": "Test fixture accessor rename; corrected before execution"},
            "ratecontrol_tests_retry.log": {"exit": 0, "ctest_suites": 2, "gtest_cases": 4},
            "selection_tests.log": {"exit": 0, "ctest_suites": 1, "gtest_cases": 5},
            "px4_sitl_default.log": {"exit": 0},
        },
        "test_scope_note": "Two deterministic 2048-step sequences compare output and integrator float bits against a frozen M00 reference, including disabled cycles.",
        "frequency_and_randomness": "Same Iris/gray world, lockstep and SDLOG_PROFILE=131 as M00; one smoke is not a statistical comparison; output log remains decimated.",
    }
    (target / "evidence.json").write_text(json.dumps(summary, indent=2) + "\n")
    paths = sorted((run.parent / "build").glob("*.log"))
    paths += sorted(p for p in run.rglob("*") if p.is_file())
    (target / "artifacts.sha256").write_text("\n".join(f"{sha(p)}  {p}" for p in paths) + "\n")
    print(json.dumps({"summary": str(target / "evidence.json"), "artifact_count": len(paths),
                      "patch_sha256": summary["tested_worktree_patch_sha256"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    main(parser.parse_args().run)
