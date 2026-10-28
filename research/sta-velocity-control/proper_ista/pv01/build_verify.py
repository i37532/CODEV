#!/usr/bin/env python3
"""PV01 offline rebuild/regression only. Default dry-run; never starts PX4/Gazebo.

Install next to PV01 common.py before use. This does not invoke any historical
stage runner, flight qualification, parameter writer or simulator command.
"""
import argparse
import json
from pathlib import Path
import re
import shlex
import shutil
import traceback
import xml.etree.ElementTree as ET

from common import BASE, CONTROL, HERE, REPO, fresh, load, run, save, sha

KERNEL = 'ProperIstaVelocityControl'
PREFIX = 'src/modules/mc_pos_control/PositionControl/'
ALLOWED = {PREFIX + KERNEL + ending for ending in ('.hpp', '.cpp', 'Test.cpp')}
ALLOWED.add(PREFIX + 'CMakeLists.txt')
PRODUCTION = ('src', 'msg', 'Tools', 'ROMFS', 'boards', 'platforms', 'sitl')
INVENTORY = REPO / 'research/sta-velocity-control/regularized_ista/ri07/offline_regression.py'
FROZEN = INVENTORY.parent / 'gates/FORMAL/frozen.json'
REQUIRED_FLAGS = ['-fno-fast-math', '-fno-reciprocal-math', '-fsigned-zeros',
                  '-ffp-contract=off', '-frounding-math']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inventory():
    # Import only the existing inventory and XML parser. Never call its main
    # or the old RI07 branch/flight audit/qualification functions.
    old = load('pv01_ri07_inventory', INVENTORY)
    targets = list(old.TARGETS) + ['unit-' + KERNEL]
    require(len(old.TARGETS) == 48 and len(targets) == len(set(targets)) == 49,
            'Unexpected test-target inventory; review before execution')
    return targets, old.receipt.completed_cases


def strict_flags(entry):
    args = entry.get('arguments') or shlex.split(entry['command'])
    standards = [arg for arg in args if arg.startswith('-std=')]
    require(standards and standards[-1] in ('-std=c++14', '-std=gnu++14'),
            'New core did not compile as C++14')
    for required in REQUIRED_FLAGS:
        require(required in args, 'Missing source-local numerical flag: ' + required)
    pairs = [('-fno-fast-math', {'-ffast-math', '-Ofast', '-funsafe-math-optimizations',
                              '-ffinite-math-only'}),
             ('-fno-reciprocal-math', {'-freciprocal-math'}),
             ('-fsigned-zeros', {'-fno-signed-zeros'}),
             ('-frounding-math', {'-fno-rounding-math'})]
    for good, bad in pairs:
        last_good = max(i for i, arg in enumerate(args) if arg == good)
        require(not any(arg in bad for arg in args[last_good + 1:]),
                'Unsafe flag overrides numerical contract: ' + good)
    contraction = [arg for arg in args if arg.startswith('-ffp-contract=')]
    require(contraction[-1] == '-ffp-contract=off', 'FMA contraction enabled')
    return dict(command=entry, standards=standards, required_flags=REQUIRED_FLAGS,
                passed=True, only_new_kernel_flags_modified=True)


def unchanged_assets():
    frozen = json.loads(FROZEN.read_text())
    groups = {}
    # The sole old frozen-file difference allowed here is the reviewed CMake
    # test-only registration. New core/test sources are absent from old freeze.
    exception = PREFIX + 'CMakeLists.txt'
    for group in ('assets', 'external_assets', 'generated_assets'):
        records = {}
        for name, expected in frozen[group].items():
            if group == 'assets' and name == exception:
                continue
            path = Path(name) if Path(name).is_absolute() else REPO / name
            require(path.is_file(), 'Missing frozen asset: ' + str(path))
            actual = sha(path)
            require(actual == expected, 'Changed frozen asset: ' + str(path))
            records[str(path)] = actual
        groups[group] = records
    return dict(freeze_path=str(FROZEN), freeze_sha256=sha(FROZEN), groups=groups,
                explicit_exception=exception, passed=True)


