#!/usr/bin/env python3
"""Build/regress M08 before final flight series; save real exit codes and counts.
Never starts a simulator or changes Git/vehicle parameters. New output only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);out=p.parse_args().output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    repo=Path(__file__).resolve().parents[3];env=os.environ.copy()
    env.update(PYTHONPATH=str(repo/'.px4-python')+':/home/yr/Desktop/codev doc/experiments/M00-20260912/python',
               PATH=str(repo/'.px4-python/bin')+':'+env['PATH'],PYTHONDONTWRITEBYTECODE='1',
               M00_PASSING_RUN='/home/yr/Desktop/codev doc/experiments/M00-20260912/run03')
    evidence=dict(commands=[],tests={},success=False,head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip())
    def run(name,argv):
        print('RUN',name,flush=True)
        with (out/(name+'.log')).open('w') as log:
            result=subprocess.run(argv,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT)
        evidence['commands'].append(dict(name=name,argv=argv,returncode=result.returncode))
        (out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
        if result.returncode:raise RuntimeError(name+' failed')
    try:
        run('diff',['git','diff','--check'])
        run('build_tests',['make','tests','TESTFILTER=IstaIntegration'])
        for name,count in [('IstaIntegration',7),('IstaRateControl',13),('StaRateControl',11),('StaProtection',18),
                           ('StaAxesApplication',12),('RateControl',1),('RateControlDispatcher',4),
                           ('ControllerSelection',5),('GyroPublicationGuard',6),('AttitudeControl',3)]:
            run(name,[str(repo/'build/px4_sitl_test'/('unit-'+name)),'--gtest_output=xml:'+str(out/(name+'.xml'))])
            a=ET.parse(out/(name+'.xml')).getroot().attrib
            actual={k:int(a[k]) for k in ('tests','failures','disabled','errors')}
            assert actual==dict(tests=count,failures=0,disabled=0,errors=0),(name,actual)
            evidence['tests'][name]=actual
        for name,folder,pattern,count in [('python_research','research/sta-rate-control/scripts','test_m*.py',33),
                                           ('python_convenience','sim_scripts/_internal','test_*.py',12)]:
            run(name,[sys.executable,'-m','unittest','discover','-s',folder,'-p',pattern])
            # Later convenience-script additions may increase the suite size.
            # Retain M08's minimum coverage, record actual nonzero executions.
            match=re.search(r'Ran (\d+) tests', (out/(name+'.log')).read_text())
            assert match is not None and int(match.group(1))>=count, name
            evidence['tests'][name]={'tests':int(match.group(1))}
        kernel='src/modules/mc_rate_control/StaRateControl'
        run('probe_build',['g++','-std=c++14','-pedantic-errors','-Wall','-Wextra','-Werror','-Wdouble-promotion',
                           '-O2','-fno-exceptions','-fno-rtti','-I'+kernel,kernel+'/IstaRateControl.cpp',
                           'research/sta-rate-control/scripts/m07_kernel_probe.cpp','-o',str(out/'probe')])
        run('m07_reference',[sys.executable,'research/sta-rate-control/scripts/reference_m07.py','--probe',str(out/'probe'),
                             '--output',str(out/'m07_reference')])
        run('sitl_build',['make','px4_sitl_default'])
        run('symbols',['nm','-C','build/px4_sitl_default/bin/px4'])
        text=(out/'symbols.log').read_text()
        assert 'IstaRateControl::update' in text and 'StaRateControl::update' in text
        run('unchanged_math_model',['git','diff','--exit-code','HEAD','--',kernel+'/IstaRateControl.cpp',kernel+'/IstaRateControl.hpp',
                                   kernel+'/StaRateControl.cpp',kernel+'/StaRateControl.hpp',
                                   'src/modules/mc_rate_control/RateControl/RateControl.cpp',
                                   'src/modules/mc_rate_control/RateControl/RateControl.hpp',
                                   'src/modules/mc_att_control','sitl','boards','ROMFS','research/sta-rate-control/m06'])
        evidence['firmware_sha256']=hashlib.sha256((repo/'build/px4_sitl_default/bin/px4').read_bytes()).hexdigest()
        evidence['success']=True
    finally:
        (out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    python_count=sum(v['tests'] for k,v in evidence['tests'].items() if k.startswith('python_'))
    print(f'M08 offline verification passed; actual C++ cases=80, Python={python_count}')


if __name__=='__main__':main()
