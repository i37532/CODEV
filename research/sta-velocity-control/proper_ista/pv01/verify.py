"""Finite PV01 independent oracles/physical objects; default dry-run, no flight."""
import argparse
import decimal
import gzip
import math
import random
import struct
from common import *

f32=old.f32
ETA=2.**-149
U=2.**-24
GAMMA=64*2.**-53/(1-64*2.**-53)
MAX=f32(3.4028234663852886e38)
PV00_DATA=ROOT.parent/'PV00'

def reference(s,nu,h,l1=2.,l2=1.):
    """Independent monotone bisection in z, output from prediction equation.

    No rationalized quadratic or production branch output expression here.
    Bracket stopping is floating adjacency, capped at 1200 for extreme scales.
    """
    q=h*h*l2
    if abs(s)<=q:
        z=0.;xi=s/q
    else:
        lo,hi=0.,abs(s)-q;rhs=hi
        for _ in range(1200):
            mid=lo+(hi-lo)/2
            if mid==lo or mid==hi:break
            if mid+h*l1*math.sqrt(mid)<rhs:lo=mid
            else:hi=mid
        else:raise AssertionError('unresolved double bracket')
        z=math.copysign(lo+(hi-lo)/2,s);xi=math.copysign(1.,s)
    nxt=math.fsum((nu,-h*l2*xi))
    a=math.fsum((nxt,(z-s)/h))
    return z,a,nxt,xi

def high_precision(s,nu,h,l1=2.,l2=1.):
    with decimal.localcontext() as ctx:
        ctx.prec=100
        D=decimal.Decimal.from_float
        s,nu,h,l1,l2=map(D,map(f32,(s,nu,h,l1,l2)))
        q=h*h*l2
        if abs(s)<=q:z=decimal.Decimal(0);xi=s/q
        else:
            lo,hi=decimal.Decimal(0),abs(s)-q;rhs=hi
            for _ in range(1200):
                mid=(lo+hi)/2
                if mid==lo or mid==hi:break
                if mid+h*l1*mid.sqrt()<rhs:lo=mid
                else:hi=mid
            else:raise AssertionError('unresolved Decimal bracket')
            z=(lo+hi)/2*(1 if s>0 else -1);xi=decimal.Decimal(1 if s>0 else -1)
        nxt=nu-h*l2*xi;a=nxt+(z-s)/h
        return dict(z=str(z),a=str(a),nu_next=str(nxt),xi=str(xi))

def budget_check(c,h,l1=2.,l2=1.,ideal=None):
    """Public rounded outputs checked with explicit ULP+binary64 budgets."""
    s,z,a,nu,nxt,xi,branch=c
    expected=2 if abs(s)<=h*h*l2 else (1 if s>0 else 3)
    assert branch==expected and abs(xi)<=1 and (z==0 or xi==math.copysign(1.,z))
    if ideal is None:ideal=reference(s,nu,h,l1,l2)
    ba=U*abs(ideal[1])+ETA/2;bn=U*abs(ideal[2])+ETA/2
    rows=[(z,[s,h*a,-h*nxt],h*(ba+bn)),
          (nxt,[nu,-h*l2*xi,0.],bn),
          (a,[-l1*math.sqrt(abs(z))*xi,2*nxt,-nu],ba+2*bn),
          (s,[z,h*l1*math.sqrt(abs(z))*xi,h*h*l2*xi],0.)]
    ratios=[]
    for lhs,terms,extra in rows:
        difference=abs(lhs-sum(terms));bound=GAMMA*(abs(lhs)+sum(map(abs,terms)))+extra
        assert difference<=bound, (c,h,l1,l2,difference,bound)
        ratios.append(difference/bound if bound else 0.)
    return max(ratios)

def compile_core(out):
    library=out/'proper_velocity.so'
    run(out,'compile_bridge',['g++','-std=c++14','-pedantic-errors','-O2','-Wall','-Wextra','-Werror',
        '-fno-fast-math','-fno-reciprocal-math','-fsigned-zeros','-ffp-contract=off','-frounding-math',
        '-fno-exceptions','-fno-rtti','-shared','-fPIC','-I',CONTROL,
        HERE/'kernel_bridge.cpp',CONTROL/'ProperIstaVelocityControl.cpp','-o',library])
    return library

