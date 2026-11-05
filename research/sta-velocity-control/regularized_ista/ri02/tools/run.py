#!/usr/bin/env python3
"""RI02 default dry-run. No argument, receipt or manifest can enable a flight."""
import argparse
import json
from configuration import candidate
from dependencies import check_pins


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', type=int, default=0)
    parser.add_argument('--axes', type=int, default=0)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--source-head')
    parser.add_argument('--qualification')
    parser.add_argument('--manifest')
    args = parser.parse_args(argv)
    if args.execute:
        raise RuntimeError('RI02 OFFLINE ONLY: zero budget, MODE4 admission closed; execution is impossible')
    result = candidate(args.mode, args.axes)
    result.update(final_chain_sha256=check_pins(), dry_run=True, writes_parameters=False,
                  starts_simulator=False, registers_seeds=False)
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
