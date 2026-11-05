#!/usr/bin/env python3
"""RI00 offline source audit. No simulator, parameters, network, or flight API."""
import argparse
import ctypes as C
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SOURCE = Path('/home/yr/Desktop/STA-ISTA-MATLAB-PX4')
RSTA = HERE.parents[1] / 'regularized_sta'
OLD_RUN = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision11/D/batch01/run029')
BASE = 'a286e40ec8bfbb0500b1c24add18c1a98b908778'
GAINS = {'XY': (.5, .1, .01, .4, .8), 'Z': (2., 1., .02, 4., 6.)}


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def save(p, value):
    with Path(p).open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def shape(p, eps):
    rho = max(-1., min(1., p/eps))
    return rho, math.sqrt(max(abs(p), eps))*rho


def root(s, h, k1, k2, eps):
    """Independent monotonic bisection: NOT the source quadratic/linear formula."""
    if s == 0:
        return 0.
    lo, hi = 0., abs(s)
    for _ in range(65):
        mid = (lo+hi)*.5
        rho, psi = shape(mid, eps)
        if mid + h*k1*psi + h*h*k2*rho > abs(s):
            hi = mid
        else:
            lo = mid
    return math.copysign((lo+hi)*.5, s)


def reference(x):
    k1,k2,eps,lo,hi,cap,s,nu,ff,h,integrate = x
    p = root(s,h,k1,k2,eps)
    rho,psi = shape(p,eps)
    candidate = nu-h*k2*rho
    raw = ff-k1*psi+candidate
    applied = min(hi,max(lo,raw))
    freeze = (raw>hi and candidate>nu) or (raw<lo and candidate<nu)
    next_nu = max(-cap,min(cap,nu if freeze else candidate))
    if not integrate:
        next_nu = nu
    return (p,raw,candidate,applied,next_nu)


class Bridge:
    def __init__(self,path):
        self.lib = C.CDLL(str(path))
        self.array = C.c_double * 11
        self.output = C.c_double * 8
        for n in ('source_float','source_double'):
            f=getattr(self.lib,n)
            f.argtypes=[C.POINTER(C.c_double),C.POINTER(C.c_double)]
            f.restype=None

    def call(self,x,precision='float'):
        out=self.output()
        getattr(self.lib,'source_'+precision)(self.array(*x),out)
        return list(out)


def source_index():
    # Manifest entries + manifest itself; excludes external build directories.
    names=[line.split(maxsplit=1)[1].lstrip('*') for line in
           (SOURCE/'SHA256SUMS.txt').read_text().splitlines()]
    names.append('SHA256SUMS.txt')
    return {n: {'sha256':sha(SOURCE/n),'bytes':(SOURCE/n).stat().st_size} for n in names}


def matlab_statements(text):
    return re.sub(r'\s+','', '\n'.join(line.split('%',1)[0] for line in text.splitlines()))