def parameters(path):
    require(path.is_file(), 'Missing generated parameter metadata')
    nodes = list(ET.parse(path).iter('parameter'))
    by_name = {node.attrib['name']: node for node in nodes}
    require(len(nodes) == len(by_name) and len(nodes) > 100, 'Invalid parameter metadata')
    mode = by_name['MPC_VC_MODE']
    require(mode.attrib['default'] == '0' and mode.findtext('max') == '4', 'MODE5 admitted/default changed')
    expected = {'MC_RTC_MODE': '0', 'MC_STA_AXES': '0', 'MC_RTC_DIV': '1',
                'MC_RATT_TEST': '0', 'MC_STA_TKO_MGT': '0', 'MPC_VC_DIV': '1',
                'MPC_VC_AXES': '0'}
    for name, default in expected.items():
        require(by_name[name].attrib['default'] == default, 'Default changed: ' + name)
    # Compare every parameter's semantic XML, not only the selected defaults.
    return {name: ET.tostring(node, encoding='unicode').strip()
            for name, node in sorted(by_name.items())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    targets, completed_cases = inventory()
    plan = dict(stage='PV01', targets=targets, target_count=len(targets),
                commands=['make tests TESTFILTER=ProperIstaVelocityControl -j4',
                          'cmake --build build/px4_sitl_test --target <49 frozen targets> --parallel 4',
                          '<each target> --gtest_output=xml:<new external directory>',
                          'strict C++14 compile; make px4_sitl_default -j4; nm -C; selector audit'],
                flights=0, simulator_launches=0, flight_qualified=False,
                firmware_note='current binary archived before rebuild; never automatically restored or launched',
                inherited_inventory=str(INVENTORY))
    if not args.execute:
        print(json.dumps(dict(dry_run=True, **plan), ensure_ascii=False, indent=2))
        return
    require(args.output is not None, '--execute requires a new --output directory')
    out = fresh(args.output)
    evidence = dict(plan, success=False, cpp_unique_tests=0, commands=[], failures=[],
                    inventory_sha256=sha(INVENTORY), targets={}, not_executed=[
                        'Gazebo/PX4 launch', 'flight qualification', 'parameter writes', 'MATLAB',
                        'PV02 or historical RI/R/rate stages', 'push'])

    def command(name, argv, timeout=1800):
        try:
            return run(out, name, argv, timeout)
        finally:
            receipt = out / (name + '.command.json')
            if receipt.is_file():
                evidence['commands'].append(json.loads(receipt.read_text()))
            save(out / 'evidence.json', evidence)

    def scope(label):
        changed = command(label + '_diff', ['git', 'diff', '--name-only', BASE, '--', *PRODUCTION]).splitlines()
        untracked = command(label + '_new', ['git', 'ls-files', '--others', '--exclude-standard', '--', *PRODUCTION]).splitlines()
        paths = set(changed + untracked)
        require(paths == ALLOWED, 'Unexpected production edit scope: ' + repr(sorted(paths)))
        return sorted(paths)

    try:
        require(command('head', ['git', 'rev-parse', 'HEAD']).strip() == BASE, 'Unexpected PV01 entry HEAD')
        require(command('branch', ['git', 'branch', '--show-current']).strip() == 'research/proper-ista-velocity', 'Wrong branch')
        evidence['worktree'] = command('status', ['git', 'status', '--short', '--untracked-files=all'])
        subs = command('submodules', ['git', 'submodule', 'status', '--recursive']).splitlines()
        require(len(subs) == 33 and all(line.startswith(' ') for line in subs), 'Submodule mismatch')
        require(not command('submodule_dirty', ['git', 'submodule', 'foreach', '--quiet', '--recursive',
                                               'git status --porcelain']).strip(), 'Dirty submodules')
        evidence['submodules'] = subs
        processes = command('processes', ['ps', '-eo', 'pid,comm,args'])
        require(not any(len(line.split()) > 1 and line.split()[1] in ('px4', 'gzserver', 'gzclient')
                        for line in processes.splitlines()), 'Existing simulator process; do not interfere')
        evidence['scope_before'] = scope('before')
        evidence['assets_before'] = unchanged_assets()
        inputs = {str(REPO / name): sha(REPO / name) for name in ALLOWED}
        for path in HERE.glob('*'):
            if path.is_file() and path.suffix in ('.py', '.cpp', '.md'):
                inputs[str(path)] = sha(path)
        evidence['input_sha256'] = inputs
        binary = REPO / 'build/px4_sitl_default/bin/px4'
        eeprom = REPO / 'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
        metadata = REPO / 'build/px4_sitl_default/parameters.xml'
        require(binary.is_file() and eeprom.is_file(), 'Missing existing firmware/EEPROM baseline')
        evidence['firmware_before'] = sha(binary)
        evidence['eeprom_before'] = sha(eeprom)
        shutil.copy2(binary, out / 'px4.pre_build')
        shutil.copy2(eeprom, out / 'eeprom.pre_build')
        require(sha(out / 'px4.pre_build') == evidence['firmware_before'], 'Firmware backup failed')
        require(sha(out / 'eeprom.pre_build') == evidence['eeprom_before'], 'EEPROM backup failed')
        before_parameters = parameters(metadata)
        save(out / 'parameters_before.json', before_parameters)
        save(out / 'evidence.json', evidence)

        command('configure_tests', ['make', 'tests', 'TESTFILTER=' + KERNEL, '-j4'])
        command('build_targets', ['cmake', '--build', REPO / 'build/px4_sitl_test',
                                 '--target', *targets, '--parallel', '4'])
        unique = set()
        for target in targets:
            executable = REPO / 'build/px4_sitl_test' / target
            xml = out / (target + '.xml')
            command(target, [executable, '--gtest_output=xml:' + str(xml)], timeout=300)
            cases = completed_cases(xml.read_bytes(), target)
            overlap = unique & cases
            require(not overlap, 'Duplicate case identities across regression binaries: ' + repr(overlap))
            unique.update(cases)
            evidence['targets'][target] = dict(tests=len(cases), cases=sorted(cases),
                xml=str(xml), xml_sha256=sha(xml), executable=str(executable), executable_sha256=sha(executable))
            evidence['cpp_unique_tests'] = len(unique)
            save(out / 'evidence.json', evidence)
        require(len(evidence['targets']) == 49 and evidence['targets']['unit-' + KERNEL]['tests'] >= 39,
                'Incomplete new/old C++ execution')
        evidence['new_kernel_tests'] = evidence['targets']['unit-' + KERNEL]['tests']
        evidence['regression_tests'] = len(unique) - evidence['new_kernel_tests']
        require(evidence['regression_tests'] >= 751, 'Prior nonzero regression inventory unexpectedly shrank')

        command('strict_cxx14', ['g++', '-std=c++14', '-O2', '-pedantic-errors', '-Wall', '-Wextra', '-Werror',
                                '-fno-exceptions', '-fno-rtti', *REQUIRED_FLAGS, '-c', CONTROL / (KERNEL + '.cpp'),
                                '-o', out / 'strict_kernel.o'])
        db = json.loads((REPO / 'build/px4_sitl_test/compile_commands.json').read_text())
        entries = [entry for entry in db if entry['file'].endswith('/' + KERNEL + '.cpp')]
        require(len(entries) == 1, 'Ambiguous/missing new core compile command')
        evidence['compile_flags'] = strict_flags(entries[0])
        save(out / 'compile_flags.json', evidence['compile_flags'])
        command('build_sitl', ['make', 'px4_sitl_default', '-j4'])
        symbols = command('firmware_symbols', ['nm', '-C', binary])
        require(len(symbols.splitlines()) > 1000 and KERNEL not in symbols, 'New kernel found in firmware or incomplete nm')
        production_db = json.loads((REPO / 'build/px4_sitl_default/compile_commands.json').read_text())
        require(not any(KERNEL in entry['file'] for entry in production_db), 'New kernel compiled in production')
        consumers = command('core_consumers', ['rg', '-l', KERNEL, 'src']).splitlines()
        require(set(consumers) == ALLOWED, 'Unexpected new kernel consumer')
        selector_source = HERE.parent / 'pv00/selector_audit.cpp'
        command('compile_selector', ['g++', '-std=c++14', '-O2', '-pedantic-errors', '-Wall', '-Wextra', '-Werror',
                                     '-I', CONTROL, selector_source, '-o', out / 'selector_audit'])
        selector = command('selector_audit', [out / 'selector_audit'])
        require('Tests run: 6, passed: 6, failed: 0' in selector, 'Selector audit did not execute all six cases')
        evidence['no_actuator_path'] = dict(selector_named_cases=6, mode5_rejected=True,
            selector_source_sha256=sha(selector_source), firmware_nm_lines=len(symbols.splitlines()),
            absent_from_firmware=True, absent_from_production_compilation=True, core_consumers=consumers,
            production_compile_database_sha256=sha(REPO / 'build/px4_sitl_default/compile_commands.json'))
        after_parameters = parameters(metadata)
        require(before_parameters == after_parameters, 'Generated parameter semantics changed')
        evidence['parameter_count'] = len(after_parameters)
        evidence['firmware_after'] = sha(binary)
        evidence['eeprom_after'] = sha(eeprom)
        require(evidence['eeprom_after'] == evidence['eeprom_before'], 'EEPROM changed unexpectedly')
        evidence['assets_after'] = unchanged_assets()
        require(evidence['assets_before'] == evidence['assets_after'], 'Frozen assets changed during builds')
        evidence['scope_after'] = scope('after')
        require(evidence['scope_before'] == evidence['scope_after'], 'Edit scope changed during builds')
        require(all(Path(path).is_file() and sha(path) == expected for path, expected in inputs.items()),
                'Verification source changed while tests were running')
        command('diff_check', ['git', 'diff', '--check'])
        evidence['success'] = True
    except BaseException as error:
        evidence['failures'].append(dict(error=repr(error), traceback=traceback.format_exc()))
        raise
    finally:
        save(out / 'evidence.json', evidence)
    print(json.dumps({key: evidence[key] for key in ('success', 'cpp_unique_tests',
        'new_kernel_tests', 'regression_tests', 'flights', 'flight_qualified')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
