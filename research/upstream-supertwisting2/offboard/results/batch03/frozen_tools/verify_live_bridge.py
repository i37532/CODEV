#!/usr/bin/env python3
"""Real ROS bridge + synthetic localhost telemetry. NO PX4, simulator or arming."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from ros_bridge import atomic_json, PEER, BIND


def execute(output, launcher):
    from pymavlink.dialects.v20 import common as mavlink
    from run import active_simulators, terminate_owned
    if active_simulators():
        raise ValueError('Loopback test must not run beside PX4/Gazebo/QGC')
    output.mkdir(parents=True, exist_ok=False)
    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.bind(PEER)
    peer.setblocking(False)
    sender = mavlink.MAVLink(None, srcSystem=1, srcComponent=1)
    forwarded_gcs = mavlink.MAVLink(None, srcSystem=255, srcComponent=190)
    decoder = mavlink.MAVLink(None)
    origin = dict(x=0., y=0., z=0., heading=0.)
    started = time.monotonic()
    native = lambda: 100000000 + int((time.monotonic() - started) * 1000) * 1000
    control_path = output / 'control.json'
    atomic_json(control_path, dict(generation=1, phase='prestream', start_us=native(), origin=origin, enabled=True))
    process = None
    counts = dict(position=0, velocity=0, heartbeat=0)
    receipt = dict(scope='synthetic localhost telemetry, real ROS, zero PX4 and zero flights', passed=False)
    log = (output / 'console.log').open('x')
    generation, disabled_at = 1, None
    last_native_send = last_heartbeat = 0.
    target_times = []
    try:
        process = subprocess.Popen([*launcher, str(Path(__file__).with_name('ros_bridge.py')),
            '--control', str(control_path), '--output', str(output / 'ros'), '--execute'],
            env=dict(os.environ, ROS_DOMAIN_ID='42', ROS_LOCALHOST_ONLY='1'),
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise ValueError('Actual ROS bridge exited before test completion')
            now = time.monotonic()
            if now - last_native_send >= .05:
                packet = mavlink.MAVLink_local_position_ned_message(native() // 1000, 0, 0, 0, 0, 0, 0).pack(sender)
                sender.seq = (sender.seq + 1) % 256
                peer.sendto(packet, BIND)
                last_native_send = now
            if now - last_heartbeat >= .5:
                packet = mavlink.MAVLink_heartbeat_message(mavlink.MAV_TYPE_QUADROTOR,
                    mavlink.MAV_AUTOPILOT_PX4, 0, 0, mavlink.MAV_STATE_STANDBY, 3).pack(sender)
                sender.seq = (sender.seq + 1) % 256
                peer.sendto(packet, BIND)
                forwarded_packet = mavlink.MAVLink_heartbeat_message(mavlink.MAV_TYPE_GCS,
                    mavlink.MAV_AUTOPILOT_INVALID, 0, 0, mavlink.MAV_STATE_ACTIVE, 3).pack(forwarded_gcs)
                forwarded_gcs.seq = (forwarded_gcs.seq + 1) % 256
                peer.sendto(forwarded_packet, BIND)
                last_heartbeat = now
            while True:
                try:
                    packet, address = peer.recvfrom(65535)
                except BlockingIOError:
                    break
                if address != BIND:
                    raise ValueError('Unexpected loopback source')
                for message in decoder.parse_buffer(packet) or []:
                    kind = message.get_type()
                    if kind == 'HEARTBEAT':
                        if message.type != mavlink.MAV_TYPE_ONBOARD_CONTROLLER:
                            raise ValueError('Unexpected GCS/vehicle heartbeat')
                        counts['heartbeat'] += 1
                    elif kind == 'SET_POSITION_TARGET_LOCAL_NED':
                        if (message.get_srcSystem(), message.get_srcComponent()) != (245, 191):
                            raise ValueError('Wrong target source identity')
                        if message.type_mask == 2552:
                            counts['position'] += 1
                        elif message.type_mask == 2524 and abs(message.vz + .2) < 1e-6:
                            counts['velocity'] += 1
                        else:
                            raise ValueError('Unexpected target/mask/pulse')
                        target_times.append(now)
                        if disabled_at is not None and now - disabled_at > .2:
                            raise ValueError('Targets continued after disabled queue-drain margin')
                    else:
                        raise ValueError('Unexpected command: ' + kind)
            if generation == 1 and counts['position'] >= 25:
                generation = 2
                atomic_json(control_path, dict(generation=2, phase='velocity', start_us=native(), origin=origin, enabled=True))
            if generation == 2 and counts['velocity'] >= 20:
                generation = 3
                disabled_at = time.monotonic()
                atomic_json(control_path, dict(generation=3, phase='velocity', start_us=native(), origin=origin, enabled=False))
            if disabled_at is not None and now - disabled_at >= 1:
                actual = json.loads((output / 'ros/receipt.json').read_text())
                if actual['publisher_count'] != 1 or actual['sent_count'] < 45:
                    raise ValueError('Actual ROS graph/send evidence absent')
                if actual.get('forwarded_runner_heartbeat_count', 0) < 1:
                    raise ValueError('Forwarded GCS heartbeat path was not tested')
                receipt.update(passed=True, packet_counts=counts, actual_ros_receipt=actual,
                    max_target_gap_s=max(b-a for a,b in zip(target_times, target_times[1:])),
                    elapsed_wall_s=now-started)
                break
            time.sleep(.005)
        else:
            raise TimeoutError('Real ROS/UDP loopback did not complete in25s')
    except BaseException as exc:
        receipt['error'] = repr(exc)
        raise
    finally:
        terminate_owned(process)
        peer.close()
        log.close()
        atomic_json(output / 'verification.json', receipt)
    print(json.dumps(receipt, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--execute-local-loopback', action='store_true')
    args = parser.parse_args()
    if not args.execute_local_loopback:
        print('DRY RUN: zero sockets, ROS, PX4 or arming')
        return 0
    execute(args.output, ['bash', '/home/yr/.local/share/codev-ros-offboard/run-python.sh'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
