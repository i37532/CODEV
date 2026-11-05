#!/usr/bin/env python3
"""R02 dry-run inventory. Execution cannot be authorized in this version."""
import argparse
import json
from config import candidate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', type=int, default=0)
    parser.add_argument('--axes', type=int, default=0)
    parser.add_argument('--epsilon', type=float, nargs=3, default=(.01, .01, .02))
    parser.add_argument('--execute', action='store_true')
    # Accepted only to produce an unambiguous denial; cannot unlock execution.
    parser.add_argument('--manifest')
    parser.add_argument('--source-head')
    parser.add_argument('--authorization')
    args = parser.parse_args(argv)
    if args.execute:
        raise RuntimeError('R02 is offline-only: no flight budget/backend. R03 needs a separately frozen manifest, clean-source qualification and approved exact budget; receipts cannot unlock this entry.')
    print(json.dumps(candidate(args.mode, args.axes, args.epsilon), indent=2, allow_nan=False))
    print('DRY RUN: no process, flight, file, EEPROM or runtime parameter changes.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
