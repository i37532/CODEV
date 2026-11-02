#!/usr/bin/env python3
"""Post-hoc read-only height response analysis; never launches a simulator."""
import argparse
import json
from pathlib import Path

import numpy as np

from analyze_hover import clock, dataset, digest, read_json, require, save_json, verify_archives, COLORS


def validate_trace(t, h, up, target):
    t, h, up = (np.asarray(v, dtype=float) for v in (t, h, up))
    require(t.ndim == 1 and len(t) > 2 and t.shape == h.shape == up.shape, 'Trace shape')
    require(np.isfinite(t).all() and np.isfinite(h).all() and np.isfinite(up).all(), 'Nonfinite trace')
    require(np.all(np.diff(t) > 0), 'Non-increasing time; no deduplication')
    require(np.isfinite(target) and target > 0, 'Invalid target')
    return t, h, up


def crossing(t, h, threshold):
    indices = np.flatnonzero(h >= threshold)
    if not len(indices):
        return None
    i = int(indices[0])
    # A value already above threshold at the first sample has no observed crossing.
    if i == 0:
        return None
    return dict(first_sample_s=float(t[i]), bracket_s=[float(t[i-1]), float(t[i])])


def settling(t, h, target, fraction, end, minimum_remaining_s=2.):
    outside = np.flatnonzero(np.abs(h-target) > target*fraction)
    i = int(outside[-1])+1 if len(outside) else 0
    if i >= len(t) or end-t[i] < minimum_remaining_s:
        return None
    return dict(first_sample_s=float(t[i]), observed_remaining_s=float(end-t[i]),
        bracket_s=[float(t[max(0,i-1)]),float(t[i])])


def response_metrics(t, h, up, target, end):
    t, h, up = validate_trace(t, h, up, target)
    require(t[0] <= 0 and t[-1] >= end > 0, 'Missing full command-to-landing window')
    # Include the most recent pre-command sample for crossing brackets, not for the metrics window.
    origin_index = int(np.searchsorted(t, 0., side='right')-1)
    stop = int(np.searchsorted(t, end, side='left'))
    require(stop-origin_index > 2, 'Empty ascent/hover interval')
    tt, hh = t[origin_index:stop], h[origin_index:stop]
    require(np.max(np.diff(t[origin_index:stop+1])) <= .5, 'Position sample gap over frozen 500 ms bound')
    require(hh[0] < .1, 'Origin is not near ground')
    levels = {name:crossing(tt, hh, value) for name,value in
              [('onset_0p1m',.1), ('t10',target*.1), ('t50',target*.5),
               ('t90',target*.9), ('t95',target*.95), ('t98',target*.98)]}
    full = (t >= 0) & (t < end)
    overshoot = max(0., float(h[full].max())-target)
    result = dict(crossings=levels,
        rise_10_90_s=None if levels['t10'] is None or levels['t90'] is None else
            levels['t90']['first_sample_s']-levels['t10']['first_sample_s'],
        settling_5pct=settling(tt, hh, target, .05, end),
        settling_2pct=settling(tt, hh, target, .02, end),
        overshoot_m=overshoot, overshoot_percent=100*overshoot/target,
        peak_upward_speed_m_s=float(up[full].max()),
        median_sample_period_s=float(np.median(np.diff(tt))),
        maximum_sample_period_s=float(np.max(np.diff(t[origin_index:stop+1]))),
        analysis_end_s=float(end), minimum_settling_observation_s=2.)
    return result


def native_command(data, command):
    i = np.flatnonzero(np.asarray(data['command']) == command)
    require(len(i) == 1, 'Ambiguous or missing native command '+str(command))
    value = int(data['timestamp'][i[0]])
    require(value > 0, 'Invalid command time')
    return value


