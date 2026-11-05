"""Archive compact evidence and original data fingerprints; no selection or flight."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from audit import digest, PROTOCOL


def main():
    p = argparse.ArgumentParser()
    p.add_argument('root', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    batch = args.root/'training01'
    ledger = json.loads((batch/'ledger.json').read_text())
    summary = dict(stage='V08', status='needs_revision', source_head=ledger['source_head'],
                   training_planned=24, training_attempted=len(ledger['attempts']),
                   training_accepted=0, training_failed=0, training_unexecuted=24-len(ledger['attempts']),
                   validation_attempted=0, pilot_attempted=0, formal_attempted=0,
                   selected_candidates=None, thresholds_changed=False, failed_run_regraded=False,
                   flights=[], raw_logs=[], independent_replays=0, commands=[])
    for item in ledger['attempts']:
        run = Path(item['directory'])
        r = json.loads((run/'result.json').read_text())
        small = out/run.name
        small.mkdir()
        names = ['result.json','job.json','runtime_parameters_start.json','model_manifest.json']
        row = dict(attempt=item['attempt'], job=item['job'], status=item['status'],
                   directory=str(run), error=r.get('error'), complete_task=bool(r['success']))
        if item['status'] == 'accepted':
            summary['training_accepted'] += 1
            names += ['xyz_metrics.json','runtime_parameters_end.json']
            if digest(run/'xyz_metrics.json') != item['metrics_sha256']:
                raise ValueError('Metrics fingerprint changed')
            m = json.loads((run/'xyz_metrics.json').read_text())
            if not m['accepted']: raise ValueError('Metrics/ledger disagree')
            row.update(rmse_xyz_m_per_s=m['diagnostic']['error']['rmse'],
                       correction_tv_per_second=m['spectral_summary']['correction_tv_per_second'])
        elif item['status'] == 'failed':
            summary['training_failed'] += 1
        else: raise ValueError('Unfinished attempt')
        for name in names: shutil.copyfile(run/name,small/name)
        for log in r['logs']:
            if digest(log['archive']) != log['sha256']: raise ValueError('Raw ULog changed')
            summary['raw_logs'].append(log)
        summary['flights'].append(row)
    replay = json.loads((args.root/'replay01/evidence.json').read_text())
    if not replay['success'] or len(replay['commands']) != summary['training_accepted']:
        raise ValueError('Missing independent replay')
    summary['independent_replays'] = len(replay['commands'])
    evidence = [
        (batch/'ledger.json','ledger.json'),
        (args.root/'verification_committed01/evidence.json','verification_committed01.json'),
        (args.root/'training01_command.json','training01_command.json'),
        (args.root/'failure_audit01.json','failure_audit01.json'),
        (args.root/'replay01/evidence.json','replay01.json'),
    ]
    for src,name in evidence: shutil.copyfile(src,out/name)
    for name,argv in [
        ('audit_tests',[sys.executable,str(Path(__file__).with_name('test_audit.py'))]),
        ('tuning_regression',[sys.executable,str(PROTOCOL/'test_tuning.py')]),
    ]:
        with (out/(name+'.log')).open('x') as stream:
            code=subprocess.run(argv,env=os.environ.copy(),stdout=stream,stderr=subprocess.STDOUT).returncode
        summary['commands'].append(dict(argv=argv,exit_code=code))
        if code: raise ValueError(name+' failed')
    index = []
    for path in sorted(batch.rglob('*')):
        if path.is_file() and not path.is_symlink():
            index.append(f'{digest(path)}  {path}\n')
    (out/'original_artifacts.sha256').write_text(''.join(index))
    summary['original_artifact_count']=len(index)
    summary['original_index_sha256']=digest(out/'original_artifacts.sha256')
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (out/'snapshot.sha256').write_text(''.join(f'{digest(f)}  {f.relative_to(out)}\n'
        for f in sorted(out.rglob('*')) if f.is_file() and f.name!='snapshot.sha256'))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('flights','raw_logs')},indent=2))


if __name__=='__main__':main()