def normal_cases():
    rng=random.Random(1012026)
    cases=[]
    for _ in range(6000):
        cases.append(tuple(map(f32,(rng.uniform(-2,2),rng.uniform(-1,1),rng.uniform(.004,.016),
                                    rng.uniform(.5,4),rng.uniform(.2,3)))))
    q=2.**-14
    bits=struct.unpack('I',struct.pack('f',q))[0]
    for sg in (1,-1):
        for word in (bits-1,bits,bits+1):
            for nu in (0.,-.25,.25):
                cases.append((sg*struct.unpack('f',struct.pack('I',word))[0],nu,2.**-7,2.,1.))
    assert len(cases)==6018
    return cases

def scalar_checks(out,library):
    rows=[];maximum=0.;old_max=0.;old_accepts=0
    legacy=PV00_DATA/'original01/kernels.so'
    # This is PV00's frozen freshly built old-core artifact, not a newly claimed rebuild.
    frozen_index=json.loads((PV00/'results/archive_index.json').read_text())
    for path in (legacy,PV00_DATA/'original01/summary.json'):
        assert sha(path)==frozen_index[str(path)]['sha256'],('changed PV00 source',path)
    for s,nu,h,l1,l2 in normal_cases():
        core=old.Kernel(library,2,(l1,l2,0.));baseline=old.Kernel(legacy,2,(l1,l2,0.))
        try:
            assert core.reset(nu) and baseline.reset(nu)
            code,c=core.evaluate(s,0.,h);assert code==0,(code,s,nu,h,l1,l2)
            oracle=reference(s,nu,h,l1,l2)
            maximum=max(maximum,budget_check(c,h,l1,l2,oracle))
            delta=max(abs(c[2]-oracle[1])/(1+abs(oracle[1])),abs(c[4]-oracle[2])/(1+abs(oracle[2])))
            assert delta<=2e-6
            before=core.state();assert before==f32(nu) and core.commit() and core.state()==c[4]
            assert not core.commit()
            old_code,oc=baseline.evaluate(s,0.,h)
            if old_code==0:
                old_accepts+=1
                change=max(abs(c[2]-oc[2])/(1+abs(oc[2])),abs(c[4]-oc[4])/(1+abs(oc[4])))
                old_max=max(old_max,change);assert change<=2e-6
            rows.append(dict(input=[s,nu,h,l1,l2],candidate=c,reference=oracle,
                old_status=old_code,scaled_output_difference=delta))
        finally:core.close();baseline.close()
    save(out/'normal.json',rows)
    return dict(cases=len(rows),max_budget_fraction=maximum,old_core_accepted=old_accepts,
        old_output_scaled_difference=old_max,legacy_library=dict(path=str(legacy),sha256=sha(legacy)),
        legacy_summary_sha256=sha(PV00_DATA/'original01/summary.json'))

def numeric_checks(out,library):
    source=PV00_DATA/'numerical01/summary.json'
    grid=json.loads(source.read_text())['grid'];assert len(grid)==122
    rows=[];accepted=rejected=0
    for item in grid:
        r=item['input'];s,nu,h,l1,l2=map(f32,(r['s'],r['nu'],r['h'],r['l1'],r['l2']))
        oracle=high_precision(s,nu,h,l1,l2)
        # Compare at the binary64 solve boundary. E.g. FLT_MAX+2 rounds to
        # FLT_MAX already in double; a roundoff-sized endpoint excess is not
        # a float infinity. Do not apply Decimal's default-context abs(),
        # which silently rounds the 39-digit FLT_MAX before comparison.
        expected=all(abs(float(oracle[k]))<=MAX for k in ('a','nu_next'))
        exact_exceeds=[k for k in ('a','nu_next') if decimal.Decimal(oracle[k]).copy_abs()>decimal.Decimal.from_float(MAX)]
        core=old.Kernel(library,2,(l1,l2,0.))
        try:
            assert core.reset(nu)
            code,c=core.evaluate(s,0.,h)
            assert (code==0)==expected,(r,code,oracle)
            bound_fraction=None
            if expected:
                accepted+=1
                exact=tuple(float(oracle[k]) for k in ('z','a','nu_next','xi'))
                bound_fraction=budget_check(c,h,l1,l2,exact)
                # Oracle output error includes binary64 intermediates plus IEEE32 rounding.
                for actual,key in ((c[2],'a'),(c[4],'nu_next')):
                    exact_d=decimal.Decimal(oracle[key])
                    with decimal.localcontext() as ctx:
                        ctx.prec=100
                        err=(decimal.Decimal.from_float(actual)-exact_d).copy_abs()
                    scale=max(abs(float(exact_d)),abs(nu),abs(s/h),abs(h*l2))
                    bound=U*abs(float(exact_d))+ETA/2+GAMMA*scale
                    assert err<=decimal.Decimal.from_float(bound),(r,key,err,bound)
                assert core.commit() and core.state()==c[4]
            else:
                rejected+=1;assert core.state()==nu and not core.commit()
            rows.append(dict(input=r,status=code,expected_representable=expected,
                candidate=c if not code else None,decimal_reference=oracle,budget_fraction=bound_fraction,
                exact_ideal_exceeds_float_max=exact_exceeds))
            save(out/'numeric.json',rows)
        finally:core.close()
    save(out/'numeric.json',rows)
    return dict(cases=122,accepted=accepted,range_rejected=rejected,source=str(source),source_sha256=sha(source))

