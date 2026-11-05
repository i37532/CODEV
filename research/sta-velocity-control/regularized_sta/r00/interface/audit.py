#!/usr/bin/env python3
"""R00 read-only source/interface assertions, not controller or flight tests.

Print evidence to stdout; never rewrite sources, logs, configuration or results.
This audits the R00 source only. Expected old-mode assertions become historical
after R02 intentionally introduces MODE3 and must not qualify new flight code.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPO = Path(__file__).resolve().parents[5]
BASE = REPO / 'src/modules/mc_pos_control'
CORE = BASE / 'PositionControl'
checks = []


def read(path):
    return path.read_text()


def check(name, ok, **evidence):
    checks.append(dict(name=name, passed=bool(ok), **evidence))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    selector = read(CORE / 'VelocityControlSelector.hpp')
    params = read(BASE / 'mc_pos_control_params.c')
    position = read(CORE / 'PositionControl.cpp')
    protection = read(CORE / 'StaVelocityProtection.cpp')
    kernel = read(CORE / 'StaVelocityControl.cpp')
    module = read(BASE / 'MulticopterPositionControl.cpp')
    requested = ['MPC_VC_EPS_X', 'MPC_VC_EPS_Y', 'MPC_VC_EPS_Z']
    definition_output = subprocess.check_output(
        ['rg', '-n', r'PARAM_DEFINE_\w+\(', 'src', 'boards'], cwd=REPO, text=True)
    defined = set(re.findall(r'PARAM_DEFINE_\w+\(\s*(\w+)', definition_output))
    check('new_epsilon_parameter_names_unused', not set(requested) & defined,
          candidates={x: len(x) for x in requested}, searched='src and boards PARAM_DEFINE declarations')
    check('epsilon_names_fit_mavlink_16', all(len(x) <= 16 for x in requested))
    check('mode3_unallocated_in_velocity_selector', 'mode > 2' in selector)
    check('mode2_reserved_rejected', 'mode == 2 ||' in selector and '@value 2 Reserved (unavailable)' in params)
    check('pid_default_unchanged', 'PARAM_DEFINE_INT32(MPC_VC_MODE, 0)' in params
          and 'PARAM_DEFINE_INT32(MPC_VC_AXES, 0)' in params)
    lines = [i for i, line in enumerate(position.splitlines(), 1)
             if 'sqrtf(fabsf(s)) * sign(s)' in line]
    check('four_nonlinear_reconstructions', len(lines) == 4, lines=lines,
          functions=['updateHoverThrust', '_velocityControlEstaZ', '_velocityControlEstaXYZ', '_velocityControlEstaMixed'])
    check('candidate_owner_axis_revision_payload', all(s in kernel for s in
          ['candidate.owner == this', 'candidate.axis == candidate.sealed_axis',
           'candidate.revision == _revision[candidate.axis]', 'std::memcmp(payload.data()']))
    check('protection_real_sample_dt', '_result.raw_dt < .002f || _result.raw_dt > .04f' in protection
          and 'f.integration_dt > 0.f ? f.integration_dt : _result.raw_dt' in protection)
    check('ff_once_after_correction_limit',
          '_result.a_req[i] = limited + (std::isfinite(f.ff[i]) ? f.ff[i] : 0.f)' in protection)
    check('legacy_pid_dt_and_sample_time_both_present',
          'time_stamp_now = local_pos.timestamp' in module and 'velocity_frame.sample = local_pos.timestamp_sample' in module
          and 'math::constrain(((time_stamp_now - _time_stamp_last_loop) * 1e-6f), 0.002f, 0.04f)' in module)
    check('actual_inner_pid_gate', all(s in module for s in
          ['_rate_diagnostic.effective_mode == 0', '_rate_diagnostic.effective_axes == 0',
           '_rate_diagnostic.div_eff == 1', '!_rate_diagnostic.termination']))
    formats = {}
    for name in ('sta_velocity_ctrl_status', 'velocity_ctrl_selection'):
        generated = REPO / f'build/px4_sitl_default/msg/topics_sources/{name}.cpp'
        text = read(generated)
        fields = re.search(r'constexpr char __orb_\w+_fields\[\] = "([^"]+)";', text).group(1)
        # Logger::write_format snprintf includes all o_fields (also padding).
        # Include terminating NUL in the buffer capacity requirement.
        size = len((name + ':' + fields).encode()) + 1
        formats[name] = dict(format_bytes=size, generated_sha256=sha(generated))
        check(name + '_format_within_1500', size < 1500, **formats[name])
        check(name + '_queue8', 'uint8 ORB_QUEUE_LENGTH = 8' in read(REPO / f'msg/{name}.msg'))
    files = [CORE / 'VelocityControlSelector.hpp', CORE / 'StaVelocityControl.cpp',
             CORE / 'StaVelocityProtection.cpp', CORE / 'PositionControl.cpp',
             BASE / 'MulticopterPositionControl.cpp', BASE / 'mc_pos_control_params.c',
             REPO / 'msg/sta_velocity_ctrl_status.msg', REPO / 'msg/velocity_ctrl_selection.msg',
             REPO / 'src/modules/logger/logged_topics.cpp']
    result = dict(stage='R00-interface', source_head=subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        check_count=len(checks), checks=checks, source_sha256={str(p.relative_to(REPO)): sha(p) for p in files},
        production_changes=False, flight_count=0, controller_runtime_tests=0,
        accepted=all(x['passed'] for x in checks))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
