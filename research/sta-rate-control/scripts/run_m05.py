#!/usr/bin/env python3
"""M05 uses the existing launcher, monitor, cleanup and archival schema.

Shared m04_ filenames are intentional for the common verifier. The saved
protocol milestone/trigger/axes distinguish M05 from historical M04 data.
"""
from pathlib import Path
from run_m00 import main
from run_m04 import Checks as BaseChecks


class Checks(BaseChecks):
    stage = 'm05'
    prefix = 'M05'
    config_name = 'iris_esta_rp.json'

    def __init__(self):
        super().__init__()
        if self.axes != (3 if self.mode else 0):
            raise ValueError('M05 requires PID AXES=0 or ESTA AXES=3')


if __name__ == '__main__':
    main(checks=Checks(), scenario_path=Path(__file__))
