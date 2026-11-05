#!/usr/bin/env python3
"""Seven historical logs, isolated offline reanalysis. Never authorize/regrade a flight."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import numpy as np
from pyulog import ULog
import analyze_v00
import analyze_v04_core04 as core
from analyze_v04_height_clock09 import height_evidence
from v04_heading_stream import LiveLog, TOPICS, data, row, index, replay
from v04_task04 import freeze_reference
from v04_attitude_clock09 import AttitudeClockPolicy, MAX_AGE_US, MAX_GAP_US

REPO = Path(__file__).resolve().parents[3]
ROOT = REPO/'research/sta-velocity-control/v04'


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def outcome(fn):
    try:
        return dict(check_passed=True, result=fn())
    except (ValueError, KeyError, IndexError, FileNotFoundError) as exc:
        return dict(check_passed=False, error=repr(exc))


def copy_metadata(source, destination):
    destination.mkdir(exist_ok=False)
    for p in source.iterdir():
        if p.is_file() and p.suffix in ('.json','.jsonl','.txt','.log'):
            shutil.copyfile(p, destination/p.name)


def historical_protocol(protocol_id):
    if protocol_id in (1,3):
        return json.loads((ROOT/f'protocol{protocol_id:02d}'/'protocol.json').read_text())
    if protocol_id not in range(4,9):
        raise ValueError('Unsupported historical protocol')
    return importlib.import_module(f'v04_protocol{protocol_id:02d}').load_protocol()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve()
    records = [ROOT/'results01/run01_result.json']+[ROOT/f'results{n:02d}/run01.json' for n in range(3,9)]
    jobs = []
    original = {}
    for record in records:
        r = json.loads(record.read_text())
        entry = max(r['logs'], key=lambda x:x['bytes'])
        source = Path(entry['archive']).parent
        if out == source or source in out.parents or out in source.parents:
            raise ValueError('Output overlaps historical input')
        if digest(entry['archive']) != entry['sha256']:
            raise ValueError('Historical ULog fingerprint changed')
        jobs.append((record,r,entry,source))
        original[str(record)] = digest(record)
        for p in source.rglob('*'):
            if p.is_file(): original[str(p)] = digest(p)
    out.mkdir(parents=True, exist_ok=False)
    evidence = dict(kind='offline_clock09_replay_not_flight_acceptance', accepted=False,
                    historical_acceptance_changed=False, new_flights=0, new_seeds=0,
                    flight_authorized=False, execution_ready=False,
                    source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
                    policy=dict(whitelist=['vehicle_attitude:0'],max_age_us=MAX_AGE_US,
                                max_gap_us=MAX_GAP_US,old_numeric_safety_limits_unchanged=True),runs=[])
    policy = AttitudeClockPolicy()
    for number,(record,r,entry,source) in enumerate(jobs,1):
        u = ULog(entry['archive'])
        if u.dropouts or u.file_corruption: raise ValueError('Raw ULog dropout/corruption')
        # Compare every field retained by the streaming decoder, including tied rows.
        live = LiveLog(entry['archive']).read(); arrays = 0
        for ds in u.data_list:
            if ds.name not in TOPICS: continue
            got = live.get_dataset(ds.name,ds.multi_id).data
            for key,value in ds.data.items():
                np.testing.assert_array_equal(value,got[key]); arrays += 1
        ev = {e['name']:int(e['timestamp_us']) for e in r['events']}
        att = u.get_dataset('vehicle_attitude').data
        pos = data(u,'vehicle_local_position')
        start = ev['takeoff_command']
        end = ev.get('landed_disarmed',min(int(pos['timestamp'][-1]),int(att['timestamp'][-1])))
        ref_file = source/'height_reference.json'
        ref = (json.loads(ref_file.read_text()) if ref_file.exists()
               else freeze_reference(row(pos,index(pos,start))))
        frozen_file = source/'task_yaw.json'
        frozen = json.loads(frozen_file.read_text()) if frozen_file.exists() else None
        item = dict(series=number, record=str(record.relative_to(REPO)),ulog=entry,
                    historical_runner_success=r['success'],historical_error=r.get('error'),
                    historical_accepted=False,accepted=False,complete_recorded_flight='landed_disarmed' in ev,
                    through_us=end,live_field_arrays_equal=arrays,
                    reference_source='archived prearm' if ref_file.exists() else 'derived development reference, not flight provenance')
        item['legacy_clock'] = outcome(lambda:dict(records=len(data(u,'vehicle_attitude')['timestamp'])))
        item['revised_clock'] = outcome(lambda:dict(records=len(policy.data(u)['timestamp'])))
        mask = (att['timestamp']>=start)&(att['timestamp']<=end)
        item['revised_rates'] = outcome(lambda:policy.topic_rates(att,mask))
        item['legacy_heading'] = outcome(lambda:replay(u,ref,end=end,frozen=frozen))
        item['revised_heading'] = outcome(lambda:replay(u,ref,end=end,frozen=frozen,attitude_policy=policy))
        item['closed_attitude_window'] = outcome(lambda:dict(records=len(policy.window(att,start,end)),
                                                reset_indices=policy.reset_indices(att,start,end).tolist()))
        target = u.get_dataset('vehicle_attitude_setpoint').data
        item['recorded_tilt_safety'] = outcome(lambda:policy.safety(att,target,start,end,check_yaw=False))
        rates = u.get_dataset('vehicle_rates_setpoint').data
        query = rates['timestamp'][(rates['timestamp']>=start)&(rates['timestamp']<=end)]
        def groups():
            candidates = policy.candidates(att,query)
            ambiguous = [dict(query_us=int(t),row_indices=g.tolist(),
                              samples_us=att['timestamp_sample'][g].tolist())
                         for t,g in zip(query,candidates) if len(g)>1]
            return dict(query_count=len(query),ambiguous_count=len(ambiguous),ambiguous=ambiguous,
                        actual_consumption_proven=False)
        item['descriptive_rate_associations'] = outcome(groups)
        item['unique_rate_association'] = outcome(lambda:dict(count=len(policy.unique_index(att,query)),
                                                             actual_consumption_proven=False))
        if 'hover_start' in ev and 'hover_end' in ev:
            item['descriptive_hover_yaw'] = outcome(lambda:policy.yaw_metrics(att,target,ev['hover_start'],ev['hover_end']))
        else:
            item['descriptive_hover_yaw'] = dict(check_passed=False,error='Incomplete original hover window; no replacement RMSE')
        runout = out/f'series{number:02d}'; runout.mkdir()
        protocol_id = 1 if number==1 else number+1
        conf = ROOT/f'protocol{protocol_id:02d}'
        protocol = historical_protocol(protocol_id)
        job = json.loads((source/'job.json').read_text())
        protocol['startup_overrides'].update(job['parameters'])
        # Same historical metadata/numeric conditions; never supply fabricated events.
        oldconf, oldbase = core.CONFIG, analyze_v00.CONFIG
        try:
            core.CONFIG = conf
            for label,p in (('legacy_components',None),('revised_components',policy)):
                isolated = runout/label; copy_metadata(source,isolated)
                item[label] = outcome(lambda:core.analyze(isolated,protocol,job,attitude_policy=p))
                if item[label]['check_passed']:
                    item[label]['component_accepted_not_flight_accepted'] = item[label]['result'].pop('accepted')
            # This checks later handoff/height stages independently of main metric
            # early failure. Missing original completion events must still reject.
            item['revised_height_components'] = outcome(lambda:height_evidence(
                u,source,u.get_dataset('sta_velocity_ctrl_status').data,ev,attitude_policy=policy))
        finally:
            core.CONFIG, analyze_v00.CONFIG = oldconf, oldbase
        evidence['runs'].append(item)
        (runout/'checks.json').write_text(json.dumps(item,indent=2)+'\n')
        print(json.dumps(dict(series=number,old_clock=item['legacy_clock']['check_passed'],
                              new_clock=item['revised_clock']['check_passed'],
                              heading=item['revised_heading']['check_passed'],accepted=False)),flush=True)
    for path,sha in original.items():
        if digest(path)!=sha: raise ValueError('Historical input mutated: '+path)
    evidence['input_fingerprints'] = original
    evidence['inputs_unchanged'] = True
    evidence['replay_completed'] = len(evidence['runs'])==7
    evidence['limitations'] = ['Component passes do not regrade historical attempts.',
        'Prior protocols used different sources; these are development replays, not paired experiments.',
        'No actual consumer sample/sequence key in legacy attitude-to-rate logs.',
        'New batch must freeze and explicitly wire this opt-in policy into live AND full analysis.']
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')


if __name__=='__main__':main()
