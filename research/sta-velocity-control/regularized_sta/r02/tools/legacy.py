"""Explicit unchanged low-level validators; never patch a legacy module global.

These modules predate packages. Resolve only the audited directories and load
leaf modules by distinct names where a generic historical name would collide.
Whole historical analyses run in a separate process, not through this importer.
"""
import importlib.util
import sys
from config import REPO

DIRECTORIES = (
    REPO / 'research/sta-velocity-control/axis_ablation/ax02',
    REPO / 'research/sta-velocity-control/v07/protocol07',
    REPO / 'research/sta-velocity-control/v08/protocol02',
    REPO / 'research/sta-velocity-control/scripts',
    REPO / 'research/sta-velocity-control/v06/soft_landing',
    REPO / 'research/sta-rate-control/scripts',
    REPO / '.px4-python',
)


def initialize():
    for path in reversed(DIRECTORIES):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def leaf(name, relative):
    initialize()
    key = 'r02_inherited_' + name
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, REPO / relative)
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


def parameter_io():
    initialize()
    import run_v00
    return run_v00


def clock_policy():
    initialize()
    import v04_attitude_clock09
    return v04_attitude_clock09


def task_checks():
    return leaf('task', 'research/sta-velocity-control/axis_ablation/ax02/task.py')


def cadence_checks():
    return leaf('cadence', 'research/sta-velocity-control/axis_ablation/ax02/cadence.py')
