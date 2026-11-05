"""Read-only failed RI04 ULog -> small C++ fixture + independent double evidence.

The historical audit helpers are loaded from the exact flight-result git object,
not from patched production source. No historical source/log/verdict is rewritten.
This is a counterfactual offline repair fixture, never flight qualification.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import types

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
DATA = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024')
RUN = DATA/'RI04/B/batch01/run003'
ENTRY = '50f354678fafb3fd4d4a09530e340f0eefa60f55'
SOURCE = '74327418e18eafd421e18b48fe3964fdad63cfb5'
AUDIT = 'research/sta-velocity-control/regularized_ista/ri04/results/audit_failure.py'
RAW = {'06_07_48.ulg': '04bee85bf9fa20aaf42e29b0bcf9f0c4c5315caa4c7e89ceace9e63d860fdc0f',
       'log001.ulg': '5fcc91abb13ed790995d6d2a05e9f8044c0fd22fb0401636c2f0dff9d086c378'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def historical_helpers():
    raw = subprocess.check_output(['git', 'show', ENTRY+':'+AUDIT], cwd=REPO)
    module = types.ModuleType('ri04_hte_fix_historical_audit')
    module.__file__ = str(REPO/AUDIT)
    exec(compile(raw, ENTRY+':'+AUDIT, 'exec'), module.__dict__)
    return module, hashlib.sha256(raw).hexdigest()


def continuous_mapping(old_hover, new_hover, correction, ff, nu, nu_limit, correction_limit):
    """Solve H_new*(a_new+FF-g)/g = previous normalized vertical mapping.

    Independent double equation solution; not the production ratio-minus-one
    expression. Only frozen inputs/geometry are compared, not a next-frame plant.
    """
    args = (old_hover, new_hover, correction, ff, nu, nu_limit, correction_limit)
    require(all(math.isfinite(x) for x in args), 'Non-finite HTE input')
    require(.1 <= old_hover <= .9 and .1 <= new_hover <= .9
            and nu_limit > 0 and correction_limit > 0, 'Invalid HTE domain')
    gravity = 9.80665
    before = (correction + ff - gravity)*old_hover/gravity
    applied = before*gravity/new_hover - ff + gravity
    delta = applied-correction
    new_nu = nu+delta
    after = (applied + ff-gravity)*new_hover/gravity
    return dict(correction_before=correction, nu_before=nu, correction_after=applied,
                nu_after=new_nu, delta=delta, normalized_vertical_before=before,
                normalized_vertical_after=after, continuity_residual=after-before,
                nu_bound_ok=abs(new_nu) <= nu_limit,
                correction_bound_ok=abs(correction) <= correction_limit and abs(applied) <= correction_limit,
                actually_executed=False, flight_accepted=False)


def render_header(values):
    lines = ['// Generated from unchanged RI04 run003 ULog by fixture.py.',
             '// Offline counterfactual repair boundary; original flight remains FAILED.',
             '#pragma once', '#include <cstdint>', 'namespace ri04_hte_fixture {',
             'constexpr const char *SourceHead = "'+SOURCE+'";',
             'constexpr const char *RawSha256 = "'+RAW['log001.ulg']+'";']
    for key, value in values.items():
        if key.endswith('Sample'):
            lines.append('constexpr uint64_t '+key+' = '+str(value)+'ULL;')
        else:
            literal = format(value, '.17g')
            if '.' not in literal and 'e' not in literal:
                literal += '.0'
            lines.append('constexpr float '+key+' = '+literal+'f;')
    return '\n'.join(lines+['} // namespace ri04_hte_fixture', ''])


def extract(run=RUN):
    from pyulog import ULog
    old, helper_sha = historical_helpers()
    run = Path(run).resolve()
    before = old.snapshot(run)
    result = json.loads((run/'result.json').read_text())
    require(result['source_head'] == SOURCE and result['success'] is False
            and result['error'] == "RuntimeError('First update/retry failure')", 'Not original failed attempt')
    require({x.name for x in run.glob('*.ulg')} == set(RAW), 'Unexpected raw files')
    decoded, raw_records = {}, []
    for name, digest in RAW.items():
        require(old.sha(run/name) == digest, 'Historical ULog changed')
        u = ULog(str(run/name))
        d = u.get_dataset('sta_velocity_ctrl_status').data
        q = u.get_dataset('velocity_ctrl_selection').data
        joined = old.exact_join(d, q)
        require(not u.dropouts, 'Historical ULog dropout')
        decoded[name] = u, d, q, joined
        raw_records.append(dict(name=name, sha256=digest, bytes=(run/name).stat().st_size,
                                diagnostic_rows=len(joined), dropouts=0))
    u, d, q, joined = decoded['log001.ulg']
    first = old.first_index(d, 'first_fail')
    require(first is not None and int(d['timestamp_sample'][first]) == 43076000, 'Failure boundary differs')
    last, j = first-1, joined[first-1]
    require(int(d['timestamp_sample'][last]) == 43064000 and int(d['sta_flags'][last]) == 8
            and not q['ri_cache_valid'][j] and not d['constraint_bits'][last], 'StateLimit/cache signature differs')
    require(int(d['sta_fault'][first]) == 10 and int(d['first_fail'][first]) == 56
            and int(d['pid_calls'][first]) == 2 and int(d['retry_result'][first]) == 2, 'Failure signature differs')
    hte = u.get_dataset('hover_thrust_estimate').data
    hi = old.first_index(hte, 'valid')
    require(hi == 22 and int(hte['timestamp'][hi]) == 43076000, 'First valid HTE differs')
    params = u.initial_parameters
    gains = [float(params[k]) for k in ('MPC_VC_L1_Z', 'MPC_VC_L2_Z', 'MPC_VC_EPS_Z')]
    candidates = []
    for i in range(first):
        k = joined[i]
        if not q['ri_valid'][k]:
            continue
        reference = old.solve(float(d['s[2]'][i]), float(q['ri_h'][k]), float(d['nu_before[2]'][i]), *gains)
        recorded = dict(p=float(q['ri_p[2]'][k]), nu_candidate=float(q['ri_nu_candidate[2]'][k]),
                        correction=float(q['ri_a_ideal[2]'][k]))
        errors = {key: abs(reference[key]-value) for key, value in recorded.items()}
        require(max(errors.values()) <= 2e-6, 'Double implicit solve differs from recorded candidate')
        candidates.append(dict(sample=int(d['timestamp_sample'][i]), reference=reference, recorded=recorded,
            absolute_error=errors, nu_applied=float(d['nu_applied[2]'][i]),
            correction_applied=float(q['correction[2]'][k]), ff=float(d['a_ff[2]'][i]),
            flags=int(d['sta_flags'][i]), constraints=int(d['constraint_bits'][i]),
            cache_valid=bool(q['ri_cache_valid'][k]), commit_axes=int(q['ri_commit_axes'][k]),
            strict_axes=int(q['ri_strict_axes'][k])))
    require(len(candidates) == 414, 'Candidate count differs')
    seed_i = [i for i in range(first) if q['ri_seed_h'][joined[i]] > 0]
    require(len(seed_i) == 1, 'Unexpected seed count')
    si, sj = seed_i[0], joined[seed_i[0]]
    seed = old.solve(float(d['s[2]'][si]), float(q['ri_seed_h'][sj]), 0., *gains)
    seed.update(sample=int(d['timestamp_sample'][si]), recorded_nu=float(d['nu_applied[2]'][si]),
                solved_nu=float(q['correction[2]'][sj])-seed['correction'])
    require(abs(seed['recorded_nu']-seed['solved_nu']) <= 2e-6, 'Seed inverse differs')
    values = dict(LastSample=int(d['timestamp_sample'][last]), FailureSample=int(d['timestamp_sample'][first]),
        LastError=float(d['s[2]'][last]), LastStep=float(q['ri_h'][j]),
        LastNu=float(d['nu_applied[2]'][last]), LastCorrection=float(q['correction[2]'][j]),
        OldHover=float(d['hover_thrust'][last]), NewHover=float(hte['hover_thrust'][hi]),
        LastFf=float(d['a_ff[2]'][last]), LastNuCandidate=float(q['ri_nu_candidate[2]'][j]),
        Lambda1=gains[0], Lambda2=gains[1], Epsilon=gains[2],
        NuLimit=float(params['MPC_VC_NU_Z']), CorrectionLimit=float(params['MPC_VC_A_Z']))
    mapping = continuous_mapping(values['OldHover'], values['NewHover'], values['LastCorrection'],
                                 values['LastFf'], values['LastNu'], values['NuLimit'], values['CorrectionLimit'])
    require(abs(mapping['continuity_residual']) < 1e-14 and mapping['nu_bound_ok']
            and mapping['correction_bound_ok'], 'Recorded mapping unexpectedly infeasible')
    historical_sources = {}
    for path in old.SOURCE_PATHS:
        raw = subprocess.check_output(['git', 'show', SOURCE+':'+path], cwd=REPO)
        historical_sources[path] = dict(source=SOURCE, sha256=hashlib.sha256(raw).hexdigest(),
            provenance='historical git object; current working source deliberately not required identical')
    after = old.snapshot(run)
    require(before == after, 'Original failed run changed')
    return dict(stage='RI04_HTE_FIX offline recorded boundary', success=True,
        flight_accepted=False, flight_authorized=False, original_failure_preserved=True,
        flights=0, new_budget=0, source_head=SOURCE, historical_helper_sha256=helper_sha,
        historical_sources=historical_sources, raw_logs=raw_records, original_result=result,
        input_fingerprints_before=before, input_fingerprints_after=after,
        values=values, candidates=candidates, seed=seed, hte_reference=mapping,
        boundary_rows=[dict(status=old.row(d, i), selection=old.row(q, joined[i]))
                       for i in (si, si+1, last, first)],
        limitations=['Counterfactual frozen-input mapping, not a new flight or accepted gate.',
                    'The failed final row is a second failsafe invocation, not the unopened first candidate.',
                    'State-clipped applied nu and unchanged current correction need not be a strict implicit pair.',
                    'No MATLAB re-execution; independent double bisection and thrust-equation solution only.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(DATA/'RI04_HTE_FIX'), 'Output must be in new offline evidence root')
    require(not output.exists(), 'Evidence directory already exists')
    output.mkdir(parents=True)
    result = extract()
    header = render_header(result['values'])
    (output/'recorded_hte_fixture.hpp').write_text(header)
    result['header_sha256'] = hashlib.sha256(header.encode()).hexdigest()
    if (HERE/'recorded_hte_fixture.hpp').exists():
        require((HERE/'recorded_hte_fixture.hpp').read_text() == header, 'Repository fixture differs from raw log')
    (output/'summary.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(success=True, candidates=len(result['candidates']), header_sha256=result['header_sha256'],
                          hte=result['hte_reference'], output=str(output)), indent=2))


if __name__ == '__main__':
    main()
