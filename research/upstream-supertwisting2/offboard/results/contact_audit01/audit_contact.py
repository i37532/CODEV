#!/usr/bin/env python3
"""Bounded offline audit of B03/B04 STA2 landing; never changes acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from pyulog import ULog

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
ORIGINAL = Path('/home/yr/Desktop/Codev-SuperTwisting2-original')
PLUGIN = ORIGINAL / 'Tools/simulation/gazebo-classic/sitl_gazebo-classic'
EXPERIMENTS = Path('/home/yr/Desktop/codev doc/experiments')
EXPECTED = {
    'B03': '313aa66b75e244a8cd1f1082f0ac3361e76148d8acdfb763fbaed0d1c64ee998',
    'B04': '6a54d350710f0108ccafa563b0f65bae5586303a7dd4a3a5d42a6411b483c73b',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def causal_index(timestamps, target, max_age_us):
    t = np.asarray(timestamps, dtype=np.int64)
    if not len(t) or np.any(t <= 0) or np.any(np.diff(t) <= 0):
        raise ValueError('Nonpositive, duplicate or reversed publication clock')
    i = int(np.searchsorted(t, target, side='right')) - 1
    if i < 0 or target - t[i] > max_age_us:
        raise ValueError('No fresh causal observation')
    return i


def own_origin_height(z, reference_z):
    z = np.asarray(z, dtype=float)
    if not np.all(np.isfinite(z)) or not np.isfinite(reference_z):
        raise ValueError('Invalid height input')
    return reference_z - z


def dataset(log, name):
    return log.get_dataset(name, 0).data


def row(data, target, keys, max_age=20000):
    i = causal_index(data['timestamp'], target, max_age)
    return {key: data[key][i].item() for key in keys}


def optional_row(data, target, keys):
    """Inactive HTE may stop publishing after landing; never fabricate freshness."""
    try:
        return dict(available=True, query_us=target, values=row(data,target,keys,max_age=1000000))
    except ValueError as exc:
        if str(exc) != 'No fresh causal observation':
            raise
        return dict(available=False,query_us=target,reason=str(exc))


def process(batch):
    directory = EXPERIMENTS / ('UPSTREAM-STA2-ROS-OFFBOARD-20261102-' + batch) / 'runs/O002'
    path = directory / 'native_00.ulg'
    assert sha(path) == EXPECTED[batch]
    log = ULog(str(path))
    result = json.loads((directory / 'result.json').read_text())
    origin = json.loads((directory / 'origin.json').read_text())
    events = {e['name']: e['timestamp_us'] for e in result['events']}
    ref = result['events'][0]['timestamp_us']
    land_time = events['land_command']
    lp = dataset(log, 'vehicle_local_position')
    gt = dataset(log, 'vehicle_local_position_groundtruth')
    imu = dataset(log, 'sensor_combined')
    thrust = dataset(log, 'vehicle_thrust_setpoint')
    land = dataset(log, 'vehicle_land_detected')
    selector = dataset(log, 'estimator_selector_status')
    reference = row(gt, ref, ['timestamp', 'z', 'ref_alt'])
    gh = own_origin_height(gt['z'], reference['z'])
    eh = own_origin_height(lp['z'], origin['z'])
    # Diagnostic geometric/kinematic marker, NOT a new landing acceptance rule.
    candidates = np.flatnonzero((gt['timestamp'] >= land_time) &
                               (np.abs(gh) < .005) & (np.abs(gt['vz']) <= .1))
    assert len(candidates)
    contact = int(gt['timestamp'][candidates[0]])
    end = min(int(lp['timestamp'][-1]), int(gt['timestamp'][-1]))
    stop = 101420000 if batch == 'B04' else events['landed_disarmed']

    def snapshot(t):
        p = row(lp, t, ['timestamp', 'timestamp_sample', 'z', 'vz'])
        g = row(gt, t, ['timestamp', 'timestamp_sample', 'z', 'vz', 'ref_alt'])
        p['relative_height_m'] = origin['z'] - p['z']
        g['relative_height_m'] = reference['z'] - g['z']
        # World altitude diagnostic uses plugin's audited default home=488 m.
        g['world_z_m_given_home_488'] = g['ref_alt'] - g['z'] - 488.
        return dict(query_us=t, estimate=p, truth=g,
                    truth_receipt_age_us=t-g['timestamp'],
                    velocity_estimate_minus_truth_m_s=p['vz']-g['vz'])

    window = (imu['timestamp'] >= contact-100000) & (imu['timestamp'] <= contact+100000)
    tail = (thrust['timestamp'] >= contact) & (thrust['timestamp'] <= min(contact+400000, stop))
    before = snapshot(contact-20000)
    after = snapshot(contact+20000)
    jump = after['velocity_estimate_minus_truth_m_s'] - before['velocity_estimate_minus_truth_m_s']
    flight = lp['timestamp'] >= events['climb_start']
    samples = [snapshot(t) for t in sorted(set([land_time, contact-20000, contact,
                   contact+20000, contact+100000, contact+200000, contact+500000, stop])) if t <= end]
    truth_stop_neighborhood = (gt['timestamp'] >= stop-100000) & (gt['timestamp'] <= stop+100000)
    attitude = dataset(log, 'vehicle_attitude')
    aw = (attitude['timestamp'] >= contact-100000) & (attitude['timestamp'] <= stop)
    c = 1 - 2 * (attitude['q[1]'][aw].astype(float)**2 + attitude['q[2]'][aw].astype(float)**2)
    max_tilt = float(np.degrees(np.arccos(np.clip(c, -1, 1))).max())
    gaps = {}
    for name, data in [('estimate', lp), ('truth', gt), ('sensor_combined', imu)]:
        t = data['timestamp'][(data['timestamp'] >= land_time) & (data['timestamp'] <= stop)].astype(np.int64)
        gaps[name] = dict(rows=len(t), min_gap_us=int(np.diff(t).min()),
                          median_gap_us=float(np.median(np.diff(t))), max_gap_us=int(np.diff(t).max()))
    report = dict(batch=batch, path=str(path), sha256=sha(path), original_success=result['success'],
                  original_error=result.get('error'), corruption=log.file_corruption, dropouts=len(log.dropouts),
                  reference_event_us=ref, estimated_reference_z=origin['z'], truth_reference=reference,
                  groundtruth_timestamp_sample_unique=np.unique(gt['timestamp_sample']).tolist(),
                  land_command_us=land_time, near_ground_stop_marker_us=contact,
                  exact_physics_contact_timestamp_available=False, source_clock='PX4 reception/publication',
                  snapshots=samples, stop=snapshot(stop), publication_spacing=gaps,
                  max_tilt_after_contact_deg=max_tilt,
                  sensor_combined_impact_z_min=float(imu['accelerometer_m_s2[2]'][window].min()),
                  sensor_combined_impact_z_max=float(imu['accelerometer_m_s2[2]'][window].max()),
                  sensor_combined_clipping_bits=np.unique(imu['accelerometer_clipping'][window]).tolist(),
                  sensor_integral_dt_us=np.unique(imu['accelerometer_integral_dt'][window]).tolist(),
                  max_thrust_command_magnitude_first_400ms=float(-thrust['xyz[2]'][tail].min()),
                  velocity_discrepancy_jump_m_s=jump,
                  one_16bit_wrap_4ms_m_s=32*9.80665*.004,
                  jump_minus_one_wrap_m_s=jump-32*9.80665*.004,
                  truth_height_range_stop_plus_minus_100ms=[float(gh[truth_stop_neighborhood].min()), float(gh[truth_stop_neighborhood].max())],
                  reset_counters={k: np.unique(lp[k][flight]).tolist() for k in
                                  ['xy_reset_counter', 'z_reset_counter', 'vxy_reset_counter', 'vz_reset_counter']},
                  primary_instances=np.unique(selector['primary_instance'][selector['timestamp'] >= events['climb_start']]).tolist(),
                  last_land={k:v[-1].item() for k,v in land.items()},
                  parameters={k:v for k,v in log.initial_parameters.items() if k in
                              ['MPC_LAND_SPEED','MPC_LAND_CRWL','LNDMC_Z_VEL_MAX','MPC_THR_MIN','MPC_USE_HTE','EKF2_HGT_REF']})
    report['impact_imu_rows']=[{k:imu[k][i].item() for k in
                              ['timestamp','accelerometer_integral_dt','accelerometer_m_s2[2]','accelerometer_clipping']}
                             for i in np.flatnonzero(window)]
    report['fusion_diagnostics']={}
    for name in ['estimator_aid_src_gnss_vel','estimator_aid_src_baro_hgt','hover_thrust_estimate']:
        data=dataset(log,name)
        keys=[k for k in ['timestamp','timestamp_sample','observation[2]','innovation[2]',
                          'test_ratio[2]','innovation_rejected','fused','hover_thrust','valid'] if k in data]
        report['fusion_diagnostics'][name]=[optional_row(data,t,keys) for t in [contact-200000,contact+400000,stop]]
    assert not log.file_corruption and not log.dropouts
    return report, dict(lp=lp, gt=gt, imu=imu, thrust=thrust, eh=eh, gh=gh)


def plots(out, reports, arrays):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    d=arrays['B04']; r=reports['B04']; t0=r['land_command_us']; stop=r['stop']['query_us']
    fig, axes=plt.subplots(3,1,figsize=(10,9),sharex=True,constrained_layout=True)
    for ax, key, values, label, color in [
        (axes[0],'lp','eh','PX4 estimated height','#d05b25'),
        (axes[0],'gt','gh','Gazebo truth: own zero','#2077b4')]:
        ax.plot((d[key]['timestamp'].astype(float)-t0)/1e6,d[values],label=label,color=color)
    for key,label,color in [('lp','PX4 estimated vz','#d05b25'),('gt','Gazebo truth vz','#2077b4')]:
        axes[1].plot((d[key]['timestamp'].astype(float)-t0)/1e6,d[key]['vz'],label=label,color=color)
    axes[2].plot((d['thrust']['timestamp'].astype(float)-t0)/1e6,-d['thrust']['xyz[2]'],label='Thrust command magnitude',color='#8052a5')
    axes[0].axhline(-.5,color='red',ls=':',label='Unchanged estimated-height limit')
    for ax, label in zip(axes,['Height above own preflight reference (m)','NED vertical velocity (m/s), down +','Normalized thrust command']):
        ax.axvline((r['near_ground_stop_marker_us']-t0)/1e6,color='gray',ls='--',label='Near-ground stop marker')
        ax.axvline((stop-t0)/1e6,color='black',ls=':',label='Runtime rejection')
        ax.set_ylabel(label);ax.grid(alpha=.25);ax.legend(fontsize=8,loc='best')
        ax.set_xlim(-.1,(stop-t0)/1e6+.01)
    axes[-1].set_xlabel('PX4 publication time since AUTO_LAND command (s)')
    axes[0].set_ylim(-.65,.75);axes[1].set_ylim(-.8,1.6);axes[2].set_ylim(.55,1.0)
    fig.suptitle('B04 original STA2: contact-region divergence (offline diagnosis)')
    fig.savefig(out/'b04_contact.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(12,7),sharex=True,constrained_layout=True)
    for j,b in enumerate(['B03','B04']):
        d=arrays[b];t0=reports[b]['near_ground_stop_marker_us']
        axes[0,j].plot((d['imu']['timestamp'].astype(float)-t0)/1e6,d['imu']['accelerometer_m_s2[2]'],color='#8052a5')
        axes[0,j].set_title(b+' original STA2 (historical outcome unchanged)')
        for key,label,color in [('lp','Estimated vz','#d05b25'),('gt','Truth vz','#2077b4')]:
            axes[1,j].plot((d[key]['timestamp'].astype(float)-t0)/1e6,d[key]['vz'],label=label,color=color)
        for ax in axes[:,j]:ax.grid(alpha=.25);ax.axvline(0,color='gray',ls='--');ax.set_xlim(-.15,.3)
        axes[0,j].set_ylim(-105,70);axes[1,j].set_ylim(-.7,1.4);axes[1,j].legend()
        axes[1,j].set_xlabel('Publication time from near-ground stop marker (s)')
    axes[0,0].set_ylabel('Logged specific force, body Z (m/s²)')
    axes[1,0].set_ylabel('NED vertical velocity (m/s), down +')
    fig.suptitle('Contact impulse: normal-sign B03 vs wrong-sign B04 measurement')
    fig.savefig(out/'impact_comparison.png',dpi=170);plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output
    out.mkdir(parents=True,exist_ok=False)
    evidence={}
    for b in EXPECTED:
        root=EXPERIMENTS/('UPSTREAM-STA2-ROS-OFFBOARD-20261102-'+b)
        evidence.update({str(p):sha(p) for p in root.rglob('*') if p.is_file()})
    sources=[ORIGINAL/'src/modules/simulation/simulator_mavlink/SimulatorMavlink.cpp',
             ORIGINAL/'src/lib/drivers/accelerometer/PX4Accelerometer.cpp',ORIGINAL/'msg/SensorAccelFifo.msg',
             ORIGINAL/'src/modules/land_detector/MulticopterLandDetector.cpp',
             ORIGINAL/'src/modules/mc_pos_control/PositionControl/PositionControl.cpp',
             PLUGIN/'src/gazebo_mavlink_interface.cpp',PLUGIN/'src/gazebo_groundtruth_plugin.cpp',
             PLUGIN/'src/gazebo_imu_plugin.cpp',PLUGIN/'src/mavlink_interface.cpp',
             PLUGIN/'include/common.h',PLUGIN/'models/iris/iris.sdf',
             PLUGIN/'models/asphalt_plane/model.sdf',PLUGIN/'models/ground_plane/model.sdf',PLUGIN/'worlds/empty.world',
             REPO/'src/modules/simulator/simulator_mavlink.cpp',
             REPO/'research/sta-velocity-control/reports/V04_IMU0_CHAIN_AUDIT.md',
             REPO/'research/sta-velocity-control/reports/V04_IMU0_CHAIN_REPAIR.md',
             ORIGINAL/'build/px4_sitl_default/bin/px4',REPO/'build/px4_sitl_default/bin/px4']
    evidence.update({str(p):sha(p) for p in sources})
    frozen=json.loads((HERE.parent/'batch04/manifest.json').read_text())
    assert all(sha(p)==h for p,h in frozen['assets'].items())
    evidence.update(frozen['assets'])
    reports={};arrays={}
    for b in EXPECTED:reports[b],arrays[b]=process(b)
    plots(out,reports,arrays)
    version=subprocess.run(['g++','--version'],capture_output=True,text=True,check=True)
    commands=[dict(argv=['g++','--version'],exit_code=0,stdout=version.stdout,stderr=version.stderr)]
    for repo in [REPO, ORIGINAL]:
        for operation in [['rev-parse','HEAD'],['status','--short'],['submodule','status','--recursive']]:
            argv=['git','-C',str(repo),*operation]
            c=subprocess.run(argv,capture_output=True,text=True,check=True)
            commands.append(dict(argv=argv,exit_code=0,stdout=c.stdout,stderr=c.stderr))
    for name,flags in [('host',['-O2']),('ubsan',['-O1','-fsanitize=float-cast-overflow','-fno-sanitize-recover=float-cast-overflow'])]:
        exe=out/('conversion_'+name)
        argv=['g++','-std=c++14',*flags,str(HERE/'conversion_probe.cpp'),'-o',str(exe)]
        c=subprocess.run(argv,capture_output=True,text=True);commands.append(dict(argv=argv,exit_code=c.returncode,stdout=c.stdout,stderr=c.stderr));assert c.returncode==0
        for value in ['-9.80665','-100','-200','200']:
            argv=[str(exe),value];c=subprocess.run(argv,capture_output=True,text=True)
            commands.append(dict(argv=argv,exit_code=c.returncode,stdout=c.stdout,stderr=c.stderr))
            expected=1 if name=='ubsan' and abs(float(value))==200 else 0
            assert c.returncode==expected
    assert all(sha(p)==h for p,h in evidence.items())
    body=dict(new_flights=0,historical_acceptance_changed=False,production_changes=False,
              evidence_before_after_identical=True,evidence_sha256=evidence,
              script_sha256={str(p):sha(p) for p in HERE.glob('*') if p.is_file()},
              diagnostic_time_alignment='Strict causal publication lookup, no future use; GT sensor clock absent.',
              exact_raw_preconversion_imu_missing=True,contact_force_messages_missing=True,
              synthetic_conversion_probe_not_actual_flight_input=True,
              reports=reports,commands=commands,frozen_assets_verified=len(frozen['assets']),
              freeze_status_read_only=frozen['status'])
    with (out/'audit.json').open('x') as f:json.dump(body,f,indent=2,ensure_ascii=False,allow_nan=False)
    print(json.dumps(dict(output=str(out),evidence_files=len(evidence),
                         B04=reports['B04']['stop'],jump=reports['B04']['velocity_discrepancy_jump_m_s'],
                         unchanged=True),indent=2))


if __name__=='__main__':main()
