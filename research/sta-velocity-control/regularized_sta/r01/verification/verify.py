#!/usr/bin/env python3
"""R01 offline build/regression audit. Never launches a simulator or changes params.

This deliberately uses AX01 functional verification without AX04 frozen-source
qualification. Each invocation requires a fresh external output directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import traceback
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
BASE = 'e3c1434081ca3ed16b274ef49f27ab871660bfd8'
PACKAGE = Path('/home/yr/Desktop/STA-ISTA-MATLAB-PX4')
PREFIX = 'src/modules/mc_pos_control/PositionControl/'
KERNEL = 'RegularizedStaVelocityControl'
CORE_FILES = [PREFIX + KERNEL + suffix for suffix in ('.cpp', '.hpp', 'Test.cpp')]
ALLOWED = set(CORE_FILES + [PREFIX + 'CMakeLists.txt'])
PRODUCTION = ('src', 'msg', 'Tools', 'sitl', 'ROMFS', 'boards', 'platforms')
HISTORICAL = REPO / 'research/sta-velocity-control/axis_ablation/ax01/verify.py'
RATE_EXTRA = ('ControllerSelection', 'StaProtection', 'StaAxesApplication',
              'TakeoffNuManager', 'IstaRateControl', 'IstaIntegration',
              'ControlDecimation', 'ProperIstaRateControl',
              'ProperIstaIntegration', 'ProperIstaProtection')
EXTRA_TESTS = RATE_EXTRA + ('VelocityAblationTask',)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def xml_inventory(paths):
    """Count actual completed testcase identities, never nested summary totals."""
    unique, documents, duplicates = {}, [], []
    for path in sorted(map(Path, paths)):
        root = ET.parse(path).getroot()
        declared = int(root.attrib.get('tests', '-1'))
        cases = list(root.iter('testcase'))
        require(declared == len(cases) and declared > 0, 'Empty/inconsistent test XML: ' + str(path))
        for key in ('failures', 'errors', 'disabled'):
            require(int(root.attrib.get(key, '0')) == 0, 'Unsuccessful XML ' + key + ': ' + str(path))
        local = set()
        for case in cases:
            require(case.attrib.get('status') == 'run', 'Testcase not executed: ' + str(path))
            require(not any(case.find(tag) is not None for tag in ('failure', 'error', 'skipped')),
                    'Testcase failed/skipped: ' + str(path))
            require(case.attrib.get('result', 'completed') == 'completed', 'Incomplete testcase: ' + str(path))
            identity = tuple(case.attrib.get(k, '') for k in ('classname', 'name', 'type_param', 'value_param'))
            require(identity[0] and identity[1] and identity not in local,
                    'Missing/duplicate identity within one XML: ' + str(path))
            local.add(identity)
            if identity in unique:
                duplicates.append(dict(identity=identity, first=unique[identity], repeated=str(path)))
            else:
                unique[identity] = str(path)
        documents.append(dict(path=str(path), tests=declared, sha256=sha(path)))
    require(bool(unique), 'Zero tests is not verification')
    return dict(unique_tests=len(unique), executed_xml_cases=sum(x['tests'] for x in documents),
                xml_documents=documents, repeated_identities=duplicates,
                identities=[dict(identity=k, first_xml=v) for k, v in sorted(unique.items())])


def python_leaf_counts(root):
    """Use only direct command logs, not ancestor JSON stdout or nested totals."""
    records, seen_logs = [], set()
    for evidence in sorted(Path(root).rglob('evidence.json')):
        document = read(evidence)
        for command in document.get('commands', []):
            argv = command.get('argv', command.get('command', []))
            if not argv or Path(argv[0]).name not in ('python', 'python3'):
                continue
            path = evidence.parent / (command['name'] + '.log')
            if not path.is_file() or path in seen_logs:
                continue
            # A wrapper may echo nested evidence containing the words "Ran";
            # only the standalone unittest summary line is a count.
            summaries = re.findall(r'^Ran (\d+) tests? in [^\n]+$', path.read_text(), re.MULTILINE)
            if not summaries:
                continue
            require(len(summaries) == 1, 'Ambiguous unittest summaries: ' + str(path))
            count = int(summaries[0])
            require(count > 0 and command['exit_code'] == 0, 'Non-passing Python run: ' + str(path))
            require(re.search(r'^OK\s*$', path.read_text(), re.MULTILINE) is not None,
                    'Skipped/failing Python test suite is not counted as all passing: ' + str(path))
            seen_logs.add(path)
            records.append(dict(log=str(path), argv=argv, tests=count, sha256=sha(path)))
    require(bool(records), 'No direct Python test logs')
    return dict(tests=sum(row['tests'] for row in records), direct_logs=records)


def production_scope(changed, untracked):
    unexpected = (set(changed) | set(untracked)) - ALLOWED
    require(not unexpected, 'R01 production scope exceeded: ' + ', '.join(sorted(unexpected)))
    return dict(allowed=sorted(ALLOWED), actual_changed=sorted(set(changed) | set(untracked)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    require(out != REPO and REPO not in out.parents, 'Evidence must be external, not inside repository')
    require(not out.exists(), 'Output exists; select a fresh unique directory')
    out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env['PATH'] = str(REPO / '.px4-python/bin') + ':' + env['PATH']
    env['PYTHONPATH'] = ':'.join([str(REPO / '.px4-python'),
        str(REPO / 'research/sta-velocity-control/scripts'),
        '/home/yr/Desktop/codev doc/experiments/M00-20260912/python', env.get('PYTHONPATH', '')])
    param = REPO / 'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    evidence = dict(schema=1, stage='R01', success=False, commands=[], baseline=BASE,
        new_flights=0, seeds_used=[], source_package=str(PACKAGE),
        not_executed=['MATLAB', 'SITL flight', 'new ISTA implementation', 'AX04 frozen-source qualification'],
        v08_provenance_not_applicable='protocol02.test_tuning.TuningTest.test_original_production_and_launcher_unchanged',
        ax04_provenance_not_applicable='New R01 source is not AX04 frozen 794301664cc0aacee6b5c62987531ab6f0b33fdf')

    def save():
        (out / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')

    def run(name, argv, cwd=REPO, timeout=3600):
        start = time.monotonic()
        with (out / (name + '.log')).open('x') as stream:
            try:
                completed = subprocess.run(argv, cwd=cwd, env=env, stdout=stream,
                                           stderr=subprocess.STDOUT, timeout=timeout)
                code, timed_out = completed.returncode, False
            except subprocess.TimeoutExpired:
                code, timed_out = 124, True
        row = dict(name=name, argv=list(map(str, argv)), cwd=str(cwd), exit_code=code,
                   timeout=timed_out, wall_seconds=time.monotonic() - start)
        evidence['commands'].append(row)
        save()
        print(name, code, flush=True)
        require(code == 0, name + ' failed; evidence retained at ' + str(out))
        return (out / (name + '.log')).read_text()

    def scope(label):
        changed = run(label + '_diff_names', ['git', 'diff', '--name-only', BASE, '--', *PRODUCTION]).splitlines()
        untracked = run(label + '_untracked', ['git', 'ls-files', '--others', '--exclude-standard', '--', *PRODUCTION]).splitlines()
        return production_scope(changed, untracked)

    inputs = {}
    try:
        evidence['eeprom_before'] = sha(param)
        evidence['head'] = run('head', ['git', 'rev-parse', 'HEAD']).strip()
        require(run('branch', ['git', 'branch', '--show-current']).strip() == 'research/sta-velocity-regularized', 'Wrong branch')
        run('baseline_ancestor', ['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'])
        run('workspace_before', ['git', 'status', '--porcelain=v1', '--untracked-files=all'])
        subs = run('submodules', ['git', 'submodule', 'status', '--recursive']).splitlines()
        require(len(subs) == 33 and all(s.startswith(' ') for s in subs), 'Submodule count/version mismatch')
        require(not run('submodules_clean', ['git', 'submodule', 'foreach', '--quiet', '--recursive',
                    'git status --porcelain --untracked-files=all']).strip(), 'Dirty submodule')
        evidence['submodules'] = subs
        evidence['scope_before'] = scope('before')
        run('protected_old_research', ['git', 'diff', '--exit-code', BASE, '--',
            'research/sta-velocity-control/axis_ablation', 'research/sta-velocity-control/v08',
            'research/sta-velocity-control/v07', 'research/sta-velocity-control/scripts', 'sim_scripts'])
        manifest = PACKAGE / 'SHA256SUMS.txt'
        old_package = read(REPO / 'research/sta-velocity-control/regularized_sta/r00/math/results02.json')
        require(sha(manifest) == old_package['package_sha256_manifest'], 'Source package manifest changed')
        run('source_package', ['sha256sum', '-c', 'SHA256SUMS.txt'], cwd=PACKAGE)
        evidence['source_package_manifest_sha256'] = sha(manifest)
        for line in manifest.read_text().splitlines():
            digest, name = line.split(None, 1)
            path = PACKAGE / name.lstrip('*')
            require(sha(path) == digest, 'Source package mismatch: ' + str(path))
            inputs[str(path)] = digest
        frozen = read(REPO / 'research/sta-velocity-control/axis_ablation/ax04/frozen.json')
        for name in list(frozen['assets']) + CORE_FILES:
            inputs[str(REPO / name)] = sha(REPO / name)
        for name, expected in frozen['external_assets'].items():
            require(sha(name) == expected, 'Historical external asset changed: ' + name)
            inputs[name] = expected
        for path in HERE.glob('*.py'):
            inputs[str(path)] = sha(path)
        evidence['input_sha256'] = inputs
        save()
        run('audit_helpers', ['python3', str(HERE / 'test_verify.py')])
        run('historical_ax01', ['python3', str(HISTORICAL), '--output', str(out / 'historical_ax01')])
        previous = read(out / 'historical_ax01/evidence.json')
        require(previous['success'], 'AX01 functional chain not successful')
        require(previous['v08_provenance_not_applicable'] == evidence['v08_provenance_not_applicable'],
                'Unexpected history exclusion')
        for name in ('test_protocol', 'test_targets'):
            run('ax02_' + name, ['python3', str(HISTORICAL.parent.parent / 'ax02' / (name + '.py'))])
        run('build_extra_tests', ['cmake', '--build', str(REPO / 'build/px4_sitl_test'),
            '--target', 'unit-' + KERNEL, *['unit-' + name for name in EXTRA_TESTS], '--parallel', '4'])
        for name in (KERNEL,) + EXTRA_TESTS:
            run(name, [str(REPO / 'build/px4_sitl_test' / ('unit-' + name)),
                '--gtest_output=xml:' + str(out / (name + '.xml'))], timeout=120)
        # The strict standalone compile proves C++14 without relying on CMake's
        # "at least cxx_std_14" feature or on a pre-existing object file.
        run('standalone_cxx14', ['g++', '-std=c++14', '-pedantic-errors', '-Wall', '-Wextra', '-Werror',
            '-fno-exceptions', '-fno-rtti', '-I' + str(REPO / PREFIX),
            '-c', str(REPO / (PREFIX + KERNEL + '.cpp')), '-o', str(out / 'kernel_cxx14.o')])
        db = read(REPO / 'build/px4_sitl_test/compile_commands.json')
        entry = next(e for e in db if e['file'].endswith('/' + KERNEL + '.cpp'))
        standards = [a for a in shlex.split(entry['command']) if a.startswith('-std=')]
        require(standards and standards[-1] in ('-std=c++14', '-std=gnu++14'), 'Unexpected actual kernel C++ standard')
        evidence['kernel_compile_command'] = entry
        matches = run('new_kernel_references', ['rg', '-l', KERNEL, 'src']).splitlines()
        require(set(matches) == ALLOWED, 'Unexpected new kernel consumer/source: ' + repr(matches))
        cmake = (REPO / (PREFIX + 'CMakeLists.txt')).read_text()
        require('target_link_libraries(PositionControl PUBLIC StaVelocityControl)' in cmake,
                'Original PositionControl library dependency changed')
        require(not re.search(r'target_link_libraries\s*\(\s*PositionControl[^)]*' + KERNEL, cmake, re.S),
                'New core linked to PositionControl')
        symbols = run('firmware_symbols', ['nm', '-C', str(REPO / 'build/px4_sitl_default/bin/px4')])
        require(len(symbols.splitlines()) > 1000 and KERNEL not in symbols,
                'Cannot prove new core absent from actual firmware symbol table')
        evidence['no_actuator_path'] = dict(source_consumers=matches, core_absent_from_firmware=True,
            position_module_and_selector_unchanged=True, default_parameters_unchanged=True,
            reason='Only isolated library/test references; R00 production paths unchanged except allowed files')
        cpp = xml_inventory(out.rglob('*.xml'))
        new = xml_inventory([out / (KERNEL + '.xml')])
        historical_cpp = xml_inventory((out / 'historical_ax01').rglob('*.xml'))
        require(historical_cpp['unique_tests'] == previous['cpp_tests'], 'Historical C++ count mismatch')
        python = python_leaf_counts(out / 'historical_ax01')
        require(python['tests'] == previous['python_tests'], 'Historical Python count mismatch')
        helper = re.findall(r'^Ran (\d+) tests? in [^\n]+$', (out / 'audit_helpers.log').read_text(), re.MULTILINE)
        require(len(helper) == 1 and int(helper[0]) > 0, 'No actual audit helper tests')
        all_python = python_leaf_counts(out)
        evidence['counts'] = dict(cpp_unique_tests=cpp['unique_tests'], new_kernel_gtests=new['unique_tests'],
            historical_cpp_tests=historical_cpp['unique_tests'], historical_python_tests=python['tests'],
            audit_helper_python_tests=int(helper[0]), python_tests=all_python['tests'],
            new_flights=0, cpp_count_policy='XML identities, not nested JSON sums or ctest re-execution totals')
        evidence['cpp_inventory'] = cpp
        evidence['historical_python_leaf_inventory'] = python
        evidence['all_python_leaf_inventory'] = all_python
        evidence['scope_after'] = scope('after')
        require(evidence['scope_after'] == evidence['scope_before'], 'Production input set changed during verification')
        mismatches = [p for p, expected in inputs.items() if sha(p) != expected]
        require(not mismatches, 'Input modified during validation: ' + repr(mismatches))
        run('diff_check', ['git', 'diff', '--check'])
        evidence['eeprom_after'] = sha(param)
        require(evidence['eeprom_before'] == evidence['eeprom_after'], 'EEPROM modified')
        evidence['firmware_sha256'] = sha(REPO / 'build/px4_sitl_default/bin/px4')
        evidence['success'] = True
    except BaseException as error:
        evidence['failure'] = dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
        raise
    finally:
        evidence['eeprom_finally'] = sha(param) if param.exists() else None
        evidence['eeprom_unchanged'] = evidence.get('eeprom_before') == evidence['eeprom_finally']
        save()
        files = sorted(p for p in out.rglob('*') if p.is_file() and p.name != 'artifacts.sha256')
        (out / 'artifacts.sha256').write_text(''.join(sha(p) + '  ' + str(p.relative_to(out)) + '\n' for p in files))
    print(json.dumps(dict(success=evidence['success'], counts=evidence['counts'], output=str(out)), indent=2))


if __name__ == '__main__':
    main()
