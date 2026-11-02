"""Pure offline tests; no fake ULog files and no simulator invocation."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

import analyze_hover as a


class HoverAnalysisTest(unittest.TestCase):
    def arrays(self):
        t = np.arange(1_000_000, 24_000_001, 100_000, dtype=np.int64)
        count = len(t)
        pos = dict(timestamp=t + 100, timestamp_sample=t, x=np.zeros(count), y=np.zeros(count),
                   z=np.full(count, -2.5), vx=np.full(count, .1), vy=np.full(count, -.2), vz=np.zeros(count),
                   xy_reset_counter=np.zeros(count), z_reset_counter=np.zeros(count))
        pos["z"][t <= 2_000_000] = 0
        att = dict(timestamp=t + 100, timestamp_sample=t, **{"q[%d]" % i: np.ones(count) if i == 0 else np.zeros(count) for i in range(4)})
        events = dict(zip(a.EVENT_NAMES, (2_000_000, 8_000_000, 18_000_000, 19_000_000, 23_000_000)))
        return pos, att, events

    def test_exact_hover_metrics_and_ned_origin(self):
        p, q, e = self.arrays()
        m, trace = a.compute_metrics(p, q, e, 10, 2.5)
        np.testing.assert_allclose(m["velocity_rms_xyz_m_s"], [.1, .2, 0], atol=1e-14)
        self.assertEqual(m["nominal_height_error_rms_m"], 0)
        self.assertEqual(m["maximum_tilt_deg"], 0)
        self.assertAlmostEqual(m["hover_seconds"], 10, places=12)
        self.assertEqual(m["takeoff_to_hover_s"], 6)
        self.assertEqual(trace["time_s"][0], 0)
        self.assertEqual(trace["displacement"][-1, 2], -2.5)

    def test_irregular_samples_are_time_weighted(self):
        i, w = a.window_weights(np.array([1, 3, 10]) * 1_000_000, 2_000_000, 8_000_000)
        np.testing.assert_array_equal(i, [0, 1])
        np.testing.assert_array_equal(w, [1, 5])
        self.assertAlmostEqual(a.weighted_rms(np.array([2., 4.]), w), np.sqrt(84 / 6))

    def test_missing_window_is_rejected_not_extrapolated(self):
        with self.assertRaisesRegex(ValueError, "Missing full"):
            a.window_weights(np.array([2, 3, 5]), 1, 4)

    def test_repeated_or_reverse_sample_is_not_deduplicated(self):
        for t in ([1, 1, 2], [2, 1, 3]):
            with self.assertRaisesRegex(ValueError, "Non-increasing"):
                a.clock({"timestamp_sample": t})

    def test_publication_tie_does_not_override_valid_sample_clock(self):
        p, q, e = self.arrays()
        p["timestamp"][1] = p["timestamp"][0]
        m, _ = a.compute_metrics(p, q, e, 10, 2.5)
        self.assertEqual(m["position_sampling"]["timestamp"]["repeated_intervals"], 1)
        self.assertEqual(m["source_clock"], "timestamp_sample")

    def test_missing_attitude_is_explicit(self):
        p, _, e = self.arrays()
        m, _ = a.compute_metrics(p, None, e, 10, 2.5)
        self.assertIsNone(m["maximum_tilt_deg"])

    def test_short_hover_does_not_become_ten_seconds(self):
        p, q, e = self.arrays()
        e["hover_end"] = e["hover_start"] + 9_000_000
        with self.assertRaisesRegex(ValueError, "Missing full requested hover"):
            a.compute_metrics(p, q, e, 10, 2.5)

    def test_nonfinite_velocity_is_rejected(self):
        p, q, e = self.arrays()
        p["vx"][100] = np.nan
        with self.assertRaisesRegex(ValueError, "Nonfinite"):
            a.compute_metrics(p, q, e, 10, 2.5)

    def test_preflight_invalid_values_not_confused_with_flight_window(self):
        p, q, e = self.arrays()
        p["vx"][0] = np.nan
        q["q[0]"][0] = np.nan
        m, _ = a.compute_metrics(p, q, e, 10, 2.5)
        self.assertAlmostEqual(m["velocity_rms_xyz_m_s"][0], .1)

    def test_invalid_estimator_flag_in_flight_is_reported(self):
        p, q, e = self.arrays()
        p["v_xy_valid"] = np.ones(len(p["timestamp"]), dtype=bool)
        p["v_xy_valid"][100] = False
        with self.assertRaisesRegex(ValueError, "Invalid estimator flag"):
            a.compute_metrics(p, q, e, 10, 2.5)

    def test_reset_not_silently_corrected(self):
        p, q, e = self.arrays()
        p["xy_reset_counter"][100:] = 1
        p["x"][100:] = .4
        m, trace = a.compute_metrics(p, q, e, 10, 2.5)
        self.assertTrue(m["coordinate_reset_warning"])
        self.assertEqual(trace["displacement"][-1, 0], .4)

    def test_events_missing_duplicate_or_unordered_are_rejected(self):
        _, _, e = self.arrays()
        records = [dict(name=k, timestamp_us=v) for k, v in e.items()]
        self.assertEqual(a.event_times(records), e)
        for invalid in (records[:-1], records + [records[0]], [dict(name=k, timestamp_us=1) for k in e]):
            with self.assertRaises(ValueError):
                a.event_times(invalid)

    def test_ulog_fingerprint_mismatch(self):
        # Byte fixture tests hashing only; it is never passed to a ULog decoder.
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "byte_fixture"
            p.write_bytes(b"digest-only")
            info = dict(archive=p.name, bytes=p.stat().st_size, sha256=a.digest(p))
            self.assertEqual(len(a.verify_archives([info], Path(tmp) / "result.json")), 1)
            info["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                a.verify_archives([info], Path(tmp) / "result.json")

    def test_failed_run_cannot_complete_comparison(self):
        rows = [dict(job=dict(id=str(i)), attempted=True, runner_success=True, analysis_valid=True) for i in range(3)]
        self.assertTrue(a.summarize(rows)["complete_three_system_comparison"])
        rows[1]["runner_success"] = False
        summary = a.summarize(rows)
        self.assertFalse(summary["complete_three_system_comparison"])
        self.assertEqual(summary["first_runner_failure"], "1")
        self.assertEqual(summary["attempted_after_first_failure"], ["2"])

    def test_four_complete_systems(self):
        rows = [dict(job=dict(id=str(i)), attempted=True, runner_success=True, analysis_valid=True) for i in range(4)]
        self.assertTrue(a.summarize(rows)['complete_comparison'])
        self.assertFalse(a.summarize(rows)['complete_three_system_comparison'])
        rows[-1]['analysis_valid'] = False
        self.assertFalse(a.summarize(rows)['complete_comparison'])

    def test_unsupported_comparison_size(self):
        rows = [dict(job=dict(id=str(i)), attempted=True, runner_success=True, analysis_valid=True) for i in range(5)]
        self.assertFalse(a.summarize(rows)['complete_comparison'])

    def test_missing_result_is_not_filled(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = dict(data_root=tmp, hover_s=10, takeoff_alt_m=2.5)
            row, trace = a.analyze_job(manifest, dict(id="missing", label="RSTA"), Path(tmp) / "manifest.json", ulog_class=object)
            self.assertFalse(row["attempted"])
            self.assertFalse(row["analysis_valid"])
            self.assertIsNone(trace)

    def test_ambiguous_result_locations_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path in (root / "a" / "result.json", root / "runs" / "a" / "result.json"):
                path.parent.mkdir(parents=True)
                path.write_text("{}")
            with self.assertRaisesRegex(ValueError, "Ambiguous"):
                a.resolve_result(root, dict(id="a"))


if __name__ == "__main__":
    unittest.main()
