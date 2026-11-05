#!/usr/bin/env python3
"""Offline protocol compatibility audit; an expected contradiction exits nonzero.

No flight, parameter writes, runner invocation, or alteration of frozen rules.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPO = Path(__file__).resolve().parents[3]
DESIGN = REPO / 'research/sta-velocity-control/v04/protocol02/protocol.json'
PROBE = REPO / 'research/sta-velocity-control/v04/protocol02_audit01/ExcitationLandingAudit.cpp'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    evidence = dict(scope='offline_real_header_protocol_compatibility', flight_attempts=0,
                    compatible=False, commands=[])

    def save():
        (out / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')

    def run(name, command):
        result = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=60)
        output = result.stdout + result.stderr
        (out / (name + '.log')).write_text(output)
        evidence['commands'].append(dict(name=name, argv=command, exit_code=result.returncode))
        save()
        return result.returncode, output

    try:
        protocol = json.loads(DESIGN.read_text())
        rules = protocol['additional_log_gates']
        assert 'excitation_fault' in rules['required_zero_fields']
        assert 'throughout the armed interval' in rules['window']
        evidence['frozen_zero_rule'] = rules
        evidence['head'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
        paths = [DESIGN, PROBE,
                 REPO / 'src/modules/mc_pos_control/PositionControl/VelocityDiagnosticExcitation.hpp',
                 REPO / 'src/modules/mc_pos_control/MulticopterPositionControl.cpp']
        evidence['sha256'] = {str(p.relative_to(REPO)): digest(p) for p in paths}
        rc, _ = run('compile', ['g++', '-std=c++14', '-Wall', '-Wextra', '-Werror',
                               '-I' + str(REPO / 'src/modules/mc_pos_control/PositionControl'),
                               str(PROBE), '-o', str(out / 'excitation_landing_audit')])
        if rc:
            raise RuntimeError('Probe compile failed, no compatibility conclusion')
        rc, output = run('probe', [str(out / 'excitation_landing_audit')])
        match = re.search(r'SUMMARY tests=(\d+) passed=(\d+) failed=(\d+)', output)
        if not match:
            raise RuntimeError('Missing nonzero probe result')
        evidence['tests'], evidence['passed'], evidence['failed'] = map(int, match.groups())
        assert evidence['tests'] == 6
        evidence['compatible'] = rc == 0 and evidence['failed'] == 0
        print(output, end='')
        print('Protocol compatible:', evidence['compatible'], flush=True)
        return 0 if evidence['compatible'] else 1
    finally:
        save()


if __name__ == '__main__':
    raise SystemExit(main())
