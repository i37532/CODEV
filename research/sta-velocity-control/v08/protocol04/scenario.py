"""Draft V08 pilot model/force evidence; not connected to training01."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
import numpy as np

REPO=Path('/home/yr/Desktop/Codev-autopilot')
sys.path.insert(0,str(REPO/'research/sta-velocity-control/v06/soft_landing'))
from contact_model import derive,shape

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def force_enu(t,phases):
    t=np.asarray(t,dtype=float);phases=np.asarray(phases,dtype=float)
    if phases.shape!=(2,) or not np.all(np.isfinite(t)) or not np.all(np.isfinite(phases)):
        raise ValueError('Invalid force reference')
    inside=(t>8)&(t<56);u=np.where(inside,t-8,0.)
    envelope=np.where(inside,np.sin(np.pi*u/48)**2,0.)
    north=.15*envelope*np.sin(2*np.pi*u/16+phases[0])
    east=.15*envelope*np.sin(2*np.pi*u/24+phases[1])
    return np.stack([east,north,np.zeros_like(t)],axis=-1)

def phases(seed):
    if not isinstance(seed,int) or seed<=0:raise ValueError('Invalid force phase seed')
    return np.random.Generator(np.random.PCG64(seed)).uniform(0,2*np.pi,2).tolist()

def inertials(root):
    result={}
    for link in root.findall('./model/link'):
        inertial=link.find('inertial')
        if inertial is None:raise ValueError('Missing link inertia')
        values={k:float(inertial.findtext('inertia/'+k)) for k in ('ixx','iyy','izz','ixy','ixz','iyz')}
        m=float(inertial.findtext('mass'))
        v=values;matrix=np.array([[v['ixx'],v['ixy'],v['ixz']],[v['ixy'],v['iyy'],v['iyz']],[v['ixz'],v['iyz'],v['izz']]])
        if not np.all(np.isfinite(matrix)) or not np.isfinite(m) or m<=0:raise ValueError('Invalid mass/inertia')
        eig=np.linalg.eigvalsh(matrix)
        if eig[0]<=0 or eig[-1]>sum(eig[:2])+1e-12:raise ValueError('Nonphysical inertia')
        pose=np.array([float(x) for x in (link.findtext('pose') or '0 0 0 0 0 0').split()])
        cg=np.array([float(x) for x in (inertial.findtext('pose') or '0 0 0 0 0 0').split()])
        if pose.shape!=(6,) or cg.shape!=(6,) or not np.all(np.isfinite(np.r_[pose,cg])):raise ValueError('Invalid pose')
        if np.any(pose[3:]) or np.any(cg[3:]):raise ValueError('New rotated link requires audited transform')
        result[link.get('name')]=dict(mass=m,inertia=values,cog=(pose[:3]+cg[:3]).tolist())
    if not result:raise ValueError('No inertials')
    return result

def scale_density(root,scale):
    if not np.isfinite(scale) or scale<=0:raise ValueError('Invalid density ratio')
    before=inertials(root);result=copy.deepcopy(root)
    for item in result.findall('./model/link/inertial'):
        for node in [item.find('mass'),*list(item.find('inertia'))]:node.text=format(float(node.text)*scale,'.17g')
    after=inertials(result)
    for name,a in before.items():
        b=after[name]
        if not np.allclose(np.array(list(a['inertia'].values()))*scale,list(b['inertia'].values()),atol=1e-14,rtol=1e-14):raise ValueError('Inertia scaling')
        if a['cog']!=b['cog'] or not np.isclose(a['mass']*scale,b['mass'],atol=1e-14,rtol=1e-14):raise ValueError('Mass/CoG scaling')
    return result

def expected_trees(run,seeded_plugins,force_library,job):
    if job['scene'] not in ('heading','force','mass'):raise ValueError('Unknown pilot scene')
    scale=1.10 if job['scene']=='mass' else 1.
    iris=scale_density(derive(ET.parse(REPO/'Tools/sitl_gazebo/models/iris/iris.sdf').getroot()),scale)
    gps=scale_density(ET.parse(REPO/'Tools/sitl_gazebo/models/gps/gps.sdf').getroot(),scale)
    gps_uri=iris.find('model/include/uri')
    if gps_uri is None or gps_uri.text!='model://gps':raise ValueError('Unexpected Iris GPS include')
    # A generic model://gps can resolve to a default model before the override.
    # Pin the derived file explicitly and audit its actual loaded inertials.
    gps_uri.text=str(run/'models/gps')
    imu=iris.find("model/plugin[@name='rotors_gazebo_imu_plugin']")
    imu.set('filename',str(seeded_plugins/'libm10_imu.so'))
    plugin=ET.SubElement(iris.find('model'),'plugin',name='v08_force_audit',filename=str(force_library))
    phi=phases(job['seed'])
    values=dict(trigger=str(run/'force.trigger'),log=str(run/'force.csv'),model_audit=str(run/'loaded_model.csv'),
                force_enabled='true' if job['scene']=='force' else 'false',north_phase=phi[0],east_phase=phi[1])
    for key,value in values.items():ET.SubElement(plugin,key).text=str(value)
    return iris,gps

def verify_model(run,seeded_plugins,force_library,job,replay=False):
    if replay:
        logs=json.loads((run/'result.json').read_text())['logs']
        dirs={Path(x['archive']).parent for x in logs}
        if len(dirs)!=1:raise ValueError('Ambiguous pilot model path')
        run=next(iter(dirs))
    expected=expected_trees(run,seeded_plugins,force_library,job)
    paths=[run/'models/iris/iris.sdf',run/'models/gps/gps.sdf']
    for wanted,path in zip(expected,paths):
        if shape(wanted)!=shape(ET.parse(path).getroot()):raise ValueError('Pilot model whitelist mismatch')
    if digest(paths[0])!=digest(run/'models/iris/iris-gen.sdf'):raise ValueError('Generated Iris differs')
    return dict(iris_sha256=digest(paths[0]),gps_sha256=digest(paths[1]),density_scale=1.1 if job['scene']=='mass' else 1.,
                force_frame='world ENU',force_unit='N',phase_north_east=phases(job['seed']))

def prepare_model(run,seeded_plugins,force_library,job):
    iris,gps=expected_trees(run,seeded_plugins,force_library,job)
    for name,tree in [('iris',iris),('gps',gps)]:
        folder=run/'models'/name;folder.mkdir(parents=True,exist_ok=False)
        ET.ElementTree(tree).write(folder/(name+'.sdf'),encoding='utf-8',xml_declaration=True)
        shutil.copyfile(REPO/f'Tools/sitl_gazebo/models/{name}/model.config',folder/'model.config')
    shutil.copyfile(run/'models/iris/iris.sdf',run/'models/iris/iris-gen.sdf')
    (run/'models/iris/meshes').symlink_to(REPO/'Tools/sitl_gazebo/models/iris/meshes',target_is_directory=True)
    return verify_model(run,seeded_plugins,force_library,job)

def trigger_origin(d):
    t=d['excitation_time'];sample=d['timestamp_sample']
    if not np.isfinite(t) or not 0<=t<1.5 or not np.isfinite(sample) or sample<=0:raise ValueError('Invalid/late task trigger')
    return sample*1e-6-t

def loaded_model(run,job):
    table=np.genfromtxt(run/'loaded_model.csv',delimiter=',',names=True,dtype=None,encoding='utf-8')
    if table.shape!=(7,):raise ValueError('Loaded model must contain seven unique links including GPS')
    scale=1.1 if job['scene']=='mass' else 1.
    expected=inertials(ET.parse(REPO/'Tools/sitl_gazebo/models/iris/iris.sdf').getroot())
    gps=inertials(ET.parse(REPO/'Tools/sitl_gazebo/models/gps/gps.sdf').getroot())['link']
    gps['cog'][0]+=.1;expected['gps0::link']=gps
    seen=set();mass=0.;weighted=np.zeros(3);nominal_mass=0.;nominal_weighted=np.zeros(3)
    for row in table:
        name=row['link'];key='gps0::link' if name.endswith('::gps0::link') else name.rsplit('::',1)[-1]
        if key not in expected or key in seen:raise ValueError('Wrong/duplicate loaded link')
        seen.add(key);wanted=expected[key]
        if not np.isclose(row['mass_kg'],wanted['mass']*scale,atol=1e-12,rtol=1e-12):raise ValueError('Actual mass differs')
        for entry,value in wanted['inertia'].items():
            if not np.isclose(row[entry],value*scale,atol=1e-12,rtol=1e-12):raise ValueError('Actual inertia differs')
        cog=np.array([row['cog_model_'+x] for x in 'xyz'])
        if not np.all(np.isfinite(cog)) or np.max(abs(cog-wanted['cog']))>1e-5:raise ValueError('Actual link CoG differs')
        mass+=row['mass_kg'];weighted+=row['mass_kg']*cog
        nominal_mass+=wanted['mass'];nominal_weighted+=wanted['mass']*np.array(wanted['cog'])
    if seen!=set(expected) or np.max(abs(weighted/mass-nominal_weighted/nominal_mass))>1e-5:raise ValueError('Total CoG differs')
    return dict(links=sorted(seen),mass_kg=float(mass),nominal_mass_kg=nominal_mass,
        cog_model_m=(weighted/mass).tolist(),density_scale=scale,sha256=digest(run/'loaded_model.csv'))

def force_evidence(run,job,d,events):
    csv=np.genfromtxt(run/'force.csv',delimiter=',',names=True)
    sim=csv['sim_s'];elapsed=csv['elapsed_s']
    force=np.column_stack([csv[k] for k in ('fx_enu_N','fy_enu_N','fz_enu_N')])
    if len(sim)<10000 or not np.all(np.isfinite(np.r_[sim,elapsed,force.ravel()])) or np.any(np.diff(sim)<=0) or np.max(np.diff(sim))>.004001:
        raise ValueError('Incomplete force physics history')
    measured=job['scene']=='force'
    expected=force_enu(elapsed,phases(job['seed'])) if measured else np.zeros_like(force)
    error=float(np.max(abs(force-expected)))
    if error>1e-12:raise ValueError('Applied world-force waveform differs')
    active=(d['timestamp']>=events['hover_start'])&(d['timestamp']<events['hover_end'])&(d['excitation_time']>=0)&(d['excitation_time']<64)
    origins=d['timestamp_sample'][active].astype(float)*1e-6-d['excitation_time'][active].astype(float)
    if len(origins)<6300 or np.ptp(origins)>1e-5:raise ValueError('Incomplete controller task clock')
    receipt=json.loads((run/'force_trigger_origin.json').read_text())
    origin=receipt['origin_sim_s']
    if abs(origin-float(np.median(origins)))>1e-5 or abs(origin-trigger_origin(receipt['diagnostic']))>1e-12:
        raise ValueError('Wrong force/controller origin')
    triggered=elapsed>=0
    if not np.any(triggered) or np.max(abs(sim[triggered]-elapsed[triggered]-origin))>1e-9:
        raise ValueError('Force clock mismatch')
    if elapsed[triggered][0]>=2 or elapsed[-1]<64:raise ValueError('Late/unfinished force task')
    nonzero=np.linalg.norm(force,axis=1)>0
    if measured and (np.count_nonzero(nonzero)<11000 or np.max(np.linalg.norm(force,axis=1))<.1):raise ValueError('Missing intended disturbance')
    if np.any(nonzero&((sim<events['hover_start']*1e-6)|(sim>=events['land_command']*1e-6))):
        raise ValueError('Force outside airborne observation')
    return dict(samples=len(sim),nonzero_samples=int(nonzero.sum()),frame='world ENU',unit='N',
        peak_norm_N=float(np.max(np.linalg.norm(force,axis=1))),waveform_max_error_N=error,
        origin_sim_s=origin,trigger_delay_s=float(elapsed[triggered][0]),sha256=digest(run/'force.csv'))