def terminal_checks(out,library):
    source=PV00_DATA/'numerical01/summary.json'
    stops=[r for r in json.loads(source.read_text())['stops'] if r['algorithm']=='proper']
    assert len(stops)==4
    rows=[]
    for item in stops:
        v,nu,h=[struct.unpack('>f',bytes.fromhex(item['input_bits'][k]))[0] for k in ('velocity','nu','h')]
        core=old.Kernel(library,2,(2.,1.,0.));initial=(v,nu,h)
        trace=out/(item['period']+'_terminal.jsonl.gz')
        try:
            assert core.reset(nu)
            with gzip.open(trace,'wt') as stream:
                for step in range(4096):
                    code,c=core.evaluate(v,0.,h);assert code==0,(item['period'],step,code,v,core.state())
                    budget_check(c,h)
                    assert core.commit() and core.state()==c[4] and not core.commit()
                    stream.write(json.dumps(dict(step=step,v=v,candidate=c))+'\n')
                    # Independent unit plant integration, never assign z to physical v.
                    v+=h*c[2]
                    assert math.isfinite(v)
            assert core.reset(initial[1]);code,c=core.evaluate(initial[0],0.,h)
            assert code==0 and core.reset() and not core.commit() and core.state()==0
            rows.append(dict(period=item['period'],input_bits=item['input_bits'],updates=4096,
                continuation='fixed_float_h_of_exact_stop; alternating robustness separately in 52 objects',
                terminal_v=v,trace=str(trace),sha256=sha(trace),old_stop_not_reclassified=True))
        finally:core.close()
    save(out/'terminals.json',rows)
    return rows

