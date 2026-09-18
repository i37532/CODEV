#!/usr/bin/env python3
"""Two disarmed boots: MODE=3 save/load, PID return and AXES=3/7 rejection."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]/'scripts'))

from verify_m06_restart import main


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    frozen=json.loads((HERE/'FROZEN.json').read_text())
    config=dict(frozen['roll_parameters'], MC_RTC_MODE=3, MC_STA_AXES=1,
                MC_RTC_DIV=1, MC_STA_TKO_MGT=0)
    path=args.output.resolve().parent/'i04_restart_config.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and json.loads(path.read_text()) != config:
        raise RuntimeError('Existing restart config differs')
    if not path.exists(): path.write_text(json.dumps(config,indent=2)+'\n')
    main(args.output.resolve(), path, modes=(3,), accepted_masks=(1,), rejected_masks=(3,7))
