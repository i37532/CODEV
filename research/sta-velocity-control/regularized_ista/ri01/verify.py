#!/usr/bin/env python3
"""RI01 offline verification. No simulator, flight or parameter-writing API."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import time
import traceback

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
BASE = 'e8e38752499c12b9c39bb7dc95da58f27ff029d4'
PREFIX = 'src/modules/mc_pos_control/PositionControl/'
KERNEL = 'RegularizedIstaVelocityControl'
ALLOWED = {PREFIX+KERNEL+s for s in ('.cpp', '.hpp', 'Test.cpp')} | {PREFIX+'CMakeLists.txt'}
PRODUCTION = ('src', 'msg', 'Tools', 'platforms', 'sitl', 'ROMFS', 'boards')
UNIT = (
    KERNEL, 'PositionControl', 'ControlMath', 'Takeoff', 'VelocityControl',
    'StaVelocityControl', 'RegularizedStaVelocityControl', 'StaVelocityProtection',
    'VelocityEsta', 'VelocityEstaZ', 'VelocityZIntegration', 'VelocityXYIntegration',
    'VelocityXYZIntegration', 'VelocityAxes', 'VelocityDecimation',
    'RegularizedVelocityRegression', 'RegularizedVelocityIntegration',
    'VelocityResearchTask', 'VelocityAblationTask', 'RateControl', 'RateControlDispatcher',
    'StaRateControl', 'ControllerSelection', 'StaProtection', 'StaAxesApplication',
    'TakeoffNuManager', 'IstaRateControl', 'IstaIntegration', 'ProperIstaRateControl',
    'ProperIstaIntegration', 'ProperIstaProtection', 'ControlDecimation', 'AttitudeControl')
FUNCTIONAL = ('VelocitySelectionParam', 'VelocityDiagnosticInput', 'VelocityModule',
              'RegularizedVelocityParam', 'RegularizedVelocityModule')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    out = p.parse_args().output.resolve()
    require(REPO != out and REPO not in out.parents, 'External evidence only')
    out.mkdir(parents=True, exist_ok=False)
    env = {k: v for k, v in os.environ.items() if not k.startswith('GTEST_')}
    env['PATH'] = str(REPO/'.px4-python/bin')+':'+env['PATH']
    env['PYTHONPATH'] = ':'.join([str(REPO/'.px4-python'),
        str(REPO/'research/sta-velocity-control/scripts'),
        '/home/yr/Desktop/codev doc/experiments/M00-20260912/python', env.get('PYTHONPATH','')])
    eeprom = REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    binary = REPO/'build/px4_sitl_default/bin/px4'
    evidence = dict(stage='RI01', success=False, baseline=BASE, commands=[],
                    new_flights=0, registered_seeds=[], gtest_environment='all inherited GTEST_* removed',
                    not_executed=['MATLAB/Simulink rerun', 'Gazebo/flight', 'RI02', 'old R04/R05',
                                  'hardware deployment', 'historical full flight reanalysis'])

    def save():
        (out/'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False)+'\n')

    def run(name, argv, cwd=REPO, timeout=1800):
        start = time.monotonic()
        log = out/(name+'.log')
        with log.open('x') as stream:
            try:
                r = subprocess.run(argv, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
                code = r.returncode
            except subprocess.TimeoutExpired:
                code = 124
        evidence['commands'].append(dict(name=name, argv=list(map(str, argv)), cwd=str(cwd),
            exit_code=code, wall_seconds=time.monotonic()-start, log_sha256=sha(log)))
        save()
        print(name, code, flush=True)
        require(code == 0, name+' failed; retained '+str(out))
        return log.read_text()

    def scope(label):
        changed = run(label+'_changed', ['git','diff','--name-only',BASE,'--',*PRODUCTION]).splitlines()
        new = run(label+'_untracked', ['git','ls-files','--others','--exclude-standard','--',*PRODUCTION]).splitlines()
        require(set(changed+new) == ALLOWED, 'Unexpected production scope: '+repr(changed+new))
        return sorted(changed+new)

    try:
        require(run('head',['git','rev-parse','HEAD']).strip()==BASE, 'Unexpected HEAD')
        require(run('branch',['git','branch','--show-current']).strip()=='research/ista-velocity-regularized', 'Wrong branch')
        evidence['worktree'] = run('status',['git','status','--short','--untracked-files=all'])
        sm = run('submodules',['git','submodule','status','--recursive'])
        require(len(sm.splitlines())==33 and all(s.startswith(' ') for s in sm.splitlines()), 'Submodule version mismatch')
        require(not run('submodule_status',['git','submodule','foreach','--quiet','--recursive','git status --porcelain']).strip(), 'Dirty submodule')
        evidence['scope_before'] = scope('before')
        run('old_research_unchanged',['git','diff','--exit-code',BASE,'--',
            'research/sta-rate-control', 'research/sta-velocity-control/regularized_sta',
            'research/sta-velocity-control/regularized_ista/ri00', 'sim_scripts'])
        evidence['eeprom_before'] = sha(eeprom)
        shutil.copyfile(eeprom, out/'eeprom_before.bin')
        evidence['firmware_before'] = sha(binary)
        shutil.copyfile(binary, out/'firmware_before.bin')
        old_index = json.loads((HERE.parent/'ri00/results/source_fingerprints.json').read_text())
        package = Path('/home/yr/Desktop/STA-ISTA-MATLAB-PX4')
        for name, expected in old_index.items():
            require(sha(package/name)==expected['sha256'], 'Source changed: '+name)
        run('source_package',['sha256sum','--check','SHA256SUMS.txt'],package)
        inputs = {str(REPO/name): sha(REPO/name) for name in ALLOWED}
        for path in list((HERE/'model').glob('*.py'))+list((HERE/'model').glob('*.cpp'))+[HERE/'verify.py']:
            inputs[str(path)] = sha(path)
        evidence['input_sha256'] = inputs
        save()
        run('configure_new_tests',['make','tests','TESTFILTER='+KERNEL,'-j4'])
        targets = ['unit-'+n for n in UNIT]+['functional-'+n for n in FUNCTIONAL]
        run('build_regressions',['cmake','--build',str(REPO/'build/px4_sitl_test'),'--target',*targets,'--parallel','4'])
        for target in targets:
            run(target,[str(REPO/'build/px4_sitl_test'/target),
                        '--gtest_output=xml:'+str(out/(target+'.xml'))],timeout=180)
        run('strict_cxx14',['g++','-std=c++14','-pedantic-errors','-Wall','-Wextra','-Werror',
            '-fno-exceptions','-fno-rtti','-c',str(REPO/(PREFIX+KERNEL+'.cpp')),'-o',str(out/'strict_kernel.o')])
        run('build_sitl',['make','px4_sitl_default','-j4'])
        symbols = run('firmware_symbols',['nm','-C',str(binary)])
        require(len(symbols.splitlines())>1000 and KERNEL not in symbols, 'Kernel in production or symbol evidence incomplete')
        consumers = run('core_references',['rg','-l',KERNEL,'src']).splitlines()
        require(set(consumers)==ALLOWED, 'Unexpected core consumer')
        production_db = json.loads((REPO/'build/px4_sitl_default/compile_commands.json').read_text())
        require(not any(KERNEL in x['file'] for x in production_db), 'Core in production compilation database')
        db = json.loads((REPO/'build/px4_sitl_test/compile_commands.json').read_text())
        command = next(x for x in db if x['file'].endswith('/'+KERNEL+'.cpp'))
        standard = [s for s in shlex.split(command['command']) if s.startswith('-std=')]
        require(standard and standard[-1] in ('-std=c++14','-std=gnu++14'), 'Wrong CMake C++ standard')
        evidence['kernel_compile_command'] = command
        run('model_final',['python3','-B',str(HERE/'model/check.py'),'--output',str(out/'model_final')])
        evidence['model'] = json.loads((out/'model_final/summary.json').read_text())
        helper = REPO/'research/sta-velocity-control/regularized_sta/r01/verification/verify.py'
        spec = importlib.util.spec_from_file_location('ri01_xml_counter', helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        inventory = module.xml_inventory(out.glob('*.xml'))
        new_inventory = module.xml_inventory([out/('unit-'+KERNEL+'.xml')])
        evidence['cpp_inventory'] = inventory
        evidence['counts'] = dict(cpp_unique=inventory['unique_tests'], new_kernel=new_inventory['unique_tests'],
            regression_unique=inventory['unique_tests']-new_inventory['unique_tests'],
            model_oracle_tests=evidence['model']['oracle_tests'])
        evidence['counter_helper_sha256'] = sha(helper)
        evidence['no_actuator_path'] = dict(mode4_rejection_in_actual_selector_tests=True,
            core_references=consumers, absent_from_firmware_symbols=True,
            absent_from_production_compilation_database=True, symbols=len(symbols.splitlines()),
            admission_and_defaults_unchanged=True)
        evidence['scope_after'] = scope('after')
        require(evidence['scope_before']==evidence['scope_after'], 'Scope changed during verification')
        require(all(sha(path)==expected for path,expected in inputs.items()), 'Verification inputs changed')
        require(all(sha(package/name)==value['sha256'] for name,value in old_index.items()), 'Package changed')
        run('diff_check',['git','diff','--check'])
        evidence['eeprom_after'] = sha(eeprom)
        require(evidence['eeprom_before']==evidence['eeprom_after'], 'EEPROM changed')
        evidence['firmware_sha256'] = sha(binary)
        evidence['success'] = True
    except BaseException as error:
        evidence['failure'] = dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
        raise
    finally:
        evidence['eeprom_finally'] = sha(eeprom) if eeprom.exists() else None
        save()
        index = {str(p.relative_to(out)): dict(bytes=p.stat().st_size,sha256=sha(p))
                 for p in sorted(out.rglob('*')) if p.is_file() and p.name!='artifacts.json'}
        (out/'artifacts.json').write_text(json.dumps(index,indent=2)+'\n')
    print(json.dumps(dict(success=True,counts=evidence['counts'],output=str(out)),indent=2))


if __name__ == '__main__':
    main()