def trajectory(library,period,scenario,periods,trace):
    core=old.Kernel(library,2,(2.,1.,0.));sg=-1 if scenario.endswith('negative') else 1
    v=vr=sg*.03;nr=sg*.1;assert core.reset(nr)
    lag=lagr=[0.,0.];full=old.Metrics();tail=old.Metrics();ref_tail=old.Metrics()
    us=steps=0;maxclosed=maxres=0.;float_dev=double_dev=0.;sliding=0
    theory=sg*.1*(periods[0]/1e6)**2 if len(set(periods))==1 and scenario.startswith('ramp_') else None
    try:
        with gzip.open(trace,'wt') as stream:
            while us<36_000_000:
                hu=periods[steps] if period=='recorded8_12ms' else periods[steps%len(periods)]
                assert us+hu<=36_000_000
                h=hu/1e6;t=us/1e6
                sp,derivative=old.target(t) if scenario not in old.SCENARIOS[:5] else (0.,0.)
                ff=derivative if scenario=='target_with_ff' else 0.
                noise=.001*math.sin(2*math.pi*13*t)+.0005*math.sin(2*math.pi*29*t) if scenario in ('noise','lag_noise') else 0.
                code,c=core.evaluate(v+noise,sp,h);assert code==0,(period,scenario,steps,code,v,core.state())
                maxres=max(maxres,budget_check(c,f32(h)))
                _,ar,nnr,_=reference(vr+noise-sp,nr,h)
                a,nxt,limited=old.protect(c[2],c[4],c[3],scenario)
                ar,nnr,limitedr=old.protect(ar,nnr,nr,scenario)
                assert core.commit(nxt if scenario.endswith('clipping') else None)
                full.add(h,v-sp,v+noise-sp,a,nxt,limited)
                if us>=12_000_000:
                    tail.add(h,v-sp,v+noise-sp,a,nxt,limited);ref_tail.add(h,vr-sp,vr+noise-sp,ar,nnr,limitedr)
                    if theory is not None:
                        float_dev=max(float_dev,abs(v-sp-theory));double_dev=max(double_dev,abs(vr-sp-theory))
                disturbance=0. if scenario=='zero_transient' else sg*.15
                if scenario.startswith('ramp_'):disturbance+=sg*.1*(t+h/2)
                stream.write(json.dumps(dict(t=t,h=h,v=v,v_sp=sp,measurement=v+noise,candidate=c,
                    a_applied=a,nu_applied=core.state(),ff=ff,disturbance_average=disturbance,
                    constrained=limited,strict_implicit_candidate=True,
                    applied_is_strict_implicit=not limited,reference_v=vr,reference_nu=nr),separators=(',',':'))+'\n')
                if scenario in ('lag','lag_noise'):
                    lag,integral=old.cascade(lag,a+ff,h);lagr,integralr=old.cascade(lagr,ar+ff,h)
                else:integral=h*(a+ff);integralr=h*(ar+ff)
                v+=integral+h*disturbance;vr+=integralr+h*disturbance;nr=nnr
                assert all(math.isfinite(x) for x in (v,vr,nr))
                maxclosed=max(maxclosed,abs(v-vr));sliding+=c[6]==2;steps+=1;us+=hu
        if theory is not None:assert float_dev<=5e-7 and double_dev<=1e-11,(period,scenario,float_dev,double_dev)
        return dict(period=period,scenario=scenario,status='complete',updates=steps,full=full.result(),
            tail_12_36=tail.result(),independent_double_tail=ref_tail.result(),
            theory_error=theory,max_float_theory_deviation=float_dev,max_double_theory_deviation=double_dev,
            max_rounded_residual_budget_fraction=maxres,max_independent_closed_velocity_difference=maxclosed,
            sliding_fraction=sliding/steps,expected_tracking_failure=scenario=='infeasible_clipping',
            trace=str(trace),sha256=sha(trace))
    finally:core.close()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');p.add_argument('--output',type=Path)
    args=p.parse_args()
    if not args.execute:print(json.dumps(dict(normal=6018,numeric=122,terminals=4,objects=52,flight=False)));return
    out=fresh(args.output);result=dict(success=False,new_flights=0,matlab_executed=False,rows=[])
    try:
        lib=compile_core(out);result['source_files']=fingerprint([HERE/'verify.py',HERE/'kernel_bridge.cpp',CONTROL/'ProperIstaVelocityControl.cpp',CONTROL/'ProperIstaVelocityControl.hpp'])
        result['normal']=scalar_checks(out,lib);print('normal 6018 passed',flush=True)
        result['numeric']=numeric_checks(out,lib);print('numeric 122 checked',flush=True)
        result['terminals']=terminal_checks(out,lib);print('terminal 4 x 4096 passed',flush=True)
        cadence_path=REPO/'research/sta-velocity-control/regularized_ista/ri00/results/cadence.json'
        assert sha(cadence_path)=='5e0dde6a0c2194efea25f024105beca0314fd774959f499929c83966790b2d95'
        cadence=json.loads(cadence_path.read_text());assert sha(Path(cadence['source_log']['archive']))==cadence['source_log']['sha256']
        result['cadence']=dict(path=str(cadence_path),sha256=sha(cadence_path),source=cadence['source_log'])
        manifest=[(period,scenario,periods) for period,periods in old.PERIODS.items() for scenario in old.SCENARIOS]
        manifest += [('recorded8_12ms',scenario,cadence['delta_us']) for scenario in ('constant_positive','lag','noise','lag_noise')]
        save(out/'manifest.json',[dict(period=p,scenario=s) for p,s,_ in manifest]);assert len(manifest)==52
        for period,scenario,periods in manifest:
            row=trajectory(lib,period,scenario,periods,out/(period+'__'+scenario+'.jsonl.gz'))
            result['rows'].append(row);save(out/'summary.json',result);print(period,scenario,row['updates'],flush=True)
        result['success']=True
    except Exception as e:result['error']=repr(e);raise
    finally:save(out/'summary.json',result)

if __name__=='__main__':main()
