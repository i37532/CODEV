"""Offline preflight: actual nonzero tests, no flight or EEPROM mutation."""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET
from common import CONFIG, REPO, fingerprint


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve(); out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy(); env['PATH'] = str(REPO / '.px4-python/bin') + ':' + env['PATH']
    env['PYTHONPATH'] = ':'.join([str(REPO / '.px4-python'),
        '/home/yr/Desktop/codev doc/experiments/M00-20260912/python', env.get('PYTHONPATH', '')])
    e = dict(success=False, commands=[], new_flights=0,
        head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip())
    def save(): (out / 'evidence.json').write_text(json.dumps(e, indent=2) + '\n')
    def run(name, argv):
        with (out / (name + '.log')).open('w') as stream:
            result = subprocess.run(argv, cwd=REPO, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=900)
        e['commands'].append(dict(name=name, argv=argv, exit_code=result.returncode)); save()
        print(name, result.returncode, flush=True)
        if result.returncode: raise RuntimeError(name + ' failed; no flight')
    save()
    try:
        run('build_log_test', ['make', 'tests', 'TESTFILTER=EstimatorDiagnosticTopics', '-j4'])
        run('logger_test', [str(REPO / 'build/px4_sitl_test/functional-EstimatorDiagnosticTopics'),
                           '--gtest_output=xml:' + str(out / 'logger.xml')])
        run('python_binding', ['python3', str(CONFIG / 'test_protocol.py')])
        run('dry_run', ['python3', str(CONFIG / 'run.py'), '--source-head', e['head'], '--output', str(out / 'NOT_CREATED')])
        run('selector_and_controls', ['python3', str(REPO / 'research/sta-velocity-control/scripts/verify_v04_selector11.py'),
                                     '--output', str(out / 'selector')])
        root = ET.parse(out / 'logger.xml').getroot()
        assert int(root.get('tests')) == 1 and int(root.get('failures')) == 0
        selector = json.loads((out / 'selector/evidence.json').read_text())
        controls = json.loads((out / 'selector/control/evidence.json').read_text())
        e['cpp_tests'] = int(root.get('tests')) + selector['tests']['tests'] + controls['z_tests']['tests'] + controls['inherited_cpp_tests']
        e['python_tests'] = controls['inherited_python_tests'] + int(re.search(
            r'Ran (\d+) tests', (out / 'python_binding.log').read_text())[1])
        frozen = json.loads((CONFIG / 'frozen.json').read_text())
        for name, expected in frozen['assets'].items():
            assert fingerprint(REPO / name) == expected, name
        e['assets_checked'] = len(frozen['assets']); e['success'] = True
    finally:
        save()
        files = sorted(x for x in out.rglob('*') if x.is_file() and x.name != 'artifacts.sha256')
        (out / 'artifacts.sha256').write_text(''.join(f'{fingerprint(x)}  {x}\n' for x in files))
    print(json.dumps(e))


if __name__ == '__main__': main()
