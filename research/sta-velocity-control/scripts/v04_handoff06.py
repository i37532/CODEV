"""Offline-developed POSCTL -> AUTO_LOITER handoff; no simulator or defaults.

Explicit COMMAND_INT coordinates preserve the existing local XY hold target.
NaN navigator triplets in POSCTL are expected, NOT a source for new coordinates.
"""
import copy
import math
import struct
from v04_heading_stream import data, index, row, replay
from v04_task04 import scalars
from check_v04_protocol02 import target_altitude

RADIUS = 6371000.0  # pinned ECL geo.h, azimuthal equidistant projection
XY_ENCODING_LIMIT_M = .02  # 1e-7 deg rounding <= 7.87mm; engineering margin, not flight error gate


def f32(x):
    try:
        value = struct.unpack('<f', struct.pack('<f', x))[0]
    except (OverflowError, struct.error) as exc:
        raise ValueError('Float32 overflow') from exc
    if not math.isfinite(value):
        raise ValueError('Nonfinite float32')
    return value


def reproject(lat0, lon0, north, east):
    if not all(math.isfinite(x) for x in (lat0, lon0, north, east)):
        raise ValueError('Nonfinite projection input')
    if not -85 <= lat0 <= 85 or not -180 <= lon0 <= 180 or math.hypot(north, east) > 10000:
        raise ValueError('Outside audited local projection domain')
    phi, lam = math.radians(lat0), math.radians(lon0)
    x, y = f32(north)/RADIUS, f32(east)/RADIUS
    c = math.hypot(x, y)
    if c == 0:
        return lat0, lon0
    lat = math.asin(math.cos(c)*math.sin(phi)+x*math.sin(c)*math.cos(phi)/c)
    lon = lam+math.atan2(y*math.sin(c), c*math.cos(phi)*math.cos(c)-x*math.sin(phi)*math.sin(c))
    return math.degrees(lat), (math.degrees(lon)+180) % 360-180


def project(lat0, lon0, lat, lon):
    if not all(math.isfinite(x) for x in (lat0, lon0, lat, lon)):
        raise ValueError('Nonfinite global target')
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError('Invalid global target')
    p0, p, dl = math.radians(lat0), math.radians(lat), math.radians(lon-lon0)
    c = math.acos(max(-1., min(1., math.sin(p0)*math.sin(p)+math.cos(p0)*math.cos(p)*math.cos(dl))))
    k = c/math.sin(c) if c else 1.
    return (f32(k*(math.cos(p0)*math.sin(p)-math.sin(p0)*math.cos(p)*math.cos(dl))*RADIUS),
            f32(k*math.cos(p)*math.sin(dl)*RADIUS))


def capture(log, ref, frozen, now_us, source_us=None):
    """Once-only target provenance, from raw onboard estimates/target, no truth."""
    ev = replay(log, ref, frozen=frozen, end=source_us)
    if not ev['ready']:
        raise ValueError('Heading not admitted')
    p = ev['latest_position']
    t = p['timestamp']
    if not 0 <= now_us-t <= 500000 or t < frozen['timestamp']:
        raise ValueError('Stale/future handoff source')
    status = data(log, 'vehicle_status'); s = row(status, index(status, t, 1200000))
    land = data(log, 'vehicle_land_detected'); l = row(land, index(land, t, 1200000))
    if s['nav_state'] != 2 or s['arming_state'] != 2 or s['failsafe'] or l['landed'] or l['ground_contact']:
        raise ValueError('Handoff needs armed airborne POSCTL')
    target = data(log, 'trajectory_setpoint'); q = row(target, index(target, t, 40000))
    if not all(math.isfinite(q.get(k, math.nan)) for k in ('x', 'y', 'yaw')):
        raise ValueError('Missing finite XY/yaw hold target')
    if not any(math.isfinite(q.get(k, math.nan)) for k in ('z', 'vz', 'acceleration[2]')):
        raise ValueError('No valid vertical target')
    if abs(math.remainder(q['yaw']-frozen['yaw'], 2*math.pi)) > .001:
        raise ValueError('Local hold yaw changed')
    if math.hypot(q['x']-ref['position']['x'], q['y']-ref['position']['y']) > 2:
        raise ValueError('Hold target outside original XY envelope')
    lat, lon = reproject(p['ref_lat'], p['ref_lon'], q['x'], q['y'])
    lat_i, lon_i = round(lat*1e7), round(lon*1e7)
    lat_wire, lon_wire = lat_i/1e7, lon_i/1e7
    xy = project(p['ref_lat'], p['ref_lon'], lat_wire, lon_wire)
    error = math.hypot(xy[0]-q['x'], xy[1]-q['y'])
    if error > XY_ENCODING_LIMIT_M:
        raise ValueError('XY wire precision exceeded')
    z, alt = target_altitude(ref['position']['z'], ref['position']['ref_alt'])
    if z != ref['target_z'] or alt != ref['command_alt']:
        raise ValueError('Height reference changed')
    return dict(source_timestamp=t, source_sample=p['timestamp_sample'], trajectory_timestamp=q['timestamp'],
        source_xy=[q['x'], q['y']], source_z=q.get('z'), source_vz=q.get('vz'),
        reference=copy.deepcopy(ref['position']), yaw_freeze=copy.deepcopy(frozen),
        xy_encoded=list(xy), encoding_error_m=error, lat=lat_wire, lon=lon_wire,
        wire=dict(target_system=1, target_component=1, frame=5, command=192, current=0, autocontinue=0,
                  param1=-1., param2=1., param3=0., param4=f32(frozen['yaw']), x=lat_i, y=lon_i, z=alt))


