"""Additional contact evidence, fail closed; never relax inherited V06 checks."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from contact_model import validate

REPO = Path(__file__).resolve().parents[4]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def require_passive(path):
    """Bind physical admission to fixed cases, source and retained raw sequences."""
    e=json.loads(Path(path).read_text())
    expected={(v,s,r) for v in ('original','compliant') for s in (.55,.7) for r in (0,5,-5,10,-10)}
    keys=[(c['variant'],c['speed'],c['roll_deg']) for c in e['cases']]
    if not e['success'] or e['ode_seed']!=26928 or len(keys)!=20 or set(keys)!=expected:
        raise ValueError('Incomplete passive contact admission')
    if not all(c['accepted'] for c in e['cases'] if c['variant']=='compliant'):
        raise ValueError('Failed contact candidate')
    for name,value in e['assets'].items():
        if sha(Path(name))!=value: raise ValueError('Changed passive source '+name)
    from passive_check import summarize
    commands={c['name']:c for c in e['commands']}
    for case in e['cases']:
        name=f"{case['variant']}_{case['speed']}_{case['roll_deg']}"
        command=commands[name]; csv=Path(command['argv'][-1])
        if command['exit_code']!=0 or sha(csv)!=case['sha256']: raise ValueError('Changed passive evidence')
        if any(case[k]!=v for k,v in summarize(csv).items()): raise ValueError('Passive result mismatch')
    return dict(cases=20,candidate_cases=10,ode_seed=26928)


def verify_model(run, plugins, replay=False):
    source = run
    if replay:
        record = json.loads((run/'result.json').read_text())
        paths = {Path(item['archive']).parent for item in record['logs']}
        if len(paths) != 1: raise ValueError('Ambiguous model evidence directory')
        source = next(iter(paths))
    original = REPO/'Tools/sitl_gazebo/models/iris/iris.sdf'
    derived = source/'models/iris/iris.sdf'
    generated = source/'models/iris/iris-gen.sdf'
    a = ET.parse(original).getroot(); b = ET.parse(derived).getroot()
    query = "model/plugin[@name='rotors_gazebo_imu_plugin']"
    if len(b.findall(query)) != 1 or b.find(query).get('filename') != str(plugins/'libm10_imu.so'):
        raise ValueError('Wrong seeded IMU plugin')
    b.find(query).set('filename', a.find(query).get('filename'))
    validate(a,b)
    if sha(derived) != sha(generated): raise ValueError('Generated Iris differs from checked model')
    if replay:
        manifest=json.loads((run/'model_manifest.json').read_text())
        if manifest['original'] != sha(original) or manifest['derived'] != sha(derived):
            raise ValueError('Changed model manifest')
    return dict(original=sha(original), derived=sha(derived), contact_variant='iris-compliant-v1')


def window(d,start,end,gap_us):
    t=np.asarray(d['timestamp'],dtype=np.int64)
    if not len(t) or np.any(t<=0) or np.any(np.diff(t)<=0):
        raise ValueError('Invalid health publication clock')
    before=np.searchsorted(t,start,side='right')-1
    after=np.searchsorted(t,end,side='left')
    if before<0 or after>=len(t): raise ValueError('Missing health boundaries')
    m=np.zeros(len(t),dtype=bool); m[before:after+1]=True
    if np.max(np.diff(t[m]))>gap_us: raise ValueError('Health evidence gap')
    return m


def check_health(log,start,end):
    if not 0<start<end: raise ValueError('Invalid landing interval')
    output=dict(accel={},imu={},estimator={},selector={})
    for instance in range(3):
        d=log.get_dataset('sensor_accel',instance).data; m=window(d,start,end,12000)
        if np.any(np.diff(d['timestamp_sample'][m].astype(np.int64))<=0):
            raise ValueError('Accel sample clock')
        values=np.column_stack([d[k][m] for k in ('x','y','z')])
        if not np.all(np.isfinite(values)): raise ValueError('Nonfinite acceleration')
        clip=np.column_stack([d[f'clip_counter[{a}]'][m] for a in range(3)])
        if np.any(clip!=clip[0]): raise ValueError('Acceleration clipping')
        output['accel'][str(instance)]=dict(samples=int(m.sum()),peak_abs=np.max(np.abs(values),axis=0).tolist())
        d=log.get_dataset('vehicle_imu',instance).data; m=window(d,start,end,12000)
        if np.any(d['delta_velocity_clipping'][m]): raise ValueError('IMU clipping')
        if not np.all(np.isfinite(d['delta_velocity_dt'][m])) or np.any(d['delta_velocity_dt'][m]<=0):
            raise ValueError('Invalid IMU integration interval')
        output['imu'][str(instance)]=dict(samples=int(m.sum()),clipping=0)
    for instance in range(6):
        d=log.get_dataset('estimator_status',instance).data; m=window(d,start,end,40000)
        if np.any(d['filter_fault_flags'][m]): raise ValueError('Estimator fault')
        output['estimator'][str(instance)]=dict(samples=int(m.sum()),faults=0)
    d=log.get_dataset('estimator_selector_status').data; m=window(d,start,end,2000000)
    if np.any(d['primary_instance'][m]!=d['primary_instance'][m][0]): raise ValueError('Estimator switched')
    output['selector']=dict(samples=int(m.sum()),primary=int(d['primary_instance'][m][0]))
    return output
