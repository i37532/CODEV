#!/usr/bin/env python3
"""Offline descriptive clock audit. Not a flight validator or revised acceptance policy."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from pyulog import ULog
from audit_v04_protocol08_failure import attitude_records
from v04_heading_stream import data, LiveLog, TOPICS

REPO = Path(__file__).resolve().parents[3]
TOPIC_LIST = ('vehicle_attitude', 'vehicle_local_position', 'trajectory_setpoint',
              'vehicle_attitude_setpoint', 'vehicle_rates_setpoint', 'sta_velocity_ctrl_status',
              'sta_rate_ctrl_status', 'actuator_controls_0', 'estimator_selector_status',
              'vehicle_command', 'vehicle_command_ack')
SOURCES = ('msg/vehicle_attitude.msg', 'src/modules/ekf2/EKF2.cpp',
    'src/modules/ekf2/EKF2Selector.cpp', 'src/modules/simulator/simulator_mavlink.cpp',
    'platforms/posix/src/px4/common/drv_hrt.cpp',
    'platforms/posix/src/px4/common/lockstep_scheduler/src/lockstep_scheduler.cpp',
    'platforms/posix/src/px4/common/lockstep_scheduler/include/lockstep_scheduler/lockstep_scheduler.h',
    'platforms/common/uORB/Subscription.hpp', 'platforms/common/uORB/uORBDeviceNode.cpp',
    'src/modules/logger/logger.cpp', 'src/modules/logger/logged_topics.cpp',
    'src/modules/mc_att_control/mc_att_control_main.cpp',
    'src/modules/mc_pos_control/MulticopterPositionControl.cpp',
    'research/sta-velocity-control/scripts/v04_heading_stream.py',
    'research/sta-velocity-control/scripts/analyze_v00.py',
    'research/sta-velocity-control/scripts/analyze_v03.py',
    'research/sta-velocity-control/scripts/analyze_v04_core04.py',
    'research/sta-velocity-control/scripts/analyze_v04_protocol08.py',
    'research/sta-velocity-control/scripts/v04_logcheck07.py')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clocks(values):
    a = np.asarray(values)
    if a.ndim != 1 or not len(a) or a.dtype.kind not in 'iu' or np.any(a<=0) or np.any(a>=2**63):
        raise ValueError('Need positive int64-representable clock records, not rounded floats')
    return a.astype(np.int64)


def describe(publish, sample=None):
    """Report facts without accepting, sorting, deduplicating or changing data."""
    p = clocks(publish); dp = np.diff(p)
    out = dict(records=len(p), equal_publish=int((dp==0).sum()), backward_publish=int((dp<0).sum()),
               min_publish_gap_us=int(dp.min()) if len(dp) else None,
               max_publish_gap_us=int(dp.max()) if len(dp) else None)
    if sample is not None:
        s = clocks(sample)
        if s.shape != p.shape:
            raise ValueError('Clock shapes differ')
        ds = np.diff(s); age = p-s
        out.update(equal_sample=int((ds==0).sum()), backward_sample=int((ds<0).sum()),
            min_sample_gap_us=int(ds.min()) if len(ds) else None,
            max_sample_gap_us=int(ds.max()) if len(ds) else None,
            future_sample_count=int((age<0).sum()), min_age_us=int(age.min()), max_age_us=int(age.max()),
            same_publish_different_forward_sample=int(((dp==0)&(ds>0)).sum()))
    return out


def tied_candidates(publish, query):
    """All rows at the latest preceding publish time. No assumed consumer identity."""
    p=clocks(publish)
    if np.any(np.diff(p)<0):
        raise ValueError('Backward publication order')
    eligible=np.flatnonzero(p<=query)
    if not len(eligible):
        return []
    return np.flatnonzero(p==p[eligible[-1]]).tolist()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    result=dict(kind='offline_clock_audit_not_acceptance',new_flights=0,new_seeds=0,
                flight_authorized=False,acceptance_changed=False,
                head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),runs=[])
    originals={}
    root=REPO/'research/sta-velocity-control/v04'
    records=[root/'results01/run01_result.json']+[root/f'results{n:02d}/run01.json' for n in range(3,9)]
    for record in records:
        r=json.loads(record.read_text());entry=max(r['logs'],key=lambda v:v['bytes'])
        path=Path(entry['archive']);expected=entry['sha256']
        if digest(path)!=expected:
            raise ValueError('Historical ULog changed')
        originals[str(path)]=expected;originals[str(record)]=digest(record)
        u=ULog(str(path)); start=next(v['timestamp_us'] for v in r['events'] if v['name']=='takeoff_command')
        run=dict(record=str(record.relative_to(REPO)),source_head=r['source_head'],ulog=entry,
                 original_runner_success=r['success'],original_error=r.get('error'),
                 dropouts=len(u.dropouts),corruption=bool(u.file_corruption),topics={})
        for name in TOPIC_LIST:
            try:d=u.get_dataset(name).data
            except (KeyError,IndexError):
                run['topics'][name]=dict(missing=True);continue
            mask=d['timestamp']>=start
            run['topics'][name]=dict(full=describe(d['timestamp'],d.get('timestamp_sample')))
            if np.any(mask):
                run['topics'][name]['after_takeoff']=describe(d['timestamp'][mask],
                    d['timestamp_sample'][mask] if 'timestamp_sample' in d else None)
        att=u.get_dataset('vehicle_attitude').data
        raw=attitude_records(path)
        np.testing.assert_array_equal([v['timestamp'] for v in raw],att['timestamp'])
        np.testing.assert_array_equal([v['timestamp_sample'] for v in raw],att['timestamp_sample'])
        bad=np.flatnonzero(np.diff(att['timestamp'].astype(np.int64))<=0)+1
        run['nonincreasing_attitude_pairs']=[dict(raw=[raw[i-1],raw[i]],
            quat_reset=[int(att['quat_reset_counter'][j]) for j in (i-1,i)],
            max_quaternion_component_change=float(max(abs(float(att[f'q[{a}]'][i])-float(att[f'q[{a}]'][i-1])) for a in range(4)))) for i in bad]
        try:data(u,'vehicle_attitude')
        except ValueError as exc:run['unchanged_strict_accessor']=str(exc)
        else:run['unchanged_strict_accessor']='passes attitude timestamp check only; not flight acceptance'
        if record.parent.name=='results08':
            live=LiveLog(path).read();arrays=0
            for stream in u.data_list:
                if stream.name in TOPICS:
                    actual=live.get_dataset(stream.name,stream.multi_id).data
                    for key,value in stream.data.items():
                        np.testing.assert_array_equal(value,actual[key]);arrays+=1
            run['live_arrays_equal']=arrays
            qtime=60128000
            run['tied_attitude_candidates_at_failure']=tied_candidates(att['timestamp'],qtime)
            # Nearby rate setpoints have no consumed attitude sample/sequence key.
            rates=u.get_dataset('vehicle_rates_setpoint').data
            run['rate_setpoint_schema']=list(rates)
            ix=np.flatnonzero(abs(rates['timestamp'].astype(np.int64)-qtime)<=8000)
            run['nearby_rate_setpoints']=[{k:rates[k][i].item() for k in ('timestamp','roll','pitch','yaw')} for i in ix]
            run['actual_attitude_consumption_identifiable_from_these_fields']=False
        result['runs'].append(run)
    db=json.loads((REPO/'build/px4_sitl_default/compile_commands.json').read_text())
    result['compiled_clock_flags']=[dict(file=d['file'],lockstep='-DENABLE_LOCKSTEP_SCHEDULER' in d['command'],
        command_sha256=hashlib.sha256(d['command'].encode()).hexdigest()) for d in db if d['file'].endswith('/drv_hrt.cpp')]
    result['sources']={p:digest(REPO/p) for p in SOURCES}
    frozen=json.loads((root/'protocol08/frozen.json').read_text())
    result['frozen_asset_count']=len(frozen['assets'])
    result['frozen_asset_mismatches']=[n for n,s in frozen['assets'].items() if digest(REPO/n)!=s]
    if result['frozen_asset_mismatches']:
        raise ValueError('Existing execution assets modified')
    for name,s in originals.items():
        if digest(Path(name))!=s:raise ValueError('Audit changed original')
    result['input_fingerprints']=originals
    result['eeprom_sha256']=digest(REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016')
    result['limitations']=['No revised admission rule or timestamp bound has been enabled.',
        'Raw ULog inter-topic order is logger polling order, not proof of consumer causal order.',
        'No complete EKF/selector scheduling reproduction or inference of actual attitude controller dt.',
        'Historical incomplete windows/failed runs remain failed; no RMSE recomputation.']
    (out/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(runs=len(result['runs']),new_flights=0,frozen_asset_count=result['frozen_asset_count'],
        attitude=[dict(record=v['record'],clock=v['topics']['vehicle_attitude']['after_takeoff']) for v in result['runs']]),indent=2))


if __name__=='__main__':main()
