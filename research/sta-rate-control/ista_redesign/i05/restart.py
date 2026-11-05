#!/usr/bin/env python3
"""I05 subgate restart/save/mask checks without arming."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'scripts'))

from verify_m06_restart import main


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--subgate', choices=('A',), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    frozen = json.loads((HERE / f'FROZEN_{args.subgate}.json').read_text())
    config = dict(frozen['parameters'], MC_RTC_MODE=3,
                  MC_STA_AXES=frozen['axes'], MC_RTC_DIV=frozen['divisor'])
    config_path = args.output.resolve().parent / f'i05_{args.subgate.lower()}_restart_config.json'
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        raise RuntimeError('Existing restart config differs')
    if not config_path.exists():
        config_path.write_text(json.dumps(config, indent=2) + '\n')
    main(args.output.resolve(), config_path, modes=(3,),
         accepted_masks=(1, 3), rejected_masks=(7,))
