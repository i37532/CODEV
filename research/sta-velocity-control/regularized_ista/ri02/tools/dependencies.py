"""Private, pinned reuse of the final R03 chain; importing cannot fly."""
import hashlib
import importlib.util
from pathlib import Path
import sys
from functools import lru_cache

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
RESEARCH = REPO / 'research/sta-velocity-control'
OLD = RESEARCH / 'regularized_sta'
PINS = {
    'r03_revision11/runner.py': '16f05b02ec004e1e710c4e5c1f708f139c3e845fc029f68db783634ff7cb00de',
    'r03_revision11/analyzer.py': 'bd95b11b9139fbfd79e4ac96d3e005adcd79b6a26b106dcfa4fe28ebbec70a7f',
    'r03_position11/adapter.py': '8d0415b82ec77c22103df016b06da83289006a538e91a2cb8c9c66706365ae41',
    'r03_position11/callbacks.py': 'd627234a62f51fd8350789c9f642167b1d390c282ccf3428bd3430e25093b670',
    'r03_position11/policy.py': 'c4665af0aa50cf3782a646b457f98f30c880e6c943eab3572bb47d8853024507',
    'r03_prearm04/integration.py': '161dd6273e37dc625472c389278df12cfd2153d3f459e0da37fc86c0c2453235',
    'r03_warmup10/evidence.py': 'b476012ddb4978e01982f37ff7fb3e741dbb036bfc002d679cae439f844e8c7e',
    'r03_numeric05/checker.py': '2eadb904b45b34e93232706418de7e097b7e34970036f0d9c7109707685c37bf',
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def check_pins():
    actual = {name: digest(OLD / name) for name in PINS}
    if actual != PINS:
        raise ValueError('Immutable R03 final-chain dependency changed')
    return actual


def load(name, path):
    key = '_ri02_tools_' + name
    path = Path(path).resolve()
    if key in sys.modules:
        if Path(sys.modules[key].__file__).resolve() != path:
            raise ValueError('Private module identity collision')
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


def local(name):
    return load('local_' + name, HERE / (name + '.py'))


def final_analysis():
    check_pins()
    return load('final_analysis', OLD / 'r03_revision11/analyzer.py')


def callbacks():
    check_pins()
    return load('callbacks', OLD / 'r03_position11/callbacks.py')


@lru_cache(maxsize=1)
def candidate_arithmetic():
    check_pins()
    return load('candidate_arithmetic', OLD / 'r03_numeric05/checker.py')


def parameter_io():
    # Exactly the existing BSON/CLI codec, not a handwritten reduced archive.
    for path in (RESEARCH / 'scripts', REPO / '.px4-python'):
        if str(path) not in sys.path:
            sys.path.append(str(path))
    return load('parameter_io', RESEARCH / 'scripts/run_v00.py')


def final_monitor_bindings():
    """Expose existing monitor classes only; never execute flight_main/main."""
    check_pins()
    runner = load('final_runner', OLD / 'r03_revision11/runner.py')
    return dict(runner=runner, analyzer=final_analysis(), authority=False,
                source_sha256=check_pins())