def send_once(mav, target):
    w = target['wire']
    mav.command_int_send(*(w[k] for k in ('target_system', 'target_component', 'frame', 'command', 'current',
        'autocontinue', 'param1', 'param2', 'param3', 'param4', 'x', 'y', 'z')))


def decode_current(raw):
    import re
    match = re.search(r'\n\s*current\s+position_setpoint_s\b(.*?)(?=\n\s*next\s+position_setpoint_s|\Z)', raw, re.S)
    if not match:
        raise ValueError('Missing current triplet record')
    result = scalars(match[1])
    if 'timestamp' not in result or 'valid' not in result:
        raise ValueError('Incomplete triplet record')
    return result


def matches_target(d, target, cli=False):
    """CLI must match its actual representation; raw ULog checks full precision."""
    w = target['wire']
    expected = dict(lat=target['lat'], lon=target['lon'], alt=w['z'], yaw=w['param4'])
    if cli:
        expected = {k:float(format(v, '.6f' if k in ('lat', 'lon') else '.4f')) for k,v in expected.items()}
    return (d.get('valid') == 1 and d.get('yaw_valid') == 1 and d.get('type') == 2
            and all(math.isfinite(d.get(k, math.nan)) and d[k] == v for k,v in expected.items()))


def local_xy_ok(d, target):
    return all(math.isfinite(d.get(k, math.nan)) and abs(d[k]-target['xy_encoded'][axis]) <= .05
               for axis,k in enumerate(('x','y')))


class Handoff:
    """Single command, asynchronous ACK/target join, bounded pending, no retries."""
    def __init__(self):
        self.target = None
        self.sent = None
        self.sent_us = None
        self.ready = False
        self.ack = None
        self.failed = False
        self.last_wall = None

    def start(self, mav, log, ref, frozen, now_us, wall, on_attempt=None):
        if self.sent is not None or self.failed:
            raise ValueError('Handoff cannot resend/restart')
        if not math.isfinite(wall) or not math.isfinite(now_us):
            self.failed = True
            raise ValueError('Invalid handoff time')
        try:
            self.target = capture(log, ref, frozen, now_us)
        except BaseException:
            self.failed = True
            raise
        # Mark attempt before I/O; an uncertain send must never be retried.
        self.sent, self.sent_us = wall, now_us
        self.last_wall = wall
        try:
            if on_attempt is not None:
                on_attempt(copy.deepcopy(self.target), self.sent, self.sent_us)
            send_once(mav, self.target)
        except BaseException:
            self.failed = True
            raise
        return copy.deepcopy(self.target)

    def poll(self, wall, acknowledgements, raw, nav_state):
        if self.sent is None or self.failed or not math.isfinite(wall) or wall < self.last_wall:
            self.failed = True
            raise ValueError('Invalid handoff lifecycle/clock')
        try:
            self.last_wall = wall
            if not self.ready and wall-self.sent > 5:
                raise ValueError('Handoff ACK/target timeout; no retry')
            fresh = [a for a in acknowledgements if a['system'] == 1 and a['component'] == 1
                     and a['message'].get('command') == 192 and a['received_monotonic'] >= self.sent]
            if len(fresh) > 1:
                raise ValueError('Duplicate handoff ACK')
            if fresh:
                if not math.isfinite(fresh[0]['received_monotonic']) or fresh[0]['received_monotonic'] > wall:
                    raise ValueError('Future/invalid handoff ACK time')
                if fresh[0]['message'].get('result') != 0:
                    raise ValueError('Rejected handoff ACK')
                self.ack = copy.deepcopy(fresh[0])
            current = decode_current(raw)
            matched = (current['timestamp'] >= self.sent_us and nav_state == 4
                       and matches_target(current, self.target, cli=True))
            if self.ready and not matched:
                raise ValueError('Accepted handoff target/mode lost')
            if self.ack is not None and matched:
                self.ready = True
            return self.ready
        except BaseException:
            self.failed = True
            raise
