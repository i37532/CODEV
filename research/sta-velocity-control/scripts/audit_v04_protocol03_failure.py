#!/usr/bin/env python3
"""Read-only failed-attempt diagnosis. New output only; never changes acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from pyulog import ULog
from analyze_v04_protocol03 import check_first_invocation


def main():
    p=argparse.ArgumentParser(); p.add_argument('run',type=Path); p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); run=args.run.resolve(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    result=json.loads((run/'result.json').read_text()); ref=json.loads((run/'height_reference.json').read_text())
    start=next(e['timestamp_us'] for e in result['events'] if e['name']=='takeoff_command')
    evidence=dict(accepted=False,original_error=result['error'],source_head=result['source_head'],
        flight_attempts=1,accepted_attempts=0,esta_attempts=0,paired_comparisons=0,
        height_command_sent=(run/'reposition_command.json').exists(),logs=[],
        missing=['explicit height task','3s height admission','32s excitation','60s observation','normal landing/disarm','PID/ESTA pairs'])
    for item in result['logs']:
        path=Path(item['archive']); assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
        u=ULog(str(path)); row=dict(ulog=item,dropouts=len(u.dropouts),topics={})
        for topic in ('vehicle_local_position','vehicle_status','sta_velocity_ctrl_status','sta_rate_ctrl_status','vehicle_land_detected'):
            try: d=u.get_dataset(topic).data
            except (KeyError,IndexError): continue
            m=d['timestamp']>=start; t=d['timestamp'][m].astype(np.int64)
            info=dict(total=len(d['timestamp']),post_command=int(m.sum()))
            if not len(t): row['topics'][topic]=info; continue
            info.update(first_timestamp=int(t[0]),last_timestamp=int(t[-1]),max_gap_us=int(np.diff(t).max()) if len(t)>1 else None)
            for key in ('requested_mode','requested_axes','effective_mode','effective_axes','div_eff','div_req',
                        'inner_mode','inner_axes','inner_divisor','inner_valid','fault','sta_fault','first_fail','first_input','retry_result',
                        'excitation_fault','pid_calls','valid','timing','failsafe','armed','arming_state','nav_state','landed','ground_contact'):
                if key in d: info[key]=np.unique(d[key][m]).tolist()
            for key in ('publish_seq','update_seq'):
                if key in d: info[key+'_nonunit_deltas']=int(np.count_nonzero(np.diff(d[key][m].astype(np.int64))!=1))
            if topic=='vehicle_local_position':
                transitions=[]
                for key in ('xy_reset_counter','z_reset_counter','vxy_reset_counter','vz_reset_counter','heading_reset_counter','ref_timestamp','ref_alt'):
                    indices=np.flatnonzero((np.r_[False,np.diff(d[key].astype(float))!=0]) & m)
                    for i in indices:
                        transitions.append(dict(field=key,timestamp=int(d['timestamp'][i]),before=float(d[key][i-1]),after=float(d[key][i]),
                            heading=float(d['heading'][i]),delta_heading_rad=float(d['delta_heading'][i]),
                            delta_heading_deg=float(np.rad2deg(d['delta_heading'][i])),height_from_ground_m=float(ref['position']['z']-d['z'][i]),
                            dist_bottom_m=float(d['dist_bottom'][i]),dist_bottom_valid=bool(d['dist_bottom_valid'][i])))
                info['reference_transitions']=transitions
                info['height_range_m']=[float((ref['position']['z']-d['z'][m]).min()),float((ref['position']['z']-d['z'][m]).max())]
            if topic=='sta_velocity_ctrl_status':
                info['first_invocation_offline_check']=check_first_invocation(d,m)
                info['excitation_peak']=float(np.max(np.abs(d['excitation'][m])))
                info['excitation_time_range']=[float(d['excitation_time'][m].min()),float(d['excitation_time'][m].max())]
                info['all_pid_nu_nan']=bool(np.all(np.isnan(d['nu_applied[0]'][m])))
            row['topics'][topic]=info
        row['estimator_alignment_transitions']=[]
        for dataset in u.data_list:
            if dataset.name!='estimator_status': continue
            d=dataset.data
            flags=d['control_mode_flags'].astype(np.uint32)
            aligned=((flags>>23)&1)
            ix=np.flatnonzero(np.r_[False,np.diff(aligned.astype(int))!=0] & (d['timestamp']>=start))
            for i in ix:
                row['estimator_alignment_transitions'].append(dict(instance=dataset.multi_id,timestamp=int(d['timestamp'][i]),
                    mag_aligned_in_flight_before=int(aligned[i-1]),mag_aligned_in_flight_after=int(aligned[i]),control_mode_flags=int(flags[i])))
        for dataset in u.data_list:
            if dataset.name=='estimator_selector_status':
                d=dataset.data; m=d['timestamp']>=start
                row['primary_estimator_instances']=np.unique(d['primary_instance'][m]).tolist()
        row['new_logging_topics']={name:sum(len(ds.data['timestamp']) for ds in u.data_list if ds.name==name)
                                   for name in ('position_setpoint_triplet','vehicle_command_ack')}
        evidence['logs'].append(row)
    evidence['interpretation']='Frozen reset-counter gate failed during PID takeoff; no completed performance window. Alignment mechanism assessment uses pinned ECL code and recorded estimator flags, not a new acceptance rule.'
    (out/'diagnosis.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence,indent=2))


if __name__=='__main__': main()
