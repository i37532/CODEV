"""Complete RI00-origin profiles. These are OFFLINE candidates, not admission."""
import json
import math
from pathlib import Path

from dependencies import REPO, digest

SOURCE = REPO / 'research/sta-velocity-control/regularized_ista/ri00/results/interface.json'
SOURCE_SHA = '37729b3d84309c899dce52803c234ef109f738ac0d1a4e1520a729dd18cbeb81'
MODES = {0: 'PID', 3: 'R-STA', 4: 'R-ISTA'}
AXES = (1, 4, 3, 7)
RATE = dict(MC_RTC_MODE=0, MC_STA_AXES=0, MC_RTC_DIV=1,
            MC_RATT_TEST=0, MC_STA_TKO_MGT=0, MPC_VC_DIV=1)


def source():
    if digest(SOURCE) != SOURCE_SHA:
        raise ValueError('RI00 parameter provenance changed')
    return json.loads(SOURCE.read_text())['full_r03_parameters']


def validate(mode, axes, parameters, *, allowed_task_modes=(0,)):
    if type(mode) is not int or mode not in MODES:
        raise ValueError('New candidates are PID/R-STA/R-ISTA only; MODE1/2 are not this matrix')
    if type(axes) is not int or (mode == 0 and axes != 0) or (mode != 0 and axes not in AXES):
        raise ValueError('Explicit axes required; no default-to-X mapping')
    if set(source()) - set(parameters):
        raise ValueError('Incomplete full parameter profile')
    if type(parameters.get('MPC_VCT_TEST')) is not int or parameters['MPC_VCT_TEST'] not in allowed_task_modes:
        raise ValueError('Unfrozen/offline task mode')
    for key, value in {**RATE, 'MPC_VC_MODE': mode, 'MPC_VC_AXES': axes}.items():
        if type(parameters.get(key)) not in (int, float) or parameters[key] != value:
            raise ValueError('Wrong fixed parameter ' + key)
    for key, value in parameters.items():
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('Nonfinite/non-numeric parameter ' + key)
    for axis in 'XYZ':
        for kind in ('L1', 'L2', 'NU', 'A'):
            if parameters['MPC_VC_' + kind + '_' + axis] <= 0:
                raise ValueError('Invalid gain/limit')
        if not .001 <= parameters['MPC_VC_EPS_' + axis] <= 1:
            raise ValueError('Invalid epsilon')
    return True


def candidate(mode=0, axes=0):
    values = {**source(), **RATE, 'MPC_VC_MODE': mode, 'MPC_VC_AXES': axes, 'MPC_VCT_TEST': 0}
    validate(mode, axes, values)
    return dict(stage='RI02', mode=mode, axes=axes, algorithm=MODES[mode], parameters=values,
                source=str(SOURCE.relative_to(REPO)), source_sha256=SOURCE_SHA,
                flight_authorized=False, maximum_attempts=0, seed=None,
                production_admission=False if mode == 4 else 'existing semantics only',
                candidate_only=True, new_statistical_groups=list(MODES.values()))
