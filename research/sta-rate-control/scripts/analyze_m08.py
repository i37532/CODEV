#!/usr/bin/env python3
"""M08 decoded ULog acceptance; delegates unchanged legacy scenario checks."""
import argparse
import json
from pathlib import Path
from analyze_m04 import main

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('run',type=Path); args=p.parse_args()
    if json.loads((args.run/'m04_protocol.json').read_text()).get('integration_milestone')!='M08':
        raise ValueError('Expected M08 integration protocol')
    main(args.run)
