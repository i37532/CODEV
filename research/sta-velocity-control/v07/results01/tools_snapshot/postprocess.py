"""Post-flight independent replay and archive; no new flights or controller writes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import numpy as np
ROOT=Path(__file__).resolve().parent
REPO=Path('/home/yr/Desktop/Codev-autopilot')
CONFIG=REPO/'research/sta-velocity-control/v07/protocol01'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def main():
    ledger=json.loads((ROOT/'series01/ledger.json').read_text())
    assert ledger['parameter_restore_exact'] and not ledger['remaining_simulators']
    assert all(a['status']!='running' for a in ledger['attempts'])
    out=ROOT/'assessment01'; out.mkdir(exist_ok=False)
    env=os.environ.copy(); env['PATH']=str(REPO/'.px4-python/bin')+':'+env['PATH']
    env['PYTHONPATH']=':'.join([str(REPO/'.px4-python'),str(REPO/'research/sta-velocity-control/scripts'),'/home/yr/Desktop/codev doc/experiments/M00-20260912/python',env.get('PYTHONPATH','')])
    result=dict(success=False,source_head=ledger['source_head'],firmware_sha256=ledger['firmware_sha256'],
        attempts=len(ledger['attempts']),accepted=0,pairs=ledger['pairs'],replays=[],rows=[],groups=[],new_flights=0)
    params=[]
    try:
        for attempt in ledger['attempts']:
            source=Path(attempt['directory']); job=attempt['job']
            if attempt['status']!='accepted':
                result['rows'].append(dict(job=job,accepted=False,error=attempt.get('error'))); continue
            target=out/'replay'/source.name
            argv=['python3',str(CONFIG/'analyze.py'),str(source),'--output',str(target)]
            with (out/(source.name+'.log')).open('w') as stream:
                r=subprocess.run(argv,cwd=REPO,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=300)
            identical=sha(source/'xyz_metrics.json')==sha(target/'xyz_metrics.json') if (target/'xyz_metrics.json').exists() else False
            result['replays'].append(dict(run=source.name,command=argv,exit_code=r.returncode,metrics_byte_identical=identical))
            print(source.name,'exit',r.returncode,'identical',identical,flush=True)
            assert r.returncode==0 and identical
            d=json.loads((source/'xyz_metrics.json').read_text()); assert d['accepted']
            result['accepted']+=1
            c=d['diagnostic']['cadence']
            result['rows'].append(dict(job=job,accepted=True,rmse=d['diagnostic']['error']['rmse'],
                windows=d['diagnostic']['windows'],position_rmse=d['position_rmse'],yaw_rmse=d['yaw_rmse'],
                hz=c['update_hz'],callback_hz=d['diagnostic']['hz'],cadence=c,
                acceleration_tv=d['diagnostic']['acceleration_tv'],thrust_tv=d['diagnostic']['normalized_thrust_tv'],
                spectrum=d['spectral_summary'],constraint_fraction=d['diagnostic']['constraint_fraction'],
                landing_health=d['landing_health'],coverage=dict(local=d['local_output'],attitude=d['attitude_output']),
                pid_reconstruction=d['pid_reconstruction'],metrics_sha256=sha(source/'xyz_metrics.json')))
            params.append(json.loads((source/'ulog_parameters.json').read_text()))
        for divisor in (1,2,4):
            for mode in (0,1):
                rows=[r for r in result['rows'] if r['accepted'] and r['job']['divisor']==divisor and r['job']['mode']==mode]
                if not rows: continue
                result['groups'].append(dict(divisor=divisor,mode=mode,accepted=len(rows),
                    mean_rmse=np.mean([r['rmse'] for r in rows],axis=0).tolist(),
                    mean_correction_tv_per_s=np.mean([r['spectrum']['correction_tv_per_second'] for r in rows],axis=0).tolist(),
                    mean_common_0_7hz_rms=np.mean([r['spectrum']['common_0_7hz_rms'] for r in rows],axis=0).tolist(),
                    mean_update_hz=float(np.mean([r['hz'] for r in rows])),
                    host_mean_of_run_medians_us={name:{phase:float(np.mean([r['cadence']['host_cost'][name][phase]['median'] for r in rows]))
                        for phase in (['update'] if divisor==1 else ['update','hold'])} for name in ('path_ns','module_ns')},
                    mean_host_us_per_sim_second={name:float(np.mean([r['cadence']['host_us_per_sim_second'][name] for r in rows])) for name in ('path_ns','module_ns')}))
        if params:
            keys=sorted(k for k in params[0] if k.startswith(('IMU_','SENS_','EKF2_','GYRO_','ACC_','MC_DTERM')))
            changed=[k for k in keys if any(p.get(k)!=params[0][k] for p in params[1:])]
            result['sensor_filter_estimator']=dict(parameters=len(keys),runs=len(params),changed=changed,values={k:params[0][k] for k in keys})
            assert not changed
        result['parameter_restore_exact']=sha(REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016')==ledger['original_parameter_sha256']
        result['success']=bool(ledger['success'] and result['accepted']==18 and len(result['pairs'])==9 and all(p['accepted'] for p in result['pairs']) and result['parameter_restore_exact'])
    finally:
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        files=sorted(p for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink() and p.name!='raw_artifacts.sha256')
        (out/'raw_artifacts.sha256').write_text(''.join(f'{sha(p)}  {p}\n' for p in files))
    print(json.dumps(dict(success=result['success'],accepted=result['accepted'],replays=len(result['replays']),raw_files=len(files))))

if __name__=='__main__': main()
