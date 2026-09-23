"""New immutable asset/seed snapshot. No simulator or parameter mutation."""
import hashlib
import json
import subprocess
from check_v04_protocol02 import seed_audit
from v04_protocol08 import REPO, CONFIG


def fresh_seeds():
    result = seed_audit([9701, 9702, 9703])
    allowed = {str(CONFIG/'execution.json'), str(CONFIG/'seed_audit.json')}
    result['design_registrations'] = [m for m in result['matches'] if m['path'] in allowed]
    result['matches'] = [m for m in result['matches'] if m['path'] not in allowed]
    result['accepted'] = not result['matches'] and not result['invalid_json']
    return result


def capture():
    prior = json.loads((CONFIG.parent/'protocol07/frozen.json').read_text())
    names = set(prior['assets'])
    names.add('research/sta-velocity-control/v04/handoff06/protocol.json')
    names.add('research/sta-velocity-control/v04/handoff06/ProjectionWireProbe.cpp')
    names.update('research/sta-velocity-control/v04/logcheck07/'+n for n in ('protocol.json','receiver_profile.json','ReceiverCoordinateProbe.cpp'))
    names.add('src/modules/mavlink/mavlink_receiver.cpp')
    names.update(str(p.relative_to(REPO)) for p in (REPO/'research/sta-velocity-control/scripts').glob('*.py'))
    names.update(str((CONFIG/p).relative_to(REPO)) for p in ('execution.json', 'pid/frozen.json', 'esta/frozen.json'))
    # Freeze the actual repaired Simulator -> FIFO -> VehicleIMU -> EKF chain,
    # not just the previous controller/logger assets.
    for directory in ('src/modules/simulator', 'src/lib/drivers/accelerometer',
                      'src/modules/sensors/vehicle_imu', 'src/modules/ekf2'):
        names.update(str(p.relative_to(REPO)) for p in (REPO/directory).rglob('*') if p.is_file())
    names.update('msg/'+n+'.msg' for n in ('sensor_accel', 'sensor_accel_fifo',
        'vehicle_imu', 'vehicle_imu_status', 'estimator_selector_status'))
    names.add('research/sta-velocity-control/v04/imu0_repair01/ImuConversionRepairTest.cpp')
    names.add('research/sta-velocity-control/v04/imu0_chain01/ImuConversionChainTest.cpp')
    return dict(kind='protocol08 exact assets; clean execution SHA/firmware recorded at launch',
                parent_head=subprocess.check_output(['git','rev-parse','HEAD'], cwd=REPO, text=True).strip(),
                assets={n:hashlib.sha256((REPO/n).read_bytes()).hexdigest() for n in sorted(names)},
                control_parameters=prior['control_parameters'],
                submodules=subprocess.check_output(['git','submodule','status','--recursive'], cwd=REPO, text=True).splitlines())


if __name__ == '__main__':
    print(json.dumps(dict(frozen=capture(), seed_audit=fresh_seeds()), indent=2))
