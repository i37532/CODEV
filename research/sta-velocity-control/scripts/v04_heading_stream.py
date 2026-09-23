"""Protocol04 raw ULog evidence, shared by live admission and final replay.

Read only. Never interpolates, repairs counters, changes samples or publishes.
An unfinished file is read only through its last complete ULog record.
"""
import io
import math
import struct
from pathlib import Path
import numpy as np
from pyulog import ULog
from v04_heading_policy import classify, freeze_task_yaw

TOPICS = ['vehicle_local_position', 'vehicle_attitude', 'trajectory_setpoint',
          'vehicle_status', 'vehicle_land_detected', 'estimator_selector_status',
          'estimator_status', 'estimator_status_flags', 'estimator_event_flags',
          'sta_velocity_ctrl_status']
REFERENCE = ('ref_timestamp', 'ref_lat', 'ref_lon', 'ref_alt', 'xy_reset_counter',
             'z_reset_counter', 'vxy_reset_counter', 'vz_reset_counter')
FORBIDDEN_EVENTS = ('reset_vel_to_gps', 'reset_vel_to_flow', 'reset_vel_to_vision',
    'reset_vel_to_zero', 'reset_pos_to_last_known', 'reset_pos_to_gps', 'reset_pos_to_vision',
    'starting_vision_yaw_fusion', 'yaw_aligned_to_imu_gps', 'bad_yaw_using_gps_course',
    'emergency_yaw_reset_mag_stopped', 'stopping_mag_use', 'stopping_navigation')


class Pending(ValueError):
    """Only missing future evidence within its bounded preparation deadline."""


def complete_prefix(raw):
    if len(raw) < 16 or raw[:7] != b'ULog\x01\x12\x35':
        raise ValueError('Missing ULog header')
    i = 16
    while i + 3 <= len(raw):
        size, kind = struct.unpack_from('<HB', raw, i)
        if i + 3 + size > len(raw): break
        if kind == ord('O'): raise ValueError('ULog dropout in live evidence')
        i += 3 + size
    return raw[:i]


class LiveLog:
    """Bounded transport, not a substitute for the final complete flight ULog.

    Logger writes >=4096-byte chunks; fsync cadence is not read visibility.
    Lack of a fresh complete prefix stops admission rather than forcing flushes.
    """
    def __init__(self, path):
        self.path = Path(path)
        self.last_size = 0
        self.inode = self.path.stat().st_ino
        self.offset = 0
        self.prefix = bytearray()
        self.ids = {}

    def read(self):
        stat = self.path.stat()
        if stat.st_ino != self.inode or stat.st_size < self.last_size:
            raise ValueError('Live log replaced/truncated')
        if stat.st_size > 128*1024*1024: raise ValueError('Unexpected oversized flight log')
        self.last_size = stat.st_size
        with self.path.open('rb') as source:
            source.seek(self.offset)
            raw = source.read(stat.st_size-self.offset)
        i = 0
        if self.offset == 0:
            if len(raw)<16 or raw[:7]!=b'ULog\x01\x12\x35': raise ValueError('Missing ULog header')
            self.prefix.extend(raw[:16]); i=16
        while i+3<=len(raw):
            size,kind=struct.unpack_from('<HB',raw,i)
            end=i+3+size
            if end>len(raw): break  # retain incomplete bytes in the original file
            if kind==ord('O'): raise ValueError('ULog dropout in live evidence')
            keep=True
            if kind==ord('A'):
                if size<4: raise ValueError('Malformed ULog subscription')
                msg_id=struct.unpack_from('<H',raw,i+4)[0]
                name=raw[i+6:end].decode('utf8')
                self.ids[msg_id]=name
            elif kind==ord('D'):
                if size<2: raise ValueError('Malformed ULog data')
                msg_id=struct.unpack_from('<H',raw,i+3)[0]
                if msg_id not in self.ids: raise ValueError('Unknown ULog message ID')
                keep=self.ids[msg_id] in TOPICS
            if keep: self.prefix.extend(raw[i:end])
            i=end
        self.offset+=i
        log = ULog(io.BytesIO(self.prefix), message_name_filter_list=TOPICS)
        if log.dropouts or log.file_corruption: raise ValueError('ULog dropout/corruption')
        return log


