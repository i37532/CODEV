#!/usr/bin/env python3
"""Archive/reproduce V03 prerequisite failures without changing V02 or flying."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

from capture_v00 import persisted_bson

REPO = Path(__file__).resolve().parents[3]
BASE = '3d7b5a0dfcf36be5ae678a76c9d8c1f0f52b3eba'
CORE = Path('src/modules/mc_pos_control/PositionControl')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    evidence = {'audited_commit': BASE, 'commands': [], 'tests': {},
                'runtime_verified': False, 'flight_attempts': 0, 'status': 'in_progress'}

    def save():
        (out/'evidence.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False)+'\n')

    def run(name, command):
        result = subprocess.run(command, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (out/(name+'.log')).write_text(result.stdout)
        evidence['commands'].append({'name': name, 'command': command, 'exit_code': result.returncode})
        save()
        print(name, result.returncode, flush=True)
        return result

    try:
        for name, cmd in [
            ('head', ['git','rev-parse','HEAD']), ('branch', ['git','branch','--show-current']),
            ('workspace', ['git','status','--short','--branch']),
            ('submodules', ['git','submodule','status','--recursive']),
            ('submodule_workspaces', ['git','submodule','foreach','--recursive','--quiet','git status --porcelain']),
            ('compiler', ['g++','--version']), ('gazebo', ['pkg-config','--modversion','gazebo']),
        ]:
            if run(name, cmd).returncode:
                raise RuntimeError('Audit command failed: '+name)
        unchanged = [CORE/name for name in ('StaVelocityControl.hpp','StaVelocityControl.cpp',
                    'StaVelocityControlTest.cpp','PositionControl.cpp','VelocityControlSelector.hpp','CMakeLists.txt')]
        sources = unchanged + [Path(__file__).relative_to(REPO),
            Path('research/sta-velocity-control/v03/preflight/CandidateAuditTest.cpp')]
        for rel in sources:
            content = (REPO/rel).read_bytes()
            if rel in unchanged:
                frozen = subprocess.check_output(['git','show',BASE+':'+str(rel)], cwd=REPO)
                if frozen != content:
                    raise ValueError('V02 source changed: '+str(rel))
            target = out/'sources'/rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

        plans = Path('/home/yr/Desktop/codev doc/plan')
        for name in ('VELOCITY_STA_TODO_CN.md','VELOCITY_STA_STATUS_CN.md'):
            shutil.copyfile(plans/name, out/name)
        shutil.copyfile(REPO/'research/sta-velocity-control/reports/V02.md', out/'V02_prior_report.md')

        saved = REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
        before = hashlib.sha256(saved.read_bytes()).hexdigest()
        shutil.copyfile(saved, out/'parameters_10016.bson')
        parameters = persisted_bson(saved.read_bytes())
        defaults = {p['name']: p['default'] for p in json.loads((REPO/'build/px4_sitl_default/parameters.json').read_text())['parameters']}
        evidence['persisted_or_generated_default_not_runtime'] = {
            name: {'saved_override': parameters.get(name), 'generated_default': defaults.get(name)}
            for name in ('MC_RTC_MODE','MC_STA_AXES','MC_RTC_DIV','MC_RATT_TEST','MC_STA_TKO_MGT','MPC_VC_MODE','MPC_VC_AXES')}

        build = REPO/'build/px4_sitl_test'
        binary = out/'candidate_audit'
        compile_cmd = ['g++','-std=c++14','-O2','-pthread','-fno-rtti','-fno-exceptions', '-I'+str(REPO/CORE),
            '-isystem',str(build/'googletest-src/googletest/include'),
            str(REPO/CORE/'StaVelocityControl.cpp'), str(REPO/CORE/'StaVelocityControlTest.cpp'),
            str(REPO/'research/sta-velocity-control/v03/preflight/CandidateAuditTest.cpp'),
            str(build/'lib/libgtest_main.a'),str(build/'lib/libgtest.a'),'-o',str(binary)]
        if run('compile',compile_cmd).returncode:
            raise RuntimeError('Could not build audit')
        xml = out/'candidate_audit.xml'
        result = run('candidate_audit', [str(binary),'--gtest_output=xml:'+str(xml)])
        root = ET.parse(xml).getroot()
        evidence['tests'] = {k: int(root.attrib[k]) for k in ('tests','failures','errors','disabled')}
        evidence['cases'] = [{'suite': suite.attrib['name'], 'name': case.attrib['name'],
                             'passed': case.find('failure') is None}
                            for suite in root for case in suite.findall('testcase')]
        evidence['parameter_sha256'] = before
        evidence['parameters_unchanged'] = hashlib.sha256(saved.read_bytes()).hexdigest() == before
        evidence['status'] = 'needs_revision' if result.returncode else 'probes_passed_not_full_V03'
        save()
        return result.returncode
    except Exception:
        evidence['status'] = 'audit_tool_failed'
        raise
    finally:
        save()
        lines = []
        for path in sorted(out.rglob('*')):
            if path.is_file() and path.name != 'artifacts.sha256':
                lines.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+str(path))
        (out/'artifacts.sha256').write_text('\n'.join(lines)+'\n')


if __name__ == '__main__':
    raise SystemExit(main())
