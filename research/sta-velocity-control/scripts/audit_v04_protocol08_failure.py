#!/usr/bin/env python3
"""Read-only diagnosis, never acceptance or repair of the protocol08 failure."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import numpy as np
from pyulog import ULog
from v04_heading_stream import LiveLog, TOPICS, replay
from analyze_v04_protocol08 import check_first_invocation


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def attitude_records(path):
    """Independent ULog framing: return original vehicle_attitude instance-0 clocks."""
    raw = path.read_bytes()
    if raw[:7] != b'ULog\x01\x12\x35':
        raise ValueError('Invalid header')
    offset, subscriptions, records = 16, {}, []
    while offset + 3 <= len(raw):
        size, kind = struct.unpack_from('<HB', raw, offset)
        end = offset + 3 + size
        if end > len(raw):
            raise ValueError('Truncated record')
        if kind == ord('A'):
            instance, message_id = struct.unpack_from('<BH', raw, offset + 3)
            subscriptions[message_id] = (raw[offset+6:end].decode(), instance)
        elif kind == ord('D'):
            message_id = struct.unpack_from('<H', raw, offset + 3)[0]
            if subscriptions[message_id] == ('vehicle_attitude', 0):
                stamp, sample = struct.unpack_from('<QQ', raw, offset + 5)
                records.append(dict(offset=offset, timestamp=stamp, timestamp_sample=sample,
                                    payload_sha256=hashlib.sha256(raw[offset+5:end]).hexdigest()))
        offset = end
    if offset != len(raw):
        raise ValueError('Incomplete trailing record')
    return records


def main():
    p = argparse.ArgumentParser(); p.add_argument('run', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(); run, out = args.run.resolve(), args.output.resolve()
    if run == out or run in out.parents:
        raise ValueError('Independent new audit directory required')
    out.mkdir(parents=True, exist_ok=False)
    result = json.loads((run/'result.json').read_text())
    e = dict(accepted=False, acceptance_changed=False, new_flights=0,
             source_head=result['source_head'], original_error=result['error'],
             events=result['events'], checks=[], logs=[])
    def check(name, passed):
        e['checks'].append(dict(name=name, passed=bool(passed)))
    decoded = []
    for item in result['logs']:
        path = Path(item['archive'])
        if sha(path) != item['sha256']:
            raise ValueError('Changed ULog')
        u = ULog(str(path)); decoded.append((item['bytes'], u, path))
        e['logs'].append(dict(**item, dropouts=len(u.dropouts), corruption=bool(u.file_corruption)))
    _, u, path = max(decoded, key=lambda item: item[0])
    check('ulog_no_reported_dropout_or_corruption', all(not x['dropouts'] and not x['corruption'] for x in e['logs']))
    events = {x['name']: x['timestamp_us'] for x in result['events']}
    check('failed_before_complete_observation_and_landing', not result['success'] and
          all(k not in events for k in ('hover_end','land_command','landed_disarmed')))
    att = u.get_dataset('vehicle_attitude').data
    original = attitude_records(path)
    check('independent_raw_record_clocks_equal_pyulog',
          np.array_equal([v['timestamp'] for v in original], att['timestamp']) and
          np.array_equal([v['timestamp_sample'] for v in original], att['timestamp_sample']))
    dt = np.diff(att['timestamp'].astype(np.int64))
    ds = np.diff(att['timestamp_sample'].astype(np.int64))
    bad = np.flatnonzero(dt <= 0) + 1
    e['attitude'] = dict(samples=len(dt)+1, equal_publish_times=int((dt==0).sum()),
        backwards_publish_times=int((dt<0).sum()), nonpositive_sample_intervals=int((ds<=0).sum()),
        sample_dt_min_us=int(ds.min()), sample_dt_max_us=int(ds.max()),
        bad_records=[[original[i-1], original[i]] for i in bad],
        bad_quaternions=[[{k:att[k][j].item() for k in att} for j in (i-1,i)] for i in bad])
    check('one_equal_publish_time_not_sample_regression', len(bad)==1 and dt[bad[0]-1]==0 and np.all(ds>0))
    check('two_different_payloads_and_samples', all(original[i-1]['payload_sha256']!=original[i]['payload_sha256']
        and original[i-1]['timestamp_sample']<original[i]['timestamp_sample'] for i in bad))
    check('duplicate_is_inside_incomplete_hover', len(bad)==1 and att['timestamp'][bad[0]]>events['hover_start'])
    live = LiveLog(path).read(); arrays = 0
    for stream in u.data_list:
        if stream.name not in TOPICS:
            continue
        actual = live.get_dataset(stream.name, stream.multi_id).data
        for key, values in stream.data.items():
            np.testing.assert_array_equal(values, actual[key]); arrays += 1
    e['live_vs_independent_field_arrays_equal'] = arrays
    check('live_reader_preserves_original_arrays', arrays > 0)
    ref = json.loads((run/'height_reference.json').read_text())
    frozen = json.loads((run/'task_yaw.json').read_text())
    try:
        replay(u, ref, frozen=frozen)
    except ValueError as exc:
        e['independent_full_log_rejection'] = str(exc)
    check('same_failure_in_complete_log', e.get('independent_full_log_rejection')=='Empty/nonmonotonic vehicle_attitude')
    selector = u.get_dataset('estimator_selector_status').data
    e['primary_instances'] = np.unique(selector['primary_instance']).tolist()
    check('no_recorded_primary_switch', e['primary_instances']==[0] and
          not np.any(np.diff(selector['instance_changed_count'].astype(np.int64))))
    pos = u.get_dataset('vehicle_local_position').data
    m = pos['timestamp']>=events['takeoff_command']
    constant = ['ref_timestamp','ref_lat','ref_lon','ref_alt','xy_reset_counter',
                'z_reset_counter','vxy_reset_counter','vz_reset_counter']
    e['reference_and_pv_counters'] = {k:np.unique(pos[k][m]).tolist() for k in constant}
    check('no_reference_or_position_velocity_reset_after_takeoff', all(len(v)==1 for v in e['reference_and_pv_counters'].values()))
    e['heading_counter_after_yaw_freeze'] = np.unique(pos['heading_reset_counter'][pos['timestamp']>=frozen['timestamp']]).tolist()
    check('no_heading_reset_after_yaw_freeze', len(e['heading_counter_after_yaw_freeze'])==1)
    d = u.get_dataset('sta_velocity_ctrl_status').data; active = d['timestamp']>=events['takeoff_command']
    fields = dict(effective_mode=0,effective_axes=0,inner_mode=0,inner_axes=0,inner_divisor=1,
                  inner_valid=1,first_fail=0,retry_result=0,fault=0,sta_fault=0,failsafe=0,timing=0,pid_calls=1,valid=1)
    e['actual_states_until_abort'] = {k:np.unique(d[k][active]).tolist() for k in fields}
    check('actual_PID_and_no_recorded_controller_fault', all(e['actual_states_until_abort'][k]==[v] for k,v in fields.items()))
    e['first_invocation_until_abort'] = check_first_invocation(d, active)
    check('no_missing_velocity_publication', np.all(np.diff(d['publish_seq'][active].astype(np.int64))==1))
    rate = u.get_dataset('sta_rate_ctrl_status').data; rm = rate['timestamp']>=events['takeoff_command']
    check('no_missing_rate_publication', np.all(np.diff(rate['publish_seq'][rm].astype(np.int64))==1))
    e['diagnostic_sample_period_us'] = np.unique(np.diff(d['timestamp_sample'][active].astype(np.int64))).tolist()
    e['rate_sample_period_us'] = np.unique(np.diff(rate['timestamp_sample'][rm].astype(np.int64))).tolist()
    ex = d['excitation_time'][active]; ex = ex[ex>=0]
    e['excitation_time_range_s'] = [float(ex.min()),float(ex.max())] if len(ex) else []
    last = json.loads((run/'samples.jsonl').read_text().splitlines()[-1])
    e['last_host_sample'] = last
    e['host_observation_before_abort_s'] = (last['position']['timestamp']-events['hover_start'])*1e-6
    check('no_complete_32s_excitation', len(ex)>0 and ex.max()<31.96)
    params = json.loads((run/'runtime_parameters_start.json').read_text())
    e['parameters'] = {k:params[k] for k in ('MC_RTC_MODE','MC_STA_AXES','MC_RTC_DIV','MC_RATT_TEST',
        'MC_STA_TKO_MGT','MPC_VC_MODE','MPC_VC_AXES','MPC_VCT_TEST','SDLOG_PROFILE')}
    e['not_evaluated'] = ('No complete 60s observation, 32s excitation, landing, ESTA or paired metrics. '
        'No inference about landing IMU repair effectiveness; no production or checker change; no removal/deduplication of records.')
    e['source_interpretation'] = ('EKF2Selector::PublishVehicleAttitude checks increasing timestamp_sample, '
        'then stamps timestamp using hrt_absolute_time. Observed distinct samples at the same publish time '
        'are consistent with this design, not proof of a sensor clock regression or flight instability. '
        'Exact scheduling cause was not traced.')
    files = sorted(p for p in run.parent.rglob('*') if p.is_file() and not p.is_symlink())
    index = ''.join(f'{sha(p)}  {p}\n' for p in files)
    (out/'original_artifacts.sha256').write_text(index)
    e['original_artifact_count'] = len(files)
    e['original_index_sha256'] = hashlib.sha256(index.encode()).hexdigest()
    e['diagnostic_passed'] = all(c['passed'] for c in e['checks'])
    (out/'diagnosis.json').write_text(json.dumps(e,indent=2)+'\n')
    print(json.dumps(dict(checks=e['checks'],diagnostic_passed=e['diagnostic_passed'],accepted=False),indent=2))
    return 0 if e['diagnostic_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