def data(log, name, instance=0):
    d = log.get_dataset(name, instance).data
    t = d['timestamp'].astype(np.int64)
    if not len(t) or np.any(np.diff(t) <= 0): raise ValueError('Empty/nonmonotonic '+name)
    return d


def index(d, t, age=None):
    i = np.searchsorted(d['timestamp'], t, side='right')-1
    if np.any(i < 0): raise ValueError('No preceding evidence')
    if age is not None and np.any(np.asarray(t)-d['timestamp'][i] > age):
        raise ValueError('Stale topic evidence')
    return i


def row(d, i):
    return {k: v[i].item() for k,v in d.items()}


def span(d, start, end):
    first = int(index(d,start))
    return np.arange(first, int(np.searchsorted(d['timestamp'],end,side='right')))


def delta_yaw(d, i):
    w,x,y,z = (float(d[f'delta_q_reset[{j}]'][i]) for j in range(4))
    if not all(math.isfinite(v) for v in (w,x,y,z)) or abs(w*w+x*x+y*y+z*z-1)>.001:
        raise ValueError('Invalid reset quaternion')
    return math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))


def replay(log, ref, end=None, frozen=None, allow_pending=False):
    """Reconstruct from raw streams, not host-provided qualification booleans.

    ref.position is an exact pre-arm ULog sample. Complete intervals are checked
    through end; alignment cannot borrow data published after that watermark.
    frozen is the once-written task_yaw.json, verified against raw samples.
    """
    if log.dropouts: raise ValueError('ULog dropout')
    pos = data(log,'vehicle_local_position'); att = data(log,'vehicle_attitude')
    start = ref['position']['timestamp']
    end = int(pos['timestamp'][-1]) if end is None else int(end)
    if end < start or end > int(pos['timestamp'][-1]): raise ValueError('Invalid replay interval')
    ix = span(pos,start,end); times = pos['timestamp'][ix].astype(np.int64)
    if int(times[0]) != int(start): raise ValueError('Reference is not exact logged sample')
    for k in ('timestamp_sample','x','y','z','heading','heading_reset_counter'):
        if not math.isfinite(ref['position'][k]) or pos[k][ix[0]]!=ref['position'][k]:
            raise ValueError('Reference does not match raw prearm sample '+k)
    for k in REFERENCE:
        if not np.all(np.isfinite(pos[k][ix])) or np.any(pos[k][ix] != ref['position'][k]):
            raise ValueError('Coordinate/reset changed: '+k)
    for k in ('timestamp','timestamp_sample'):
        gaps = np.diff(pos[k][ix].astype(np.int64))
        if len(gaps) and (np.any(gaps<=0) or np.max(gaps)>40000): raise ValueError('Position/sample gap')
    for k in ('xy_valid','z_valid','v_xy_valid','v_z_valid'):
        if not np.all(pos[k][ix]): raise ValueError('Invalid estimate '+k)
    selector = data(log,'estimator_selector_status')
    sj = span(selector,start,end); primary = int(selector['primary_instance'][sj[0]])
    for k in ('primary_instance','instance_changed_count'):
        if np.any(selector[k][sj] != selector[k][sj[0]]): raise ValueError('Primary estimator switch')
    if (not np.all(selector[f'healthy[{primary}]'][sj]) or np.any(selector['gyro_fault_detected'][sj])
            or np.any(selector['accel_fault_detected'][sj])): raise ValueError('Unhealthy primary')
    selidx = index(selector,times,1200000)
    est = data(log,'estimator_status',primary); flags = data(log,'estimator_status_flags',primary)
    ei = index(est,times,500000); fi = index(flags,times,1200000)
    for stream,indices in ((est,span(est,start,end)),(flags,span(flags,start,end))):
        if 'filter_fault_flags' in stream and np.any(stream['filter_fault_flags'][indices]):
            raise ValueError('Filter fault')
        for k in stream:
            if (k.startswith('fs_') or k in ('cs_mag_fault','cs_mag_field_disturbed','cs_ev_yaw','cs_gps_yaw')) and np.any(stream[k][indices]):
                raise ValueError('Forbidden estimator state '+k)
    if not np.all(flags['cs_yaw_align'][fi]): raise ValueError('Yaw not aligned')
    events = data(log,'estimator_event_flags',primary); evix = span(events,start,end)
    # Snapshot before arm is required; an old event isn't replayed as a new event.
    for k in ('information_event_changes','warning_event_changes'):
        increments = np.diff(events[k][evix].astype(np.int64)) % (2**32)
        if np.any(increments>1): raise ValueError('Unobservable event counter interval')
    new = evix[events['timestamp'][evix]>start]
    for k in FORBIDDEN_EVENTS:
        if np.any(events[k][new]): raise ValueError('Forbidden new event '+k)
    status = data(log,'vehicle_status'); land = data(log,'vehicle_land_detected')
    si = index(status,times); li = index(land,times)
    if np.any(status['failsafe'][span(status,start,end)]) or np.any(status['failure_detector_status'][span(status,start,end)]):
        raise ValueError('Vehicle failure')
    diag = data(log,'sta_velocity_ctrl_status'); di = span(diag,start,end)
    if np.any(np.diff(diag['publish_seq'][di].astype(np.int64)) != 1): raise ValueError('Missing diagnostic publication')
    if np.any(np.diff(diag['update_seq'][di].astype(np.int64)) != diag['pid_calls'][di[1:]]):
        raise ValueError('Missing diagnostic update')
    if len(di)>1 and np.max(np.diff(diag['timestamp'][di].astype(np.int64)))>40000:
        raise ValueError('Diagnostic gap')
    consumed=di[(diag['input_timestamp'][di]>=start)&(diag['input_timestamp'][di]<=end)]
    pi=np.searchsorted(pos['timestamp'],diag['input_timestamp'][consumed])
    if np.any(pi>=len(pos['timestamp'])) or not np.array_equal(pos['timestamp'][pi],diag['input_timestamp'][consumed]):
        raise ValueError('Missing consumed local position sample')
    if not np.array_equal(pos['timestamp_sample'][pi],diag['timestamp_sample'][consumed]):
        raise ValueError('Consumed sample clock mismatch')
    active = di[diag['armed'][di].astype(bool)&diag['enabled'][di].astype(bool)]
    for k,v in dict(first_fail=0,retry_result=0,fault=0,failsafe=0,timing=0,valid=1,pid_calls=1,sta_fault=0,
                    inner_mode=0,inner_axes=0,inner_divisor=1,inner_valid=1).items():
        if np.any(diag[k][active]!=v): raise ValueError('Controller '+k)
    resets = ix[1:][np.diff(pos['heading_reset_counter'][ix].astype(int))!=0]
    ai = span(att,start,end)
    qr = ai[1:][np.diff(att['quat_reset_counter'][ai].astype(int))!=0]
    if len(resets)>1 or len(qr)>1: raise ValueError('Repeated heading/quaternion reset')
    result = dict(primary=primary,through_us=end,position_samples=len(ix),confirmed=False,pending=False,
                  quiet_s=0.,ready=False,latest_position=row(pos,ix[-1]))
    if not len(resets):
        if len(qr) and end-int(att['timestamp'][qr[0]])>40000: raise ValueError('Unpaired quaternion reset')
        if frozen: raise ValueError('Task frozen without alignment')
        return result
    i=int(resets[0]); t=int(pos['timestamp'][i]); before=i-1
    transitions = np.flatnonzero(np.r_[False,np.diff(flags['cs_mag_aligned_in_flight'].astype(int))==1]
        & (flags['timestamp']>=t)&(flags['timestamp']<=min(end,t+500000)))
    if not len(qr) or not len(transitions):
        if allow_pending and end-t<=500000:
            result['pending']=True; result['candidate_us']=t; return result
        raise ValueError('Missing/late alignment or quaternion confirmation')
    if len(transitions)!=1: raise ValueError('Ambiguous alignment')
    q=int(qr[0]); f=int(transitions[0]); prev=int(index(flags,t-1)); e=int(index(est,t))
    s=int(index(status,t)); l=int(index(land,t)); sel=int(index(selector,t))
    packet=dict(phase='TAKEOFF_PREPARATION',armed=int(status['arming_state'][s])==2,
        airborne=not bool(land['landed'][l]),contact=bool(land['ground_contact'][l]),
        command_sent=bool(frozen and t>=frozen['timestamp']),excitation_started=bool(np.any(diag['excitation'][di[diag['timestamp'][di]<=t]]!=0)),
        primary_constant=True,primary_healthy=True,reference_unchanged=True,pv_counters_unchanged=True,
        controller_ok=True,aligned_before=bool(flags['cs_mag_aligned_in_flight'][prev]),aligned_after=True,
        yaw_aligned=bool(flags['cs_yaw_align'][f]),mag_fault=False,mag_disturbed=False,emergency_reset=False,
        other_yaw_source=False,filter_fault=False,nav_state=int(status['nav_state'][s]),previous_events=0,
        heading_before=int(pos['heading_reset_counter'][before]),heading_after=int(pos['heading_reset_counter'][i]),
        quat_before=int(att['quat_reset_counter'][q-1]),quat_after=int(att['quat_reset_counter'][q]),
        delta_rad=float(pos['delta_heading'][i]),quat_delta_rad=delta_yaw(att,q),
        quat_pair_offset_s=(int(att['timestamp'][q])-t)*1e-6,
        sample_gap_s=(t-int(pos['timestamp'][before]))*1e-6,
        metadata_age_s=(t-int(est['timestamp'][e]))*1e-6,
        selector_age_s=(t-int(selector['timestamp'][sel]))*1e-6,
        status_flags_age_s=(t-int(flags['timestamp'][prev]))*1e-6,
        event_stream_observable=True,event_counter_gaps=0,
        alignment_lag_s=(int(flags['timestamp'][f])-t)*1e-6,
        height_m=ref['position']['z']-float(pos['z'][i]),missing_samples=0)
    classify(packet)
    confirmed=max(t,int(att['timestamp'][q]),int(flags['timestamp'][f]))
    target=data(log,'trajectory_setpoint'); ti=index(target,times)
    good=(times>=confirmed)&(status['nav_state'][si]==2)&(status['arming_state'][si]==2)
    good &= ~land['landed'][li].astype(bool)&~land['ground_contact'][li].astype(bool)
    good &= (times-target['timestamp'][ti])<=40000
    errors=np.angle(np.exp(1j*(pos['heading'][ix]-target['yaw'][ti])))
    good &= np.isfinite(errors)&(np.abs(errors)<=math.radians(1))
    if frozen:
        matches=np.flatnonzero(times==frozen['timestamp'])
        if len(matches)!=1: raise ValueError('Freeze not exact sample')
        last=int(matches[0])
    else: last=len(times)-1
    quiet=0.
    if good[last]:
        j=last
        while j>0 and good[j-1]: j-=1
        quiet=(int(times[last])-int(times[j]))*1e-6
    result.update(confirmed=True,confirmation_us=confirmed,event_us=t,packet=packet,quiet_s=quiet,ready=quiet>=1)
    if quiet>=1:
        chosen=freeze_task_yaw(float(pos['heading'][ix[last]]),float(target['yaw'][ti[last]]),quiet,
            (int(times[last])-int(target['timestamp'][ti[last]]))*1e-6,confirmed=True,nav_state=2,already_frozen=False)
        result['freeze_candidate']=dict(timestamp=int(times[last]),timestamp_sample=int(pos['timestamp_sample'][ix[last]]),
            yaw=chosen,existing_target_yaw=float(target['yaw'][ti[last]]),primary=primary,
            heading_counter=int(pos['heading_reset_counter'][ix[last]]),prearm_heading=ref['position']['heading'])
    if frozen:
        if not result['ready'] or result['freeze_candidate']!=frozen: raise ValueError('Incorrect/fabricated yaw freeze')
        if t>=frozen['timestamp']: raise ValueError('Reset after freeze')
    return result
