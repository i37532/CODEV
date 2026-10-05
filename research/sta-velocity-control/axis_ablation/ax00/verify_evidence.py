#!/usr/bin/env python3
"""Recheck AX00 evidence against files; no simulator, no parameter writes."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
e = json.loads((HERE/'evidence.json').read_text())
checks = 0


def check(ok, label):
    global checks
    if not ok: raise RuntimeError(label)
    checks += 1


for name, expected in e['source_sha256'].items():
    check(hashlib.sha256((REPO/name).read_bytes()).hexdigest() == expected, name)
for name in ('TODO', 'PROMPTS', 'STATUS'):
    filename = 'VELOCITY_AXIS_ABLATION_'+name+'_CN.md'
    check((HERE.parent/'plan/v1'/filename).read_bytes() ==
          (HERE.parent/'plan/ax00_entry'/filename).read_bytes(), filename)
p = e['parameters']
for run, mode in (('run01', '0'), ('run02', '1')):
    actual = p['historical_runtime'][run]['audited_parameters']
    for k, v in p['v08_selected_overrides'][mode].items():
        check(actual[k] == v, run+':'+k)
for key, value in dict(MPC_XY_VEL_P_ACC=2.16, MPC_XY_VEL_I_ACC=.48,
                      MPC_XY_VEL_D_ACC=.24, MPC_Z_VEL_P_ACC=4,
                      MPC_Z_VEL_I_ACC=2, MPC_Z_VEL_D_ACC=0,
                      MPC_VC_DIV=1, MC_RTC_MODE=0, MC_STA_AXES=0,
                      MC_RTC_DIV=1, MC_RATT_TEST=0, MC_STA_TKO_MGT=0).items():
    check(p['proposed_fixed_per_axis_baseline'][key] == value, key)
check(not p['new_matrix_qualification'], 'not flight-qualified')
check(not e['seeds']['candidate_matches'] and not e['seeds']['invalid_json'], 'scan result')
check(e['seeds']['forbidden_numbers'] == list(range(41001, 41021)), 'V09 isolation')
check(hashlib.sha256(Path(e['persisted_eeprom']['path']).read_bytes()).hexdigest() ==
      e['persisted_eeprom']['sha256'], 'EEPROM unchanged')
print(f'PASS {checks} evidence checks; no flight or full PX4 regression')