def analyze(row):
    from pyulog import ULog
    require(row['runner_success'] and row['analysis_valid'], 'Source run was not accepted')
    require(digest(row['result_path']) == row['result_sha256'], 'Source result changed')
    verify_archives(row['verified_logs'], Path(row['result_path']))
    u = ULog(row['ulog']['archive'], message_name_filter_list=['vehicle_local_position',
        'vehicle_local_position_setpoint','trajectory_setpoint','vehicle_command','vehicle_status'])
    require(not u.dropouts and not getattr(u,'file_corruption',False), 'Invalid ULog')
    command = dataset(u,'vehicle_command')
    require(command is not None, 'No native command evidence')
    start, end = native_command(command,22), native_command(command,176)
    require(abs(start-row['events']['takeoff_command']) <= 1e6, 'Unexpected takeoff event disagreement')
    require(abs(end-row['events']['land_command']) <= 1e6, 'Unexpected landing event disagreement')
    p = dataset(u,'vehicle_local_position'); t, time_field = clock(p)
    full = (t >= start) & (t <= end)
    for flag in ('z_valid','v_z_valid'):
        require(flag in p and np.all(p[flag][full]), 'Invalid estimated vertical state')
    for name in ('z_reset_counter','vz_reset_counter'):
        require(name in p and not np.any(np.diff(p[name][full].astype(np.int64))), 'Vertical reset in analysis window')
    origin = row['metrics']['origin_position_ned_m'][2]
    h = origin-np.asarray(p['z'],dtype=float)
    up = -np.asarray(p['vz'],dtype=float)
    ts = (t.astype(np.int64)-start)*1e-6
    duration = (end-start)*1e-6
    a = max(0,int(np.searchsorted(t,start,side='right'))-1)
    b = min(len(t),int(np.searchsorted(t,end,side='left'))+1)
    m = response_metrics(ts[a:b],h[a:b],up[a:b],2.5,duration)
    trace = dict(time=ts[full],height=h[full],up=up[full])
    target = dataset(u,'vehicle_local_position_setpoint')
    require(target is not None, 'Missing output position setpoint')
    st, st_clock = clock(target)
    sm = (st >= start) & (st <= end)
    trace.update(target_time=(st[sm].astype(np.int64)-start)*1e-6,
        target_height=origin-np.asarray(target['z'][sm],dtype=float),
        target_up=-np.asarray(target['vz'][sm],dtype=float))
    state = dataset(u,'vehicle_status')
    takeoffs = np.unique(state['takeoff_time'][state['takeoff_time'] > 0])
    m.update(native_takeoff_command_us=start, native_land_command_us=end,
        command_minus_runner_event_s=(start-row['events']['takeoff_command'])*1e-6,
        logged_takeoff_detection_s=[(int(x)-start)*1e-6 for x in takeoffs],
        origin_z_ned_m=origin, source_clock=time_field, target_clock=st_clock,
        runner_hover_entry_s=(row['events']['hover_start']-start)*1e-6,
        landing_to_disarm_s=row['metrics']['landing_command_to_disarm_s'],
        target_note='Published controller setpoint, not an identical step input across systems')
    return dict(id=row['job']['id'],label=row['job']['label'],metrics=m,
        source_ulog=row['ulog'],source_result_sha256=row['result_sha256']),trace


def figures(rows,traces,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    files=[]
    fig,axs=plt.subplots(2,1,figsize=(11,7),sharex=True,constrained_layout=True)
    for i,(row,tr) in enumerate(zip(rows,traces)):
        axs[0].plot(tr['time'],tr['height'],color=COLORS[i],label=row['label'])
        axs[1].plot(tr['time'],tr['up'],color=COLORS[i],label=row['label'])
    axs[0].set_title('Height response to 2.5 m takeoff request | one flight per system')
    axs[0].set_ylabel('Height above own origin / m')
    axs[1].set_ylabel('Upward estimated velocity / m/s')
    axs[1].set_xlabel('Time since native takeoff command / s')
    axs[0].legend(ncol=4)
    for ax in axs:
        ax.grid(alpha=.2); ax.set_xlim(0,20)
        require(len(ax.lines)==4,'Unexpected extra response curve')
    for ext in ('png','svg'):
        p=out/('height_response.'+ext);fig.savefig(p,dpi=170);files.append(dict(path=p.name,sha256=digest(p)))
    plt.close(fig)
    # Separate diagnostic figure makes differing target trajectories visible;
    # never put four targets into the requested actual-only overlay.
    fig,axs=plt.subplots(2,2,figsize=(11,7),sharex=True,sharey=True,constrained_layout=True)
    for i,(ax,row,tr) in enumerate(zip(axs.flat,rows,traces)):
        ax.plot(tr['time'],tr['height'],color=COLORS[i],label='Actual height')
        ax.plot(tr['target_time'],tr['target_height'],color='#444444',ls='--',label='Published height target')
        ax.set_title(row['label']);ax.grid(alpha=.2);ax.set_xlim(0,20);ax.legend(fontsize=8)
        ax.set_xlabel('Time since native command / s');ax.set_ylabel('Height above own origin / m')
    fig.suptitle('Target audit: dashed line is a target, not another controller')
    p=out/'target_audit.png';fig.savefig(p,dpi=170);files.append(dict(path=p.name,sha256=digest(p)))
    plt.close(fig)
    return files


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metrics',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    require(not args.output.exists(),'Refusing to overwrite response output')
    source=read_json(args.metrics)
    require(source['summary']['complete_comparison'] and len(source['runs'])==4,'Need four accepted systems')
    pairs=[analyze(row) for row in source['runs']]
    rows,traces=[p[0] for p in pairs],[p[1] for p in pairs]
    args.output.mkdir(parents=True)
    payload=dict(analysis='Exploratory post-hoc task response, not preregistered controller step test',
        source_metrics=str(args.metrics.resolve()),source_metrics_sha256=digest(args.metrics),
        script_sha256=digest(__file__),nominal_height_m=2.5,
        timing='First observed crossing; no interpolation; brackets show sample resolution',
        settling='Within band at every recorded sample until land command, at least 2 s observed remaining',
        origin='Same pre-takeoff estimated origin as the earlier four-system figures',
        runs=rows,figures=figures(rows,traces,args.output))
    save_json(args.output/'response_metrics.json',payload)
    print(json.dumps(rows,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
