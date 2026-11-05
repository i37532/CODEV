"""Pure manifest construction for the next stage. No simulator imports."""
import copy
import numpy as np

SCENES=('hover','figure8','heading','force','mass')
SEEDS=tuple(range(41001,41021))

def build_manifest(selection):
    if set(selection['selected'])!={'0','1'} or set(selection['parameters'])!={'0','1'}:
        raise ValueError('Both frozen selected algorithms required')
    result=[]
    for ti,scene in enumerate(SCENES):
        task=scene if scene in ('hover','figure8','heading') else 'figure8'
        for si,seed in enumerate(SEEDS):
            for mode in ((0,1) if (ti+si)%2==0 else (1,0)):
                p=copy.deepcopy(selection['parameters'][str(mode)])
                if p['MPC_VC_MODE']!=mode or p['MPC_VC_AXES']!=3*mode or p['MPC_VC_DIV']!=1:
                    raise ValueError('Wrong formal configuration')
                if any(p[k]!=0 for k in p if k.startswith(('MPC_VC_L','MPC_VC_NU','MPC_VC_A_')) and k.endswith('_Z')):
                    raise ValueError('Formal comparison must keep Z PID')
                if not all(np.isfinite(x) for x in p.values()):raise ValueError('Nonfinite selected parameters')
                p['MPC_VCT_TEST']={'hover':5,'figure8':6,'heading':7}[task]
                phases=np.random.Generator(np.random.PCG64(seed)).uniform(0,2*np.pi,2).tolist()
                result.append(dict(id=f'run{len(result)+1:03d}',phase='formal',scene=scene,task=task,gate=scene,
                    seed=seed,mode=mode,axes=3*mode,divisor=1,candidate=selection['selected'][str(mode)],parameters=p,
                    force_phase_north_east=phases if scene=='force' else None,density_scale=1.1 if scene=='mass' else 1.))
    return result

def empty_outcomes(manifest):
    if len(manifest)!=200:raise ValueError('Exact 200-job manifest required')
    return [dict(id=j['id'],scene=j['scene'],seed=j['seed'],mode=j['mode'],status='unattempted',
                 reason='V08 freezes only; formal holdout not executed') for j in manifest]
