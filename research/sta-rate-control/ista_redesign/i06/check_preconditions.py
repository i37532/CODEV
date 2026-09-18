#!/usr/bin/env python3
"""Reproduce the I06 dependency audit without starting SITL."""
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


audit = json.loads((HERE / 'PRECONDITION_AUDIT.json').read_text())
summary = json.loads((HERE.parent / 'i05/results/A/summary.json').read_text())
protection = (REPO / 'src/modules/mc_rate_control/StaRateControl/StaProtection.cpp').read_text()
application = (REPO / 'src/modules/mc_rate_control/StaRateControl/StaAxesApplication.hpp').read_text()

checks = {
    'branch': git('branch', '--show-current') == audit['branch'],
    'audited_head_is_ancestor': subprocess.run(
        ['git', 'merge-base', '--is-ancestor', audit['audited_head'], 'HEAD'], cwd=REPO
    ).returncode == 0,
    'production_tree_unchanged': subprocess.run(
        ['git', 'diff', '--quiet', '--', 'src', 'msg', 'boards', 'ROMFS', 'sitl'], cwd=REPO
    ).returncode == 0,
    'i05_gate_failed': summary['success'] is False,
    'i05_attempts_retained': summary['attempted'] == 6 and summary['accepted'] == 6,
    'i05_violation_retained': summary['violations'] == ['6301:pitch_only:1'],
    'proper_axes7_rejected_by_config': '(c.mode == 3 && c.axes != 1 && c.axes != 3)' in protection,
    'proper_axes7_rejected_by_application':
        'c.mode == 3 && (c.axes == 1 || c.axes == 3)' in application,
}
for name, passed in checks.items():
    require(passed, name)
print(json.dumps({'success': True, 'checks': checks, 'status': 'blocked'}, indent=2))
