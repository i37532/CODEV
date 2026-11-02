#!/usr/bin/env python3
"""Explicit custom ROS 2/MAVLink bridge for the frozen local SITL experiment.

This is not MAVROS. Two rclpy nodes exchange std_msgs/String JSON on an
isolated localhost ROS domain. Only the subscriber sends position targets;
neither node arms, changes mode, starts a simulator, or sends a GCS heartbeat.
Without --execute this program validates configuration and exits without
importing ROS/MAVLink, opening a socket, or publishing a message.
"""

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import socket
import struct
import sys
import time
import xml.etree.ElementTree as ET

from task_contract import Phase, SETPOINT_HZ, make_target, validate_origin, validate_target


TARGET_TOPIC = '/codev_offboard/target'
TELEMETRY_TOPIC = '/codev_offboard/telemetry'
BIND = ('127.0.0.1', 14540)
PEER = ('127.0.0.1', 14580)
SOURCE_SYSTEM = 245
SOURCE_COMPONENT = 191
MAX_AGE_S = 0.5
FUTURE_PHASE_TOLERANCE_US = 100000
MAX_WALL_S = 900.0
CONTROL_FIELDS = {'generation', 'phase', 'start_us', 'origin', 'enabled'}
ENVELOPE_FIELDS = {'seq', 'generation', 'phase', 'sim_us', 'wall_stamp', 'elapsed_s', 'target'}
TELEMETRY_FIELDS = {'time_boot_ms', 'sim_us', 'wall_stamp', 'x', 'y', 'z', 'vx', 'vy', 'vz'}


def strict_json_loads(value):
    def bad_constant(text):
        raise ValueError('Nonfinite JSON constant: ' + text)

    def unique_object(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = item
        return result

    return json.loads(value, parse_constant=bad_constant, object_pairs_hook=unique_object)


def canonical_json(value):
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(',', ':'))


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(name + ' must be an integer >= ' + str(minimum))
    return value


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name + ' must be finite')
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(name + ' must be finite') from exc
    if not math.isfinite(result):
        raise ValueError(name + ' must be finite')
    return result


def check_age(stamp, now, maximum=MAX_AGE_S):
    age = finite(now, 'now') - finite(stamp, 'wall_stamp')
    if age < -0.001 or age > maximum:
        raise ValueError('Stale or future wall stamp: ' + str(age))
    return max(0.0, age)


def validate_control(value):
    if not isinstance(value, dict) or set(value) != CONTROL_FIELDS:
        raise ValueError('Unexpected control fields')
    integer(value['generation'], 'generation')
    integer(value['start_us'], 'start_us')
    if value['phase'] not in tuple(phase.value for phase in Phase):
        raise ValueError('Unknown control phase')
    if type(value['enabled']) is not bool:
        raise ValueError('enabled must be boolean')
    if not isinstance(value['origin'], dict) or set(value['origin']) != {'x', 'y', 'z', 'heading'}:
        raise ValueError('Unexpected origin fields')
    return dict(value, origin=validate_origin(value['origin']))


class ControlReader:
    """Absence before the first write is normal; malformed existing data is fatal."""

    def __init__(self, path):
        self.path = Path(path)
        self.last = None

    def read(self):
        try:
            raw = self.path.read_text(encoding='utf-8')
        except FileNotFoundError:
            if self.last is not None:
                raise ValueError('Control file disappeared after initialization')
            return None
        value = validate_control(strict_json_loads(raw))
        if self.last is not None:
            if value['generation'] < self.last['generation']:
                raise ValueError('Control generation regressed')
            if value['generation'] == self.last['generation'] and value != self.last:
                raise ValueError('Control mutated without a new generation')
        self.last = value
        return value


