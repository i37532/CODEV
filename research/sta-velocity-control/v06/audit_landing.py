#!/usr/bin/env python3
"""Read-only landing clipping audit; never reclassifies failed trials."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from pyulog import ULog
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def changes(d,key,start):
    t=d['timestamp']; ix=np.flatnonzero(np.r_[True,np.diff(d[key])!=0]); ix=ix[t[ix]>=start]
    return [dict(timestamp=int(t[i]),value=float(d[key][i])) for i in ix]
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=json.loads((a.run/'result.json').read_text()); entry=max(r['logs'],key=lambda e:e['bytes'])
    assert sha(entry['archive'])==entry['sha256']
    u=ULog(entry['archive']); events={e['name']:int(e['timestamp_us']) for e in r['events']}
    assert not r['success'] and 'land_command' in events and 'landed_disarmed' not in events
    start=events['land_command']; tables={}
    for ds in u.data_list:
        if ds.name not in ('sensor_accel','vehicle_imu','vehicle_imu_status','estimator_status','estimator_status_flags','estimator_selector_status','vehicle_local_position'):continue
        d=ds.data; m=d['timestamp']>=start
        if not m.any():continue
        key=f'{ds.name}:{ds.multi_id}'; row=dict(samples=int(m.sum()))
        if ds.name=='sensor_accel':
            k=np.flatnonzero(m)[np.argmin(d['z'][m])]
            row.update(z_min_m_s2=float(d['z'][k]),peak_publish_us=int(d['timestamp'][k]),peak_sample_us=int(d['timestamp_sample'][k]),
                       z_clipping=changes(d,'clip_counter[2]',start))
        elif ds.name=='vehicle_imu':
            row.update(clipping=changes(d,'delta_velocity_clipping',start),
                delta_velocity_dt_range=[int(d['delta_velocity_dt'][m].min()),int(d['delta_velocity_dt'][m].max())])
        elif ds.name=='vehicle_imu_status':row['clipping_total']=changes(d,'accel_clipping[2]',start)
        elif ds.name=='estimator_status':row['fault_flags']=changes(d,'filter_fault_flags',start)
        elif ds.name=='estimator_status_flags':row['bad_acc_clipping']=changes(d,'fs_bad_acc_clipping',start)
        elif ds.name=='estimator_selector_status':row['primary']=changes(d,'primary_instance',start)
        else:
            row['reference_altitude']=changes(d,'ref_alt',start)
            row['reference_before_m']=float(d['ref_alt'][np.searchsorted(d['timestamp'],start)-1])
            row['reference_after_m']=float(d['ref_alt'][m][-1])
        tables[key]=row
    repo=Path(__file__).resolve().parents[3]
    params={p['name']:p for p in json.loads((repo/'build/px4_sitl_default/parameters.json').read_text())['parameters']}
    bounds={k:{n:params[k].get(n) for n in ('default','min','max')} for k in ('MPC_LAND_SPEED','MPC_Z_VEL_MAX_DN','LNDMC_Z_VEL_MAX')}
    p0=tables['estimator_status:0']['fault_flags']; assert any(x['value']==131072 for x in p0)
    assert [int(x['value']) for x in tables['estimator_selector_status:0']['primary']]==[2,4]
    pos=tables['vehicle_local_position:0']; assert abs(pos['reference_after_m']-pos['reference_before_m'])>.06
    result=dict(status='failed_retained_requires_separate_landing_scope',source_head=r['source_head'],
        original_error=r['error'],ulog=entry,events=events,dropouts=len(u.dropouts),
        file_corruption=bool(getattr(u,'file_corruption',False)),tables=tables,parameter_metadata=bounds,
        conclusion='Observed landing acceleration clipping (fault bit17), followed by selector changes and real reference/reset changes; not listener rounding. No estimator/land-detector change, new flight or historical reacceptance.',
        limitations='Not a complete contact-physics causal proof. Existing FIFO clipping repair preserves direction but cannot reconstruct out-of-range impulse. No evidence justifying selective waiver, disabling estimator instances, lower-than-metadata parameters, or seed retries.')
    with a.output.open('x') as f: json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
