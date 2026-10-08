"""AX04 preregistration: deterministic balanced blocks, no flight operations."""
import copy
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
OLD = HERE.parent / 'ax02'
BASE_HEAD = '4d5e2a7f5dfee5b12615d8d07cbe3d3519f7bd55'
NAMES = ('PID', 'X', 'Y', 'Z', 'XY', 'XZ', 'YZ', 'XYZ')
MASKS = dict(zip(NAMES, (0, 1, 2, 4, 3, 5, 6, 7)))
SEEDS = tuple(range(52001, 52021))
ORDER_SEED = 62001
BOOTSTRAP_SEED = 62002
SIGN_SEED = 62003
BOOTSTRAPS = 200000
SIGN_DRAWS = 100000
MIN_PRACTICAL = .001  # m/s, plus 10% relative; inherited V08 convention, not tuned


def build():
    old = json.loads((OLD / 'execution.json').read_text())
    d = copy.deepcopy(old)
    d.update(stage='AX05-axis-ablation-formal01', maximum_attempts=320,
             seeds=list(SEEDS), task_seeds={t: list(SEEDS) for t in ('H', 'V')},
             output_root='/home/yr/Desktop/codev doc/experiments/VELOCITY-AXIS-ABLATION-20261008/AX05/formal01')
    rng = np.random.Generator(np.random.PCG64(ORDER_SEED))
    # Williams rows; 20 is not divisible by eight. Complement the extra four
    # rows across tasks: every treatment occupies every position five times
    # pooled, and two/three times in each task. No claim of perfect carryover.
    base = np.array([0, 1, 7, 2, 6, 3, 5, 4])
    rows = [(base + i) % 8 for i in range(8)]
    jobs = []
    for task_index, task in enumerate(('H', 'V')):
        order = list(range(8)) * 2 + list(range(4*task_index, 4*task_index+4))
        rng.shuffle(order)
        seeds = rng.permutation(SEEDS).tolist()
        for block_index, (seed, row) in enumerate(zip(seeds, order), 1):
            for position, name_index in enumerate(rows[row], 1):
                name = NAMES[int(name_index)]
                mask = MASKS[name]
                template = copy.deepcopy(next(j for j in old['jobs'] if j['task'] == task and j['candidate'] == name))
                template.update(id=f'run{len(jobs)+1:03d}', seed=seed,
                                block=block_index, position=position)
                jobs.append(template)
    d['jobs'] = jobs
    d['authority'] = 'AX04 offline only; separate explicit AX05 authorization and exact receipt required'
    d['order_rationale'] = 'All eight qualified in AX03. Balance PID too; same seed blocks across H/V, order frozen below.'
    d['V_safety_gate'] = 'Prior AX03 V24 qualification plus formal H160/140paired gate; no additional pilot'
    d['stop_rule'] = 'First mandatory safety/log or newly available paired risk failure stops batch; no retry or replacement'
    d['formal_order'] = dict(engine='numpy.PCG64', randomization_seed=ORDER_SEED,
        method='Williams eight rows, two complete sets plus complementary four rows; task gates H then V',
        individual_failure='stop immediately', paired_risk='check all newly available pairs immediately; unresolved pairs must finish within current block',
        qualified_pilot='AX03 all48 accepted; no new formal pilot, all320 count toward budget')
    return d


def expanded(d):
    return [{**j, 'parameters': {**d['fixed_parameters'], **j['parameters']}} for j in d['jobs']]


def validate(d):
    if d != build():
        raise ValueError('Formal design/order/budget/parameters differs from deterministic preregistration')
    if len(d['jobs']) != 320 or set(d['seeds']) & set(range(41001, 41021)):
        raise ValueError('Budget or protected seed conflict')
    return True


def empty_outcomes(d):
    return [{**{k: j[k] for k in ('id', 'task', 'seed', 'candidate', 'mode', 'axes')},
             'status': 'unattempted', 'reason': 'AX04 only freezes protocol; AX05 not started'}
            for j in expanded(d)]
