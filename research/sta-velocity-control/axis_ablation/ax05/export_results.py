"""Export already-frozen AX04 statistics and figures, without flights or tuning."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from audit_results import digest, read, save, validate_complete, ROOT

GROUPS = ('PID', 'X', 'Y', 'Z', 'XY', 'XZ', 'YZ', 'XYZ')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--external', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); b = a.external
    s = read(b / 'summary.json'); audit = read(b / 'audit01/evidence.json')
    replay = read(b / 'replay01/evidence.json'); ledger = read(b / 'formal01/ledger.json')
    qpath = b.parent / 'AX04/qualified_source.json'
    validate_complete(ledger, read(ROOT / 'ax04/manifest.json'), read(qpath))
    if (not s['complete_all_accepted'] or s['accepted'] != 320 or not audit['success']
            or audit['decoded_ulogs'] != 640 or len(audit['runs']) != 320
            or not replay['success'] or len(replay['commands']) != 320
            or any(c['exit_code'] or not c.get('metrics_values_identical') for c in replay['commands'])
            or any(e['ledger_sha256'] != digest(b / 'formal01/ledger.json') for e in (audit, replay))):
        raise ValueError('Incomplete independent evidence')
    a.output.mkdir(parents=True, exist_ok=False)
    save(a.output / 'summary.json', {k:v for k,v in s.items() if k != 'rows'})
    rows = []
    for r in s['rows']:
        sec = r['secondary']; d = sec['diagnostic']
        rows.append(dict(**{k:v for k,v in r.items() if k != 'secondary'}, J=float(np.mean(r['rmse_m_s'])),
            position_rmse_m=sec['position_rmse'], height=sec['height'], yaw_rmse_rad=sec['yaw_rmse'],
            error_mean_m_s=d['error']['mean'], error_std_m_s=d['error']['std'],
            nu_peak=d['nu_peak'], correction_tv_m_s3=sec['spectral_summary']['correction_tv_per_second'],
            acceleration_tv_m_s3=(np.asarray(d['acceleration_tv'])/64).tolist(),
            normalized_thrust_tv_per_s=(np.asarray(d['normalized_thrust_tv'])/64).tolist(),
            common_0_7hz_rms_m_s2=sec['spectral_summary']['common_0_7hz_rms'],
            constraint_fraction=d['constraint_fraction'], cadence=d['cadence'],
            local_output=sec['local_output'], attitude_output=sec['attitude_output']))
    save(a.output / 'metrics.json', rows)
    save(a.output / 'actual_states.json', audit['runs'])
    save(a.output / 'ulog_index.json', [{k:r[k] for k in ('archive','sha256','bytes','dropouts','corruption')}
        for r in audit['ulogs']])
    inputs = [b / r for r in ('summary.json','outcomes.json','formal01/ledger.json','formal01.stdout.log',
        'replay01/evidence.json','audit01/evidence.json','audit01/artifacts.json',
        'authorization01.json','isolate.sh','isolation_build01.log','preflight01/evidence.json','preflight02/evidence.json')]
    inputs += [qpath, ROOT / 'ax04' / 'manifest.json', ROOT / 'ax04' / 'execution.json', ROOT / 'ax04' / 'frozen.json']
    receipt = dict(source_head=ledger['source_head'], firmware_sha256=ledger['firmware_sha256'],
        new_flights=0, accepted=320, pairs=280, decoded_ulogs=640,
        batch_artifacts=audit['batch_artifacts'], replay_bytes_identical=sum(c['metrics_comparison']['bytes_identical'] for c in replay['commands']),
        replay_count_order_only=sum(c['metrics_comparison']['counts_order_only'] for c in replay['commands']),
        inputs={str(f):dict(sha256=digest(f),bytes=f.stat().st_size) for f in inputs})
    save(a.output / 'evidence_index.json', receipt)
    # Graph the registered contrasts, not an unpaired group-mean CI.
    fig, axs = plt.subplots(1, 2, figsize=(11, 5), sharey=True, layout='constrained')
    for ax, task in zip(axs, ('H','V')):
        c = [s['primary_comparisons'][f'{task}/{g}-PID'] for g in GROUPS[1:]]
        mu = np.array([v['mean_difference_m_s'] for v in c]); ci = np.array([v['ci_bonferroni14'] for v in c])
        ax.errorbar(mu, np.arange(7), xerr=np.array([mu-ci[:,0],ci[:,1]-mu]), fmt='o', capsize=4, color='#2166ac')
        ax.axvline(0, color='black', linewidth=1); ax.axvline(-.001, color='grey', linestyle='--', linewidth=1)
        ax.set_yticks(np.arange(7), GROUPS[1:]); ax.set_title(task + ' task: 20 paired seeds')
        ax.set_xlabel('J(configuration) - J(PID) [m/s]'); ax.grid(axis='x', alpha=.25)
    axs[0].invert_yaxis();fig.suptitle('Mean paired effects with 99.642857% Bonferroni bootstrap intervals\nNegative: lower error; dashed: -0.001 m/s point threshold')
    fig.savefig(a.output / 'paired_effects.png', dpi=160);plt.close(fig)
    fig, axs = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
    colors = ('#2166ac','#e08214','#8e44ad')
    for ti, task in enumerate(('H','V')):
        for axis, label in enumerate(('X','Y','Z')):
            x = np.arange(8)+(axis-1)*.24
            axs[ti,0].bar(x,[s['descriptive'][f'{task}/{g}']['xyz_rmse_mean'][axis] for g in GROUPS],.24,label=label,color=colors[axis])
            axs[ti,1].bar(x,[s['secondary_descriptive'][f'{task}/{g}']['means']['correction_tv_m_s3'][axis] for g in GROUPS],.24,label=label,color=colors[axis])
        for ax in axs[ti]:ax.set_xticks(np.arange(8), GROUPS);ax.legend(ncol=3);ax.grid(axis='y',alpha=.2)
        axs[ti,0].set_title(task+' per-axis velocity RMSE (run means)');axs[ti,0].set_ylabel('m/s')
        axs[ti,1].set_title(task+' correction TV / time (log scale, NOT energy)');axs[ti,1].set_ylabel('m/s^3');axs[ti,1].set_yscale('log')
    fig.savefig(a.output / 'axes_error_tv.png',dpi=160);plt.close(fig)
    lines=['# AX05 全组次指标（运行均值）','',
        '每格n=20；完整逐轮结果见metrics.json，全部主比较/区间/探索性交互见summary.json。',
        '位置/高度/yaw为原90–92秒观测窗；V高度相对固定2.5m的偏差含命令升降，不等于高度目标跟踪误差，后者看位置Z。',
        'TV按64秒主窗真实更新；共同带宽RMS单位m/s²。宿主耗时为每轮分位数的均值（µs），不是合并分位数/板级CPU。','']
    for task in ('H','V'):
        lines += [f'## {task}','', '| 配置 | X/Y/Z速度RMSE(m/s) | X/Y/Z位置RMSE(m) | yaw RMSE(rad) | 固定2.5m高度偏差RMSE(m) | X/Y/Z纠偏TV/T(m/s³) | 核p95 / 模块p95(µs) |', '|---|---|---|---:|---:|---|---|']
        for g in GROUPS:
            k=f'{task}/{g}';d=s['descriptive'][k];m=s['secondary_descriptive'][k]['means']
            vec=lambda v:'/'.join(f'{x:.6f}' for x in v)
            lines.append(f"| {g} | {vec(d['xyz_rmse_mean'])} | {vec(m['position_rmse_m'])} | {m['yaw_rmse_rad']:.7f} | {m['height_rmse_m']:.6f} | {vec(m['correction_tv_m_s3'])} | {m['path_ns_already_us_p95']:.3f} / {m['module_ns_already_us_p95']:.3f} |")
        lines += ['', '| 配置 | 总加速度TV/T(m/s³) | 归一化推力TV/T(s⁻¹) | 共同0–7Hz纠偏RMS(m/s²) | 约束比例 | 真实更新Hz |', '|---|---|---|---|---:|---:|']
        for g in GROUPS:
            m=s['secondary_descriptive'][f'{task}/{g}']['means']
            lines.append(f"| {g} | {vec(m['acceleration_tv_m_s3'])} | {vec(m['normalized_thrust_tv_per_s'])} | {vec(m['common_0_7hz_rms_m_s2'])} | {m['constraint_fraction']:.6f} | {m['update_hz']:.4f} |")
        lines += ['']
    with (a.output/'SECONDARY_CN.md').open('x') as stream:stream.write('\n'.join(lines).rstrip()+'\n')
    save(a.output/'files.json',{f.name:digest(f) for f in sorted(a.output.iterdir()) if f.is_file()})
    print(json.dumps(dict(success=True, exported_runs=len(rows), output=str(a.output))))


if __name__ == '__main__':main()
