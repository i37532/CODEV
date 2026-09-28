"""Bounded passive ODE fixtures, no flight controllers or SITL launch/parameters."""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import xml.etree.ElementTree as ET
import numpy as np
from contact_model import derive, effective_contact

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(path):
    d = np.genfromtxt(path, delimiter=',', names=True)
    if len(d) != 500 or not all(np.all(np.isfinite(d[n])) for n in d.dtype.names):
        raise ValueError('Incomplete/nonfinite passive series')
    if not np.allclose(np.diff(d['t']), .004, rtol=0, atol=1e-12):
        raise ValueError('Wrong physics step')
    accel = np.column_stack([d[n] for n in ('fx','fy','fz','fdx','fdy','fdz')])
    speed = np.sqrt(sum(d[n]**2 for n in ('vx','vy','vz')))
    peak = float(np.max(np.abs(accel)))
    depth = float(np.max(d['depth']))
    settled = float(np.max(speed[-50:]))
    hit = np.flatnonzero(d['depth'] > 0)
    return dict(samples=len(d), peak_specific_force=peak, max_depth=depth,
                final_200ms_max_speed=settled, touched=bool(len(hit)),
                max_rebound_speed=float(np.max(d['vz'])),
                max_tilt_deg=float(np.max(np.arccos(np.clip(np.cos(d['roll'])*np.cos(d['pitch']),-1,1)))*180/math.pi),
                accepted=bool(len(hit) and peak < 120 and depth < .02 and settled < .03))


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    out = p.parse_args().output.resolve(); out.mkdir(parents=True, exist_ok=False)
    evidence = dict(success=False, px4_flights=0, ode_seed=26928, cases=[], commands=[], contact=effective_contact())
    def save(): (out/'evidence.json').write_text(json.dumps(evidence, indent=2)+'\n')
    def run(name, args):
        with (out/(name+'.log')).open('w') as f:
            r = subprocess.run(args, cwd=REPO, stdout=f, stderr=subprocess.STDOUT, timeout=180,
                               env={**os.environ,'GAZEBO_MASTER_URI':'http://127.0.0.1:11365',
                                    'GAZEBO_MODEL_DATABASE_URI':''})
        evidence['commands'].append(dict(name=name, argv=args, exit_code=r.returncode)); save()
        if r.returncode: raise RuntimeError(name+' failed')
    try:
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','gazebo'],text=True))
        run('compile',['g++',str(ROOT/'contact_probe.cpp'),'-std=c++17','-O2','-o',str(out/'probe')]+flags)
        original=ET.parse(REPO/'Tools/sitl_gazebo/models/iris/iris.sdf').getroot()
        ground_path=Path('/usr/share/gazebo-11/models/ground_plane/model.sdf')
        evidence['assets']={str(f):sha(f) for f in [REPO/'Tools/sitl_gazebo/models/iris/iris.sdf',
            REPO/'sitl/worlds/empty_grey.world',ground_path,ROOT/'contact_probe.cpp',ROOT/'contact_model.py',ROOT/'passive_check.py']}
        for variant in ('original','compliant'):
            model=copy.deepcopy((derive(original) if variant=='compliant' else original).find('model'))
            removed=[]
            for parent in model.iter():
                for child in list(parent):
                    if child.tag in ('plugin','sensor','visual'):
                        removed.append(dict(tag=child.tag, name=child.get('name'))); parent.remove(child)
            # Same body, inertias, geometry and joints, with no actuator/communication plugins.
            root=ET.parse(REPO/'sitl/worlds/empty_grey.world').getroot()
            world=root.find('world')
            for child in list(world.findall('include')): world.remove(child)
            world.append(ET.parse(ground_path).getroot().find('model'))
            world.append(model)
            world.find('physics/real_time_update_rate').text='0'  # offline wall-time only; dt stays .004
            path=out/(variant+'.world'); ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
            evidence[variant+'_fixture']=dict(sha256=sha(path), removed=removed)
            for speed in (.55,.7):
                for degrees in (0,5,-5,10,-10):
                    name=f'{variant}_{speed}_{degrees}'; csv=out/(name+'.csv')
                    run(name,[str(out/'probe'),str(path),str(speed),str(math.radians(degrees)),str(csv)])
                    result=dict(variant=variant,speed=speed,roll_deg=degrees,sha256=sha(csv),**summarize(csv))
                    evidence['cases'].append(result); save(); print(json.dumps(result),flush=True)
        evidence['success']=all(c['accepted'] for c in evidence['cases'] if c['variant']=='compliant')
    finally:
        save()
        (out/'artifacts.sha256').write_text(''.join(f'{sha(f)}  {f}\n' for f in sorted(out.rglob('*')) if f.is_file() and f.name!='artifacts.sha256'))
    raise SystemExit(0 if evidence['success'] else 1)


if __name__ == '__main__': main()
