"""Read-only RI04 qualification leaf-evidence validation.

This checks recorded execution evidence, not source/flight authority. The caller
must separately verify clean source, the firmware, freeze and authorization.
Nothing here launches a process or writes an artifact.
"""
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]


def require(value, message):
    if not value:
        raise ValueError(message)


def python_scripts():
    """The complete direct-suite inventory, shared with RI04 verification.

Dynamic entries are frozen source files; deleting one also invalidates the
separate source freeze. The archived receipt may not select its own subset.
"""
    old = REPO/'research/sta-velocity-control/regularized_sta'
    paths = [HERE.parent/'ri02/tools/test_tools.py']
    for folder in ('r03_position11', 'r03_warmup10', 'r03_monitor02', 'r03_prearm04',
                   'r03_numeric05', 'r03_handoff06', 'r03_upstream08'):
        paths.extend(sorted((old/folder).glob('test_*.py')))
    v08 = REPO/'research/sta-velocity-control/v08'
    for folder, name in [('protocol02','test_cli_clock'), ('protocol03b','test_validation'),
            ('protocol03b','test_task_output'), ('protocol04','test_pilot'),
            ('protocol04','test_design'), ('protocol04','test_formal_design'),
            ('evidence_tools','test_replay_batch'), ('protocol05','test_mass'),
            ('formal','test_runtime'), ('formal','test_formal_package'),
            ('evidence_tools','test_qualified_gate_summary')]:
        paths.append(v08/folder/(name+'.py'))
    paths.extend(sorted(HERE.glob('test_*.py')))
    paths.extend(sorted((HERE/'tools').glob('test_*.py')))
    require(paths and len(paths) == len(set(paths)), 'Duplicate/empty Python source inventory')
    return paths


def python_commands():
    commands = {f'py{index:02d}_{path.parent.name}_{path.stem}': ['python3', '-B', str(path)]
                for index, path in enumerate(python_scripts())}
    commands['r02_tools'] = ['python3', '-B', '-m', 'unittest', 'discover', '-s',
        str(REPO/'research/sta-velocity-control/regularized_sta/r02/tools'), '-p', 'test_*.py', '-v']
    return commands


def positive_integer(value, label):
    require(type(value) is int and value > 0, 'Missing/nonpositive integer '+label)
    return value


def completed_cases(raw, label):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ValueError('Malformed test XML '+label) from error
    require(root.tag in ('testsuites', 'testsuite'), 'Wrong test XML root '+label)
    cases = list(root.iter('testcase'))
    require(bool(cases), 'Empty test XML '+label)
    for suite in root.iter():
        if suite.tag not in ('testsuites', 'testsuite'):
            continue
        count = suite.attrib.get('tests', '')
        require(re.fullmatch(r'[0-9]+', count) is not None
                and int(count) == len(list(suite.iter('testcase'))), 'Inconsistent XML count '+label)
        for key in ('failures', 'errors', 'disabled', 'skipped'):
            value = suite.attrib.get(key, '0')
            require(re.fullmatch(r'[0-9]+', value) is not None and int(value) == 0,
                    'Unsuccessful XML '+key+' '+label)
    identities = set()
    for case in cases:
        require(case.get('status') == 'run' and case.get('result', 'completed') == 'completed',
                'Unexecuted/incomplete XML testcase '+label)
        require(not any(case.find(tag) is not None for tag in ('failure', 'error', 'skipped')),
                'Failed/skipped XML testcase '+label)
        identity = tuple(case.get(key, '') for key in ('classname', 'name', 'type_param', 'value_param'))
        require(identity[0] and identity[1] and identity not in identities,
                'Missing/duplicate XML identity '+label)
        identities.add(identity)
    return identities


def unittest_count(raw, label):
    try:
        text = raw.decode('utf-8')
    except UnicodeError as error:
        raise ValueError('Invalid unittest log encoding '+label) from error
    runs = list(re.finditer(r'^Ran ([0-9]+) tests? in [^\n]+$', text, re.MULTILINE))
    verdicts = list(re.finditer(r'^(?:OK|FAILED)(?: \([^\n]*\))?\s*$', text, re.MULTILINE))
    require(len(runs) == 1 and len(verdicts) == 1 and verdicts[0].group().strip() == 'OK',
            'Missing/ambiguous/nonpassing unittest summary '+label)
    require(runs[0].end() <= verdicts[0].start()
            and not text[runs[0].end():verdicts[0].start()].strip(), 'Non-leaf unittest summary '+label)
    return positive_integer(int(runs[0].group(1)), 'unittest count '+label)


