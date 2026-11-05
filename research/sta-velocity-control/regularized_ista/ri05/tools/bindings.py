"""Private reuse of frozen RI02 mathematics and final R03 transport/science.

Imports do not start processes, write parameters, or grant qualification.
Generic names used inside RI02 are scoped and restored; old globals unchanged.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types

HERE = Path(__file__).resolve().parent
STAGE = HERE.parent
REPO = HERE.parents[4]
RI02 = STAGE.parent / 'ri02/tools'


def load(name, path):
    key = '_ri05_' + name
    path = Path(path).resolve()
    if key in sys.modules:
        if Path(sys.modules[key].__file__).resolve() != path:
            raise ValueError('RI05 private module identity collision')
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[key]
        raise
    return module


def clone(function, **bindings):
    result = types.FunctionType(function.__code__, dict(function.__globals__, **bindings),
        function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def frozen_ri02():
    names = ('dependencies', 'configuration', 'analyzer', 'full_chain')
    saved = {name: sys.modules.get(name) for name in names}
    try:
        modules = {}
        for name in names:
            modules[name] = load('frozen_ri02_' + name, RI02 / (name + '.py'))
            sys.modules[name] = modules[name]
        return types.SimpleNamespace(**modules)
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


KERNEL = frozen_ri02()
# Match the actual final R03 CLI bootstrap: runtime first, science second.
# This prevents the analyzer's V07 generic import paths selecting homonyms
# before the V08 execution dependency chain has been loaded.
OLD_RUNNER = KERNEL.dependencies.final_monitor_bindings()['runner']
FINAL = KERNEL.dependencies.final_analysis()
# Analyzer-first imports can leave the older V07 homonym in sys.modules.
# Pin the exact V08 recorder/release implementation used by R03 execution,
# privately, without rebinding any frozen module's globals.
RAM_LOG = load('ram_log_v08', REPO / 'research/sta-velocity-control/v08/protocol02/ram_log.py')


def api():
    return load('protocol', STAGE / 'protocol.py')


def local(name):
    if name not in ('analyzer', 'runner', 'replay'):
        raise ValueError('Unknown RI05 tool dependency')
    saved = sys.modules.get('bindings')
    sys.modules['bindings'] = sys.modules.get(__name__, types.SimpleNamespace(**globals()))
    try:
        return load('tools_' + name, HERE / (name + '.py'))
    finally:
        if saved is None:
            sys.modules.pop('bindings', None)
        else:
            sys.modules['bindings'] = saved


def digest(path):
    return KERNEL.dependencies.digest(path)


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    OLD_RUNNER.save(Path(path), value)


def exact(left, right):
    return json.dumps(left, sort_keys=True, separators=(',', ':'), allow_nan=True) == \
        json.dumps(right, sort_keys=True, separators=(',', ':'), allow_nan=True)


def source_binding():
    return dict(ri02={str((RI02 / name).relative_to(REPO)): digest(RI02 / name)
                     for name in ('analyzer.py', 'full_chain.py', 'configuration.py', 'dependencies.py')},
        r03=KERNEL.dependencies.check_pins(), implicit_mode=4, implicit_axes=[3, 7],
        ram_log_sha256=digest(Path(RAM_LOG.__file__)),
        numeric_thresholds_changed=False, raw_records_preserved=True)
