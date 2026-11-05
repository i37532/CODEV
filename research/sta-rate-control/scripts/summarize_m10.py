#!/usr/bin/env python3
"""Seed-block descriptive inference, failure ledger and reproducible figures.

Only complete success pairs get a conditional-on-success metric contrast.
All attempts, including missing metrics, stay in the success denominator.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import numpy as np
from m10_design import SCENES, TEST_SEEDS


def wilson(success,total):
    if not 0<=success<=total or total<=0:raise ValueError('Invalid binomial counts')
    z=1.959963984540054;p=success/total;den=1+z*z/total
    center=(p+z*z/(2*total))/den
    half=z*np.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return [max(0.,float(center-half)),min(1.,float(center+half))]


def paired_interval(differences,seed=10102026,reps=10000,family=24):
    x=np.asarray(differences,float)
    if x.ndim!=1 or len(x)<2 or not np.all(np.isfinite(x)):raise ValueError('Need >=2 finite paired differences')
    rng=np.random.Generator(np.random.PCG64(seed))
    samples=x[rng.integers(0,len(x),(reps,len(x)))].mean(axis=1)
    return dict(n=len(x),mean_difference=float(x.mean()),sd_difference=float(x.std(ddof=1)),
                ci95=np.quantile(samples,[.025,.975]).tolist(),
                family_interval=np.quantile(samples,[.025/family,1-.025/family]).tolist(),
                bootstrap_replicates=reps,seed=seed,
                note='Descriptive percentile bootstrap of independent seed blocks conditional on both succeeding; not a p-value/power proof. Extreme family tails have limited Monte Carlo resolution.')


def summarize(root,out,pilot=False):
    out.mkdir(parents=True,exist_ok=False)
    jobs=json.loads((root/'jobs.json').read_text())
    rows=[]
    fixed_parameters=None
    for n,job in enumerate(jobs):
        label=f"{n:04d}_{job.get('group','train')}_m{job['mode']}_{job['scene']}_s{job['seed']}"
        path=root/label/'m10_analysis.json'
        row=json.loads(path.read_text()) if path.exists() else dict(**{k:job[k] for k in ('mode','group','scene','seed')},success=False,missing=True)
        row['path']=str(path);rows.append(row)
        parameter_file=root/label/'ulog_initial_parameters.json'
        if row['success'] and parameter_file.exists():
            params=json.loads(parameter_file.read_text())
            fixed={k:v for k,v in params.items() if k.startswith(('IMU_','SENS_','INS_','EKF2_','MC_DTERM','MC_DGYRO'))}
            if fixed_parameters is None:fixed_parameters=fixed
            elif fixed!=fixed_parameters:raise RuntimeError('Sensor/filter/estimator configuration drift')
    cells=[];contrasts=[]
    for scene in SCENES:
        for group,modes in [('A',(1,2)),('B',(0,1,2))]:
            for mode in modes:
                subset=[r for r in rows if (r['scene'],r['group'],r['mode'])==(scene,group,mode)]
                ok=[r for r in subset if r['success']]
                cell=dict(scene=scene,group=group,mode=mode,planned=len(subset),success=len(ok),
                          missing=sum(r.get('missing',False) for r in subset),failures=[r for r in subset if not r['success']],
                          flight_completed=sum(r.get('flight_success',False) for r in subset),
                          failure_classes={kind:sum(r.get('failure_class')==kind for r in subset)
                                           for kind in ('flight','control_boundary','infrastructure','analysis_or_data_quality')})
                cell['attempted']=cell['planned']-cell['missing']
                cell['accepted_fraction']=len(ok)/cell['attempted'] if cell['attempted'] else None
                cell['accepted_wilson95']=wilson(len(ok),cell['attempted']) if cell['attempted'] else None
                cell['flight_completion_fraction']=cell['flight_completed']/cell['attempted'] if cell['attempted'] else None
                cell['flight_completion_wilson95']=wilson(cell['flight_completed'],cell['attempted']) if cell['attempted'] else None
                for metric in ('rmse_tracking','iae_tracking_rad','rmse_steady','control_rms','control_peak','protected_fraction',
                               'native_highband_rms','common_0_20hz_rms'):
                    cell[metric+'_mean']=np.mean([r[metric] for r in ok],axis=0).tolist() if ok else None
                if ok:
                    cell['tv_per_s_mean']=np.mean([r['tv_actual_updates']['tv_per_s'] for r in ok],axis=0).tolist()
                    cell['kernel_median_ns_mean']=float(np.mean([r['kernel_cost']['median_ns'] for r in ok]))
                    cell['module_median_ns_mean']=float(np.mean([r['module_cost']['median_ns'] for r in ok]))
                    cell['update_hz_range']=[min(r['update_hz'] for r in ok),max(r['update_hz'] for r in ok)]
                    cell['max_clock_offset_s']=max(abs(r['torque_clock_offset_s']) for r in ok)
                    cell['unrecovered']=sum(r['recovery'].get('censored',False) for r in ok)
                    cell['motor_missing_total']=sum(r['motor_original']['missing'] for r in ok)
                    for metric in ('mixer_saturation_fraction','kernel_wall_ns_per_sim_second','module_wall_ns_per_sim_second'):
                        cell[metric+'_mean']=float(np.mean([r[metric] for r in ok]))
                    for cost in ('kernel_cost','module_cost'):
                        for quantile in ('p95_ns','p99_ns'):
                            cell[cost+'_'+quantile+'_mean']=float(np.mean([r[cost][quantile] for r in ok]))
                cells.append(cell)
            comparisons=[(1,2)] if group=='A' else [(0,1),(0,2),(1,2)]
            for left,right in comparisons:
                a={r['seed']:r for r in rows if (r['scene'],r['group'],r['mode'])==(scene,group,left) and r['success']}
                b={r['seed']:r for r in rows if (r['scene'],r['group'],r['mode'])==(scene,group,right) and r['success']}
                seeds=sorted(set(a)&set(b))
                delta=[np.mean(b[s]['rmse_tracking'])-np.mean(a[s]['rmse_tracking']) for s in seeds]
                contrast=dict(scene=scene,group=group,left=left,right=right,seeds=seeds,
                              interpretation='right minus left; negative means lower mean 3-axis RMSE')
                if len(delta)>=2:
                    contrast.update(paired_interval(delta))
                    if pilot:contrast['anticipated_n20_normal_halfwidth']=float(1.96*np.std(delta,ddof=1)/np.sqrt(20))
                else:contrast['unavailable']='fewer than two complete successful seed pairs'
                contrasts.append(contrast)
    # Actual explicit RNG acceptance: first increments compare same seed within
    # each scenario. Background GPS/mag/baro are NOT claimed independently seeded.
    pairing=[]
    diversity=[]
    correlations=[]
    for scene in SCENES:
        streams={}
        for seed in sorted({j['seed'] for j in jobs}):
            matching=[r for r in rows if r['scene']==scene and r['seed']==seed and r['success']]
            if matching:
                samples=np.array([r['imu_initial_realization'] for r in matching])
                gap=float(np.max(np.abs(samples-samples[0])))
                prefixes=[]
                for row in matching:
                    raw=np.genfromtxt(Path(row['path']).parent/'imu_innovations.csv',delimiter=',',names=True,max_rows=5000)
                    prefixes.append(np.column_stack([raw[k] for k in ('gx','gy','gz')]))
                count=min(map(len,prefixes));prefixes=np.array([v[:count] for v in prefixes])
                prefix_gap=float(np.max(np.abs(prefixes-prefixes[0])))
                streams[seed]=prefixes[0]
                pairing.append(dict(scene=scene,seed=seed,runs=len(matching),max_initial_imu_delta=gap,
                                    paired_gyro_prefix_samples=count,max_gyro_prefix_delta=prefix_gap,
                                    paired_rng_confirmed=gap<1e-10 and prefix_gap<1e-10 and count==5000))
        representatives={r['seed']:np.asarray(r['imu_initial_realization']) for r in rows if r['scene']==scene and r['success']}
        keys=sorted(representatives)
        differences=[float(np.max(np.abs(representatives[a]-representatives[b]))) for i,a in enumerate(keys) for b in keys[i+1:]]
        diversity.append(dict(scene=scene,seeds=keys,minimum_between_seed_difference=min(differences) if differences else None,
                              distinct_realizations_confirmed=bool(differences) and min(differences)>1e-10))
        for i,left in enumerate(keys):
            for right in keys[i+1:]:
                a=streams[left];b=streams[right];count=min(len(a),len(b))
                correlations.append(dict(scene=scene,left_seed=left,right_seed=right,samples=count,
                    gyro_prefix_correlation=[float(np.corrcoef(a[:count,j],b[:count,j])[0,1]) for j in range(3)]))
    result=dict(planned=len(jobs),attempted=sum(not r.get('missing',False) for r in rows),
                success=sum(r['success'] for r in rows),cells=cells,contrasts=contrasts,seed_audit=pairing,
                seed_diversity=diversity,
                cross_seed_noise_correlation=correlations,
                correlation_note='Descriptive first-5000-sample cross-stream Pearson correlation, not proof/test of independence; flight remains the experimental unit.',
                unchanged_sensor_filter_estimator_parameters=fixed_parameters,
                all_planned_present=not any(r.get('missing',False) for r in rows),
                independence_scope=f"{len({j['seed'] for j in jobs})} planned seeded IMU/phase streams per scene; actual available counts in seed_audit/cells. Fresh processes; other plugins keep original default engines and host scheduling is not randomized by seed.")
    if any(j.get('formal') for j in jobs):
        result['formal_source_heads']=sorted({r['source_head'] for r in rows if 'source_head' in r})
        result['formal_binaries']=sorted({r['binary_sha256'] for r in rows if 'binary_sha256' in r})
        if len(result['formal_source_heads'])!=1 or len(result['formal_binaries'])!=1:
            raise RuntimeError('Formal source/firmware drift or absent evidence')
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'runs.json').write_text(json.dumps(rows,indent=2)+'\n')
    if os.environ.get('M10_PLOT_PYTHON'):
        sys.path.append(os.environ['M10_PLOT_PYTHON'])
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['svg.hashsalt']='m10-frozen'
    fig,axs=plt.subplots(2,3,figsize=(12,6),constrained_layout=True)
    for ax,scene in zip(axs.flat,SCENES):
        values=[];labels=[]
        for group,modes in [('A',(1,2)),('B',(0,1,2))]:
            for mode in modes:
                labels.append(group+'/'+('PID','ESTA','ISTA')[mode])
                values.append([float(np.mean(r['rmse_tracking'])) for r in rows if r['success'] and (r['scene'],r['group'],r['mode'])==(scene,group,mode)])
        ax.boxplot([v if v else [np.nan] for v in values],labels=labels,showmeans=True)
        if not any(values):
            ax.text(.5,.5,'No accepted runs',ha='center',va='center',transform=ax.transAxes)
            ax.set_ylim(0,.01)
        ax.tick_params(axis='x',rotation=35);ax.set_title(scene);ax.set_ylabel('Mean axis rate RMSE [rad/s]');ax.grid(axis='y',alpha=.3)
    fig.suptitle('Iris SITL: accepted runs only; see failure ledger and paired contrasts')
    fig.savefig(out/'rmse.svg');fig.savefig(out/'rmse.png',dpi=160);plt.close(fig)
    fig,axs=plt.subplots(2,2,figsize=(12,8),constrained_layout=True)
    colors=('tab:blue','tab:orange','tab:green')
    for mode in (0,1,2):
        c=[next(x for x in cells if (x['scene'],x['group'],x['mode'])==(s,'B',mode)) for s in SCENES]
        x=np.arange(len(SCENES))+(mode-1)*.24
        for ax,values,title in [
                (axs[0,0],[z['accepted_fraction'] if z['accepted_fraction'] is not None else np.nan for z in c],'Accepted / attempted (missing shown separately)'),
                (axs[0,1],[np.mean(z.get('tv_per_s_mean',[np.nan])) for z in c],'Native-update mean-axis TV/s'),
                (axs[1,0],[np.mean(z['control_rms_mean']) if z['control_rms_mean'] is not None else np.nan for z in c],'Mean-axis normalized command RMS'),
                (axs[1,1],[z.get('kernel_median_ns_mean',np.nan)/1000 for z in c],'Mean of per-run kernel wall medians [us]')]:
            ax.bar(x,values,width=.23,color=colors[mode],label=('PID','ESTA','ISTA')[mode])
            ax.set_xticks(np.arange(len(SCENES)),SCENES,rotation=25);ax.set_title(title);ax.grid(axis='y',alpha=.25)
    axs[0,0].set_ylim(0,1.05);axs[0,0].legend();fig.suptitle('Engineering group B; failures retained, performance conditional on acceptance')
    fig.savefig(out/'engineering.svg');fig.savefig(out/'engineering.png',dpi=160);plt.close(fig)
    fig,axs=plt.subplots(2,3,figsize=(12,6),constrained_layout=True)
    for ax,scene in zip(axs.flat,SCENES):
        for mode in (0,1,2):
            subset=[r for r in rows if r['success'] and (r['scene'],r['group'],r['mode'])==(scene,'B',mode)]
            spectra=[];frequency=None
            for row in subset:
                with np.load(Path(row['path']).parent/'m09_spectra.npz') as data:
                    f=data['common_hz'];mask=f<=20
                    if frequency is not None and not np.array_equal(f[mask],frequency):
                        raise RuntimeError('Different common-band frequency grids')
                    frequency=f[mask];spectra.append(data['common_psd'][mask].mean(axis=1))
            if spectra:
                ax.semilogy(frequency,np.maximum(np.mean(spectra,axis=0),1e-30),
                            color=colors[mode],label=('PID','ESTA','ISTA')[mode])
        ax.set_title(scene);ax.set_xlabel('Frequency [Hz]');ax.set_ylabel('Mean-axis command PSD [1/Hz]')
        ax.set_xlim(0,20);ax.grid(alpha=.25)
    axs[0,0].legend()
    fig.suptitle('Group B: same anti-aliased 0-20 Hz band; mean of accepted runs')
    fig.savefig(out/'common_psd.svg');fig.savefig(out/'common_psd.png',dpi=160);plt.close(fig)
    # Matplotlib emits trailing blanks in SVG path data. Normalize whitespace
    # without changing SVG tokens so generated artifacts pass diff review.
    for path in out.glob('*.svg'):
        path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines())+'\n')
    print(json.dumps({k:result[k] for k in ('planned','attempted','success','all_planned_present')},indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--pilot',action='store_true')
    a=p.parse_args();summarize(a.root.resolve(),a.output.resolve(),a.pilot)
