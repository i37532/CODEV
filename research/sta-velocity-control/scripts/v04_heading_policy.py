"""Offline specification checker only. Not wired into a flight runner/controller."""
import json
import math
from pathlib import Path

CONFIG=Path(__file__).resolve().parents[1]/'v04/protocol04/protocol.json'


def classify(event):
    """Requires an assembled, complete evidence packet; absence is not zero/valid."""
    p=json.loads(CONFIG.read_text())['reference_policy']; ev=p['evidence']
    expected=dict(phase='TAKEOFF_PREPARATION',armed=True,airborne=True,contact=False,
        command_sent=False,excitation_started=False,primary_constant=True,primary_healthy=True,
        reference_unchanged=True,pv_counters_unchanged=True,controller_ok=True,
        aligned_before=False,aligned_after=True,yaw_aligned=True,mag_fault=False,
        mag_disturbed=False,emergency_reset=False,other_yaw_source=False,filter_fault=False)
    for key,value in expected.items():
        if key not in event or event[key]!=value: raise ValueError('Unqualified event: '+key)
    if event['nav_state'] not in (17,2): raise ValueError('Wrong preparation mode')
    if event['previous_events']!=0: raise ValueError('Repeated heading reset')
    for prefix in ('heading','quat'):
        before,after=event[prefix+'_before'],event[prefix+'_after']
        if any(type(v) is not int or not 0<=v<=255 for v in (before,after)) or (after-before)%256!=1:
            raise ValueError('Counter jump '+prefix)
    limits={'delta_rad':math.radians(p['heading_delta_abs_max_deg']),
            'quat_pair_offset_s':ev['quat_heading_pair_max_offset_s'],
            'sample_gap_s':ev['sample_max_gap_s'], 'metadata_age_s':ev['metadata_max_age_s'],
            'selector_age_s':ev['selector_max_age_s'], 'status_flags_age_s':ev['status_flags_max_age_s']}
    for key,maximum in limits.items():
        value=event[key]
        if not math.isfinite(value) or abs(value)>maximum: raise ValueError('Invalid bound '+key)
    if event['sample_gap_s']<=0 or any(event[k]<0 for k in ('metadata_age_s','selector_age_s','status_flags_age_s')):
        raise ValueError('Invalid time')
    if not event['event_stream_observable'] or event['event_counter_gaps']!=0: raise ValueError('Unobservable event history')
    lag=event['alignment_lag_s']
    if not math.isfinite(lag) or not 0<=lag<=ev['alignment_confirmation_max_lag_s']: raise ValueError('Missing/late alignment')
    if not math.isfinite(event['quat_delta_rad']) or abs(math.remainder(event['quat_delta_rad']-event['delta_rad'],2*math.pi))>ev['quat_heading_delta_tolerance_rad']:
        raise ValueError('Quaternion/heading disagreement')
    h=event['height_m']
    if not math.isfinite(h) or not p['event_height_m'][0]<=h<=p['event_height_m'][1]: raise ValueError('Not preparation height')
    if event['missing_samples']!=0: raise ValueError('Missing sequence')
    return 'expected_first_takeoff_alignment'


def freeze_task_yaw(heading,target,quiet_s,target_age_s,*,confirmed,nav_state,already_frozen):
    p=json.loads(CONFIG.read_text())['task_yaw_policy']
    if already_frozen or not confirmed or nav_state!=2: raise ValueError('Not eligible for one-shot task yaw')
    if not all(math.isfinite(v) for v in (heading,target,quiet_s,target_age_s)): raise ValueError('Nonfinite yaw gate')
    if quiet_s<p['quiet_interval_s'] or not 0<=target_age_s<=p['target_max_age_s']: raise ValueError('Not quiet/fresh')
    if abs(math.remainder(heading-target,2*math.pi))>math.radians(p['heading_to_existing_target_abs_max_deg']):
        raise ValueError('Excess yaw target step')
    # Already in the post-reset estimate convention: never add delta a second time.
    return math.remainder(heading,2*math.pi)