def validate(q, path, required_targets, minimum_python, *, expected_python_commands=None):
    """Recompute all C++/Python counts from SHA-bound local leaf artifacts.

    expected_python_commands is an optional trusted name -> exact argv mapping,
    primarily for small isolated tests. It must never come from the receipt.
    Production calls use the complete current frozen RI04 inventory by default.
    """
    root = Path(path).resolve().parent
    positive_integer(minimum_python, 'Python minimum')
    targets = set(required_targets)
    require(targets and all(isinstance(t, str) and re.fullmatch(r'(?:unit|functional)-[A-Za-z0-9_]+', t)
                            for t in targets), 'Invalid required C++ inventory')
    declared = q.get('cpp_test_targets')
    require(isinstance(declared, list) and all(isinstance(t, str) for t in declared)
            and len(declared) == len(set(declared)) and set(declared) == targets,
            'Incomplete/duplicate C++ executable inventory')
    artifacts = q.get('evidence_files')
    require(isinstance(artifacts, dict) and artifacts, 'Missing bound artifacts')

    def bound(name):
        file = root/name
        require(file.parent == root and file.is_file() and not file.is_symlink()
                and file.resolve() == file, 'Missing/nonlocal/symlink artifact '+name)
        expected = artifacts.get(str(file))
        require(isinstance(expected, str) and re.fullmatch(r'[0-9a-f]{64}', expected),
                'Missing artifact SHA '+name)
        raw = file.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, 'Changed artifact '+name)
        return raw, expected

    commands = {}
    records = q.get('commands')
    require(isinstance(records, list) and records, 'Missing executed commands')
    for record in records:
        require(isinstance(record, dict), 'Malformed command record')
        name = record.get('name')
        require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_-]+', name)
                and name not in commands, 'Missing/duplicate command name')
        require(type(record.get('exit_code')) is int and record['exit_code'] == 0,
                'Failed/uncompleted command '+name)
        commands[name] = record

    def command(name, argv):
        require(name in commands, 'Required command missing '+name)
        record = commands[name]
        require(record.get('argv') == argv and record.get('cwd') == str(REPO),
                'Wrong executable/script/filter/cwd '+name)
        raw, sha = bound(name+'.log')
        require(record.get('log_sha256') == sha, 'Command log SHA differs '+name)
        return raw, sha

    unique = set()
    executed = 0
    for target in sorted(targets):
        command(target, [str(REPO/'build/px4_sitl_test'/target),
                         '--gtest_output=xml:'+str(root/(target+'.xml'))])
        raw, _ = bound(target+'.xml')
        identities = completed_cases(raw, target)
        executed += len(identities)
        unique.update(identities)
    counts = q.get('counts', {})
    require(isinstance(counts, dict), 'Missing/malformed receipt counts')
    require(positive_integer(counts.get('cpp_unique_tests'), 'C++ count') == len(unique), 'False C++ unique count')
    require(positive_integer(counts.get('cpp_targets'), 'C++ target count') == len(targets), 'False C++ target count')
    if 'cpp_inventory' in q:
        inventory = q['cpp_inventory']
        require(isinstance(inventory, dict)
                and type(inventory.get('unique_tests')) is int and inventory['unique_tests'] == len(unique)
                and type(inventory.get('executed_xml_cases')) is int and inventory['executed_xml_cases'] == executed,
                'False C++ inventory totals')

    expected = python_commands() if expected_python_commands is None else expected_python_commands
    require(isinstance(expected, dict) and expected, 'Missing expected Python inventory')
    leaves = q.get('python_tests_executed')
    require(isinstance(leaves, list) and leaves, 'Missing actual Python leaves')
    actual = {}
    for leaf in leaves:
        require(isinstance(leaf, dict), 'Malformed Python leaf')
        name = leaf.get('name')
        require(isinstance(name, str) and name in expected and name not in actual, 'Unexpected/duplicate Python leaf')
        actual[name] = leaf
    require(set(actual) == set(expected), 'Incomplete actual Python suite inventory')
    total = 0
    for name, argv in expected.items():
        raw, sha = command(name, argv)
        number = unittest_count(raw, name)
        require(actual[name].get('log_sha256') == sha, 'Python leaf log SHA differs '+name)
        require(positive_integer(actual[name].get('tests'), 'Python leaf count') == number, 'False Python leaf count '+name)
        total += number
    require(positive_integer(counts.get('python_tests'), 'Python total') == total and total >= minimum_python,
            'False/insufficient actual Python total')
    return dict(cpp_unique_tests=len(unique), executed_xml_cases=executed,
                cpp_targets=len(targets), python_tests=total, python_suites=len(expected))
