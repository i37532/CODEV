"""Compact immutable evidence copies; large raw logs remain outside Git."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('batch',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--replay',type=Path,required=True)
    parser.add_argument('--verification',type=Path,required=True)
    parser.add_argument('--command',type=Path,required=True)
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False)
    ledger=json.loads((args.batch/'ledger.json').read_text())
    summary=dict(source_head=ledger['source_head'],planned=ledger['planned'],attempted=len(ledger['attempts']),
                 success=ledger['success'],accepted=0,failed=0,flights=[],raw_logs=[],formal_attempted=0)
    for item in ledger['attempts']:
        run=Path(item['directory']);record=json.loads((run/'result.json').read_text())
        small=out/run.name;small.mkdir()
        row=dict(attempt=item['attempt'],job=item['job'],status=item['status'],directory=str(run),error=record.get('error'))
        names=['result.json','job.json','runtime_parameters_start.json','runtime_parameters_end.json','model_manifest.json',
               'pilot_model_manifest.json','loaded_model_preflight.json','validation_pair.json','pilot_pair.json','force_trigger_origin.json']
        if item['status']=='accepted':
            summary['accepted']+=1
            if digest(run/'xyz_metrics.json')!=item['metrics_sha256']:raise ValueError('Changed accepted metrics')
            m=json.loads((run/'xyz_metrics.json').read_text())
            if not m['accepted']:raise ValueError('Ledger/metrics disagreement')
            names.append('xyz_metrics.json')
            row.update(rmse_xyz_m_per_s=m['diagnostic']['error']['rmse'],correction_tv_per_second=m['spectral_summary']['correction_tv_per_second'])
        elif item['status']=='failed':summary['failed']+=1
        else:raise ValueError('Batch still active')
        for name in names:
            if (run/name).is_file():shutil.copyfile(run/name,small/name)
        for log in record['logs']:
            if digest(log['archive'])!=log['sha256']:raise ValueError('Raw ULog fingerprint mismatch')
            summary['raw_logs'].append(log)
        summary['flights'].append(row)
    replay=json.loads(args.replay.read_text())
    if not replay['success'] or len(replay['commands'])!=summary['accepted']:raise ValueError('Incomplete independent replay')
    for src,name in [(args.batch/'ledger.json','ledger.json'),(args.replay,'replay.json'),(args.verification,'verification.json'),(args.command,'command.json')]:
        shutil.copyfile(src,out/name)
    index=[f'{digest(f)}  {f}\n' for f in sorted(args.batch.rglob('*')) if f.is_file() and not f.is_symlink()]
    (out/'original_artifacts.sha256').write_text(''.join(index))
    summary.update(original_artifacts=len(index),original_index_sha256=digest(out/'original_artifacts.sha256'),independent_replays=len(replay['commands']))
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (out/'snapshot.sha256').write_text(''.join(f'{digest(f)}  {f.relative_to(out)}\n' for f in sorted(out.rglob('*')) if f.is_file() and f.name!='snapshot.sha256'))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('flights','raw_logs')},indent=2))

if __name__=='__main__':main()
