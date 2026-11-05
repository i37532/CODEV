"""R02 offline candidates. No flight manifest, budget, parameter write or launch."""
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
SOURCE = REPO / 'research/sta-velocity-control/axis_ablation/ax04/execution.json'
SOURCE_SHA256 = '308aa5a4e52828585bbf6ee3ec0be339a8081475663ceb759de0aee40167d2d3'
RATE = dict(MC_RTC_MODE=0, MC_STA_AXES=0, MC_RTC_DIV=1,
            MC_RATT_TEST=0, MC_STA_TKO_MGT=0)
MODES = {0: 'PID', 1: 'hard-sign ESTA', 3: 'regularized explicit STA'}
NEW_AXES = (1, 4, 3, 7)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(mode, axes, parameters, *, allowed_task_modes=(0,)):
    if type(mode) is not int or mode not in MODES:
        raise ValueError('Only explicit MODE0/1/3; MODE2 is reserved and rejected')
    if type(axes) is not int or (mode == 0 and axes != 0) or (mode == 1 and axes not in range(1, 8)) or (mode == 3 and axes not in NEW_AXES):
        raise ValueError('Unavailable/unknown axes; never silently map to X')
    expected = {**RATE, 'MPC_VC_MODE': mode, 'MPC_VC_AXES': axes, 'MPC_VC_DIV': 1}
    required = set(json.loads(SOURCE.read_text())['fixed_parameters']) | {'MPC_VC_EPS_' + axis for axis in 'XYZ'}
    if required - set(parameters):
        raise ValueError('Incomplete full parameter configuration: ' + ', '.join(sorted(required - set(parameters))))
    if type(parameters.get('MPC_VCT_TEST')) is not int or parameters['MPC_VCT_TEST'] not in allowed_task_modes:
        raise ValueError('R02 candidate must have MPC_VCT_TEST=0; only an explicit historical task replay can differ')
    for name, value in expected.items():
        if parameters.get(name) != value:
            raise ValueError('Wrong fixed configuration ' + name)
    for axis in 'XYZ':
        epsilon = parameters.get('MPC_VC_EPS_' + axis)
        if not isinstance(epsilon, (int, float)) or isinstance(epsilon, bool) or not math.isfinite(epsilon) or not .001 <= epsilon <= 1:
            raise ValueError('epsilon outside [.001, 1] m/s: ' + axis)
        for prefix in ('MPC_VC_L1_', 'MPC_VC_L2_', 'MPC_VC_NU_', 'MPC_VC_A_'):
            value = parameters.get(prefix + axis)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError('Invalid gain/limit ' + prefix + axis)
    return True


def candidate(mode=0, axes=0, epsilon=(.01, .01, .02)):
    if digest(SOURCE) != SOURCE_SHA256:
        raise ValueError('AX04 fixed parameter source fingerprint changed')
    if len(epsilon) != 3:
        raise ValueError('Exactly three epsilon values required')
    original = json.loads(SOURCE.read_text())['fixed_parameters']
    parameters = {**original, **RATE, 'MPC_VC_MODE': mode, 'MPC_VC_AXES': axes,
                  'MPC_VC_DIV': 1, 'MPC_VCT_TEST': 0,
                  **{'MPC_VC_EPS_' + axis: value for axis, value in zip('XYZ', epsilon)}}
    validate(mode, axes, parameters)
    return dict(stage='R02-offline-only', mode=mode, axes=axes, divisor=1,
                parameters=parameters, parameter_source=str(SOURCE.relative_to(REPO)),
                parameter_source_sha256=SOURCE_SHA256,
                source_qualification='AX04 historical parameters only; no inherited source/flight qualification',
                new_parameters={'MPC_VC_EPS_' + axis: value for axis, value in zip('XYZ', epsilon)},
                flight_authorized=False, maximum_attempts=0)
