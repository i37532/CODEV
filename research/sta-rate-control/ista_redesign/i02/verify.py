#!/usr/bin/env python3
"""I02 no-flight verification. A fresh output directory is mandatory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True); p.add_argument('--regression', action='store_true')
    args = p.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    folder = Path(__file__).resolve().parent; repo = folder.parents[3]
    kernel = repo/'src/modules/mc_rate_control/StaRateControl'
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    env['PYTHONPATH'] = str(repo/'.px4-python')+':/home/yr/Desktop/codev doc/experiments/M00-20260912/python'
    env['PATH'] = str(repo/'.px4-python/bin')+':'+env['PATH']
    evidence = dict(success=False, commands=[], tests={},
                    head=subprocess.check_output(['git','rev-parse','HEAD'], cwd=repo, text=True).strip(),
                    branch=subprocess.check_output(['git','branch','--show-current'], cwd=repo, text=True).strip(),
                    submodules=subprocess.check_output(['git','submodule','status','--recursive'], cwd=repo, text=True),
                    flight_executed=False, gazebo_started=False,
                    matlab=shutil.which('matlab'), octave=shutil.which('octave'))
    sources = sorted(folder.glob('*.py')) + sorted(folder.glob('*.md'))
    for pattern in ('ProperIsta*', 'StaProtection*', 'TakeoffNuManager*'):
        sources += sorted(kernel.glob(pattern))
    sources += [kernel/'CMakeLists.txt']
    snapshot = out/'source_snapshot'; snapshot.mkdir()
    evidence['source_hashes'] = {}
    for path in sorted(set(sources)):
        relative = path.relative_to(repo); target = snapshot/relative
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
        evidence['source_hashes'][str(relative)] = digest(path)

    def run(name, argv):
        print('RUN', name, flush=True)
        with (out/(name+'.log')).open('x') as stream:
            result = subprocess.run(list(map(str, argv)), cwd=repo, env=env, stdout=stream, stderr=subprocess.STDOUT)
        evidence['commands'].append(dict(name=name, argv=list(map(str, argv)), returncode=result.returncode))
        if result.returncode: raise RuntimeError(f'{name} failed ({result.returncode})')

    try:
        run('diff_check', ['git','diff','--check'])
        for target in ('ProperIstaProtection', 'TakeoffNuManager', 'ProperIstaRateControl', 'StaProtection'):
            run('build_'+target, ['make','tests','TESTFILTER='+target])
        expected = {'ProperIstaProtection': 11, 'TakeoffNuManager': 10, 'ProperIstaRateControl': 16, 'StaProtection': 18}
        for target, count in expected.items():
            xml = out/(target+'.xml')
            run('test_'+target, [repo/'build/px4_sitl_test'/('unit-'+target), '--gtest_output=xml:'+str(xml)])
            root = ET.parse(xml).getroot()
            actual = {key: int(root.attrib[key]) for key in ('tests','failures','errors','disabled')}
            assert actual == dict(tests=count, failures=0, errors=0, disabled=0), (target, actual)
            evidence['tests'][target] = actual
        if args.regression:
            run('m09_regression', ['python3', repo/'research/sta-rate-control/scripts/verify_m09.py', '--output', out/'m09'])
            m09 = json.loads((out/'m09/evidence.json').read_text())
            assert m09['success'] and m09['logger_format_length'] < 1500
            evidence['existing'] = m09
            evidence['logger_format_length'] = m09['logger_format_length']
            run('sitl_symbols', ['nm','-C',repo/'build/px4_sitl_default/bin/px4'])
            symbols = (out/'sitl_symbols.log').read_text()
            assert 'ProperIstaRateControl' not in symbols and 'ProperIstaProtection' not in symbols
            assert 'IstaRateControl::update' in symbols and 'StaRateControl::update' in symbols
            evidence['firmware_sha256'] = digest(repo/'build/px4_sitl_default/bin/px4')
            protected = ['src/modules/mc_rate_control/MulticopterRateControl.cpp',
                         'src/modules/mc_rate_control/MulticopterRateControl.hpp',
                         'src/modules/mc_rate_control/mc_rate_control_params.c', 'src/modules/land_detector',
                         'msg', 'boards', 'ROMFS', 'sitl', 'sim_scripts']
            run('scope_check', ['git','diff','--exit-code','547d324f6528a2fc05651574e5dd3ec5cb44e7de','--']+protected)
        assert all(digest(repo/path) == value for path, value in evidence['source_hashes'].items())
        evidence['success'] = True
    except Exception as exc:
        evidence['failure'] = repr(exc)
        raise
    finally:
        (out/'evidence.json').write_text(json.dumps(evidence, indent=2, allow_nan=False)+'\n')
    print('I02 passed:', evidence['tests'], 'regression=', args.regression)


if __name__ == '__main__': main()
