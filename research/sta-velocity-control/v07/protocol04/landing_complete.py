"""Offline full-chain wrapper, never a new-batch flight acceptance entry.

The existing protocol09 full analyzer remains unchanged. Its output plus the
new raw landing component must both pass in a synthetic provenance fixture.
Old data may diagnose the component, but this wrapper never regrades a flight.
"""
import json
from pathlib import Path
from pyulog import ULog
from analyze_v04_protocol09 import analyze as historical_analyze
from landing import replay, validate_context


def check_complete(log, events, context):
    validate_context(context)
    if (context['hover_start_us'] != events['hover_start'] or
            context['hover_end_us'] != events['hover_end'] or
            not events['hover_end'] <= context['command_lower_us'] < events['landed_disarmed']):
        raise ValueError('Landing context differs from complete event window')
    result = replay(log, context, events['landed_disarmed'], final=True)
    d = log.get_dataset('sta_velocity_ctrl_status').data
    after = (d['timestamp'] >= events['landed_disarmed']) & ~d['armed'].astype(bool)
    if not after.any() or (d['excitation_fault'][after] != 0).any():
        raise ValueError('Missing disarmed clear diagnostic')
    return result
