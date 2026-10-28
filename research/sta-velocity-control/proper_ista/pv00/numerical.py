"""Exact-stop diagnostics. Instrument a COPY of the old kernel, never production."""
import argparse
import ctypes
import decimal
import json
import math
from pathlib import Path
import struct

from common import HERE, HISTORY, OLD, ROOT, command, fresh, probe, save, sha

MIN = 2.**-126
DENORM = 2.**-149
MAX = probe.f32(3.4028234663852886e38)


def bits(x):
    return struct.pack('>f', probe.f32(x)).hex()


def neighbour(x, offset):
    word = struct.unpack('>I', struct.pack('>f', x))[0]
    return struct.unpack('>f', struct.pack('>I', word+offset))[0]


def classify(x):
    if not math.isfinite(x):
        return 'nonfinite'
    if x == 0:
        return 'zero'
    if abs(x) < MIN:
        return 'subnormal_or_round_to_zero'
    if abs(x) > MAX:
        return 'overflow_float'
    return 'normal'


def rounded(x):
    f = probe.f32(x)
    return dict(double=x if math.isfinite(x) else str(x), kind=classify(x),
                float_value=f if math.isfinite(f) else str(f), float_bits=bits(f),
                absolute_rounding_error=abs(x-f) if math.isfinite(x) and math.isfinite(f) else None)


def proper_arithmetic(s, nu, h, l1=2., l2=1.):
    """Diagnostic shadow of intermediates, NOT the independent correctness oracle."""
    s, nu, h, l1, l2 = map(probe.f32, (s, nu, h, l1, l2))
    alpha, q = h*l1, h*h*l2
    if abs(s) <= q:
        z, xi = 0., s/q
        next_nu, a = nu-s/h, nu-2*s/h
        root = naive_root = 0.
    else:
        xi = math.copysign(1., s)
        delta = abs(s)-q
        disc = alpha*alpha+4*delta
        root = 2*delta/(math.sqrt(disc)+alpha)
        naive_root = (math.sqrt(disc)-alpha)/2
        z = xi*root*root
        next_nu, a = nu-h*l2*xi, nu-2*h*l2*xi-l1*root*xi
    terms = {k: rounded(v) for k,v in dict(s=s, nu=nu, h=h, alpha=alpha, q=q,
                                         z=z, xi=xi, next_nu=next_nu, a=a).items()}
    def residual(lhs, *rhs):
        difference = abs(lhs-sum(rhs))
        scale = max(abs(lhs), *(abs(x) for x in rhs))
        tolerance = 8*2**-23*scale
        return dict(difference=difference, scale=scale, tolerance=tolerance, passes=difference <= tolerance)
    rn, ra, rz, rx = map(probe.f32, (next_nu, a, z, xi))
    finite = all(math.isfinite(v) for v in (rn, ra, rz, rx))
    residuals = ([residual(rz, s, h*ra, -h*rn), residual(rn, nu, -h*l2*rx),
                  residual(ra, -l1*math.sqrt(abs(rz))*rx, 2*rn, -nu)] if finite else [])
    return dict(terms=terms, branch='sliding' if abs(s)<=q else 'outer', residuals=residuals,
                rational_root=root, subtractive_root=naive_root,
                narrowed_non_normal=[k for k in ('next_nu','a','z','xi') if terms[k]['kind'] not in ('zero','normal')])


def decimal_reference(s, nu, h, l1=2., l2=1.):
    """80-digit independent monotone solve, then prediction equation for output."""
    with decimal.localcontext() as ctx:
        ctx.prec = 80
        D = decimal.Decimal.from_float
        s, nu, h, l1, l2 = [D(probe.f32(x)) for x in (s, nu, h, l1, l2)]
        q = h*h*l2
        if abs(s) <= q:
            z, xi = decimal.Decimal(0), s/q
        else:
            lo, hi = decimal.Decimal(0), abs(s)-q
            rhs = hi
            for _ in range(640):
                mid = (lo+hi)/2
                if mid+h*l1*mid.sqrt() < rhs:
                    lo = mid
                else:
                    hi = mid
            z = (lo+hi)/2 * (1 if s>0 else -1)
            xi = decimal.Decimal(1 if s>0 else -1)
        nxt = nu-h*l2*xi
        a = nxt+(z-s)/h
        return {k:str(v) for k,v in dict(z=z, xi=xi, nu_next=nxt, a=a).items()}


def grid():
    rows = []
    for h in (.008, .012):
        q = probe.f32(probe.f32(h)**2)
        values = [0., DENORM, neighbour(MIN,-1), MIN, neighbour(MIN,1),
                  probe.f32(1e-35), probe.f32(1e-20), neighbour(q,-1), q, neighbour(q,1)]
        for s in values + [-x for x in values if x]:
            for nu in (0., -.1, .1):
                rows.append(dict(s=s, nu=nu, h=h, l1=2., l2=1., category='grid'))
    for s,nu,h,l1,l2 in (
            (1.,0.,MIN,MIN,MIN), (1.,0.,MAX,MAX,MAX),
            (MAX,0.,.008,MAX,1.), (MIN,0.,MIN,1.,MIN),
            (1.,MAX,.008,2.,1.), (-1.,MAX,.008,2.,1.),
            (neighbour(2.**-14,1),0.,2.**-7,2.,1.),
            (1.,0.,.008,1e20,1.)):
        rows.append(dict(s=s,nu=nu,h=h,l1=l1,l2=l2,category='stress'))
    assert len(rows) == 122
    return rows


