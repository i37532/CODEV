#!/usr/bin/env python3
"""R02 offline verification. No simulator, flight, parameter write or seed use."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
import traceback
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
R02 = HERE.parent
REGULARIZED = R02.parent
REPO = HERE.parents[4]
BASE = '9d1c74fce9fa386e94e790514aeb8f2c718abc47'
spec = importlib.util.spec_from_file_location('r01_verification', REGULARIZED/'r01/verification/verify.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
sha, require = helper.sha, helper.require
POS = 'src/modules/mc_pos_control/PositionControl/'
MODULE = 'src/modules/mc_pos_control/'
ALLOWED = {POS + name for name in (
    'CMakeLists.txt', 'PositionControl.cpp', 'PositionControl.hpp',
    'StaVelocityProtection.cpp', 'StaVelocityProtection.hpp', 'VelocityControlSelector.hpp',
    'RegularizedVelocityRegressionTest.cpp', 'RegularizedVelocityIntegrationTest.cpp',
    'RegularizedVelocityParamTest.cpp')}
ALLOWED |= {MODULE + name for name in (
    'CMakeLists.txt', 'MulticopterPositionControl.cpp', 'MulticopterPositionControl.hpp',
    'mc_pos_control_params.c', 'RegularizedVelocityModuleTest.cpp')}
ALLOWED.add('msg/velocity_ctrl_selection.msg')
TESTS = [('RegularizedStaVelocityControl', 'unit'), ('RegularizedVelocityRegression', 'unit'),
         ('RegularizedVelocityIntegration', 'unit'), ('RegularizedVelocityParam', 'functional'),
         ('RegularizedVelocityModule', 'functional')]
TESTS += [(name, 'unit') for name in helper.EXTRA_TESTS]


def check_reference():
    results = {}
    for name in ('PositionControl.cpp', 'PositionControl.hpp', 'StaVelocityProtection.cpp',
                 'StaVelocityProtection.hpp', 'VelocityControlSelector.hpp'):
        original = subprocess.check_output(['git', 'show', BASE + ':' + POS + name], cwd=REPO, text=True)
        for token in ('StaVelocityProtection', 'VelocityControlSelector', 'PositionControl'):
            original = original.replace(token, 'R01' + token)
        path = R02/'reference'/('R01' + name)
        require(path.read_text() == original, 'Frozen R01 reference differs: ' + name)
        results[str(path.relative_to(REPO))] = sha(path)
    return results


def check_metadata():
    metadata = {p.attrib['name']: p for p in ET.parse(REPO/'build/px4_sitl_default/parameters.xml').iter('parameter')}
    result = {}
    for axis, expected in zip('XYZ', (.01, .01, .02)):
        name = 'MPC_VC_EPS_' + axis
        node = metadata[name]
        require(len(name) <= 16 and float(node.attrib['default']) == expected, 'epsilon default ' + name)
        require(float(node.findtext('min')) == .001 and float(node.findtext('max')) == 1., 'epsilon range ' + name)
        require(node.findtext('unit') == 'm/s', 'epsilon units ' + name)
        result[name] = dict(default=expected, min=.001, max=1., unit='m/s')
    for name, default in [('MPC_VC_MODE', 0), ('MPC_VC_AXES', 0), ('MPC_VC_DIV', 1)]:
        require(int(metadata[name].attrib['default']) == default, 'Changed firmware default ' + name)
    result['formats'] = {}
    for name in ('sta_velocity_ctrl_status', 'velocity_ctrl_selection'):
        generated = (REPO/f'build/px4_sitl_default/msg/topics_sources/{name}.cpp').read_text()
        fields = re.search('__orb_' + name + r'_fields\[\] = "([^"]+)"', generated)[1]
        length = len(name + ':' + fields) + 1
        require(length < 1500, 'ULog format too long: ' + name)
        require('ORB_QUEUE_LENGTH = 8' in (REPO/f'msg/{name}.msg').read_text(), 'Unexpected queue ' + name)
        result['formats'][name] = dict(bytes=length, queue=8)
    require(result['formats']['sta_velocity_ctrl_status']['bytes'] == 1475, 'Primary layout changed')
    return result


def check_closed_admission():
    source = (REPO/(POS + 'PositionControl.cpp')).read_text()
    header = (REPO/(POS + 'PositionControl.hpp')).read_text()
    require('_regularized_test_admission{false}' in header, 'No closed default')
    require(re.search(r'regularized_ready\s*=\s*_regularized_test_admission\s*&&', source) is not None,
            'Production gate does not depend on private offline admission')
    allowed = {POS + 'PositionControl.cpp', POS + 'PositionControl.hpp',
               POS + 'RegularizedVelocityIntegrationTest.cpp', POS + 'RegularizedVelocityParamTest.cpp',
               MODULE + 'RegularizedVelocityModuleTest.cpp'}
    matches = subprocess.check_output(['rg', '-l', '_regularized_test_admission', 'src'], cwd=REPO, text=True).splitlines()
    require(set(matches) == allowed, 'Unexpected admission consumer')
    require('= true' not in '\n'.join(line for line in source.splitlines() if '_regularized_test_admission' in line),
            'Production modifies offline gate')
    return dict(private_default=False, source_consumers=sorted(matches),
        actual_run_test='RegularizedVelocityModule.ProductionRejectsNewModeAllMasksWithoutEffectiveMutation',
        not_claimed='Core is linked in R02; absence of symbols is NOT the admission proof')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    require(REPO not in out.parents and out != REPO and not out.exists(), 'Fresh external output required')
    out.mkdir(parents=True)
    env = os.environ.copy()
    # Ambient filters/sharding/repetition must not silently turn the frozen
    # complete matrix into a selected subset with a misleading sample count.
    removed_gtest_env = {key: env.pop(key) for key in list(env) if key.startswith('GTEST_')}
    env['PATH'] = str(REPO/'.px4-python/bin') + ':' + env['PATH']
    env['PYTHONPATH'] = ':'.join([str(REPO/'.px4-python'), str(REPO/'research/sta-velocity-control/scripts'),
        '/home/yr/Desktop/codev doc/experiments/M00-20260912/python', env.get('PYTHONPATH', '')])
    eeprom = REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    evidence = dict(stage='R02', success=False, commands=[], new_flights=0, seeds_used=[], baseline=BASE,
        removed_gtest_environment=removed_gtest_env,
        not_executed=['MATLAB', 'SITL flight', 'real parameter changes', 'hardware build/deployment',
                      'V08/AX04 frozen-source qualification'],
        v08_provenance_not_applicable='protocol02.test_tuning.TuningTest.test_original_production_and_launcher_unchanged')
    inputs = {}

    def save():
        (out/'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')

    def run(name, argv, cwd=REPO, timeout=3600):
        start = time.monotonic()
        with (out/(name + '.log')).open('x') as stream:
            try:
                result = subprocess.run(argv, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
                code, timed_out = result.returncode, False
            except subprocess.TimeoutExpired:
                code, timed_out = 124, True
        evidence['commands'].append(dict(name=name, argv=list(map(str, argv)), cwd=str(cwd),
            exit_code=code, timeout=timed_out, wall_seconds=time.monotonic()-start))
        save()
        print(name, code, flush=True)
        require(code == 0, name + ' failed; retain ' + str(out))
        return (out/(name + '.log')).read_text()

    try:
        evidence['eeprom_before'] = sha(eeprom)
        evidence['head'] = run('head', ['git', 'rev-parse', 'HEAD']).strip()
        require(run('branch', ['git', 'branch', '--show-current']).strip() == 'research/sta-velocity-regularized', 'Wrong branch')
        run('ancestor', ['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'])
        run('workspace', ['git', 'status', '--short'])
        subs = run('submodules', ['git', 'submodule', 'status', '--recursive']).splitlines()
        require(len(subs) == 33 and all(s.startswith(' ') for s in subs), 'Submodule mismatch')
        require(not run('submodules_clean', ['git', 'submodule', 'foreach', '--quiet', '--recursive',
            'git status --porcelain --untracked-files=all']).strip(), 'Dirty submodule')
        evidence['submodules'] = subs
        changed = run('scope', ['git', 'diff', '--name-only', BASE, '--', *helper.PRODUCTION]).splitlines()
        untracked = run('untracked', ['git', 'ls-files', '--others', '--exclude-standard', '--', *helper.PRODUCTION]).splitlines()
        require(not (set(changed) | set(untracked)) - ALLOWED, 'Unexpected production scope')
        evidence['scope'] = sorted(set(changed) | set(untracked))
        evidence['reference'] = check_reference()
        evidence['closed_admission'] = check_closed_admission()
        run('protected_scope', ['git', 'diff', '--exit-code', BASE, '--',
            *helper.CORE_FILES, 'msg/sta_velocity_ctrl_status.msg',
            'research/sta-velocity-control/axis_ablation', 'research/sta-velocity-control/v08',
            'research/sta-velocity-control/v07', 'research/sta-velocity-control/scripts', 'sim_scripts'])
        for name in ALLOWED | set(helper.CORE_FILES):
            inputs[str(REPO/name)] = sha(REPO/name)
        for path in R02.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix in ('.py', '.json', '.cpp', '.hpp', '.msg'):
                inputs[str(path)] = sha(path)
        package = helper.PACKAGE
        manifest = package/'SHA256SUMS.txt'
        expected_package = helper.read(REGULARIZED/'r00/math/results02.json')['package_sha256_manifest']
        require(sha(manifest) == expected_package, 'Package manifest changed')
        run('source_package', ['sha256sum', '-c', 'SHA256SUMS.txt'], cwd=package)
        evidence['source_package_manifest_sha256'] = expected_package
        for line in manifest.read_text().splitlines():
            digest, name = line.split(None, 1)
            inputs[str(package/name.lstrip('*'))] = digest
        frozen = helper.read(REPO/'research/sta-velocity-control/axis_ablation/ax04/frozen.json')
        for name in frozen['assets']:
            inputs[str(REPO/name)] = sha(REPO/name)
        for name, digest in frozen['external_assets'].items():
            require(sha(name) == digest, 'Historical external asset changed: ' + name)
            inputs[name] = digest
        evidence['input_sha256'] = inputs
        save()
        run('new_audit_helpers', ['python3', str(HERE/'test_verify.py')])
        run('historical_ax01', ['python3', str(helper.HISTORICAL), '--output', str(out/'historical_ax01')])
        previous = helper.read(out/'historical_ax01/evidence.json')
        require(previous['success'] and previous['v08_provenance_not_applicable'] == evidence['v08_provenance_not_applicable'],
            'Historical functional chain failed or exclusion changed')
        for name in ('test_protocol', 'test_targets'):
            run('ax02_' + name, ['python3', str(helper.HISTORICAL.parent.parent/'ax02'/(name + '.py'))])
        run('build_extra_tests', ['cmake', '--build', str(REPO/'build/px4_sitl_test'), '--target',
            *[kind + '-' + name for name, kind in TESTS], '--parallel', '4'])
        for name, kind in TESTS:
            run(name, [str(REPO/'build/px4_sitl_test'/(kind + '-' + name)),
                '--gtest_output=xml:' + str(out/(name + '.xml'))], timeout=180)
        run('new_tools', ['python3', '-m', 'unittest', 'discover', '-s', str(R02/'tools'), '-p', 'test_*.py', '-v'])
        run('helper_regression', ['python3', str(REGULARIZED/'r01/verification/test_verify.py')])
        evidence['metadata'] = check_metadata()
        cpp = helper.xml_inventory(out.rglob('*.xml'))
        python = helper.python_leaf_counts(out)
        regression = helper.xml_inventory([out/'RegularizedVelocityRegression.xml'])
        values = {row['identity'][3] for row in regression['identities']}
        require(regression['unique_tests'] == 16 and values == {f'({axis}, {sequence})'
            for axis in range(8) for sequence in range(2)}, 'Incomplete legacy fixed-sequence matrix')
        require(all('Two2048SampleSequencesPreserveR01OutputAndStateExactly' in row['identity'][1]
            for row in regression['identities']), 'Unexpected regression identity')
        evidence['counts'] = dict(cpp_unique_tests=cpp['unique_tests'], python_tests=python['tests'],
            fixed_legacy_samples=8*2*2048, fixed_same_sample_recalculations=8*2*16, new_flights=0,
            count_policy='Completed XML testcase identities and leaf unittest summaries; no duplicate execution inflation')
        evidence['cpp_inventory'] = cpp
        evidence['python_inventory'] = python
        require(all(sha(name) == digest for name, digest in inputs.items()), 'Inputs changed during validation')
        changed_after = run('scope_after', ['git', 'diff', '--name-only', BASE, '--', *helper.PRODUCTION]).splitlines()
        untracked_after = run('untracked_after', ['git', 'ls-files', '--others', '--exclude-standard', '--', *helper.PRODUCTION]).splitlines()
        require(sorted(set(changed_after) | set(untracked_after)) == evidence['scope'], 'Production scope changed during verification')
        require(run('submodules_after', ['git', 'submodule', 'status', '--recursive']).splitlines() == subs, 'Submodule versions changed')
        require(not run('submodules_clean_after', ['git', 'submodule', 'foreach', '--quiet', '--recursive',
            'git status --porcelain --untracked-files=all']).strip(), 'Dirty submodule after verification')
        run('protected_scope_after', ['git', 'diff', '--exit-code', BASE, '--',
            *helper.CORE_FILES, 'msg/sta_velocity_ctrl_status.msg',
            'research/sta-velocity-control/axis_ablation', 'research/sta-velocity-control/v08',
            'research/sta-velocity-control/v07', 'research/sta-velocity-control/scripts', 'sim_scripts'])
        require(check_reference() == evidence['reference'], 'Frozen reference changed during verification')
        run('diff_check', ['git', 'diff', '--check'])
        evidence['eeprom_after'] = sha(eeprom)
        require(evidence['eeprom_before'] == evidence['eeprom_after'], 'Persistent parameters changed')
        evidence['firmware_sha256'] = sha(REPO/'build/px4_sitl_default/bin/px4')
        evidence['success'] = True
    except BaseException as error:
        evidence['error'] = repr(error)
        evidence['traceback'] = traceback.format_exc()
        raise
    finally:
        evidence['eeprom_final'] = sha(eeprom) if eeprom.is_file() else None
        evidence['eeprom_unchanged_at_exit'] = evidence.get('eeprom_before') == evidence['eeprom_final']
        save()
        (out/'artifacts.sha256').write_text(''.join(f'{sha(path)}  {path}\n' for path in sorted(out.rglob('*'))
            if path.is_file() and path.name != 'artifacts.sha256'))
    print(json.dumps(dict(success=True, output=str(out), counts=evidence['counts']), indent=2))


if __name__ == '__main__':
    main()
