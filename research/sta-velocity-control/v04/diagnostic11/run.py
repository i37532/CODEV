#!/usr/bin/env python3
"""One PID attempt, no automatic retry; full inherited safety checks."""
import argparse
import json
from pathlib import Path
import shutil
import socket
import sys
from common import CONFIG, REPO, load_protocol, fresh_seeds, require_authorization
from run_v00 import ROOTFS, git, save, digest, active_simulators, persisted_bson, encode_bson, check_parameters
from run_v04_protocol10 import Checks as CurrentChecks
from run_v04_protocol04 import Checks as ModelBuilder
from v04_logcheck07 import validate_receiver_profile
from flight import main as flight


class Checks(CurrentChecks):
    def prepare_environment(self, output):
        save(output / 'authorization.json', require_authorization(self.authorization_token, load_protocol()))
        return ModelBuilder.prepare_environment(self, output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--source-head', required=True)
    parser.add_argument('--authorization', default='')
    args = parser.parse_args(); p = load_protocol(); job = p['jobs'][0]
    print(json.dumps(dict(job=job, budget=1, diagnostic_only=True), indent=2), flush=True)
    if not args.execute:
        print('DRY RUN: no process, output directory or parameter changes'); return
    authorization = require_authorization(args.authorization, p)
    if git('branch', '--show-current') != 'research/sta-velocity-control' or git('rev-parse', 'HEAD') != args.source_head:
        raise RuntimeError('Wrong branch/HEAD')
    if git('status', '--porcelain') or git('submodule', 'foreach', '--recursive', '--quiet', 'git status --porcelain'):
        raise RuntimeError('Dirty source')
    if any(s[:1] in ('+', '-', 'U') for s in git('submodule', 'status', '--recursive').splitlines()):
        raise RuntimeError('Submodule mismatch')
    if active_simulators(): raise RuntimeError('Conflicting simulator')
    if shutil.disk_usage(ROOTFS).free < 10 * 1024**3: raise RuntimeError('Insufficient disk')
    if (ROOTFS / 'etc/logging/logger_topics.txt').exists(): raise RuntimeError('Custom logger overrides profiles')
    if any((REPO / 'Tools/sitl_gazebo/models/iris').glob('*-gen.sdf')): raise RuntimeError('Unexpected model override')
    audit = fresh_seeds()
    if not audit['accepted']: raise RuntimeError('Seed history changed')
    frozen = json.loads((CONFIG / 'frozen.json').read_text())
    for name, expected in frozen['assets'].items():
        if digest(REPO / name) != expected: raise RuntimeError('Frozen source changed: ' + name)
    for port in (14550, 11345):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM if port == 14550 else socket.SOCK_STREAM) as sock:
            sock.bind(('127.0.0.1', port))
    validate_receiver_profile()
    plugins = Path(p['plugins'])
    for path, expected in json.loads((plugins / 'manifest.json').read_text()).items():
        if digest(Path(path)) != expected: raise RuntimeError('Plugin dependency changed')
    if args.source_head not in (REPO / 'build/px4_sitl_default/src/lib/version/build_git_version.h').read_text():
        raise RuntimeError('Firmware not built on frozen source')
    out = Path(p['diagnostic']['new_run_root'])
    if out.exists(): raise RuntimeError('Attempt budget already consumed or directory occupied')
    param = ROOTFS / 'eeprom/parameters_10016'; original = param.read_bytes()
    values = persisted_bson(original)
    defaults = json.loads((REPO / 'build/px4_sitl_default/parameters.json').read_text())['parameters']
    check_parameters({**{x['name']: x['default'] for x in defaults}, **values}, frozen['control_parameters'])
    profile = int(values.get('SDLOG_PROFILE', 131)) | 16 | p['diagnostic']['logging_bit']
    overrides = {**p['startup_overrides'], **job['parameters'], 'SDLOG_PROFILE': profile}
    expected = {**frozen['control_parameters'], **overrides, 'SYS_AUTOSTART': 10016}
    out.mkdir(parents=True, exist_ok=False)
    (out / 'original_parameters.bson').write_bytes(original)
    save(out / 'authorization.json', authorization); save(out / 'seed_audit_before_launch.json', audit)
    ledger = dict(planned=1, attempts=1, job=job, source_head=args.source_head, success=False,
        formal_acceptance=False, firmware_sha256=digest(REPO / 'build/px4_sitl_default/bin/px4'),
        original_parameter_sha256=digest(param), applied_profile=profile)
    save(out / 'ledger.json', ledger)
    old_argv = sys.argv
    try:
        param.write_bytes(encode_bson({**values, **overrides}, {x['name']: x['type'] for x in defaults}))
        checks = Checks(p, expected, job, plugins)
        checks.execution_permitted = True; checks.authorization_token = args.authorization
        sys.argv = [__file__, '--output', str(out / 'run01')]
        flight(checks=checks, scenario_path=CONFIG / 'execution.json')
        if digest(REPO / 'build/px4_sitl_default/bin/px4') != ledger['firmware_sha256']:
            raise RuntimeError('Firmware changed during attempt')
        ledger['success'] = True  # Runtime task only. Still not formal V04 acceptance.
    except BaseException as exc:
        ledger['error'] = repr(exc); raise
    finally:
        sys.argv = old_argv
        if not active_simulators(): param.write_bytes(original)
        ledger['parameter_restore_exact'] = param.read_bytes() == original
        ledger['remaining_simulators'] = active_simulators(); save(out / 'ledger.json', ledger)
    if not ledger['parameter_restore_exact'] or ledger['remaining_simulators']:
        raise RuntimeError('Cleanup failed')


if __name__ == '__main__':
    main()