def validate_telemetry(value, now, previous_sim_us=None):
    if not isinstance(value, dict) or set(value) != TELEMETRY_FIELDS:
        raise ValueError('Unexpected telemetry fields')
    integer(value['time_boot_ms'], 'time_boot_ms')
    integer(value['sim_us'], 'sim_us')
    if value['time_boot_ms'] > 0xffffffff or value['sim_us'] != value['time_boot_ms'] * 1000:
        raise ValueError('Invalid native simulation timestamp')
    if previous_sim_us is not None and value['sim_us'] < previous_sim_us:
        raise ValueError('Native sample time regressed')
    check_age(value['wall_stamp'], now)
    for key in ('x', 'y', 'z', 'vx', 'vy', 'vz'):
        finite(value[key], key)
    return dict(value)


def elapsed_from_native(control, sim_us):
    delta = integer(sim_us, 'sim_us') - control['start_us']
    if delta < -FUTURE_PHASE_TOLERANCE_US:
        raise ValueError('Phase starts too far ahead of native telemetry')
    return max(0.0, delta / 1000000.0)


class NativeClockGuard:
    """Fresh duplicate packets are allowed briefly, but cannot hide a frozen clock."""

    def __init__(self):
        self.last_sim_us = None
        self.last_advance_wall = None

    def observe(self, sim_us, monotonic_now):
        integer(sim_us, 'sim_us')
        now = finite(monotonic_now, 'monotonic_now')
        if self.last_sim_us is not None and sim_us < self.last_sim_us:
            raise ValueError('Native clock regressed')
        if self.last_sim_us is None or sim_us > self.last_sim_us:
            self.last_sim_us = sim_us
            self.last_advance_wall = now

    def age(self, monotonic_now):
        if self.last_advance_wall is None:
            return None
        return max(0.0, finite(monotonic_now, 'monotonic_now') - self.last_advance_wall)

    def check(self, monotonic_now, enabled):
        age = self.age(monotonic_now)
        if enabled and age is not None and age > MAX_AGE_S:
            raise ValueError('Native simulation clock has not advanced for 0.5 wall seconds')
        return age


def make_envelope(control, telemetry, seq, now):
    control = validate_control(control)
    if not control['enabled']:
        raise ValueError('Cannot create targets while disabled')
    telemetry = validate_telemetry(telemetry, now)
    elapsed = elapsed_from_native(control, telemetry['sim_us'])
    return {'seq': integer(seq, 'seq', 1), 'generation': control['generation'],
            'phase': control['phase'], 'sim_us': telemetry['sim_us'],
            'wall_stamp': finite(now, 'now'), 'elapsed_s': elapsed,
            'target': make_target(control['phase'], elapsed, control['origin'])}


class TargetGuard:
    """Reject bad data and safely drain already queued older generations."""

    def __init__(self):
        self.last_seq = 0
        self.last_sim_us = None
        self.last_generation = None
        self.rejected_stale_generation = 0
        self.rejected_disabled = 0

    def accept(self, value, control, now):
        if not isinstance(value, dict) or set(value) != ENVELOPE_FIELDS:
            raise ValueError('Unexpected ROS target envelope fields')
        integer(value['seq'], 'seq', 1)
        integer(value['generation'], 'generation')
        integer(value['sim_us'], 'sim_us')
        if value['sim_us'] % 1000:
            raise ValueError('Target time is not a native millisecond sample')
        if value['seq'] <= self.last_seq:
            raise ValueError('Duplicate or regressing ROS sequence')
        if self.last_sim_us is not None and value['sim_us'] < self.last_sim_us:
            raise ValueError('Target simulation time regressed')
        if self.last_generation is not None and value['generation'] < self.last_generation:
            raise ValueError('Target generation regressed within the ROS stream')
        if value['phase'] not in tuple(phase.value for phase in Phase):
            raise ValueError('Unknown target phase')
        elapsed = finite(value['elapsed_s'], 'elapsed_s')
        if elapsed < 0:
            raise ValueError('Negative phase elapsed time')
        check_age(value['wall_stamp'], now)
        target = validate_target(value['target'])
        if (value['phase'] == 'velocity') != (target['kind'] == 'z_velocity'):
            raise ValueError('Target kind disagrees with phase')
        control = validate_control(control)
        if value['generation'] > control['generation']:
            raise ValueError('Target generation is ahead of control')
        self.last_seq = value['seq']
        self.last_sim_us = value['sim_us']
        self.last_generation = value['generation']
        if value['generation'] < control['generation']:
            self.rejected_stale_generation += 1
            return False
        if value['phase'] != control['phase']:
            raise ValueError('Target phase disagrees with control')
        expected_elapsed = elapsed_from_native(control, value['sim_us'])
        if elapsed != expected_elapsed:
            raise ValueError('Target elapsed time disagrees with native clock')
        expected_target = make_target(control['phase'], elapsed, control['origin'])
        if target != expected_target:
            raise ValueError('ROS target differs from the frozen task contract')
        if not control['enabled']:
            self.rejected_disabled += 1
            return False
        return True


