"""Four real logger filename/CLI probes, no logger thread or simulator started."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import xml.etree.ElementTree as ET
REPO=Path(__file__).resolve().parents[4]
BUILD=REPO/'build/px4_sitl_test'

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    e=dict(success=False,new_flights=0,commands=[])
    def run(name,argv):
        with (out/(name+'.log')).open('w') as f:
            r=subprocess.run(argv,cwd=BUILD,stdout=f,stderr=subprocess.STDOUT,timeout=180)
        e['commands'].append(dict(name=name,argv=argv,exit_code=r.returncode))
        (out/'evidence.json').write_text(json.dumps(e,indent=2)+'\n')
        print(name,r.returncode,flush=True)
        if r.returncode:raise RuntimeError(name)
    db=json.loads((BUILD/'compile_commands.json').read_text())
    entry=next(x for x in db if x['file'].endswith('/EstimatorDiagnosticTopicsTest.cpp'))
    argv=shlex.split(entry['command']);obj=out/'probe.o'
    argv[argv.index('-c')+1]=str(Path(__file__).with_name('LoggerFileNamingTest.cpp'))
    argv[argv.index('-o')+1]=str(obj)
    argv+=['-fno-access-control','-I'+str(REPO/'src/modules/logger')]
    run('compile',argv)
    commands=subprocess.check_output(['ninja','-t','commands','functional-EstimatorDiagnosticTopics'],cwd=BUILD,text=True)
    line=next(x for x in reversed(commands.splitlines()) if ' -o functional-EstimatorDiagnosticTopics ' in x)
    link=[x for x in shlex.split(line.split(' && ')[1]) if not x.endswith('EstimatorDiagnosticTopicsTest.cpp.o')]
    binary=out/'probe';link[link.index('-o')+1]=str(binary)
    link.insert(next(i for i,x in enumerate(link) if x.endswith('.a')),str(obj))
    run('link',link)
    run('tests',[str(binary),'--gtest_filter=LoggerFileNaming.*','--gtest_output=xml:'+str(out/'tests.xml')])
    a=ET.parse(out/'tests.xml').getroot().attrib
    e['tests']={k:int(a[k]) for k in ('tests','failures','errors','disabled')}
    assert e['tests']==dict(tests=4,failures=0,errors=0,disabled=0)
    e['success']=True;(out/'evidence.json').write_text(json.dumps(e,indent=2)+'\n')

if __name__=='__main__':main()
