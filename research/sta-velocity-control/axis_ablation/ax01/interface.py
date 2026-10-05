#!/usr/bin/env python3
"""AX01 offline parameter/diagnostic contract. No connection or flight commands."""
import argparse
import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
NAMES = {'pid': 0, 'x': 1, 'y': 2, 'xy': 3, 'z': 4, 'xz': 5, 'yz': 6, 'xyz': 7}


def configuration(name):
    if name not in NAMES:
        raise ValueError('Unknown axis configuration; no fallback to X')
    audited = json.loads((REPO/'research/sta-velocity-control/axis_ablation/ax00/evidence.json').read_text())
    params = dict(audited['parameters']['proposed_fixed_per_axis_baseline'])
    mask = NAMES[name]
    params.update(MPC_VC_MODE=int(mask != 0), MPC_VC_AXES=mask, MPC_VC_DIV=1, MPC_VCT_TEST=0)
    return dict(name=name, parameters=params, qualification='offline only, not AX03 qualified',
                flight_enabled=False, source='AX00 inventory; identical per-axis parameters across groups')


def analyze_trace(records):
    """Real offline module Run/uORB trace or negative fixture, NOT ULog acceptance.

    Publication and sample clocks are intentionally not interchanged. The
    synchronous harness's sample clock is synthetic; this is no frequency claim.
    AX02 still must bind full ULog/output/matching/reset/window evidence.
    """
    if not records:
        raise ValueError('Empty trace')
    result = {}
    for mask in range(8):
        rows = [r for r in records if r['mask'] == mask]
        if len(rows) < 3:
            raise ValueError('Missing configuration')
        active = 0
        for i, row in enumerate(rows):
            expected = dict(mode=int(mask != 0), axes=mask, requested=mask, reject=0, pending=0,
                            valid=1, fault=0, inner=0, inner_axes=0, inner_div=1, inner_valid=1)
            if any(row[k] != v for k, v in expected.items()):
                raise ValueError('Wrong mode, request, inner loop or validity')
            if not row['sample'] or not row['timestamp']:
                raise ValueError('Missing clock')
            if i:
                previous = rows[i-1]
                if (not 2000 <= row['sample']-previous['sample'] <= 40000
                        or row['timestamp'] < previous['timestamp'] or row['seq'] != previous['seq']+1):
                    raise ValueError('Clock/sequence gap')
            if len(row['nu']) != 3 or any(
                    (not isinstance(x, (int,float)) or not math.isfinite(x)) if mask & (1 << axis)
                    else x is not None for axis,x in enumerate(row['nu'])):
                raise ValueError('Invalid state representation')
            if row['committed'] & ~mask or row['active'] & ~mask:
                raise ValueError('Unselected axis commit')
            if mask & 4 and row['phase'] in (1, 2):
                if row['pid'] != 7 or row['active'] or row['committed']:
                    raise ValueError('Invalid ground/handover')
            elif i == 0 and mask in (1, 2, 3) and row['committed'] == 0:
                if row['pid'] != (7 ^ mask):
                    raise ValueError('Horizontal priming PID axes')
            else:
                if (row['phase'] != (3 if mask & 4 else 0) or row['active'] != mask
                        or row['committed'] != mask or row['pid'] != (7 ^ mask)):
                    raise ValueError('Not selected exclusive normal control')
                active += 1
        if active < 2:
            raise ValueError('Never engaged')
        result[str(mask)] = dict(samples=len(rows), normal_samples=active, remaining_pid_axes=7 ^ mask)
    if len(records) != sum(v['samples'] for v in result.values()):
        raise ValueError('Unexpected mask')
    return dict(accepted=True, meaning='offline module trace, NOT flight/ULog qualification', masks=result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('configuration', choices=NAMES, nargs='?')
    p.add_argument('--trace-log', type=Path)
    a = p.parse_args()
    if a.trace_log:
        rows = [json.loads(line[len('AX01_SAMPLE '):]) for line in a.trace_log.read_text().splitlines()
                if line.startswith('AX01_SAMPLE ')]
        print(json.dumps(analyze_trace(rows), indent=2))
    elif a.configuration:
        print(json.dumps(configuration(a.configuration), indent=2))
    else:
        print(json.dumps(dict(configurations=NAMES, flight_enabled=False,
            next='AX02 owns live runner, backup/restore and flight protocol; no execute option in AX01'), indent=2))


if __name__ == '__main__':
    main()
