"""PV01 final offline checks and compact export; never flight or git mutation."""
import argparse
import gzip
import math
import shutil
from common import *

def replay(model):
    result=[]
    for row in model['rows']:
        p=Path(row['trace']);assert sha(p)==row['sha256']
        with gzip.open(p,'rt') as f: samples=[json.loads(line) for line in f]
        assert len(samples)==row['updates']
        for name,start in (('full',0.),('tail_12_36',12.)):
            window=[x for x in samples if x['t']>=start]
            duration=math.fsum(x['h'] for x in window)
            mean=math.fsum(x['h']*(x['v']-x['v_sp']) for x in window)/duration
            rmse=math.sqrt(math.fsum(x['h']*(x['v']-x['v_sp'])**2 for x in window)/duration)
            tv=math.fsum(abs(b['a_applied']-a['a_applied']) for a,b in zip(window,window[1:]))/duration
            for key,value in (('seconds',duration),('mean',mean),('rmse',rmse),('correction_tv_per_s',tv)):
                assert abs(value-row[name][key])<=1e-10*max(1.,abs(value)),(p,name,key,value,row[name][key])
        assert all(x['strict_implicit_candidate'] and x['applied_is_strict_implicit']==(not x['constrained']) for x in samples)
        result.append(dict(path=str(p),sha256=sha(p),rows=len(samples),metric_replay_passed=True))
    assert len(result)==52
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--output',type=Path)
    p.add_argument('--entry',type=Path,default=ROOT/'entry01/entry.json')
    p.add_argument('--build',type=Path,default=ROOT/'build03/evidence.json')
    args=p.parse_args()
    if not args.execute:print('67 Python tests, final fixed model replay, no flight/commit');return
    out=fresh(args.output);result=dict(success=False,new_flights=0,python_tests=0,commands=[])
    def command(name,argv):
        try:return run(out,name,argv)
        finally:
            receipt=out/(name+'.command.json')
            if receipt.exists():result['commands'].append(json.loads(receipt.read_text()))
            save(out/'evidence.json',result)
    try:
        for name,path,count in (
            ('new_verifier',HERE/'test_verifier.py',21),
            ('old_probe',REPO/'research/sta-velocity-control/proper_ista_probe/test_probe.py',18),
            ('old_analysis',REPO/'research/sta-velocity-control/proper_ista_probe/test_analysis.py',6),
            ('pv00',PV00/'test_pv00.py',22)):
            argv=['python3',path,'-v']
            if name=='old_probe':
                legacy=ROOT.parent/'PV00/original01/kernels.so'
                frozen=json.loads((PV00/'results/archive_index.json').read_text())
                assert sha(legacy)==frozen[str(legacy)]['sha256']
                argv=['env','PROPER_VELOCITY_LIBRARY='+str(legacy),*argv]
            text=command(name,argv)
            assert f'Ran {count} tests' in text and '\nOK\n' in text,(name,text)
            result['python_tests']+=count
        command('final_model',['python3',HERE/'verify.py','--execute','--output',out/'model'])
        model=json.loads((out/'model/summary.json').read_text());assert model['success']
        result['model_summary']=dict(path=str(out/'model/summary.json'),sha256=sha(out/'model/summary.json'))
        result['trace_replay']=replay(model)
        build=json.loads(args.build.read_text());assert build['success']
        # Inputs used to compile/test are not allowed to change after acceptance.
        for path,expected in build['input_sha256'].items():
            if path.startswith(str(CONTROL)):assert sha(Path(path))==expected,('changed built input',path)
        result['build']=dict(path=str(args.build),sha256=sha(args.build),cpp_tests=build['cpp_unique_tests'],
            new_tests=build['new_kernel_tests'],old_tests=build['regression_tests'],selector=6,
            firmware_sha256=build['firmware_after'],eeprom_sha256=build['eeprom_after'])
        entry=json.loads(args.entry.read_text())
        for path,item in entry['preserved_files'].items():
            assert sha(Path(path))==item['sha256'],('changed preserved file',path)
        result['preserved_files_checked']=len(entry['preserved_files'])
        result['entry']=dict(path=str(args.entry),sha256=sha(args.entry))
        subs=command('submodules',['git','submodule','status','--recursive'])
        assert subs==entry['submodules']
        assert not command('submodule_dirty',['git','submodule','foreach','--quiet','--recursive','git status --porcelain'])
        assert sha(REPO/'build/px4_sitl_default/bin/px4')==build['firmware_after']
        # Task-scoped temporary review evidence, including failed attempts, archived unchanged.
        archives=[]
        for source in (Path('/tmp/pv01-core-IkdK0f'),Path('/tmp/pv01-math-review-LWKhGZ')):
            destination=out/source.name
            shutil.copytree(source,destination)
            for path in source.rglob('*'):
                if path.is_file():assert sha(path)==sha(destination/path.relative_to(source))
            archives.append(dict(source=str(source),archive=str(destination)))
        result['review_archives']=archives
        result['success']=True
    except Exception as error:result['error']=repr(error);raise
    finally:save(out/'evidence.json',result)
    print(json.dumps(dict(success=True,cpp=790,selector=6,python=result['python_tests'],objects=52,new_flights=0)))

if __name__=='__main__':main()
