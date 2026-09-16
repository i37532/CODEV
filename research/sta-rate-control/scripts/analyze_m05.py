#!/usr/bin/env python3
"""Shared full-rate verifier plus frozen M05 all-axis/phase checks."""
import argparse
import json
from pathlib import Path
from analyze_m04 import main

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('run', type=Path)
    run = parser.parse_args().run
    if json.loads((run/'m04_protocol.json').read_text()).get('milestone') != 'M05':
        raise ValueError('Expected M05 protocol')
    main(run)
