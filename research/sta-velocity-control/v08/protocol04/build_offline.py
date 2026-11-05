"""External preparation only: compile Gazebo force plugin, do not launch it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import numpy as np
import scenario

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
root=Path(__file__).resolve().parent;out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
e=dict(success=False,new_flights=0,commands=[],probe_cases=[])
def run(name,argv,expected=0):
    r=subprocess.run(argv,text=True,capture_output=True)
    (out/(name+'.log')).write_text(r.stdout+r.stderr)
    e['commands'].append(dict(name=name,argv=argv,exit_code=r.returncode,expected_exit=expected))
    if r.returncode!=expected:raise ValueError(name+' failed')
    return r.stdout
try:
    flags=shlex.split(run('gazebo_flags',['pkg-config','--cflags','--libs','gazebo']))
    run('plugin_build',['g++','-std=c++14','-O2','-fPIC','-shared',str(root/'ForcePlugin.cpp'),'-o',str(out/'libv08_force.so'),*flags])
    run('probe_build',['g++','-std=c++14','-O2',str(root/'ForceWaveProbe.cpp'),'-o',str(out/'force_probe')])
    for i,t in enumerate([-1.,0.,8.-1e-9,8.,8.+1e-9,12.,20.,32.,48.,56.-1e-9,56.,56.+1e-9,80.]):
        argv=[str(out/'force_probe'),str(t),'.4','.7']
        actual=np.fromstring(run('probe'+str(i),argv),sep=' ')
        expected=scenario.force_enu(t,[.4,.7]);error=float(np.max(abs(actual-expected)))
        if error>1e-14:raise ValueError('Independent force reference mismatch')
        e['probe_cases'].append(dict(t=t,max_error_N=error))
    for i,arg in enumerate(['nan','inf','-inf']):
        run('invalid_probe'+str(i),[str(out/'force_probe'),arg,'0','0'],expected=1)
    run('python_tests',[sys.executable,str(root/'test_design.py')])
    e['success']=True
finally:
    e['sha256']={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [root/'ForcePlugin.cpp',root/'ForceWave.hpp',out/'libv08_force.so'] if f.is_file()}
    (out/'evidence.json').write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
