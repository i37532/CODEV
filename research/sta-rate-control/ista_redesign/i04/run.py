#!/usr/bin/env python3
"""One frozen I04 flight using the existing M10 seeded Iris launcher."""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]/'scripts'))

from run_m00 import main
from run_m10 import Checks as M10Checks


class Checks(M10Checks):
    allowed_modes = (0, 1, 2, 3)

    def __init__(self):
        super().__init__()
        frozen = json.loads((HERE/'FROZEN.json').read_text())
        self.protocol = frozen['flight_protocol']
        # The inherited constructor staged the M08 protocol before applying the
        # job. Replace exactly the scene fields frozen for I04.
        for name in ('MPC_LAND_SPEED', 'LNDMC_Z_VEL_MAX', 'MPC_YAW_MODE'):
            self.config[name] = self.protocol['scenario_parameters'][name]


if __name__ == '__main__':
    main(checks=Checks(), scenario_path=Path(__file__))
