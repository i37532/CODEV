"""Capture a new immutable research snapshot; no flight/parameter mutation."""
import json
from common import CONFIG, REPO, fingerprint, fresh_seeds
from capture_v04_protocol10 import capture as inherited_capture


def capture():
    for mode in ('pid', 'esta'):
        data = json.loads((CONFIG.parent / 'protocol10' / mode / 'frozen.json').read_text())
        data['control_parameters']['MPC_Z_VEL_MAX_DN'] = .55
        data['control_parameters']['MPC_LAND_SPEED'] = .6
        (CONFIG / mode).mkdir(exist_ok=True)
        (CONFIG / mode / 'frozen.json').write_text(json.dumps(data, indent=2) + '\n')
    data = inherited_capture()
    names = set(data['assets'])
    names.update(str(p.relative_to(REPO)) for p in CONFIG.rglob('*')
                 if p.is_file() and p.suffix in ('.py', '.md', '.json')
                 and p not in (CONFIG / 'frozen.json', CONFIG / 'seed_audit.json'))
    names.update(('src/modules/mc_pos_control/VelocityModuleTest.cpp',
                  'src/modules/logger/logged_topics.cpp', 'src/modules/logger/logged_topics.h',
                  'src/modules/logger/params.c', 'src/modules/logger/EstimatorDiagnosticTopicsTest.cpp',
                  'src/modules/logger/CMakeLists.txt'))
    for directory in ('src/modules/land_detector', 'src/modules/flight_mode_manager/tasks/AutoMapper',
                      'src/modules/flight_mode_manager/tasks/AutoLineSmoothVel'):
        names.update(str(p.relative_to(REPO)) for p in (REPO / directory).rglob('*') if p.is_file())
    data['kind'] = 'protocol13 common descent/landing intent consistent; stored baseline restored after each run'
    data['assets'] = {n: fingerprint(REPO / n) for n in sorted(names)}
    # Root parameters check the original EEPROM; mode snapshots check runtime overrides.
    assert data['control_parameters']['MPC_Z_VEL_MAX_DN'] == 1
    audit = fresh_seeds()
    if not audit['accepted']: raise RuntimeError(json.dumps(audit))
    (CONFIG / 'seed_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    (CONFIG / 'frozen.json').write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps(dict(assets=len(names), seed_audit_accepted=True)))


if __name__ == '__main__': capture()
