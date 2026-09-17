#!/usr/bin/env python3
"""Prospective M10 design. No flight/test data consulted here."""
import copy
import json
from pathlib import Path
import numpy as np

RESEARCH = Path(__file__).resolve().parents[1]
SCENES = ('nominal','torque','inertia','noise','div2','div4')
TRAIN_SEEDS = (1101,1102)
PILOT_SEEDS = (2101,2102,2103)
TEST_SEEDS = tuple(range(3101,3121))
SCALES = (.85,1.,1.15)


def fixed_parameters(parameters):
    variable=set(candidate(0,0))|{'COM_FLIGHT_UUID','LND_FLIGHT_T_HI','LND_FLIGHT_T_LO','MC_RATT_TEST'}
    return {k:v for k,v in parameters.items() if k not in variable}


def scenario(scene, seed):
    if scene not in SCENES or not 0 < seed < 2**31:
        raise ValueError('Invalid scene/seed')
    rng=np.random.Generator(np.random.PCG64(seed))
    return dict(scene=scene,seed=seed,imu_seed=seed,div={'div2':2,'div4':4}.get(scene,1),
                inertia_scale=1.2 if scene=='inertia' else 1.,
                gyro_density_scale=2. if scene=='noise' else 1.,
                torque_scale=1. if scene=='torque' else 0.,
                torque_phases=rng.uniform(-np.pi,np.pi,3).tolist())


def candidate(mode, index):
    if mode not in (0,1,2) or index not in range(3):raise ValueError('Invalid candidate')
    names=('iris_pid.json','iris_esta_rpy.json','iris_ista_rpy_candidate02.json')
    p=json.loads((RESEARCH/'m08'/names[mode]).read_text())
    p['MC_RTC_MODE']=mode;p['MC_STA_AXES']=7 if mode else 0;p['MC_RTC_DIV']=1
    scale=SCALES[index]
    for axis in ('ROLL','PITCH','YAW'):
        for gain, base in [('P',.2 if axis=='YAW' else .15),('I',.1 if axis=='YAW' else .2),
                           ('D',0. if axis=='YAW' else .003),('FF',0.),('K',1.)]:
            p[f'MC_{axis}RATE_{gain}']=base*(scale if mode==0 and gain in ('P','I','D') else 1.)
    if mode:
        for a in 'RPY':
            for k in (1,2):p[f'MC_STA_L{k}_{a}']*=scale
    return p


def equal_gains(mode):
    if mode not in (1,2):raise ValueError('A group is ESTA/ISTA only')
    p=candidate(1,1);p['MC_RTC_MODE']=mode
    return p


def select(training):
    """All 4 flights/candidate count. Any failed flight disqualifies candidate."""
    selection={};scores={}
    for mode in (0,1,2):
        scored=[]
        for index in range(3):
            rows=[r for r in training if r['mode']==mode and r['candidate']==index]
            expected={(s,seed) for s in ('nominal','torque') for seed in TRAIN_SEEDS}
            if len(rows)!=4 or {(r['scene'],r['seed']) for r in rows}!=expected:
                raise ValueError('Incomplete/equal-budget training manifest')
            value=float(np.mean([np.mean(r['rmse_tracking']) for r in rows])) if all(r['success'] for r in rows) else None
            scored.append(dict(candidate=index,score=value,failed=sum(not r['success'] for r in rows)))
        eligible=[x for x in scored if x['score'] is not None]
        if not eligible:raise RuntimeError('No eligible candidate for mode '+str(mode))
        winner=min(eligible,key=lambda x:(x['score'],abs(SCALES[x['candidate']]-1),x['candidate']))
        selection[str(mode)]=dict(candidate=winner['candidate'],parameters=candidate(mode,winner['candidate']))
        scores[str(mode)]=scored
    return dict(selection=selection,scores=scores,objective='mean of three axis RMSE, averaged across 4 training flights')


def formal_jobs(frozen):
    jobs=[]
    for scene in SCENES:
        for seed in TEST_SEEDS:
            block=[]
            for group,modes in [('A',(1,2)),('B',(0,1,2))]:
                for mode in modes:
                    params=equal_gains(mode) if group=='A' else copy.deepcopy(frozen['selection'][str(mode)]['parameters'])
                    block.append(dict(group=group,mode=mode,scene=scene,seed=seed,parameters=params,
                                      simulation_speed_requested=frozen.get('simulation_speed_requested',5.),
                                      fixed_parameters=frozen.get('fixed_parameters',{})))
            np.random.Generator(np.random.PCG64(seed+SCENES.index(scene)*10000)).shuffle(block)
            jobs+=block
    return jobs
