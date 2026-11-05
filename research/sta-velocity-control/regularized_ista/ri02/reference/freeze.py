#!/usr/bin/env python3
"""Freeze/check the RI01 implementation for RI02 bitwise sequence regression.

Only symbol/file-name renaming is performed. Source is read from the explicit
Git object, never from a concurrently modified working tree. --write is used
once to generate new files; ordinary invocation is a read-only verification.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


BASE = "2f19cefc850ef4b77a8bcdc455aaec193f3da331"
DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parents[4]
SOURCE = "src/modules/mc_pos_control/PositionControl/"
STEMS = ("PositionControl", "ControlMath", "StaVelocityProtection",
         "StaVelocityControl", "RegularizedStaVelocityControl")
FILES = [stem + suffix for stem in STEMS for suffix in (".hpp", ".cpp")]
FILES += ["VelocityControlSelector.hpp", "VelocityDecimation.hpp", "VelocityHostClock.hpp"]
SYMBOLS = list(STEMS) + ["PositionControlStates", "VelocityControlSelector",
                       "VelocityDecimation", "VelocityHostClock", "velocityHostClock",
                       "VelocityControlTestAccess", "RegularizedVelocityTestAccess"]
RENAMES = {name: "RI01" + name for name in SYMBOLS}
PATTERN = re.compile(r"\b(" + "|".join(map(re.escape, SYMBOLS)) + r")\b")
REVERSE = re.compile(r"\b(" + "|".join(map(re.escape, RENAMES.values())) + r")\b")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    manifest = {"baseline": BASE, "mapping": RENAMES, "files": []}
    inverse = {value: key for key, value in RENAMES.items()}
    for name in FILES:
        original = subprocess.check_output(["git", "show", BASE + ":" + SOURCE + name], cwd=ROOT)
        transformed = PATTERN.sub(lambda match: RENAMES[match[0]], original.decode()).encode()
        assert REVERSE.sub(lambda match: inverse[match[0]], transformed.decode()).encode() == original
        target = DIRECTORY / ("RI01" + name)
        if args.write:
            if target.exists():
                raise SystemExit("refusing to overwrite " + str(target))
            target.write_bytes(transformed)
        assert target.read_bytes() == transformed, target
        manifest["files"].append({"source": SOURCE + name, "source_sha256": sha(original),
                                  "target": target.name, "target_sha256": sha(transformed),
                                  "source_bytes": len(original), "target_bytes": len(transformed)})
    encoded = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    destination = DIRECTORY / "manifest.json"
    if args.write:
        if destination.exists():
            raise SystemExit("refusing to overwrite " + str(destination))
        destination.write_bytes(encoded)
    assert destination.read_bytes() == encoded
    print(json.dumps({"baseline": BASE, "checked": len(FILES), "mechanical_inverse": True,
                      "manifest_sha256": sha(encoded)}))


if __name__ == "__main__":
    main()
