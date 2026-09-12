#!/usr/bin/env python3
"""Negative acceptance checks using a real archived passing ULog fixture."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from analyze_m00 import analyze


class AcceptanceRejectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((Path(os.environ["M00_PASSING_RUN"]) / "result.json").read_text())
        if not cls.fixture["success"]:
            raise ValueError("Fixture must be an actual passing run")

    def reject(self, modify, expected):
        data = copy.deepcopy(self.fixture)
        modify(data)
        with tempfile.TemporaryDirectory(prefix="m00-analysis-test-") as name:
            p = Path(name)
            (p / "result.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, expected):
                analyze(p)
            self.assertFalse((p / "metrics.json").exists())

    def test_failed_run_is_not_accepted(self):
        self.reject(lambda d: d.update(success=False), "Run must pass")

    def test_wrong_ulog_hash_is_not_accepted(self):
        self.reject(lambda d: d["logs"][0].update(sha256="0" * 64), "checksum mismatch")

    def test_short_hover_is_not_accepted(self):
        def shorten(d):
            start = next(e["timestamp_us"] for e in d["events"] if e["name"] == "hover_start")
            for e in d["events"]:
                if e["name"] == "hover_end":
                    e["timestamp_us"] = start + 59e6
        self.reject(shorten, "Hover shorter than 60 s")


if __name__ == "__main__":
    unittest.main()
