"""Read-only outcome aggregation; requires SHA-bound metrics and independent replay."""
import argparse
import json
from pathlib import Path
import numpy as np
from common import design, jobs, fingerprint, validate_manifest, CONFIG, qualification
from paired_stats import summarize


def outcome_rows(outcomes):
    manifest = jobs()
    if len(outcomes) != 320:
        raise ValueError('Need all320 outcomes')
    rows = []
    for job, outcome in zip(manifest, outcomes):
        if any(outcome.get(k) != job[k] for k in ('id','task','seed','candidate','mode','axes')):
            raise ValueError('Wrong/reordered outcome')
        row = {k: outcome[k] for k in ('id','task','seed','candidate','status')}
        if outcome['status'] != 'accepted':
            if any(k in outcome for k in ('rmse_m_s','J','metrics_path')):
                raise ValueError('Missing/failed outcome must not fabricate accepted metrics')
            row['reason'] = outcome.get('reason')
        else:
            mpath, rpath = Path(outcome['metrics_path']), Path(outcome['replay_metrics_path'])
            if not mpath.is_absolute() or not rpath.is_absolute() or mpath.resolve() == rpath.resolve():
                raise ValueError('Independent absolute replay path required')
            if fingerprint(mpath) != outcome['metrics_sha256'] or fingerprint(rpath) != outcome['replay_metrics_sha256']:
                raise ValueError('Changed metrics or replay')
            m, replay = json.loads(mpath.read_text()), json.loads(rpath.read_text())
            if m != replay or m.get('accepted') is not True or m.get('job') != job:
                raise ValueError('Unaccepted, wrong job, or differing independent replay')
            binding = m['formal_binding']
            frozen = json.loads((CONFIG/'frozen.json').read_text())
            if (binding['execution_sha256'] != fingerprint(CONFIG/'execution.json')
                or binding['frozen_sha256'] != fingerprint(CONFIG/'frozen.json')
                or binding['firmware_sha256'] != qualification()['firmware_sha256']
                or binding['source_head'] != qualification()['source_head']):
                raise ValueError('Wrong formal source/asset binding')
            if not 63.96 <= m['diagnostic']['seconds'] <= 64.04:
                raise ValueError('Wrong primary window')
            row['rmse_m_s'] = m['diagnostic']['error']['rmse']
            # Preserve secondary outputs/units, not just the primary scalar.
            row['secondary'] = {k:m[k] for k in ('position_rmse','yaw_rmse','height','diagnostic','spectral_summary','mixer','local_output','attitude_output')}
            row['metrics_path'] = str(mpath)
            row['metrics_sha256'] = outcome['metrics_sha256']
        rows.append(row)
    sources = {json.loads(Path(x['metrics_path']).read_text())['formal_binding']['source_head'] for x in outcomes if x['status']=='accepted'}
    if len(sources) > 1:
        raise ValueError('Mixed formal source commits')
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outcomes', type=Path, default=CONFIG/'outcomes_unattempted.json')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    validate_manifest()
    rows = outcome_rows(json.loads(args.outcomes.read_text()))
    result = summarize(rows)
    result['rows'] = rows
    result['secondary_descriptive'] = secondary_summary(rows)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k:result[k] for k in ('planned','attempted','accepted')}))


def secondary_summary(rows):
    """Equal run weights, explicit units; not per-frame pooled inference."""
    groups = {}
    for task in ('H','V'):
        for candidate in ('PID','X','Y','Z','XY','XZ','YZ','XYZ'):
            selected = [r for r in rows if r['task']==task and r['candidate']==candidate and r['status']=='accepted']
            values = {}
            for r in selected:
                s=r['secondary'];d=s['diagnostic'];c=d['cadence']
                fields=dict(position_rmse_m=s['position_rmse'],yaw_rmse_rad=s['yaw_rmse'],
                    height_rmse_m=s['height']['rmse'],height_peak_m=s['height']['max_abs'],
                    correction_tv_m_s3=s['spectral_summary']['correction_tv_per_second'],
                    acceleration_tv_m_s3=(np.asarray(d['acceleration_tv'])/64).tolist(),
                    normalized_thrust_tv_per_s=(np.asarray(d['normalized_thrust_tv'])/64).tolist(),
                    common_0_7hz_rms_m_s2=s['spectral_summary']['common_0_7hz_rms'],
                    constraint_fraction=d['constraint_fraction'],update_hz=c['update_hz'])
                for component in ('path_ns','module_ns'):
                    fields[component+'_us_per_sim_second']=c['host_us_per_sim_second'][component]
                    for percentile in ('median','p95','p99','max'):
                        fields[component+'_already_us_'+percentile]=c['host_cost'][component]['update'][percentile]
                for key,value in fields.items():
                    a=np.asarray(value,dtype=float)
                    if not np.all(np.isfinite(a)):raise ValueError('Nonfinite secondary metric '+key)
                    values.setdefault(key,[]).append(a)
            groups[task+'/'+candidate]=dict(n=len(selected),
                means={key:np.mean(value,axis=0).tolist() for key,value in values.items()},
                note='Run-level descriptive means, including means of within-run timing percentiles; NOT pooled CPU percentiles or energy')
    return groups


if __name__ == '__main__':
    main()
