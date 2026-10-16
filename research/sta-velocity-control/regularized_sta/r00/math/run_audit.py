#!/usr/bin/env python3
"""Build a read-only source package in a new temporary directory; save audit facts."""
import argparse
import csv
import hashlib
import io
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from math_probe import MathProbe, audit_summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite an existing result")
    source = args.package.resolve(strict=True)
    work = pathlib.Path(tempfile.mkdtemp(prefix="r00-source-audit-"))
    commands = []

    def run(argv, cwd=source):
        result = subprocess.run([str(x) for x in argv], cwd=str(cwd), text=True, capture_output=True)
        commands.append(dict(argv=[str(x) for x in argv], cwd=str(cwd), exit_code=result.returncode,
                             stdout=result.stdout, stderr=result.stderr))
        return result

    source_hashes = run(["sha256sum", "-c", "SHA256SUMS.txt"])
    run(["cmake", "--version"])
    run(["g++", "--version"])
    configure = run(["cmake", "-S", source, "-B", work / "build", "-DCMAKE_BUILD_TYPE=Release"])
    build = run(["cmake", "--build", work / "build", "--parallel", "2"])
    ctest = run(["ctest", "--test-dir", work / "build", "--output-on-failure", "-V"])
    probe_cpp = pathlib.Path(__file__).resolve().parent / "source_probe.cpp"
    compile_probe = run(["g++", "-std=c++14", "-O2", "-Wall", "-Wextra", "-Wpedantic",
                         "-I", source / "cpp", probe_cpp, "-o", work / "source_probe"])
    probe = run([work / "source_probe"]) if compile_probe.returncode == 0 else None
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MathProbe)
    test_result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    # Historical fixture metadata: reading it is not running MATLAB.
    with (source / "tests/matlab/controller_reference.csv").open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    all_ok = all(x["exit_code"] == 0 for x in commands) and test_result.wasSuccessful()
    result = dict(schema=1, purpose="R00 audit, no production changes or flight", success=all_ok,
                  build_directory=str(work), package=str(source),
                  package_sha256_manifest=digest(source / "SHA256SUMS.txt"),
                  package_sha256_count=sum(1 for line in source_hashes.stdout.splitlines() if line.endswith(": OK")),
                  commands=commands,
                  source_probe=json.loads(probe.stdout) if probe and probe.returncode == 0 else None,
                  unittest=dict(tests_run=test_result.testsRun, failures=len(test_result.failures),
                                errors=len(test_result.errors), output=stream.getvalue()),
                  ctest=dict(registered_and_executed=2 if ctest.returncode == 0 and "100% tests passed, 0 tests failed out of 2" in ctest.stdout else None,
                             exit_code=ctest.returncode),
                  historical_matlab_fixture=dict(rows=len(rows), sta_rows=sum(r["algorithm"] == "0" for r in rows),
                                                 ista_rows=sum(r["algorithm"] == "1" for r in rows),
                                                 sha256=digest(source / "tests/matlab/controller_reference.csv")),
                  matlab=dict(path=shutil.which("matlab"), octave_path=shutil.which("octave"),
                              executed=False, reason="R00 reruns package C++ against historical fixture; no MATLAB available on PATH"),
                  math=audit_summary(),
                  source_files={str(p.relative_to(source)): digest(p) for p in [source / "cpp/velocity_sta_ista.hpp",
                                source / "matlab/sta/sta_velocity_ff_conditional.m", source / "matlab/sta/height_sta_acceleration.m",
                                source / "parameters/controller_parameters.json"]})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    print(json.dumps(dict(success=all_ok, result=str(args.output), unittest_count=test_result.testsRun,
                          ctest=result["ctest"], source_probe=result["source_probe"]), ensure_ascii=False))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
