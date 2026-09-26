"""Read-only contact/landing-intent audit. Never changes flight acceptance."""
import argparse
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from audit_v04_diagnostic11 import audit, sha


def main():
    p = argparse.ArgumentParser(); p.add_argument('run', type=Path); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    e = audit(args.run)
    u = ULog(e['ulog']['archive'], message_name_filter_list=['trajectory_setpoint', 'vehicle_land_detected',
        'vehicle_local_position_groundtruth', 'sta_velocity_ctrl_status'])
    land = e['events']['land_command']; end = max(u.get_dataset('sta_velocity_ctrl_status').data['timestamp'])
    e['parameters'] = {k: float(u.initial_parameters[k]) for k in ['MPC_LAND_SPEED', 'MPC_Z_VEL_MAX_DN']}
    threshold = .9 * e['parameters']['MPC_LAND_SPEED']; e['landing_intent_threshold'] = threshold
    e['post_touchdown'] = {}
    # Last 30 s is well after contact; truth is diagnostic only, not an onboard input.
    for name in ['trajectory_setpoint', 'vehicle_land_detected', 'vehicle_local_position_groundtruth']:
        d = u.get_dataset(name).data; mask = d['timestamp'] >= end - 30e6
        fields = ['vz', 'landed', 'ground_contact', 'in_descend', 'has_low_throttle', 'vertical_movement', 'horizontal_movement']
        e['post_touchdown'][name] = {k: dict(min=float(np.min(d[k][mask])), max=float(np.max(d[k][mask])))
                                   for k in fields if k in d}
        e['post_touchdown'][name]['samples'] = int(mask.sum())
    d = u.get_dataset('trajectory_setpoint').data; mask = d['timestamp'] >= land
    e['landing_target_satisfies_intent'] = int(np.sum(d['vz'][mask] >= threshold))
    assert e['formal_accepted'] is False
    (out / 'audit.json').write_text(json.dumps(e, indent=2, allow_nan=False) + '\n')
    (out / 'artifacts.sha256').write_text(f"{sha(out / 'audit.json')}  {out / 'audit.json'}\n")
    print(json.dumps({k:e[k] for k in ['parameters', 'landing_intent_threshold', 'post_touchdown',
        'landing_target_satisfies_intent', 'dropout_count', 'corruption', 'faults', 'clipping', 'reset_changes', 'timing_faults']}))


if __name__ == '__main__': main()
