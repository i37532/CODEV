#!/usr/bin/env python3
"""Full-rate M06 ESTA/PID, all-axis and lifecycle log verification."""
import argparse
import json
from pathlib import Path
from analyze_m04 import main

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path)
    run=parser.parse_args().run
    if json.loads((run/'m04_protocol.json').read_text()).get('milestone')!='M06':
        raise ValueError('Expected M06 protocol')
    main(run)
