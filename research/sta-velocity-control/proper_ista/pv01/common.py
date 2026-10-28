"""PV01 offline helpers; no flight or parameter writing."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
BASE='39f1e9bc006655e6240f633310c6c44cb64a8266'
ROOT=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-PROPER-20261028/PV01')
PV00=HERE.parent/'pv00'
CONTROL=REPO/'src/modules/mc_pos_control/PositionControl'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m

old=load('pv01_old_probe',REPO/'research/sta-velocity-control/proper_ista_probe/probe.py')
sha=old.sha
save=old.save

def fingerprint(paths):
    return {str(p):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(paths) if p.is_file()}

def fresh(path):
    p=Path(path).resolve()
    if REPO==p or REPO in p.parents:raise ValueError('external output required')
    p.mkdir(parents=True,exist_ok=False);return p

def environment():
    env={k:v for k,v in os.environ.items() if not k.startswith('GTEST_')}
    env['PYTHONDONTWRITEBYTECODE']='1'
    env['PATH']=str(REPO/'.px4-python/bin')+':'+env['PATH']
    env['PYTHONPATH']=':'.join([str(REPO/'.px4-python'),str(HERE),
        '/home/yr/Desktop/codev doc/experiments/M00-20260912/python',env.get('PYTHONPATH','')])
    return env

def run(out,name,argv,timeout=1800):
    log=out/(name+'.log');started=time.monotonic()
    with log.open('x') as stream:
        try:
            result=subprocess.run(list(map(str,argv)),cwd=REPO,env=environment(),
                stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
            code=result.returncode
        except subprocess.TimeoutExpired:code=124
    receipt=dict(argv=list(map(str,argv)),cwd=str(REPO),exit_code=code,
        wall_seconds=time.monotonic()-started,log=str(log),sha256=sha(log))
    save(out/(name+'.command.json'),receipt)
    print(name,code,flush=True)
    if code:raise RuntimeError(f'{name} failed: {log}')
    return log.read_text()
