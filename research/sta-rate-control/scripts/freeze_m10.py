#!/usr/bin/env python3
"""Generate small, auditable frozen parameter artifact after training/pilot.

Does not commit, launch flights, tune with pilot/test scores, or overwrite files.
"""
import argparse
import hashlib
import json
from pathlib import Path
from m10_design import equal_gains,TRAIN_SEEDS,PILOT_SEEDS,TEST_SEEDS,formal_jobs,fixed_parameters


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def freeze(train,pilot,summary,plugins,out):
    if out.exists():raise RuntimeError('Freeze target must not exist')
    selected=json.loads((train/'selected.json').read_text())
    training=json.loads((train/'summary.json').read_text())
    report=json.loads((summary/'summary.json').read_text())
    if training['attempted']!=36:raise RuntimeError('Training not complete')
    if not report['all_planned_present'] or report['attempted']!=90:raise RuntimeError('Pilot not complete')
    if not all(x['paired_rng_confirmed'] for x in report['seed_audit']):raise RuntimeError('Seed pairing failed')
    if not all(x['distinct_realizations_confirmed'] for x in report['seed_diversity']):raise RuntimeError('Different seed realization not demonstrated')
    if any(c['failure_classes']['infrastructure'] for c in report['cells']):
        raise RuntimeError('Unresolved pilot infrastructure failure')
    fixed=None
    for row in json.loads((summary/'runs.json').read_text()):
        if row.get('failure_class')=='analysis_or_data_quality':
            run=Path(row['path']).parent
            reviewed=json.loads((pilot/(run.name+'.adjudication.json')).read_text())
            if not (reviewed.get('retained_prearm_gap') and reviewed.get('accepted') is False
                    and reviewed['new_analysis_sha256']==sha(Path(row['path']))):
                raise RuntimeError('Unresolved pilot data validity failure')
        if not row['success']:continue
        params=fixed_parameters(json.loads((Path(row['path']).parent/'ulog_initial_parameters.json').read_text()))
        if fixed is None:fixed=params
        elif params!=fixed:raise RuntimeError('Non-experimental parameters drifted across pilot')
    if not fixed or len(fixed)<100:raise RuntimeError('No full fixed parameter evidence')
    selected['fixed_parameters']=fixed
    selected.update(protocol_version='v1-final-preformal',simulation_speed_requested=5.,A_parameters={str(m):equal_gains(m) for m in (1,2)},
                    training_seeds=TRAIN_SEEDS,pilot_seeds=PILOT_SEEDS,test_seeds=TEST_SEEDS,
                    test_runs_planned=len(formal_jobs(selected)),
                    sample_size_basis='20 pre-fixed seed blocks/scenario as feasibility budget; pilot halfwidths below are approximations, not demonstrated power.',
                    pilot_precision=[{k:c[k] for k in ('scene','group','left','right','n','sd_difference','anticipated_n20_normal_halfwidth') if k in c}
                                     for c in report['contrasts']],
                    paths=dict(training=str(train),pilot=str(pilot),pilot_summary=str(summary),plugins=str(plugins)),
                    evidence={str(p):sha(p) for p in (train/'selected.json',train/'summary.json',pilot/'jobs.json',
                                                      summary/'summary.json',plugins/'manifest.json')},
                    default_mode_unchanged=True,hardware_tested=False)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(selected,indent=2,ensure_ascii=False)+'\n')
    print('Frozen artifact',out,sha(out))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('train','pilot','summary','plugins','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();freeze(a.train.resolve(),a.pilot.resolve(),a.summary.resolve(),a.plugins.resolve(),a.output.resolve())
