"""RI07 clean qualification with authorized version-only rebuild; zero flights."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import traceback
_spec=importlib.util.spec_from_file_location('_ri07_qualify_protocol',Path(__file__).with_name('protocol.py'))
p=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(p)

receipt=p.load_file('_ri07_leaf_counter',p.HERE.parent/'ri06/receipt.py')
regression=p.load_file('_ri07_regression_inventory',p.HERE/'offline_regression.py')

def validate_regression(path):
    root=Path(path).parent;r=p.read(path)
    if r.get('success') is not True or r.get('new_flights')!=0:raise ValueError('Incomplete regression')
    commands={c['name']:c for c in r['commands']}
    if len(commands)!=len(r['commands']):raise ValueError('Repeated command names')
    for c in commands.values():
        log=root/(c['name']+'.log')
        if c['exit_code'] or c['cwd']!=str(p.REPO) or c['sha256']!=p.fingerprint(log):raise ValueError('Failed/changed leaf')
    identities=set()
    for target in regression.TARGETS:
        xml=root/(target+'.xml')
        if commands[target]['argv']!=[str(p.REPO/'build/px4_sitl_test'/target),'--gtest_output=xml:'+str(xml)]:
            raise ValueError('Wrong test executable/filter')
        identities.update(receipt.completed_cases(xml.read_bytes(),target))
    expected=receipt.python_commands()
    expected={k:v for k,v in expected.items() if str(p.HERE.parent/'ri06/test_freeze.py') not in v}
    total=0
    for name,argv in expected.items():
        if commands[name]['argv']!=argv:raise ValueError('Wrong Python leaf inventory')
        total+=receipt.unittest_count((root/(name+'.log')).read_bytes(),name)
    if len(identities)!=r['cpp_unique_tests'] or total!=r['python_tests'] or len(identities)<751 or total<1121:
        raise ValueError('False test count')
    return dict(cpp_unique_tests=len(identities),cpp_targets=len(regression.TARGETS),python_tests=total)

def validate_receipt(q,path):
    root=Path(path).parent
    counts=validate_regression(root/'regression/evidence.json')
    commands={c['name']:c for c in q['commands']}
    required={'regression','formal_tests','transaction_tests','replay_wiring_tests','prestart_tests','seed_scan','model_reference','history_failure','build_sitl','gazebo_build_only','production_diff'}
    required.update('history_%02d'%i for i in range(18))
    if set(commands)!=required or len(commands)!=len(q['commands']):raise ValueError('Missing qualification command')
    for name,c in commands.items():
        if c['exit_code'] or c['sha256']!=p.fingerprint(root/(name+'.log')):raise ValueError('Bad qualification leaf')
    for label,script in [('formal_tests','test_formal.py'),('transaction_tests','test_transaction.py'),('replay_wiring_tests','test_replay_wiring.py'),('prestart_tests','test_prestart_audit.py')]:
        if commands[label]['argv']!=['python3','-B',str(p.HERE/script)]:raise ValueError('Untrusted test command')
        counts['python_tests']+=receipt.unittest_count((root/(label+'.log')).read_bytes(),label)
    if counts!=q['counts']:raise ValueError('Qualification counts differ from actual leaves')
    return counts

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve()
    if p.DATA_ROOT/'FORMAL' not in out.parents or out.exists() or p.git('status','--porcelain'):
        raise ValueError('Fresh output and clean committed workspace required')
    p.require_execution_authority();p.check()
    out.mkdir(parents=True)
    env={k:v for k,v in os.environ.items() if not k.startswith('GTEST_')}
    env['PYTHONDONTWRITEBYTECODE']='1'
    env['PATH']=str(p.REPO/'.px4-python/bin')+':'+env['PATH']
    env['PYTHONPATH']=':'.join([str(p.REPO/'.px4-python'),str(p.REPO/'research/sta-velocity-control/scripts'),
        '/home/yr/Desktop/codev doc/experiments/M00-20260912/python'])
    e=dict(p.qualification_binding(p.git('rev-parse','HEAD'),p.fingerprint(p.REPO/'build/px4_sitl_default/bin/px4')),success=False,clean=False,approved=False,commands=[],
        firmware_policy='User-authorized version-only rebuild; original production assets unchanged, one RI07 binary for all200',
        eeprom_before=p.fingerprint(regression.REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'))
    def save():
        (out/'evidence.json').write_text(json.dumps(e,indent=2,allow_nan=False)+'\n')
    def run(name,argv):
        log=out/(name+'.log');began=time.monotonic()
        with log.open('x') as stream:r=subprocess.run(list(map(str,argv)),cwd=p.REPO,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=1800)
        e['commands'].append(dict(name=name,argv=list(map(str,argv)),cwd=str(p.REPO),exit_code=r.returncode,
            elapsed_s=time.monotonic()-began,sha256=p.fingerprint(log)))
        save();print(name,r.returncode,flush=True)
        if r.returncode:raise ValueError('Mandatory qualification command failed: '+name)
    try:
        run('regression',['python3','-B',p.HERE/'offline_regression.py','--output',out/'regression'])
        for name,script in [('formal_tests','test_formal.py'),('transaction_tests','test_transaction.py'),('replay_wiring_tests','test_replay_wiring.py'),('prestart_tests','test_prestart_audit.py')]:
            run(name,['python3','-B',p.HERE/script])
        run('seed_scan',['python3','-B',p.HERE/'seed_scan.py','--output',out/'seed_scan_evidence.log'])
        if not p.read(out/'seed_scan_evidence.log')['accepted']:raise ValueError('Formal seed collision')
        run('model_reference',['python3','-B',p.HERE.parent/'ri01/model/check.py','--output',out/'model_reference'])
        old=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016')
        cases=[]
        for gate,revision,numbers in [('A','R03_revision09',(1,2,3)),('B','R03_revision09',(10,11,12)),
            ('C','R03_revision09',(19,20,21)),('D','R03_revision11',(28,29,30))]:
            cases.extend((p.HERE.parent/'ri02/tools/replay.py',old/revision/gate/'batch01'/f'run{n:03d}') for n in numbers)
        for stage,gate,script in [('RI03','A','ri03'),('RI04_REVISION01','B','ri04_revision01')]:
            cases.extend((p.HERE.parent/script/'tools/analyzer.py',Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024')/stage/gate/'batch01'/f'run{n:03d}') for n in (1,2,3))
        for i,(script,source) in enumerate(cases):
            dest=out/('history_%02d'%i)
            run('history_%02d'%i,['python3','-B',script,source,'--output',dest])
            if i>=12:
                same=lambda a,b:json.dumps(a,sort_keys=True,allow_nan=True)==json.dumps(b,sort_keys=True,allow_nan=True)
                if not same(p.read(source/'r03_metrics.json'),p.read(dest/'r03_metrics.json')) or p.fingerprint(source/'spectra.json')!=p.fingerprint(dest/'spectra.json'):
                    raise ValueError('Historical metric/spectrum changed')
        run('history_failure',['python3','-B',p.REPO/'research/sta-velocity-control/regularized_sta/r03_position11/audit.py','--output',out/'history_failure.json'])
        run('production_diff',['git','diff','--exit-code',p.EXECUTABLE_HEAD,'--','src','msg','Tools','sitl','platforms','ROMFS','boards'])
        run('build_sitl',['make','px4_sitl_default','-j4'])
        run('gazebo_build_only',['env','DONT_RUN=1','make','px4_sitl_default','gazebo_iris','-j4'])
        if e['source_head'] not in (p.REPO/'build/px4_sitl_default/src/lib/version/build_git_version.h').read_text():
            raise ValueError('New firmware version does not identify the clean qualified source')
        e.update(p.qualification_binding(e['source_head'],p.fingerprint(p.REPO/'build/px4_sitl_default/bin/px4')))
        e['counts']=validate_regression(out/'regression/evidence.json')
        for name in ('formal_tests','transaction_tests','replay_wiring_tests','prestart_tests'):
            e['counts']['python_tests']+=receipt.unittest_count((out/(name+'.log')).read_bytes(),name)
        validate_receipt(e,out/'evidence.json')
        e['eeprom_final']=p.fingerprint(regression.REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016')
        if e['eeprom_final']!=e['eeprom_before']:raise ValueError('EEPROM changed')
        if p.git('status','--porcelain') or p.git('rev-parse','HEAD')!=e['source_head']:raise ValueError('Qualification source changed')
        p.check();e.update(success=True,clean=True,approved=True)
    except BaseException as exc:
        e.update(error=repr(exc),traceback=traceback.format_exc());raise
    finally:
        e['evidence_files']={str(f):p.fingerprint(f) for f in sorted(out.rglob('*')) if f.is_file() and f!=out/'evidence.json'}
        save()
    approval=dict(approved=True,qualification_sha256=p.fingerprint(out/'evidence.json'),**p.qualification_binding(e['source_head'],e['firmware_sha256']))
    with (out/'authorization.json').open('x') as f:json.dump(approval,f,indent=2);f.write('\n')
    p.require_qualification('FORMAL',e['source_head'],out/'evidence.json')
    print(json.dumps(dict(approved=True,counts=e['counts'],new_flights=0)))

if __name__=='__main__':main()
