#!/usr/bin/env python3
"""Frozen I03 job construction; no simulation side effects."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_frozen():
    frozen = json.loads((HERE/'FROZEN.json').read_text())
    m10_path = REPO/frozen['m10_frozen']['path']
    plugin_manifest = Path(frozen['plugins_manifest']['path'])
    if digest(m10_path) != frozen['m10_frozen']['sha256']:
        raise RuntimeError('M10 frozen parameter source changed')
    if digest(plugin_manifest) != frozen['plugins_manifest']['sha256']:
        raise RuntimeError('Seeded plugin manifest changed')
    return frozen, json.loads(m10_path.read_text()), plugin_manifest.parent


def build_jobs(head):
    frozen, m10, _ = load_frozen()
    jobs = []
    for seed, algorithm, protection in frozen['ordered_jobs']:
        spec = frozen['source_algorithms'][algorithm]
        mode = spec['mode']
        parameters = dict(m10['selection'][spec['m10_selection']]['parameters'])
        parameters['MC_STA_TKO_MGT'] = frozen['protection_variants'][protection]
        jobs.append(dict(mode=mode, group='I03_'+algorithm+'_'+protection,
                         algorithm=algorithm, protection=protection, scene=frozen['scene'],
                         seed=seed, parameters=parameters, fixed_parameters=m10['fixed_parameters'],
                         formal=True, frozen_head=head,
                         simulation_speed_requested=frozen['simulation_speed_requested']))
    return frozen, jobs