def compile_instrumented(out):
    original = probe.RATE/'ProperIstaRateControl.cpp'
    source = original.read_text()
    start = source.index('ProperIstaRateControl::Candidate ProperIstaRateControl::evaluate')
    end = source.index('\nbool ProperIstaRateControl::commit(', start)
    segment = source[start:end]
    chunks = segment.split('return candidate;')
    sites = []
    modified = chunks[0]
    for index, chunk in enumerate(chunks[1:],1):
        sites.append(dict(site=index, preceding=chunks[index-1][-300:]))
        modified += f'pv_reject_site = {index}; return candidate;' + chunk
    assert len(sites) == 10, len(sites)
    instrumented = out/'ProperIstaRateControl.instrumented.cpp'
    instrumented.write_text('int pv_reject_site = 0;\n'+source[:start]+modified+source[end:])
    save(out/'instrumentation.json', dict(original=str(original), sha256=sha(original),
                                         copy=str(instrumented), copy_sha256=sha(instrumented), sites=sites))
    sources = [OLD/'kernel_bridge.cpp', probe.VELOCITY/'RegularizedStaVelocityControl.cpp',
               probe.VELOCITY/'RegularizedIstaVelocityControl.cpp', instrumented, HERE/'numeric_env.cpp']
    lib = out/'instrumented.so'
    command(out, 'compile', ['g++','-std=c++14','-O2','-Wall','-Wextra','-Werror','-pedantic-errors',
                            '-shared','-fPIC','-I',probe.VELOCITY,'-I',probe.RATE,*sources,'-o',lib])
    return lib


def evaluate(library, mode, params, s, nu, h, flush):
    core = probe.Kernel(library, mode, params)
    try:
        if not core.reset(nu):
            return dict(reset=False)
        core.lib.pv_evaluate.argtypes = [ctypes.c_void_p, ctypes.c_int]+[ctypes.c_float]*3+[ctypes.POINTER(ctypes.c_double),ctypes.c_int]
        core.lib.pv_evaluate.restype = ctypes.c_int
        core.lib.pv_site.restype = ctypes.c_int
        out = (ctypes.c_double*7)()
        old = core.state()
        code = core.lib.pv_evaluate(core.handle,2,s,0.,h,out,flush)
        site = core.lib.pv_site() if mode==2 else None
        assert core.state() == old
        return dict(reset=True, code=code, site=site, state_unchanged=True,
                    outputs=[x if math.isfinite(x) else str(x) for x in out])
    finally:
        core.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(dict(raw_stop_cases=12, proper_cases=4, grid_cases=len(grid()),
                              environments=['IEEE gradual', 'x86 FTZ+DAZ'], flight_authorized=False),indent=2))
        return
    if args.output is None:
        parser.error('--output required')
    out = fresh(args.output)
    result = dict(success=False, stops=[], grid=[], protocol_sha256=sha(HERE/'PROTOCOL_CN.md'))
    try:
        library = compile_instrumented(out)
        history = json.loads((HISTORY/'summary.json').read_text())
        assert sha(HISTORY/'summary.json') == 'ed98eb5e97ec26b2c330829f2b8f160941ae907c223c6815b590287a4bea583d'
        stops = [r for r in history['rows'] if r['stop']]
        assert len(stops)==12
        for row in stops:
            stop = row['stop']
            mode, params = probe.CONFIGS[row['algorithm']]
            assert stop['target']==stop['noise']==0.
            outputs=[evaluate(library,mode,params,stop['velocity'],stop['nu'],stop['h'],f) for f in (0,1)]
            assert outputs[0]['code']==stop['code']
            result['stops'].append(dict(algorithm=row['algorithm'],period=row['period'],stop=stop,
                input_bits={k:bits(stop[k]) for k in ('velocity','nu','h')},environments=outputs,
                arithmetic=proper_arithmetic(stop['velocity'],stop['nu'],stop['h']) if mode==2 else None,
                decimal_reference=decimal_reference(stop['velocity'],stop['nu'],stop['h']) if mode==2 else None))
        for row in grid():
            params=(row['l1'],row['l2'],0.)
            outputs=[evaluate(library,2,params,row['s'],row['nu'],row['h'],f) for f in (0,1)]
            result['grid'].append(dict(input=row,environments=outputs,
                arithmetic=proper_arithmetic(row['s'],row['nu'],row['h'],row['l1'],row['l2']),
                decimal_reference=decimal_reference(row['s'],row['nu'],row['h'],row['l1'],row['l2'])))
        result['success']=True
    except Exception as error:
        result['error']=repr(error)
        raise
    finally:
        save(out/'summary.json',result)


if __name__=='__main__':
    main()
