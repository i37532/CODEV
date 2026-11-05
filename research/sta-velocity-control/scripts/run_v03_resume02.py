#!/usr/bin/env python3
"""V03 newly authorized one-attempt protocol02; dry-run by default."""
from pathlib import Path
import analyze_v03 as analysis
import run_v01 as runner
from run_v03 import Checks

CONFIG = Path(__file__).resolve().parents[1] / 'v03' / 'protocol02'


def configure():
    analysis.CONFIG = CONFIG
    runner.CONFIG = CONFIG
    runner.Checks = Checks
    runner.analyze = analysis.analyze


if __name__ == '__main__':
    configure()
    runner.main()
