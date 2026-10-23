"""Describe the qualified R03 gates separately; never rerank/reclassify runs."""
import argparse,hashlib,json,statistics,math
from pathlib import Path

ROOT=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016')
REPO=Path('/home/yr/Desktop/Codev-autopilot')

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def read(path):return json.loads(Path(path).read_text())

def mean(values):
    if isinstance(values[0],list):return [mean([v[i] for v in values]) for i in range(len(values[0]))]
    return statistics.mean(values)

def collect():
    result=dict(stage='R03',development_only=True,formal_significance_claim=False,gate_results=[],input_sha256={},
        interpretation=['Three paired IMU seeds per algorithm/task, not a formal holdout experiment.',
          'A/B/C retain revision09 identity; D uses revision11. No pooled same-binary 36-run claim.',
          'Historical accepted partial batches do not fill the accepted four-gate design.',
          'Common external trajectories do not imply identical actual velocity setpoints.',
          'TV is not energy. Host wall-clock cost is not flight-controller CPU.',
          'Only IMU noise is explicitly seeded; other randomness and host scheduling remain limitations.'])
    for gate,revision in [('A','09'),('B','09'),('C','09'),('D','11')]:
        root=ROOT/f'R03_revision{revision}'/gate
        receipt=read(root/'gate_pass.json');ledger=read(root/'batch01/ledger.json')
        if (not receipt.get('success') or receipt['accepted']!=9 or receipt['independent_replays']!=9
                or receipt['paired_checks']!=6 or not ledger.get('success') or ledger.get('unattempted')
                or len(ledger['attempts'])!=9):raise ValueError('Incomplete gate '+gate)
        if ledger.get('parameter_restore_exact') is not True or ledger.get('remaining_simulators')!=[]:
            raise ValueError('Incomplete parameter restoration or simulator cleanup')
        records=[]
        for item in ledger['attempts']:
            run=Path(item['directory']);m=read(run/'r03_metrics.json');r=read(run/'result.json')
            if not m.get('accepted') or not r.get('success') or item['status']!='accepted':raise ValueError('Unaccepted run')
            if sha(run/'r03_metrics.json')!=item['metrics_sha256']:raise ValueError('Original metrics changed')
            for name in ('r03_metrics.json','result.json','parameter_restore.json','job.json','spectra.json'):
                result['input_sha256'][str(run/name)]=sha(run/name)
            for log in r['logs']:
                if sha(log['archive'])!=log['sha256']:raise ValueError('Original log changed')
                result['input_sha256'][log['archive']]=log['sha256']
            d=m['diagnostic']
            if not math.isclose(d['J'],statistics.mean(d['error']['rmse']),rel_tol=1e-14,abs_tol=1e-16):
                raise ValueError('J is not the arithmetic mean of the three axis RMSEs')
            if not all(m['baseline_checks'].values()):raise ValueError('Failed baseline checks')
            records.append(dict(id=item['job']['id'],seed=item['job']['seed'],algorithm=item['job']['candidate'],
                rmse_m_s=d['error']['rmse'],mean_error_m_s=d['error']['mean'],variance=d['error']['variance'],
                J_m_s=d['J'],position_rmse_m=m['position_rmse'],yaw_rmse_rad=m['yaw_rmse'],
                correction_TV_per_s=d['correction_tv_per_second'],acceleration_TV_per_s=d['acceleration_tv_per_second'],
                normalized_thrust_TV_per_s=d['normalized_thrust_tv_per_second'],constraint_fraction=d['constraint_fraction'],
                max_constraint_s=d['maximum_continuous_constraint_s'],nu_peak=d['nu_peak'],height=m['height'],
                actual_updates=d['actual_updates'],samples=d['samples'],seconds=d['seconds'],
                update_hz=m['spectral_summary']['update_hz'],common_band_rms=m['spectral_summary']['common_0_7hz_rms'],
                host_cost=m['host_cost'],lifecycle=m['lifecycle'],actual_output=m['actual_output'],mixer=m['mixer'],
                position_log=m['position_log'],rate_actuator=m['rate_actuator'],
                upstream_time_slip=m.get('upstream_time_slip'),baseline_checks=m['baseline_checks'],
                position_clock_binding=m.get('position_clock_binding'),
                upstream_timing=m.get('upstream_timing'),
                common_band_notes=m['spectral_summary']['notes'],
                original_metrics=str(run/'r03_metrics.json')))
        groups={}
        for algorithm in ('PID','ESTA','RSTA'):
            rows=[r for r in records if r['algorithm']==algorithm]
            if len(rows)!=3 or len({r['seed'] for r in rows})!=3:raise ValueError('Wrong paired sample count')
            keys=('rmse_m_s','J_m_s','position_rmse_m','yaw_rmse_rad','correction_TV_per_s',
                  'acceleration_TV_per_s','normalized_thrust_TV_per_s','constraint_fraction','max_constraint_s')
            groups[algorithm]=dict(n=3,means={k:mean([r[k] for r in rows]) for k in keys},
                J_sample_sd=statistics.stdev([r['J_m_s'] for r in rows]))
        paired=[]
        for candidate in ('ESTA','RSTA'):
            for row in [r for r in records if r['algorithm']==candidate]:
                pid=next(r for r in records if r['algorithm']=='PID' and r['seed']==row['seed'])
                paired.append(dict(candidate=candidate,seed=row['seed'],J_difference=row['J_m_s']-pid['J_m_s'],
                    rmse_difference=[a-b for a,b in zip(row['rmse_m_s'],pid['rmse_m_s'])]))
        for path in (root/'gate_pass.json',root/'batch01/ledger.json',root/'batch01/journal.jsonl',
                     root/'replay01/summary.json',root/'qualification01/evidence.json',
                     REPO/f'research/sta-velocity-control/regularized_sta/r03_revision{revision}/gates/{gate}/frozen.json'):
            result['input_sha256'][str(path)]=sha(path)
        result['gate_results'].append(dict(gate=gate,revision=revision,source_head=receipt['source_head'],
            firmware_sha256=receipt['firmware_sha256'],accepted=9,replays=9,paired_checks=6,
            groups=groups,paired_differences=paired,runs=records))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise ValueError('Fresh output required')
    result=collect()
    with args.output.open('x') as f:json.dump(result,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
    print(json.dumps(dict(gates=len(result['gate_results']),runs=36,input_files=len(result['input_sha256']),output_sha256=sha(args.output))))
