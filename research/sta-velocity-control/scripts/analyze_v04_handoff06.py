"""Strict raw handoff evidence, separate from inherited numerical flight metrics."""
import json
import numpy as np
from v04_heading_stream import data, index, row
from v04_handoff06 import capture, matches_target, decode_current
from v04_task04 import accepted_ack


def check_handoff(u, run, ref, frozen, events):
    target = json.loads((run/'handoff_target.json').read_text())
    command = json.loads((run/'reposition_command.json').read_text())
    sent = command['timestamp_us']
    rebuilt = capture(u, ref, frozen, sent, source_us=target['source_timestamp'])
    # NaN may legitimately occur in source Z/vz. Serialization preserves that provenance.
    if json.dumps(rebuilt, sort_keys=True) != json.dumps(target, sort_keys=True):
        raise ValueError('Fabricated handoff provenance')
    if command['message'] != 'COMMAND_INT' or command['wire'] != target['wire'] or command['maximum_sends'] != 1:
        raise ValueError('Wrong handoff encoding or send budget')
    if not frozen['timestamp'] <= target['source_timestamp'] <= sent == events['reposition_command'] < events['handoff_ready'] < events['hover_start']:
        raise ValueError('Handoff event order')
    ack = json.loads((run/'reposition_ack.json').read_text())
    if not accepted_ack(ack, command['sent_monotonic']) or ack['received_monotonic']-command['sent_monotonic'] > 5:
        raise ValueError('Missing/late/rejected handoff ACK')
    c = data(u, 'vehicle_command')
    cm = (c['command'] == 192) & (c['timestamp'] >= events['takeoff_command'])
    if np.count_nonzero(cm) != 1:
        raise ValueError('Nonunique handoff command')
    k = int(np.flatnonzero(cm)[0]); w = target['wire']
    if not sent <= c['timestamp'][k] <= events['handoff_ready']:
        raise ValueError('Wrong logged command timestamp')
    expected = {key:w[key] for key in ('command','target_system','target_component','param1','param2','param3','param4')}
    expected.update(param5=target['lat'], param6=target['lon'], param7=w['z'],
                    source_system=255, source_component=190, from_external=1, confirmation=0)
    if any(c[key][k] != value for key,value in expected.items()):
        raise ValueError('Logged command differs from encoded target')
    a = data(u, 'vehicle_command_ack')
    am = (a['command'] == 192) & (a['timestamp'] >= c['timestamp'][k])
    if np.count_nonzero(am) != 1 or np.any(a['result'][am] != 0):
        raise ValueError('Missing/duplicate/rejected logged ACK')
    if a['timestamp'][am][0] > events['handoff_ready']:
        raise ValueError('ACK after claimed handoff')
    trip = data(u, 'position_setpoint_triplet')
    first = int(index(trip, events['handoff_ready']))
    # Observation is half-open; a planned landing publication at its end is not drift.
    last = int(np.searchsorted(trip['timestamp'], events['hover_end'], side='left'))-1
    if trip['timestamp'][first] < c['timestamp'][k]:
        raise ValueError('Stale triplet at handoff')
    for i in range(first, last+1):
        d = {key[8:]:value[i].item() for key,value in trip.items() if key.startswith('current.')}
        if not matches_target(d, target):
            raise ValueError('Wrong/lost raw Navigator target')
    if not matches_target(decode_current((run/'triplet_after.txt').read_text()), target, cli=True):
        raise ValueError('CLI handoff readback differs')
    status = data(u, 'vehicle_status')
    i = int(index(status, events['handoff_ready']))
    j = int(np.searchsorted(status['timestamp'], events['hover_end'], side='left'))-1
    if np.any(status['nav_state'][i:j+1] != 4):
        raise ValueError('Left AUTO_LOITER after handoff')
    # These are trajectory/output requests, never called actual acceleration/motion.
    trajectory = data(u, 'trajectory_setpoint')
    diagnostic = data(u, 'sta_velocity_ctrl_status')
    for d, fields in ((trajectory, ('x','y')), (diagnostic, ('p_sp[0]','p_sp[1]'))):
        m = (d['timestamp'] >= events['hover_start']-3e6) & (d['timestamp'] < events['hover_end'])
        t = d['timestamp'][m].astype(np.int64)
        if len(t) < 2 or t[0]-(events['hover_start']-3e6) > 40000 or events['hover_end']-t[-1] > 40000 or np.max(np.diff(t)) > 40000:
            raise ValueError('Missing downstream XY target window')
        for axis, field in enumerate(fields):
            x = d[field][m]
            if not np.all(np.isfinite(x)) or np.any(np.abs(x-target['xy_encoded'][axis]) > .05):
                raise ValueError('Downstream XY target differs')
    return dict(source=target, raw_command_timestamp=int(c['timestamp'][k]),
                first_matching_triplet_timestamp=int(trip['timestamp'][first]),
                observation_triplets=last-first+1)
