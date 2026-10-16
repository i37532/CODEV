#!/usr/bin/env python3
"""Read-only historical target/P/FF probes; never R03 controller/flight admission."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
loader=importlib.util.spec_from_file_location('r03_target_probe_analysis',HERE/'analyzer.py')
a=importlib.util.module_from_spec(loader);loader.loader.exec_module(a)
t=a._targets

FORMAL=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-AXIS-ABLATION-20261008/AX05/formal01')
CASES=[('H_PID','C',FORMAL/'run007',True),('H_XYZ','C',FORMAL/'run008',True),
       ('V_PID','D',FORMAL/'run163',True),('V_XYZ','D',FORMAL/'run165',True),
       ('X_60s','A',Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04/series15/run01'),False),
       ('Z_60s','B',Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260927/Z03/paired01/run01'),False)]


def short_components(u,d,events,job):
    start,end=events['hover_start'],events['hover_end']
    m=(d['timestamp']>=start)&(d['timestamp']<end);x={k:v[m] for k,v in d.items()}
    if not 60e6<=end-start<=62e6 or len(x['timestamp'])<5900:raise ValueError('Missing historical60s observation')
    source=u.get_dataset('trajectory_setpoint').data;j,age=t.old.consumed_targets(source,x)
    errors={}
    for field,keys in [('p_sp',('x','y','z')),('v_ff',('vx','vy','vz')),('a_ff',('acceleration[0]','acceleration[1]','acceleration[2]'))]:
        errors[field]=[t.equal_topology(x[f'{field}[{axis}]'],source[key][j],field) for axis,key in enumerate(keys)]
    waveform=t.waveform(x['excitation_time'],.2 if job['gate']=='A' else .1)
    if not np.allclose(waveform,x['excitation'],atol=1e-6,rtol=0):raise ValueError('Legacy32s waveform mismatch')
    em=(x['excitation_time']>=0)&(x['excitation_time']<32)
    if em.sum()<3190 or x['excitation_time'][0]>=0 or x['excitation_time'][-1]<32:raise ValueError('Missing32s window')
    _,_,attitude=t.attitude_match(x,u.get_dataset('vehicle_attitude_setpoint').data,start,end,job)
    return dict(observation_seconds=(end-start)*1e-6,main_samples=int(em.sum()),maximum_target_error=errors,
        position_p=t.check_position_sum(u,x,job),attitude=attitude,
        missing_newer_diagnostic_fields=[key for key in ('excitation_y','excitation_z') if key not in x],
        max_source_age_us=int(age.max()),scope='Historical60s/32s target components only; not R03 90s acceptance')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    paths=[HERE/name for name in ('analyzer.py','targets.py','test_analysis.py','targets_replay.py')]
    before={str(path):a.digest(path) for path in paths}
    result=dict(success=False,flight_accepted=False,controller_admission_checked=False,new_flights=0,
        source_sha256_before=before,cases=[])
    try:
        for label,gate,run,modern in CASES:
            original=json.loads((run/'job.json').read_text());record=json.loads((run/'result.json').read_text())
            events={event['name']:event['timestamp_us'] for event in record['events']}
            inputs=[run/'job.json',run/'result.json',run/'runtime_parameters_start.json']+[Path(log['archive']) for log in record['logs']]
            item=dict(label=label,source_run=str(run),historical_job=original,component_valid=False,
                controller_admission_checked=False,flight_accepted=False,input_sha256_before={str(p):a.digest(p) for p in inputs})
            result['cases'].append(item)
            try:
                task,axes,test,duration=t.SPECS[gate]
                schema={**original,'gate':gate,'task':task,'main_duration_s':duration,'divisor':1,
                    'axes':0 if original['mode']==0 else axes,
                    'parameters':{**json.loads((run/'runtime_parameters_start.json').read_text()),**original['parameters']}}
                item['target_schema']=schema
                item['schema_mapping_note']='Only task/window validation. Historical axes preserved above; schema axes do not assert a different real controller or amend the old verdict.'
                if modern:ulog=a.ULog
                else:
                    from pyulog import ULog
                    ulog=ULog
                candidates=[]
                for path in inputs[3:]:
                    u=ulog(str(path))
                    try:
                        d=u.get_dataset('sta_velocity_ctrl_status').data
                        if d['timestamp'][0]<=events['hover_start'] and d['timestamp'][-1]>=events['hover_end']:candidates.append((u,d))
                    except (KeyError,IndexError):pass
                if len(candidates)!=1:raise ValueError('Not one complete historical diagnostic ULog')
                u,d=candidates[0]
                item['components']=t.check_targets(u,d,events,schema) if modern else short_components(u,d,events,schema)
                item['component_valid']=True
            except Exception as exc:
                item['error']=repr(exc)
            finally:
                item['input_sha256_after']={str(p):a.digest(p) for p in inputs}
                item['inputs_unchanged']=item['input_sha256_before']==item['input_sha256_after']
                a.save(output/(label+'.json'),item)
            print(json.dumps(dict(label=label,component_valid=item['component_valid'],error=item.get('error'))),flush=True)
        result['success']=all(c['component_valid'] and c['inputs_unchanged'] for c in result['cases']) and len(result['cases'])==6
    finally:
        result['source_sha256_after']={str(path):a.digest(path) for path in paths}
        result['source_unchanged']=before==result['source_sha256_after']
        result['success']=result['success'] and result['source_unchanged']
        a.save(output/'summary.json',result)
    return 0 if result['success'] else 1


if __name__=='__main__':raise SystemExit(main())
