#!/usr/bin/env python3
"""Collect versioned assets and hashes into a small reproducibility manifest."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[3]
TARGET = REPO / "research/sta-rate-control/baseline"
DATA = Path("/home/yr/Desktop/codev doc/experiments/M00-20260912")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args):
    r = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    return {"command": list(args), "exit_code": r.returncode,
            "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}


if command("git", "rev-parse", "HEAD")["stdout"] != "9a3c4e3625474ce7fd2cd5c9687933ccf6a70bc7":
    raise RuntimeError("One-time M00 collector: refusing to overwrite historical evidence from another HEAD")
for name in ("STA_MILESTONES_CN.md", "STA_MILESTONE_PROMPTS_CN.md", "STA_MILESTONE_STATUS_CN.md"):
    external = Path("/home/yr/Desktop/codev doc/plan") / name
    snapshot = REPO / "research/sta-rate-control/plan" / name
    if sha(external) != sha(snapshot):
        raise ValueError(f"Plan snapshot mismatch: {name}; nothing overwritten")


paths = [
    "sitl/run.sh", "Tools/sitl_run.sh", "sitl/worlds/empty_grey.world",
    "Tools/sitl_gazebo/models/iris/iris.sdf",
    "Tools/sitl_gazebo/models/iris/iris.sdf.jinja",
    "Tools/sitl_gazebo/models/gps/gps.sdf",
    "ROMFS/px4fmu_common/init.d-posix/airframes/10016_iris",
    "ROMFS/px4fmu_common/init.d/airframes/4065_codev_dp_1000",
    "ROMFS/px4fmu_common/init.d/rc.mc_defaults",
    "ROMFS/px4fmu_common/init.d-posix/rcS",
    "ROMFS/px4fmu_common/mixers/quad_w.main.mix",
    "src/modules/mc_rate_control/RateControl/RateControl.cpp",
    "src/modules/mc_rate_control/RateControl/RateControlTest.cpp",
    "src/modules/mc_rate_control/MulticopterRateControl.cpp",
    "build/px4_sitl_default/bin/px4",
    "build/px4_sitl_default/CMakeCache.txt",
    "build/px4_sitl_test/unit-RateControl",
]
paths.extend(str(p.relative_to(REPO)) for p in
             sorted((REPO / "build/px4_sitl_default/build_gazebo").glob("libgazebo*.so")))
for sensor in ("imu", "gps", "magnetometer", "barometer"):
    paths.extend([f"Tools/sitl_gazebo/src/gazebo_{sensor}_plugin.cpp",
                  f"Tools/sitl_gazebo/include/gazebo_{sensor}_plugin.h"])
assets = {}
for name in paths:
    p = REPO / name
    if p.exists():
        assets[name] = {"sha256": sha(p), "bytes": p.stat().st_size}

model = ET.parse(REPO / "Tools/sitl_gazebo/models/iris/iris.sdf")
links = {n.attrib["name"]: float(n.findtext("inertial/mass"))
         for n in model.findall(".//model/link") if n.find("inertial/mass") is not None}
manifest = {
    "source": command("git", "rev-parse", "HEAD"),
    "submodules": command("git", "submodule", "status", "--recursive"),
    "submodule_worktrees": command("git", "submodule", "foreach", "--recursive", "--quiet",
                                  "git status --porcelain"),
    "gazebo": command("gazebo", "--version"),
    "gcc": command("gcc", "--version"),
    "cmake": command("cmake", "--version"),
    "ninja": command("ninja", "--version"),
    "python": command("python3", "--version"),
    "board_toolchain_present_not_tested": command("arm-none-eabi-gcc", "--version"),
    "assets": assets,
    "iris_explicit_link_masses_kg": links,
    "mass_note": "Link masses do not include externally included gps0 model; base_link is not total mass.",
    "model": "Iris / SYS_AUTOSTART=10016 / quad_w",
    "not_tested": "CODEV DP1000 airframe 4065 / quad_x; no hardware flight or board firmware build.",
    "physics": {"engine": "ode", "step_s": 0.004, "requested_update_hz": 250,
                "requested_real_time_factor": 1, "gravity_m_s2": [0, 0, -9.8066],
                "lockstep_model_enabled": True},
    "randomness": {
        "gazebo_seed_explicitly_set": False,
        "external_force_injection": False,
        "sensor_noise_changed": False,
        "observed_source": "IMU/magnetometer/GPS/barometer use default-constructed std::default_random_engine; no explicit seed override found in inspected plugin sources.",
        "limitation": "Engine sequence/callback ordering, Gazebo startup and EKF multi-instance selection prevent a claim of bitwise determinism or independent random seeds.",
    },
    "test_results": {
        # Observed exit statuses from the actual M00 commands and retained logs;
        # this one-time collector does not execute the builds/tests itself.
        "px4_sitl_default": {"exit_code": 0, "log": str(DATA / "build/px4_sitl_default.log")},
        "RateControl": {"exit_code": 0, "ctest_count": 1, "gtest_case": "RateControlTest.AllZeroCase",
                        "log": str(DATA / "build/ratecontrol_tests.log"),
                        "scope": "Existing zero-input regression only; not a stability or full-controller proof."},
    },
}
(TARGET / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
print("Recorded", len(assets), "asset hashes; all three initial plan snapshots match.")