def elements(data):
    """Read MAT-v5 tagged elements in the SLX workspace (not MATLAB execution)."""
    offset=0
    while offset<len(data):
        tag,n=struct.unpack_from('<II',data,offset)
        if tag>>16:
            size=tag>>16
            yield tag&0xffff,data[offset+4:offset+4+size]
            offset+=8
        else:
            yield tag,data[offset+8:offset+8+n]
            offset+=8+((n+7)//8)*8


def matrix(data):
    e=list(elements(data))
    kind=struct.unpack_from('<I',e[0][1])[0]&0xff
    if kind==2:  # scalar struct: field width, names, one matrix per field
        width=struct.unpack('<I',e[3][1])[0]
        names=[e[4][1][i:i+width].split(b'\0')[0].decode()
               for i in range(0,len(e[4][1]),width)]
        assert len(names)==len(e)-5
        return {n:matrix(v[1]) for n,v in zip(names,e[5:])}
    assert kind==6, ('unsupported MAT class',kind)
    values=list(struct.unpack('<'+'d'*(len(e[3][1])//8),e[3][1]))
    return values[0] if len(values)==1 else values


def models():
    manifest=json.loads((SOURCE/'parameters/source_manifest.json').read_text())
    cfg=json.loads((SOURCE/'parameters/controller_parameters.json').read_text())
    checks=[]
    for item in manifest['matlab_functions']:
        wanted=matlab_statements((SOURCE/item['file']).read_text())
        assert sha(SOURCE/item['file'])==item['sha256']
        for address in item['embedded_matches']:
            model,entry=address.split(':')
            with zipfile.ZipFile(SOURCE/model) as z:
                tree=ET.fromstring(z.read(entry))
            scripts=[p.text or '' for p in tree.iter('P') if p.get('Name')=='script']
            assert any(wanted in matlab_statements(s) for s in scripts), address
            checks.append(address+':'+item['file'])
    result=[]
    for model in manifest['models']:
        path=SOURCE/model['file']
        assert sha(path)==model['sha256']
        with zipfile.ZipFile(path) as z:
            workspace=z.read('simulink/modelWorkspace.mxarray')
            assert workspace[:4]==b'\x00\x01IM'
            tagged=list(elements(workspace[8:]))
            assert len(tagged)==1 and tagged[0][0]==14
            variables=matrix(tagged[0][1])
            xml={n:z.read(n).decode() for n in z.namelist() if n.endswith('.xml')}
        family='ista' if '/ista/' in model['file'] else 'sta'
        key='HeightISTAParams' if family=='ista' else 'HeightSTAParams'
        assert variables[key]==cfg[family]['z']
        assert variables['HeightNominalPlant']==cfg['plant']
        if family=='ista':
            assert variables['XYISTAParams']==cfg[family]['xy']
        else:
            # STA XY constants live in two subsystem XML blocks.
            expected=cfg['sta']['xy']
            matches=[]
            for name,text in xml.items():
                for block in ET.fromstring(text).iter('Block'):
                    if block.get('Name')=='parameters':
                        for p in block.findall('P'):
                            if p.get('Name')=='Value' and p.text:
                                try: nums=[float(v) for v in p.text.strip('[]').split()]
                                except ValueError: continue
                                if nums==expected: matches.append(name)
            assert len(matches)==2, matches
        configuration=ET.fromstring(xml['simulink/configSet0.xml'])
        settings={p.get('Name'):p.text for p in configuration.iter('P')
                  if p.get('Name') in ('Solver','FixedStep','StopTime','StartTime','SolverType')}
        result.append(dict(file=model['file'],sha256=sha(path),workspace=variables,settings=settings))
    return dict(function_files=8,embedded_matches=len(checks),checks=checks,models=result,
                provenance_limit='Original Windows source tree/ZIP unavailable; verify packaged contents only; no Simulink run.')


def cadence(output):
    from pyulog import ULog
    record=json.loads((OLD_RUN/'result.json').read_text())
    log=next(v for v in record['logs'] if v['archive'].endswith('/log001.ulg'))
    path=Path(log['archive'])
    assert sha(path)==log['sha256']
    u=ULog(str(path),message_name_filter_list=['sta_velocity_ctrl_status','velocity_ctrl_selection'])
    assert not u.dropouts and not u.file_corruption
    d=u.get_dataset('sta_velocity_ctrl_status').data
    ix=np.flatnonzero((d['excitation_time']>=0)&(d['excitation_time']<64)&(d['effective_mode']==3)&(d['active_axes']==7))
    # Require a continuous logged sequence, do not discard bad rows.
    assert len(ix)>6000 and np.all(np.diff(ix)==1)
    sample=d['timestamp_sample'][ix].astype(np.int64)
    delta=np.diff(sample)
    assert np.all(np.diff(d['publish_seq'][ix].astype(np.int64))==1)
    assert np.all(d['inner_mode'][ix]==0) and np.all(d['inner_axes'][ix]==0)
    assert np.all(d['inner_divisor'][ix]==1)
    assert set(delta.tolist())=={8000,12000}
    assert np.max(np.abs(d['raw_dt'][ix[1:]]-delta*1e-6))<1e-8
    save(output/'cadence.json',dict(source_log=log,source_result_sha256=sha(OLD_RUN/'result.json'),
        rows=len(ix),first_sample_us=int(sample[0]),last_sample_us=int(sample[-1]),
        delta_us=delta.tolist(),delta_sha256=hashlib.sha256(delta.astype('<i8').tobytes()).hexdigest(),
        counts={str(v):int(np.sum(delta==v)) for v in (8000,12000)},
        hz=(len(sample)-1)*1e6/(sample[-1]-sample[0]),live_flight=False))
    assert sha(path)==log['sha256']
    return delta*1e-6


def grid(bridge):
    records=[]; maximum={'float':0.,'double':0.}
    cfg=json.loads((SOURCE/'parameters/controller_parameters.json').read_text())
    families=[('R03_'+n,v[:3]) for n,v in GAINS.items()]
    families += [('source_'+n,tuple(cfg['ista'][n][:3])) for n in ('xy','z')]
    for precision in maximum:
        cast=float if precision=='double' else lambda x:float(np.float32(x))
        for name,(k1,k2,eps) in families:
            for h in (.002,.008,.012,.04):
                b=eps+h*k1*math.sqrt(eps)+h*h*k2
                q=np.float32(b) if precision=='float' else b
                adjacent=[float(np.nextafter(q,-math.inf,dtype=np.float32 if precision=='float' else np.float64)),
                          float(q),float(np.nextafter(q,math.inf,dtype=np.float32 if precision=='float' else np.float64))]
                errors=[0.,1e-10,eps*.5,eps,.2,2.]+adjacent
                errors=errors+[-s for s in errors if s]
                for s in errors:
                    for nu in (-.3,0.,.3):
                        for ff in (-.2,0.,.2):
                            x=list(map(cast,[k1,k2,eps,-1000,1000,1000,s,nu,ff,h,1]))
                            got=bridge.call(x,precision)
                            assert got[0]==0
                            ref=reference(x)
                            gap=max(abs(a-b)/(1+abs(b)) for a,b in zip(got[1:6],ref))
                            rho,psi=shape(got[1],x[2])
                            a=got[2]-x[8]
                            residual=max(abs(got[1]-x[6]-x[9]*(a-x[7]))/(1+abs(x[6])),
                                abs(got[3]-x[7]+x[9]*x[1]*rho)/(1+abs(x[7])),
                                abs(a+x[0]*psi-got[3])/(1+abs(a)))
                            maximum[precision]=max(maximum[precision],gap,residual)
                            assert max(gap,residual)<(2e-6 if precision=='float' else 2e-12)
                            records.append((precision,name))
    return dict(cases=len(records),by_precision={p:sum(r[0]==p for r in records) for p in maximum},
                maximum_scaled_error_or_residual=maximum)


def closed_loops(bridge,actual):
    rows=[]
    constant=[('constant',d,nu,0.,0.,None) for d in (-.15,0.,.15) for nu in (-.1,0.,.1)]
    cases=constant+[('ramp',0.,.1,r,0.,None) for r in (-.002,.002)]
    cases += [('lag',.15,0.,0.,.06,None),('feasible_limit',.15,0.,0.,0.,.3),
              ('infeasible_limit',.15,0.,0.,0.,.05),('target_ff',.15,.1,0.,0.,None)]
    for family,(k1,k2,eps,nu_cap,_) in GAINS.items():
        for clock,steps in [('8ms',[.008]),('12ms',[.012]),('recorded',actual)]:
            for kind,d0,nu0,ramp,tau,limit in cases:
                nu,ref_nu=nu0,nu0
                v,ref_v=.05,.05
                acceleration,ref_accel=0.,0.
                t=0.; n=0; gap=0.; tail=[]; caps=0; peak=0.
                while t<60.-1e-9:
                    h=float(steps[n%len(steps)])
                    target=.1*math.sin(.4*t) if kind=='target_ff' else 0.
                    next_target=.1*math.sin(.4*(t+h)) if kind=='target_ff' else 0.
                    ff=(next_target-target)/h
                    lo,hi=(-limit,limit) if limit else (-1e6,1e6)
                    cap=nu_cap if limit else 1e6
                    x=[k1,k2,eps,lo,hi,cap,v-target,nu,ff,h,1.]
                    q=bridge.call(x)
                    assert q[0]==0
                    rr=reference([k1,k2,eps,lo,hi,cap,ref_v-target,ref_nu,ff,h,1.])
                    nu,ref_nu=q[5],rr[4]
                    u,ref_u=q[4],rr[3]
                    if tau:
                        decay=math.exp(-h/tau)
                        dv=u*h+(acceleration-u)*tau*(1-decay)
                        ref_dv=ref_u*h+(ref_accel-ref_u)*tau*(1-decay)
                        acceleration=u+(acceleration-u)*decay
                        ref_accel=ref_u+(ref_accel-ref_u)*decay
                    else:
                        dv,ref_dv=u*h,ref_u*h
                    disturbance=d0*h+ramp*(t*h+h*h*.5)
                    v+=dv+disturbance; ref_v+=ref_dv+disturbance
                    gap=max(gap,abs(v-ref_v)); peak=max(peak,abs(v-next_target))
                    caps+=int(abs(q[2]-q[4])>0)
                    if t>=50: tail.append((v-next_target,h))
                    t+=h; n+=1
                mean=sum(s*h for s,h in tail)/sum(h for _,h in tail)
                rmse=math.sqrt(sum(s*s*h for s,h in tail)/sum(h for _,h in tail))
                assert gap<2e-4,(family,clock,kind,gap)
                prediction=None
                if kind in ('constant','target_ff'):
                    assert abs(mean)<2e-5,(family,clock,kind,mean)
                if kind=='ramp' and clock!='recorded':
                    h=steps[0]
                    prediction=ramp*(eps+h*k1*math.sqrt(eps)+h*h*k2)/k2
                    assert abs(mean-prediction)<2e-5,(family,clock,mean,prediction)
                if kind=='infeasible_limit':
                    assert mean>1 and caps>0
                rows.append(dict(family=family,clock=clock,condition=kind,d0=d0,ramp=ramp,nu0=nu0,
                    steps=n,time_s=t,tail_mean=mean,tail_rmse=rmse,last_nu=nu,peak_error=peak,
                    maximum_independent_trajectory_difference=gap,limited_steps=caps,
                    fixed_h_ramp_prediction=prediction,
                    tracking_conclusion=('not_convergent' if kind=='infeasible_limit' else
                        'checked_constant_tail' if kind in ('constant','target_ff') else
                        'checked_fixed_h_ramp_relation' if kind=='ramp' and clock!='recorded' else
                        'finite_trajectory_only'),
                    scope='scalar offline object, not PX4 adapter/flight'))
    assert len(rows)==90
    return rows


class ProbeTests(unittest.TestCase):
    def test_root_sign_and_zero(self):
        self.assertEqual(root(0,.008,.5,.1,.01),0)
        self.assertAlmostEqual(root(.2,.008,.5,.1,.01),-root(-.2,.008,.5,.1,.01))

    def test_boundary_and_equation(self):
        eps=.01;h=.012;k1=.5;k2=.1
        b=eps+h*k1*math.sqrt(eps)+h*h*k2
        self.assertAlmostEqual(root(b,h,k1,k2,eps),eps)
        for s in (-2,-b,0,b,2):
            p=root(s,h,k1,k2,eps);rho,psi=shape(p,eps)
            self.assertAlmostEqual(p+h*k1*psi+h*h*k2*rho,s)

    def test_no_compensation_bias(self):
        h=.012;d=.15;nu=-d
        # General (uncompensated) relation has RHS s+h*nu.
        self.assertEqual(root(h*d+h*nu,h,.5,.1,.01),0)
        self.assertNotEqual(root(h*d,h,.5,.1,.01),0)

    def test_layer_matrix(self):
        for h in (.008,.012):
            for k1,k2,eps,_,_ in GAINS.values():
                alpha=k1/math.sqrt(eps);beta=k2/eps;D=1+h*alpha+h*h*beta
                m=np.array([[1/D,h],[-h*beta/D,1]])
                self.assertLess(max(abs(np.linalg.eigvals(m))),1)
                s,nu=.0002,.0001
                p,a,n,_,_=reference([k1,k2,eps,-10,10,10,s,nu,0,h,1])
                np.testing.assert_allclose([s+h*a,n],m@np.array([s,nu]),atol=1e-16)

    def test_seed_inverse_requires_h_and_candidate(self):
        s=.02;h=.012;k1=.5;k2=.1;eps=.01;c=.1
        p=root(s,h,k1,k2,eps);rho,psi=shape(p,eps)
        seed=c+k1*psi+h*k2*rho
        self.assertAlmostEqual(reference([k1,k2,eps,-10,10,10,s,seed,0,h,1])[1],c)
        old=c+k1*shape(s,eps)[1]
        self.assertGreater(abs(reference([k1,k2,eps,-10,10,10,s,old,0,h,1])[1]-c),1e-4)

    def test_protection_breaks_predictor(self):
        x=[.5,.1,.01,-10,10,10,.1,.2,0,.012,1]
        p,a,c,_,_=reference(x);applied=x[7]
        altered=a+applied-c
        self.assertGreater(abs(p-x[6]-x[9]*(altered-x[7])),1e-6)
        self.assertAlmostEqual(p-x[6]-x[9]*(altered-x[7]),-x[9]*(applied-c))

    def test_matlab_normalization(self):
        self.assertEqual(matlab_statements('a = 1; % foo\nb=2;'), 'a=1;b=2;')

    def test_parameter_units_no_rateg(self):
        for k1,k2,eps,nu,a in GAINS.values():
            self.assertTrue(0<eps<=1 and 0<k1 and 0<k2 and 0<nu and 0<a)

    def test_source_invalid_inputs(self):
        x=[.5,.1,.01,-10,10,10,.1,.2,0,.008,1]
        for index,values in [(9,[0,-.01,math.inf,math.nan]),
                             (2,[0,-.1,math.inf]),(6,[math.nan,math.inf])]:
            for value in values:
                y=x.copy();y[index]=value
                q=self.bridge.call(y)
                self.assertNotEqual(q[0],0)
                self.assertAlmostEqual(q[5],float(np.float32(.2)))

    def test_source_output_survives_external_state_freeze(self):
        x=[.5,.1,.01,-10,10,10,.1,.2,0,.012,1]
        before=self.bridge.call(x)
        x[-1]=0
        frozen=self.bridge.call(x)
        self.assertEqual(before[2],frozen[2])
        self.assertNotEqual(frozen[3],frozen[5])

    def test_source_local_and_state_limits_do_not_recompute_output(self):
        x=[.5,.1,.01,-.01,.01,.01,-.1,0,0,.012,1]
        limited=self.bridge.call(x)
        self.assertEqual(limited[6],1)
        self.assertEqual(limited[5],0)
        self.assertGreater(limited[2],limited[4])
        x[3:6]=[-10,10,.0001]
        capped=self.bridge.call(x)
        self.assertEqual(capped[7],1)
        self.assertNotEqual(capped[3],capped[5])
        self.assertEqual(capped[2],limited[2])

    def test_hte_saved_output_not_next_evaluation(self):
        x=[2,1,.02,-10,10,10,.01,.1,0,.012,1]
        p,a,nu_next,_,_=reference(x)
        x[7]=nu_next
        next_a=reference(x)[1]
        self.assertNotEqual(next_a,a)  # would integrate once more
        old,new,g,ff=.7,.71,9.80665,.2
        shift=(old/new-1)*(a+ff-g)
        self.assertAlmostEqual((a+ff-g)*old,(a+ff+shift-g)*new)


def interface_evidence():
    mode_source=REPO/'src/modules/mc_pos_control/mc_pos_control_params.c'
    names=re.findall(r'PARAM_DEFINE_\w+\((\w+)',mode_source.read_text())
    params=[f'MPC_VC_{kind}_{axis}' for kind in ('L1','L2','EPS','NU','A') for axis in 'XYZ']
    assert all(names.count(n)==1 and len(n)<=16 for n in params)
    generated={}
    for name in ('velocity_ctrl_selection','sta_velocity_ctrl_status'):
        p=REPO/'build/px4_sitl_default/msg/topics_sources'/f'{name}.cpp'
        fields=re.search(r'fields\[\] = "([^"]+)"',p.read_text()).group(1)
        # logger's snprintf includes name separator and terminating NUL.
        length=len(name+':'+fields)+1
        assert length<1500
        msg=REPO/'msg'/f'{name}.msg'
        assert 'ORB_QUEUE_LENGTH = 8' in msg.read_text()
        generated[name]=dict(format_bytes_including_nul=length,generated_sha256=sha(p),
            message_sha256=sha(msg),queue=8)
    files=[
        'src/modules/mc_pos_control/PositionControl/PositionControl.cpp',
        'src/modules/mc_pos_control/PositionControl/PositionControl.hpp',
        'src/modules/mc_pos_control/PositionControl/VelocityControlSelector.hpp',
        'src/modules/mc_pos_control/PositionControl/StaVelocityProtection.cpp',
        'src/modules/mc_pos_control/PositionControl/StaVelocityProtection.hpp',
        'src/modules/mc_pos_control/PositionControl/RegularizedStaVelocityControl.cpp',
        'src/modules/mc_pos_control/PositionControl/RegularizedStaVelocityControl.hpp',
        'src/modules/mc_pos_control/MulticopterPositionControl.cpp',
        'src/modules/mc_pos_control/MulticopterPositionControl.hpp',
        'src/modules/mc_pos_control/mc_pos_control_params.c',
        'src/modules/logger/logged_topics.cpp',
        'src/modules/mc_rate_control/StaRateControl/IstaRateControl.cpp',
        'src/modules/mc_rate_control/StaRateControl/ProperIstaRateControl.cpp']
    manifest_path=RSTA/'r03_revision11/manifest.json'
    jobs=json.loads(manifest_path.read_text())
    selected=next(j for j in jobs if j['id']=='run029')
    assert selected['mode']==3 and selected['axes']==7
    params_actual=selected['parameters']
    for name,val in dict(MC_RTC_MODE=0,MC_STA_AXES=0,MC_RTC_DIV=1,
                          MC_RATT_TEST=0,MC_STA_TKO_MGT=0,MPC_VC_DIV=1).items():
        assert params_actual[name]==val
    for axis in 'XYZ':
        expected=GAINS['Z' if axis=='Z' else 'XY']
        for key,value in zip(('L1','L2','EPS','NU','A'),expected):
            assert params_actual[f'MPC_VC_{key}_{axis}']==value
    # Reserve an unoccupied future class name, without adding any production path.
    collisions=[]
    for p in (REPO/'src/modules/mc_pos_control').rglob('*'):
        if p.is_file() and p.suffix in ('.cpp','.hpp','.c','.h'):
            if 'RegularizedIstaVelocityControl' in p.read_text():
                collisions.append(str(p))
    assert not collisions
    return dict(mode_candidate=4,production_admission=False,parameter_strategy='reuse complete 15-field profile, atomic disarmed apply; separate algorithm files',
        parameter_names=params,formats=generated,code_fingerprints={p:sha(REPO/p) for p in files},
        parameter_source=str(manifest_path.relative_to(REPO)),parameter_source_sha256=sha(manifest_path),
        full_r03_parameters=params_actual,offline_candidate=GAINS,flight_qualified=False)


def run(output):
    output.mkdir(parents=True,exist_ok=False)
    commands=[]
    def command(argv,cwd=REPO,check=True):
        p=subprocess.run(argv,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        log=output/f'command_{len(commands)+1:02d}.log'
        log.write_text(p.stdout)
        commands.append(dict(argv=argv,cwd=str(cwd),exit_code=p.returncode,log=str(log),sha256=sha(log)))
        save(output/f'command_{len(commands):02d}.json',commands[-1])
        if check and p.returncode: raise RuntimeError(commands[-1])
        return p.stdout
    try:
        entry=dict(head=command(['git','rev-parse','HEAD']).strip(),
            branch=command(['git','branch','--show-current']).strip(),
            worktree=command(['git','status','--porcelain']),
            submodules=command(['git','submodule','status','--recursive']))
        assert entry['head']==BASE and entry['branch']=='research/ista-velocity-regularized'
        assert len(entry['submodules'].splitlines())==33
        assert all(s.startswith(' ') for s in entry['submodules'].splitlines())
        internal=command(['git','submodule','foreach','--quiet','--recursive','git status --porcelain'])
        assert not internal.strip()
        save(output/'entry.json',entry)
        source_before=source_index();save(output/'source_fingerprints.json',source_before)
        command(['sha256sum','--check','SHA256SUMS.txt'],SOURCE)
        frozen=json.loads((RSTA/'r03_revision11/gates/D/frozen.json').read_text())
        # Result reports may evolve since freezing; bind production/model/tools
        # and all external assets, report historical documentation separately.
        matched=[];changed=[]
        for name,expected in frozen['assets'].items():
            actual=sha(REPO/name)
            (matched if actual==expected else changed).append(name)
            if name.startswith(('src/','msg/','sitl/','Tools/','platforms/','boards/','ROMFS/')):
                assert actual==expected,name
        for name,expected in frozen['external_assets'].items():
            assert sha(name)==expected,name
        save(output/'r03_assets.json',dict(matched=len(matched),changed_since_flight=changed,
            external_verified=len(frozen['external_assets']),derived_iris_sha256=frozen['derived_iris_sha256']))
        save(output/'models.json',models())
        build=output/'source_build'
        command(['cmake','-S',str(SOURCE),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release'])
        command(['cmake','--build',str(build),'-j2'])
        command(['ctest','--test-dir',str(build),'--output-on-failure','-V'])
        library=output/'source_bridge.so'
        command(['g++','-std=c++14','-O2','-fPIC','-shared','-Wall','-Wextra','-Werror','-pedantic-errors',
                 '-I'+str(SOURCE/'cpp'),'-I'+str(REPO/'src/modules/mc_pos_control/PositionControl'),
                 str(HERE/'source_bridge.cpp'),'-o',str(library)])
        bridge=Bridge(library)
        ProbeTests.bridge=bridge
        save(output/'interface.json',interface_evidence())
        assert bridge.lib.selector_rejects_mode4()
        weaknesses=[bridge.lib.source_weak_commit(i) for i in range(3)]
        assert weaknesses==[1,1,1]
        # Source float underflow is not rejected. Future production policy must differ.
        underflow=bridge.call([.5,.1,.01,-10,10,10,1e-44,0,0,.008,1])
        overflow=bridge.call([.5,.1,.01,-1e38,1e38,1e38,1e38,0,0,.008,1])
        assert underflow[0]==0 and overflow[0]==2
        # Compensated MATLAB input shift can erase a small residual numerically.
        s=1e-12;h=.012;nu=1e20
        shifted=(s+h*nu)-h*nu
        assert shifted==0 and root(s,h,.5,.1,.01)!=0
        save(output/'source_limitations.json',dict(foreign_reset_tamper_commits=weaknesses,
            float_subnormal_input=1e-44,underflow_status=underflow[0],underflow_candidate_nu=underflow[3],
            large_error_status=overflow[0],shift_cancellation=dict(error=s,nu=nu,h=h,after_shift=shifted),
            mode4_rejected=True,matlab_executable=shutil.which('matlab'),octave_executable=shutil.which('octave')))
        stream=io.StringIO()
        tests=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProbeTests))
        (output/'probe_tests.log').write_text(stream.getvalue())
        assert tests.wasSuccessful()
        g=grid(bridge);save(output/'grid.json',g)
        actual=cadence(output)
        loops=closed_loops(bridge,actual);save(output/'closed_loops.json',loops)
        assert source_index()==source_before
        assert command(['git','diff',BASE,'--','src','msg','Tools','platforms','sitl','ROMFS','boards'])==''
        summary=dict(success=True,source_tests_ctest=2,matlab_fixture_rows=7980,new_python_tests=tests.testsRun,
            grid=g,closed_loop_cases=len(loops),source_calls=sum(v['steps'] for v in loops),
            max_trajectory_difference=max(v['maximum_independent_trajectory_difference'] for v in loops),
            source_unchanged=True,production_unchanged=True,new_flights=0,new_seed_registrations=0,
            matlab_run=False,px4_build=False,commands=commands)
        save(output/'summary.json',summary)
        print(json.dumps({k:v for k,v in summary.items() if k!='commands'},indent=2))
    except Exception as e:
        save(output/'failure.json',dict(error=repr(e),commands=commands))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output.resolve())