def float32(value):
    return struct.unpack('<f', struct.pack('<f', finite(value, 'wire float')))[0]


def wire_fields(target, sim_us):
    target = validate_target(target)
    integer(sim_us, 'sim_us')
    fields = {'time_boot_ms': (sim_us // 1000) & 0xffffffff,
              'target_system': 1, 'target_component': 1, 'coordinate_frame': 1,
              'type_mask': target['type_mask']}
    for key in ('x', 'y', 'z', 'vx', 'vy', 'vz', 'yaw'):
        fields[key] = float32(target[key])
    fields.update(afx=0.0, afy=0.0, afz=0.0, yaw_rate=0.0)
    return fields


def check_peer(address):
    if address != PEER:
        raise ValueError('Unexpected UDP peer: ' + repr(address))


def check_native_source(system, component):
    if (system, component) != (1, 1):
        raise ValueError('Native telemetry must originate from system 1 component 1')


def forwarded_runner_heartbeat(kind, system, component, vehicle_type):
    """PX4 -f forwards the known runner GCS; it is NOT native vehicle evidence."""
    return kind == 'HEARTBEAT' and (system, component, vehicle_type) == (255, 190, 6)


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp.' + str(os.getpid()))
    with temporary.open('w', encoding='utf-8') as stream:
        stream.write(canonical_json(value) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


def append_json(stream, value):
    stream.write(canonical_json(value) + '\n')
    stream.flush()


def assert_isolated_environment():
    if os.environ.get('ROS_DOMAIN_ID') != '42' or os.environ.get('ROS_LOCALHOST_ONLY') != '1':
        raise ValueError('Execute requires explicit ROS_DOMAIN_ID=42 and ROS_LOCALHOST_ONLY=1')


def package_version(name, module=None):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        # ROS distributions commonly expose package.xml, not Python metadata.
        prefixes = [Path(value) for value in os.environ.get('AMENT_PREFIX_PATH', '').split(os.pathsep) if value]
        if getattr(module, '__file__', None):
            prefixes.extend(Path(module.__file__).resolve().parents)
        for prefix in prefixes:
            manifest = prefix / 'share' / name / 'package.xml'
            if manifest.is_file():
                return ET.parse(str(manifest)).getroot().findtext('version', 'unavailable')
        return getattr(module, '__version__', 'unavailable')


def execute(control_path, output, receipt):
    # Runtime-only imports keep validation and unit tests independent of ROS.
    assert_isolated_environment()
    import rclpy
    from rclpy.clock import Clock, ClockType
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
    import std_msgs
    from std_msgs.msg import String
    import pymavlink
    from pymavlink.dialects.v20 import common as mavlink

    receipt['ros_versions'] = {'rclpy': package_version('rclpy', rclpy),
                               'std_msgs': package_version('std_msgs', std_msgs),
                               'pymavlink': package_version('pymavlink', pymavlink),
                               'ros_distro': os.environ.get('ROS_DISTRO', 'unavailable'),
                               'python': sys.version.split()[0]}
    reader = ControlReader(control_path)
    guard = TargetGuard()
    wire_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    executor = None
    nodes = []
    published_log = sent_log = None
    try:
        wire_socket.bind(BIND)
        wire_socket.setblocking(False)
        published_log = (output / 'ros_published.jsonl').open('x', encoding='utf-8')
        sent_log = (output / 'sent.jsonl').open('x', encoding='utf-8')
        rx = mavlink.MAVLink(None)
        tx = mavlink.MAVLink(None, srcSystem=SOURCE_SYSTEM, srcComponent=SOURCE_COMPONENT)
        rx.robust_parsing = False
        rclpy.init(args=[])
        executor = SingleThreadedExecutor()
        qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=10,
                         reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.VOLATILE)
        steady_clock = Clock(clock_type=ClockType.STEADY_TIME)

        class BridgeNode(Node):
            def __init__(self):
                super().__init__('codev_offboard_mavlink_bridge', use_global_arguments=False)
                self.telemetry_publisher = self.create_publisher(String, TELEMETRY_TOPIC, qos)
                self.target_subscription = self.create_subscription(String, TARGET_TOPIC, self.on_target, qos)
                self.create_timer(0.005, self.poll_native, clock=steady_clock)
                self.create_timer(1.0, self.heartbeat, clock=steady_clock)
                self.create_timer(0.1, self.write_receipt, clock=steady_clock)
                self.latest_native = None
                self.heartbeat_wall = None
                self.native_count = 0
                self.heartbeat_count = 0
                self.forwarded_runner_heartbeat_count = 0
                self.sent_count = 0
                self.last_sent = None
                self.native_clock = NativeClockGuard()

            def graph(self):
                pubs = self.count_publishers(TARGET_TOPIC)
                subs = self.count_subscribers(TARGET_TOPIC)
                if pubs > 1:
                    raise ValueError('More than one ROS target publisher')
                if self.count_publishers(TELEMETRY_TOPIC) > 1:
                    raise ValueError('More than one ROS native telemetry publisher')
                return pubs, subs

            def packet(self, message):
                packet = message.pack(tx)
                tx.seq = (tx.seq + 1) % 256
                return packet

            def heartbeat(self):
                self.graph()
                message = mavlink.MAVLink_heartbeat_message(
                    mavlink.MAV_TYPE_ONBOARD_CONTROLLER, mavlink.MAV_AUTOPILOT_INVALID,
                    0, 0, mavlink.MAV_STATE_ACTIVE, 3)
                packet = self.packet(message)
                if wire_socket.sendto(packet, PEER) != len(packet):
                    raise RuntimeError('Incomplete UDP heartbeat transmission')

            def poll_native(self):
                for unused in range(256):
                    try:
                        data, address = wire_socket.recvfrom(65535)
                    except BlockingIOError:
                        break
                    check_peer(address)
                    messages = rx.parse_buffer(data) or []
                    for message in messages:
                        kind = message.get_type()
                        if kind not in ('HEARTBEAT', 'LOCAL_POSITION_NED'):
                            continue
                        if forwarded_runner_heartbeat(kind, message.get_srcSystem(), message.get_srcComponent(),
                                                      getattr(message, 'type', None)):
                            self.forwarded_runner_heartbeat_count += 1
                            continue
                        check_native_source(message.get_srcSystem(), message.get_srcComponent())
                        now = time.time()
                        if kind == 'HEARTBEAT':
                            self.heartbeat_wall = now
                            self.heartbeat_count += 1
                            continue
                        value = {'time_boot_ms': int(message.time_boot_ms),
                                 'sim_us': int(message.time_boot_ms) * 1000, 'wall_stamp': now}
                        for key in ('x', 'y', 'z', 'vx', 'vy', 'vz'):
                            value[key] = float(getattr(message, key))
                        previous = None if self.latest_native is None else self.latest_native['sim_us']
                        self.latest_native = validate_telemetry(value, now, previous)
                        self.native_clock.observe(value['sim_us'], time.monotonic())
                        self.native_count += 1
                        ros_message = String()
                        ros_message.data = canonical_json(value)
                        self.telemetry_publisher.publish(ros_message)

            def on_target(self, message):
                self.graph()
                control = reader.read()
                if control is None:
                    raise ValueError('Target arrived before control initialization')
                now = time.time()
                value = strict_json_loads(message.data)
                if not guard.accept(value, control, now):
                    return
                self.native_clock.check(time.monotonic(), control['enabled'])
                if self.latest_native is None or self.heartbeat_wall is None:
                    raise ValueError('Target arrived before native telemetry and heartbeat')
                check_age(self.latest_native['wall_stamp'], now)
                check_age(self.heartbeat_wall, now, maximum=3.0)
                if value['sim_us'] > self.latest_native['sim_us']:
                    raise ValueError('Target references an unseen native sample')
                if self.latest_native['sim_us'] - value['sim_us'] > 500000:
                    raise ValueError('Target native sample is more than 0.5 simulation seconds old')
                fields = wire_fields(value['target'], value['sim_us'])
                packet = self.packet(mavlink.MAVLink_set_position_target_local_ned_message(**fields))
                # Decode the exact packet to prove ROS payload -> float32 wire identity.
                decoded = mavlink.MAVLink(None).parse_char(packet)
                if decoded is None or decoded.get_type() != 'SET_POSITION_TARGET_LOCAL_NED':
                    raise RuntimeError('Cannot independently decode outgoing target')
                if decoded.get_srcSystem() != SOURCE_SYSTEM or decoded.get_srcComponent() != SOURCE_COMPONENT:
                    raise RuntimeError('Unexpected MAVLink source in outgoing target')
                actual = {key: getattr(decoded, key) for key in fields}
                if actual != fields:
                    raise RuntimeError('ROS payload and MAVLink wire fields differ')
                if wire_socket.sendto(packet, PEER) != len(packet):
                    raise RuntimeError('Incomplete UDP target transmission')
                self.sent_count += 1
                self.last_sent = value
                append_json(sent_log, dict(value, ros_sha256=hashlib.sha256(message.data.encode('utf-8')).hexdigest(),
                                           wire_fields=actual, wire_hex=packet.hex(), identity_verified=True,
                                           sent_wall_stamp=now, peer=list(PEER), source_system=SOURCE_SYSTEM,
                                           source_component=SOURCE_COMPONENT))

            def write_receipt(self):
                pubs, subs = self.graph()
                control = reader.read()
                now = time.time()
                age = None if self.latest_native is None else max(0.0, now - self.latest_native['wall_stamp'])
                receipt.update(sent_count=self.sent_count,
                               last_sent_sim_us=None if self.last_sent is None else self.last_sent['sim_us'],
                               last_sent_seq=None if self.last_sent is None else self.last_sent['seq'],
                               last_sent_phase=None if self.last_sent is None else self.last_sent['phase'],
                               last_sent_generation=None if self.last_sent is None else self.last_sent['generation'],
                               phase=None if control is None else control['phase'],
                               generation=None if control is None else control['generation'],
                               enabled=False if control is None else control['enabled'],
                               publisher_count=pubs, subscriber_count=subs, telemetry_age=age,
                               native_clock_age=self.native_clock.age(time.monotonic()),
                               latest_native_sim_us=None if self.latest_native is None else self.latest_native['sim_us'],
                               telemetry_count=self.native_count, native_heartbeat_count=self.heartbeat_count,
                               forwarded_runner_heartbeat_count=self.forwarded_runner_heartbeat_count,
                               rejected_stale_generation=guard.rejected_stale_generation,
                               rejected_disabled=guard.rejected_disabled, wall_stamp=now)
                atomic_json(output / 'receipt.json', receipt)

        bridge = BridgeNode()
        nodes.append(bridge)

        class MissionNode(Node):
            def __init__(self):
                super().__init__('codev_offboard_mission_publisher', use_global_arguments=False)
                self.target_publisher = self.create_publisher(String, TARGET_TOPIC, qos)
                self.telemetry_subscription = self.create_subscription(String, TELEMETRY_TOPIC, self.on_telemetry, qos)
                self.create_timer(1.0 / SETPOINT_HZ, self.tick, clock=steady_clock)
                self.telemetry = None
                self.seq = 0

            def on_telemetry(self, message):
                previous = None if self.telemetry is None else self.telemetry['sim_us']
                self.telemetry = validate_telemetry(strict_json_loads(message.data), time.time(), previous)

            def tick(self):
                pubs, subs = bridge.graph()
                control = reader.read()
                if control is None or not control['enabled'] or self.telemetry is None:
                    return
                bridge.native_clock.check(time.monotonic(), control['enabled'])
                if bridge.heartbeat_wall is None or pubs != 1 or subs < 1:
                    return
                now = time.time()
                check_age(bridge.heartbeat_wall, now, maximum=3.0)
                self.seq += 1
                value = make_envelope(control, self.telemetry, self.seq, now)
                message = String()
                message.data = canonical_json(value)
                self.target_publisher.publish(message)
                append_json(published_log, dict(value, ros_sha256=hashlib.sha256(message.data.encode('utf-8')).hexdigest()))
                receipt['published_count'] = self.seq

        mission = MissionNode()
        nodes.append(mission)
        for node in nodes:
            executor.add_node(node)
        started = time.monotonic()
        receipt['status'] = 'running'
        bridge.write_receipt()
        while rclpy.ok():
            if time.monotonic() - started > MAX_WALL_S:
                raise TimeoutError('Bridge exceeded its 900 second wall limit')
            executor.spin_once(timeout_sec=0.05)
        raise RuntimeError('ROS context shut down unexpectedly')
    finally:
        if executor is not None:
            executor.shutdown(timeout_sec=1.0)
        for node in reversed(nodes):
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        wire_socket.close()
        for stream in (published_log, sent_log):
            if stream is not None:
                stream.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--execute', action='store_true', help='Enable actual ROS and local MAVLink traffic')
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    # Refusal is outside attempt error handling: preserve previous evidence byte for byte.
    for name in ('ros_published.jsonl', 'sent.jsonl', 'fatal.json', 'receipt.json'):
        if (args.output / name).exists():
            print('Refusing existing experiment evidence: ' + name, file=sys.stderr)
            return 1
    receipt = {'dry_run': not args.execute, 'status': 'initializing', 'sent_count': 0,
               'published_count': 0, 'last_sent_sim_us': None, 'phase': None, 'generation': None,
               'publisher_count': 0, 'subscriber_count': 0, 'telemetry_age': None,
               'ros_versions': {}, 'target_topic': TARGET_TOPIC, 'telemetry_topic': TELEMETRY_TOPIC,
               'bind': list(BIND), 'peer': list(PEER), 'source_system': SOURCE_SYSTEM,
               'source_component': SOURCE_COMPONENT, 'wall_stamp': time.time()}
    try:
        initial = ControlReader(args.control).read()
        if initial is not None:
            receipt.update(phase=initial['phase'], generation=initial['generation'])
        if not args.execute:
            receipt['status'] = 'dry_run_validated'
            atomic_json(args.output / 'receipt.json', receipt)
            print(canonical_json(receipt))
            return 0
        atomic_json(args.output / 'receipt.json', receipt)
        execute(args.control, args.output, receipt)
        return 0
    except BaseException as exc:
        receipt.update(status='fatal', error_type=type(exc).__name__, error=str(exc), wall_stamp=time.time())
        atomic_json(args.output / 'fatal.json', receipt)
        atomic_json(args.output / 'receipt.json', receipt)
        print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
