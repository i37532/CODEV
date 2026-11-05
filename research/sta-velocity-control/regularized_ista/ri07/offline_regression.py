"""RI07 read-only flight-hardware regression using the frozen SITL binary.

Rebuilds test targets, not the flight firmware. No simulator or parameter writes.
This preliminary evidence does not grant execution authority.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import traceback

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

audit = load('ri07_prestart_regression', HERE/'prestart_audit.py')
receipt = load('ri07_ri06_receipt', HERE.parent/'ri06/receipt.py')
base = load('ri07_test_inventory', HERE.parent/'ri01/verify.py')
EXTRA = ['unit-RegularizedIstaRegression', 'unit-RegularizedIstaProtection',
    'unit-RegularizedIstaPosition', 'unit-RegularizedIstaNonSitl',
    'functional-RegularizedIstaVelocityParam', 'functional-RegularizedIstaVelocityModule',
    'functional-VehicleIMU', 'functional-EKF2SelectorTiming', 'functional-EKF2Selector',
    'functional-EstimatorDiagnosticTopics']
TARGETS = ['unit-'+x for x in base.UNIT] + ['functional-'+x for x in base.FUNCTIONAL] + EXTRA

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    assert REPO not in out.parents and not out.exists()
    out.mkdir(parents=True)
    env = {k:v for k,v in os.environ.items() if not k.startswith('GTEST_')}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PATH'] = str(REPO/'.px4-python/bin')+':'+env['PATH']
    env['PYTHONPATH'] = ':'.join([str(REPO/'.px4-python'),str(REPO/'research/sta-velocity-control/scripts'),
        '/home/yr/Desktop/codev doc/experiments/M00-20260912/python'])
    e = dict(stage='RI07-preliminary', success=False, flight_authorized=False, new_flights=0,
        commands=[], cpp_unique_tests=0, python_tests=0, excluded_tests=[dict(
        path=str(HERE.parent/'ri06/test_freeze.py'),reason='RI06 current-HEAD scope is closed to RI07; replace with RI07 scope/qualification tests before flight, not an exemption for production changes')])
    def save():
        (out/'evidence.json').write_text(json.dumps(e,indent=2,allow_nan=False)+'\n')
    def run(name, argv, unittest=False):
        began = time.monotonic()
        log = out/(name+'.log')
        with log.open('x') as stream:
            result = subprocess.run(list(map(str,argv)),cwd=REPO,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=1800)
        e['commands'].append(dict(name=name,argv=list(map(str,argv)),cwd=str(REPO),exit_code=result.returncode,
            elapsed_s=time.monotonic()-began,log=str(log),sha256=audit.sha(log)))
        save()
        print(name,result.returncode,flush=True)
        assert result.returncode == 0, name+' failed; retained '+str(log)
        if unittest:
            e['python_tests'] += receipt.unittest_count(log.read_bytes(),name)
            save()
    try:
        entry = audit.audit()
        (out/'entry_audit.json').write_text(json.dumps(entry,indent=2)+'\n')
        assert entry['repo_assets']['passed'] and entry['external_assets']['passed']
        assert entry['firmware']['matching'] and entry['eeprom']['matching'] and entry['capacity']['passed']
        assert entry['submodules']['clean'] and entry['submodules']['matching'] and not entry['simulators']
        e['firmware_before'] = entry['firmware']['sha256']
        e['eeprom_before'] = entry['eeprom']['sha256']
        # Check dependencies before spending time on builds. All prior direct
        # suites remain except the explicitly historical stage-scope assertion.
        for index,path in enumerate(receipt.python_scripts()):
            if path == HERE.parent/'ri06/test_freeze.py':
                continue
            run(f'py{index:02d}_{path.parent.name}_{path.stem}',['python3','-B',path],True)
        run('r02_tools',['python3','-B','-m','unittest','discover','-s',REPO/'research/sta-velocity-control/regularized_sta/r02/tools','-p','test_*.py','-v'],True)
        run('configure_tests',['make','tests','TESTFILTER=RegularizedIsta','-j4'])
        run('build_test_targets',['cmake','--build',REPO/'build/px4_sitl_test','--target',*TARGETS,'--parallel','4'])
        unique = set()
        for target in TARGETS:
            xml = out/(target+'.xml')
            run(target,[REPO/'build/px4_sitl_test'/target,'--gtest_output=xml:'+str(xml)])
            unique.update(receipt.completed_cases(xml.read_bytes(),target))
            e['cpp_unique_tests'] = len(unique)
            save()
        assert len(unique)>=751 and e['python_tests']>=1121
        assert audit.sha(REPO/'build/px4_sitl_default/bin/px4')==e['firmware_before']
        assert audit.sha(REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016')==e['eeprom_before']
        e['success'] = True
    except BaseException as exc:
        e.update(error=repr(exc),traceback=traceback.format_exc())
        raise
    finally:
        save()
    print(json.dumps({k:e[k] for k in ('success','cpp_unique_tests','python_tests','new_flights')}))

if __name__ == '__main__':
    main()
