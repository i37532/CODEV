#!/usr/bin/env python3
"""Read-only series09 diagnosis. Partial windows never replace full acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from v04_live_clock09 import replay as heading_replay
from v04_landing10 import replay as landing_replay
from analyze_v04_core04 import check_diagnostic
from analyze_v04_protocol10 import check_first_invocation
from v04_task04 import check_cli_reference


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def changes(d, key, start):
    ids = np.flatnonzero(np.r_[False, d[key][1:] != d[key][:-1]] & (d['timestamp'] >= start))
    return [dict(timestamp_us=int(d['timestamp'][i]), before=d[key][i-1].item(),
                 after=d[key][i].item()) for i in ids]


def outcome(call):
    try:
        return dict(passed=True, value=call())
    except (ValueError, KeyError, IndexError) as exc:
        return dict(passed=False, error=str(exc))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('run', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); run, out = a.run.resolve(), a.output.resolve()
    if run == out or run in out.parents or out in run.parents:
        raise ValueError('Use an independent new output directory')
    originals = {str(f):digest(f) for f in run.parent.rglob('*') if f.is_file() and not f.is_symlink()}
    out.mkdir(parents=True, exist_ok=False)
    r = json.loads((run/'result.json').read_text())
    events = {e['name']:e['timestamp_us'] for e in r['events']}
    e = dict(accepted=False, historical_acceptance_changed=False, new_flights=0,
             source_head=r['source_head'], original_error=r.get('error'), events=r['events'], logs=[], checks=[])
    def check(name, value): e['checks'].append(dict(name=name, passed=bool(value)))
    for item in r['logs']:
        if digest(item['archive']) != item['sha256']: raise ValueError('Original ULog changed')
        u = ULog(item['archive'])
        e['logs'].append(dict(**item, dropouts=len(u.dropouts), corruption=bool(u.file_corruption)))
    entry = max(r['logs'], key=lambda v:v['bytes']); u = ULog(entry['archive'])
    lp = u.get_dataset('vehicle_local_position').data
    d = u.get_dataset('sta_velocity_ctrl_status').data
    ss = u.get_dataset('estimator_selector_status').data
    ref = json.loads((run/'height_reference.json').read_text())
    frozen = json.loads((run/'task_yaw.json').read_text())
    context = json.loads((run/'landing_context.json').read_text())
    begin, end = events['hover_start'], events['hover_end']
    check('failed_without_complete_landing', not r['success'] and 'landed_disarmed' not in events)
    check('no_recorded_dropouts_or_corruption', all(not x['dropouts'] and not x['corruption'] for x in e['logs']))
    e['observation_seconds'] = (end-begin)*1e-6
    check('complete_observation_window', 60 <= e['observation_seconds'] <= 62)
    e['heading_through_hover_only'] = outcome(lambda:heading_replay(u,ref,end=int(end),frozen=frozen))
    # The inherited data accessor validates whole-topic clocks before slicing.
    # A late selector duplicate can therefore reject an earlier requested window.
    # Keep that rejection; do not crop/deduplicate it into a claimed hover pass.
    check('uncropped_heading_replay_recorded',bool(e['heading_through_hover_only']))
    e['full_raw_heading'] = outcome(lambda:heading_replay(u,ref,frozen=frozen))
    check('full_raw_history_rejects',not e['full_raw_heading']['passed'])
    last = json.loads((run/'samples.jsonl').read_text().splitlines()[-1])
    e['last_host_sample_timestamp_us'] = last['position']['timestamp']
    e['cli_rejection'] = outcome(lambda:check_cli_reference(last['position'],ref))
    check('cli_rejection_reproduced',not e['cli_rejection']['passed'] and 'xy_reset_counter' in e['cli_rejection']['error'])
    e['local_position_changes_after_land'] = {k:changes(lp,k,events['land_command']) for k in
        ('ref_timestamp','ref_alt','xy_reset_counter','z_reset_counter','vxy_reset_counter','vz_reset_counter','heading_reset_counter')}
    e['primary_changes_after_land'] = changes(ss,'primary_instance',events['land_command'])
    check('actual_raw_resets',bool(e['local_position_changes_after_land']['xy_reset_counter']))
    check('actual_raw_primary_changes',bool(e['primary_changes_after_land']))
    e['landing_component_only'] = outcome(lambda:landing_replay(u,context,int(d['timestamp'][-1]),final=True))
    check('full_landing_component_rejects_late_timing',not e['landing_component_only']['passed']
          and 'timing' in e['landing_component_only']['error'])
    polls = [json.loads(line) for line in (run/'landing10_monitor.jsonl').read_text().splitlines()]
    e['landing_polls'] = dict(count=len(polls),pending=sum(x['evidence']['pending'] for x in polls),
                             last=polls[-1]['evidence'] if polls else None)
    check('live_new_landing_component_really_used',len(polls)>0)
    prefix_end = polls[-1]['evidence']['evidence']['through_us']
    e['landing_before_reset_component_only'] = outcome(lambda:landing_replay(u,context,prefix_end,final=True))
    check('landing_prefix_matches_online_evidence',e['landing_before_reset_component_only']['passed'])
    m = d['timestamp'] >= events['takeoff_command']
    keys = ('effective_mode','effective_axes','inner_mode','inner_axes','inner_divisor','inner_valid',
            'first_fail','retry_result','fault','sta_fault','failsafe','timing','excitation_fault')
    e['recorded_flight_values'] = {k:np.unique(d[k][m]).tolist() for k in keys}
    check('actual_outer_and_inner_PID',all(e['recorded_flight_values'][k]==[v] for k,v in
          dict(effective_mode=0,effective_axes=0,inner_mode=0,inner_axes=0,inner_divisor=1,inner_valid=1).items()))
    check('no_first_retry_or_fault_flags',all(e['recorded_flight_values'][k]==[0] for k in
          ('first_fail','retry_result','fault','sta_fault','failsafe')))
    ix = np.flatnonzero(d['timing'] != 0)
    e['timing_anomalies'] = [{k:d[k][i].item() for k in
        ('timestamp','timestamp_sample','input_timestamp','raw_dt','timing','excitation_fault')} for i in ix]
    check('late_negative_raw_dt_preserved',len(ix)>0 and np.all(d['timestamp'][ix]>end)
          and np.any(d['raw_dt'][ix]<0))
    ix = np.flatnonzero(np.diff(ss['timestamp'].astype(np.int64))<=0)+1
    e['selector_nonincreasing_publications'] = [dict(timestamp_us=int(ss['timestamp'][i]),
        before=int(ss['primary_instance'][i-1]),after=int(ss['primary_instance'][i])) for i in ix]
    e['first_invocation'] = check_first_invocation(d,m)
    e['hover_diagnostic_descriptive_only'] = check_diagnostic(d,begin,end,0)
    status = u.get_dataset('vehicle_status').data
    land = u.get_dataset('vehicle_land_detected').data
    e['last_raw_status'] = {k:status[k][-1].item() for k in ('timestamp','nav_state','arming_state','failsafe')}
    e['last_raw_land'] = {k:land[k][-1].item() for k in ('timestamp','landed','ground_contact')}
    check('no_disarm_after_land',not np.any(status['arming_state'][status['timestamp']>=events['land_command']]==1))
    e['not_evaluated'] = 'No complete landing acceptance or paired ESTA performance. Primary/reset observations do not identify their physical or numerical root cause. No production fix or reset exemption authorized.'
    for path, sha in originals.items():
        if digest(path) != sha: raise ValueError('Original changed during diagnosis')
    check('original_files_unchanged', True)
    e['original_artifacts'] = originals
    e['diagnostic_checks_passed'] = all(c['passed'] for c in e['checks'])
    (out/'diagnosis.json').write_text(json.dumps(e,indent=2)+'\n')
    (out/'original_artifacts.sha256').write_text(''.join(f'{h}  {p}\n' for p,h in sorted(originals.items())))
    print(json.dumps({k:v for k,v in e.items() if k in ('checks','diagnostic_checks_passed','accepted','primary_changes_after_land','local_position_changes_after_land','full_raw_heading')},indent=2))
    return 0 if e['diagnostic_checks_passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
