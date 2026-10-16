"""Per-class, opt-in binding; never patch historical module globals.

The monitor methods, full-history predicates and 500000 us age checks are
inherited unchanged. Only start_heading's reader constructor is replaced.
"""
import ast
import inspect
import json
from pathlib import Path
import textwrap
import time

import importlib.util
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('r03_monitor02_incremental', HERE/'incremental.py')
incremental = importlib.util.module_from_spec(spec)
spec.loader.exec_module(incremental)


def bind_start_heading(function):
    """Delete exactly the known generic import, supply the isolated constructor.

    All other AST nodes remain identical, including when 'now' is queried,
    prearm state, reference/reset checks, the full replay and its 500 ms test.
    """
    source = Path(inspect.getsourcefile(function)).resolve()
    if source != incremental.REPO/'research/sta-velocity-control/axis_ablation/ax04/run.py':
        raise ValueError('Unexpected inherited heading implementation')
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    body = tree.body[0].body
    imports = [node for node in body if isinstance(node, ast.ImportFrom)
               and node.module == 'position_live']
    if len(imports) != 1 or ast.dump(imports[0]) != ast.dump(
            ast.parse('from position_live import PositionLiveLog').body[0]):
        raise ValueError('Unexpected inherited reader binding')
    body.remove(imports[0])
    namespace = dict(function.__globals__)
    namespace['PositionLiveLog'] = incremental.PositionLiveLog
    exec(compile(ast.fix_missing_locations(tree), str(source), 'exec'), namespace)
    return namespace[function.__name__]


def make_checks(base_cls):
    start = bind_start_heading(base_cls.start_heading)

    class IncrementalChecks(base_cls):
        start_heading = start

        def monitor(self, phase, cli, topic, output, state):
            began = time.monotonic()
            actual_positions = []
            error = None

            def observed_topic(name, *args, **kwargs):
                value = topic(name, *args, **kwargs)
                if name == 'vehicle_local_position':
                    actual_positions.append(value.get('timestamp'))
                return value

            try:
                return super().monitor(phase, cli, observed_topic, output, state)
            except Exception as exc:
                error = repr(exc)
                raise
            finally:
                reader = getattr(self, 'live', None)
                evidence = dict(phase=phase, host_elapsed_s=time.monotonic()-began,
                    actual_position_cli_timestamps=actual_positions,
                    raw_reader=dict(getattr(reader, 'last_timing', {})), error=error,
                    safety_checks='Unchanged complete-history heading/landing checks',
                    transport_max_age_us=500000)
                with (Path(output)/'r03_monitor_timing.jsonl').open('a') as stream:
                    stream.write(json.dumps(evidence, allow_nan=False)+'\n')

    return IncrementalChecks
