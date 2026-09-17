#!/usr/bin/env python3
"""M08 disarmed save/restart/load across PID, ESTA and ISTA; never arms."""
import argparse
from pathlib import Path
from verify_m06_restart import main
from run_m00 import REPO

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    main(args.output.resolve(),REPO/'research/sta-rate-control/m08/iris_ista_rpy_candidate02.json',modes=(1,2))
