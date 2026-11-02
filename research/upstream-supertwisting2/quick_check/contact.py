#!/usr/bin/env python3
"""Independent read-only contact diagnostics; truth is never fed to control."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from pyulog import ULog
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from run_hover import digest, require, save


def aligned_tail(lp, gt, end, origin_z, reference_us):
    """Causal 20 ms truth pairing, each stream's own preflight height origin."""
    t = np.asarray(lp['timestamp'], dtype=np.int64)
    g = np.asarray(gt['timestamp'], dtype=np.int64)
    require(len(t)>2 and len(g)>2 and np.all(np.diff(t)>0) and np.all(np.diff(g)>0), 'Contact clocks')
    r = np.searchsorted(g, reference_us, side='right')-1
    require(r>=0 and reference_us-g[r]<=20000, 'Missing preflight truth origin')
    indices = np.flatnonzero((t>=end-500000) & (t<=end))
    require(len(indices)>=10 and t[indices[0]]<=end-480000 and t[indices[-1]]>=end-20000,
            'Missing complete 500 ms terminal tail')
    require(np.max(np.diff(t[indices]))<=20000, 'Contact tail sampling gap')
    gi = np.searchsorted(g,t[indices],side='right')-1
    require(np.all(gi>=0) and np.all(t[indices]-g[gi]<=20000), 'Stale contact truth pairing')
    eh = origin_z-np.asarray(lp['z'])[indices]
    gh = gt['z'][r]-np.asarray(gt['z'])[gi]
    dv = np.asarray(lp['vz'])[indices]-np.asarray(gt['vz'])[gi]
    require(np.isfinite(eh).all() and np.isfinite(gh).all() and np.isfinite(dv).all(), 'Nonfinite contact tail')
    return dict(samples=len(indices), max_truth_age_us=int(np.max(t[indices]-g[gi])),
                max_abs_height_difference_m=float(np.max(abs(eh-gh))),
                max_abs_vertical_speed_difference_m_s=float(np.max(abs(dv))),
                estimated_height_last_m=float(eh[-1]), truth_height_last_m=float(gh[-1]),
                accepted=bool(np.max(abs(eh-gh))<=.3 and np.max(abs(dv))<=.2),
                clock='publication/reception; groundtruth sample timestamp is not assumed valid')


def audit(directory):
    directory=Path(directory)
    result=json.loads((directory/'result.json').read_text())
    origin=json.loads((directory/'origin.json').read_text())
    require(result.get('success') and result.get('independent_replay_passed'), 'Flight acceptance required before contact gate')
    source=max(result['logs'],key=lambda r:r['bytes'])
    require(digest(source['archive'])==source['sha256'], 'Raw ULog changed')
    log=ULog(source['archive'],message_name_filter_list=['vehicle_local_position','vehicle_local_position_groundtruth',
             'sensor_combined','vehicle_land_detected','estimator_selector_status'])
    require(not log.dropouts and not log.file_corruption, 'Contact ULog dropout/corruption')
    ds=lambda n:log.get_dataset(n).data
    events={e['name']:e['timestamp_us'] for e in result['events']}
    end=events['landed_disarmed']; start=events['land_command']
    tail=aligned_tail(ds('vehicle_local_position'),ds('vehicle_local_position_groundtruth'),end,origin['z'],result['events'][0]['timestamp_us'])
    imu=ds('sensor_combined'); mask=(imu['timestamp']>=start)&(imu['timestamp']<=end)
    require(np.count_nonzero(mask)>=10 and np.max(np.diff(imu['timestamp'][mask].astype(np.int64)))<=500000,
            'Missing landing IMU')
    z=imu['accelerometer_m_s2[2]'][mask]
    require(np.isfinite(z).all(), 'Nonfinite acceleration')
    output=dict(accepted=tail['accepted'], source=source, tail=tail,
                sensor_combined_z_range_m_s2=[float(z.min()),float(z.max())],
                clipping_bits=np.unique(imu['accelerometer_clipping'][mask]).tolist(),
                integral_dt_us=np.unique(imu['accelerometer_integral_dt'][mask]).tolist(),
                limitation='No raw pre-conversion HIL waveform; clipping does not recover impulse area; no causal landing claim')
    return output


def main():
    p=argparse.ArgumentParser(); p.add_argument('directory',type=Path); a=p.parse_args()
    path=a.directory/'contact_audit.json'; require(not path.exists(),'Do not overwrite contact evidence')
    value=audit(a.directory); save(path,value)
    require(value==audit(a.directory),'Contact independent replay differs')
    print(json.dumps(value,indent=2)); require(value['accepted'],'Contact tail gate failed')
    r=json.loads((a.directory/'result.json').read_text()); r['contact_audit_passed']=True
    r['contact_audit_sha256']=digest(path); save(a.directory/'result.json',r)


if __name__=='__main__': main()
