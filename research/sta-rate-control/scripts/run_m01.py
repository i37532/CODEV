#!/usr/bin/env python3
"""M01 PID flight smoke plus real parameter/selection checks, using the M00 launcher."""
import json
from pathlib import Path
import time

from run_m00 import main


class SelectionChecks:
    def __init__(self):
        self.modified = False

    def __call__(self, phase, cli, topic, output):
        def wait_selection(mode, axes, reason, pending):
            deadline = time.monotonic() + 8
            expected = {"requested_mode": mode, "requested_axes": axes,
                        "effective_mode": 0, "effective_axes": 0,
                        "request_status": reason, "pending": pending}
            while time.monotonic() < deadline:
                status = topic("rate_ctrl_selection")
                if all(status.get(k) == v for k, v in expected.items()):
                    with (output / "selection_checks.jsonl").open("a") as stream:
                        stream.write(json.dumps({"phase": phase, "expected": expected, "observed": status}) + "\n")
                    return
                time.sleep(0.2)
            raise RuntimeError(f"Selection mismatch: expected {expected}, observed {status}")

        def request(mode, axes, reason, pending):
            self.modified = True
            cli("param", "set", "MC_RTC_MODE", mode)
            cli("param", "set", "MC_STA_AXES", axes)
            wait_selection(mode, axes, reason, pending)

        if phase == "preflight":
            # Require the M01 default at entry; do not silently replace a user's
            # previously selected configuration to make a baseline pass.
            wait_selection(0, 0, 0, False)
            request(1, 1, 1, False)
            request(2, 7, 1, False)
            request(-1, 0, 2, False)
            request(256, 0, 2, False)
            request(0, 8, 3, False)
            request(0, -1, 3, False)
            request(0, 7, 0, False)
            request(0, 0, 0, False)
            (output / "selection_preflight_status.txt").write_text(cli("mc_rate_control", "status"))
        elif phase == "hover":
            request(1, 1, 1, True)
            request(2, 7, 1, True)
            request(0, 0, 0, False)  # Cancels the pending request.
            request(0, 7, 0, True)
            # Keep this inactive PID mask pending through landing. Disarm must
            # process it without any experimental axis ever becoming effective.
            (output / "selection_armed_status.txt").write_text(cli("mc_rate_control", "status"))
        elif phase == "disarmed":
            wait_selection(0, 7, 0, False)
            request(0, 0, 0, False)
            (output / "selection_disarmed_status.txt").write_text(cli("mc_rate_control", "status"))
        elif phase == "cleanup" and self.modified:
            request(0, 0, 0, False)
            cli("param", "save")


if __name__ == "__main__":
    main(checks=SelectionChecks(), scenario_path=Path(__file__))
