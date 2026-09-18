#!/usr/bin/env python3
"""Build the immutable I04 job list; no simulator or Git mutation."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_frozen():
    frozen = json.loads((HERE/'FROZEN.json').read_text())
    for key in ('m10_frozen', 'calibration', 'plugins_manifest'):
        spec = frozen[key]
        path = Path(spec['path']) if Path(spec['path']).is_absolute() else REPO/spec['path']
        if digest(path) != spec['sha256']:
            raise RuntimeError(key+' fingerprint changed: '+str(path))
    m10 = json.loads((REPO/frozen['m10_frozen']['path']).read_text())
    return frozen, m10, Path(frozen['plugins_manifest']['path']).parent


def build_jobs(head):
    frozen, m10, _ = load_frozen()
    mode = frozen['mode']
    jobs = []
    for seed, label in frozen['ordered_jobs']:
        selected = '0' if label == 'pid_smoke' else ('2' if label == 'original_ista_regression' else '1')
        parameters = dict(m10['selection'][selected]['parameters'])
        parameters.update(frozen['roll_parameters'])
        parameters.update(MC_RTC_MODE=mode['pid'] if label == 'pid_smoke' else
                          mode['original_ista'] if label == 'original_ista_regression' else
                          mode[label], MC_STA_AXES=0 if label == 'pid_smoke' else frozen['axes'],
                          MC_RTC_DIV=frozen['divisor'], MC_STA_TKO_MGT=frozen['MC_STA_TKO_MGT'])
        jobs.append(dict(mode=parameters['MC_RTC_MODE'], group='I04_'+label, algorithm=label,
                         scene=frozen['scene'], seed=seed, parameters=parameters,
                         fixed_parameters=m10['fixed_parameters'], formal=True, frozen_head=head,
                         simulation_speed_requested=frozen['simulation_speed_requested']))
    return frozen, jobs
