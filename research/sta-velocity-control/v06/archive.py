#!/usr/bin/env python3
"""Read-only raw batch audit and small repository evidence; never reaccept failures."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
from pyulog import ULog

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v): p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--source',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); source=args.source.resolve(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    ledger=json.loads((source/'ledger.json').read_text()); summary=dict(ledger=ledger,diagnostics=[])
    for attempt in ledger['attempts']:
        run=Path(attempt['directory']); record=json.loads((run/'result.json').read_text())
        target=out/run.name; target.mkdir()
        for name in ('result.json','job.json','authorization.json','runtime_parameters_start.json','runtime_parameters_end.json',
                     'world_process.json','model_manifest.json','xyz_metrics.json','xyz_core_metrics.json','v00_metrics.json'):
            if (run/name).is_file(): shutil.copyfile(run/name,target/name)
        logs=[]
        for entry in record['logs']:
            path=Path(entry['archive']); assert digest(path)==entry['sha256']
            u=ULog(str(path)); item=dict(ulog=entry,dropouts=len(u.dropouts),corruption=bool(getattr(u,'file_corruption',False)))
            try: d=u.get_dataset('sta_velocity_ctrl_status').data
            except (KeyError,IndexError): logs.append(item); continue
            m=d['armed'].astype(bool)&d['enabled'].astype(bool)
            item.update(samples=len(d['timestamp']),armed_enabled=int(m.sum()))
            for field in ('requested_mode','effective_mode','requested_axes','effective_axes','pid_axes','active_axes','committed_axes',
                          'config_pending','sta_fault','fault','first_fail','retry_result','timing','z_phase'):
                values,counts=np.unique(d[field][m],return_counts=True)
                item[field]={str(int(v)):int(n) for v,n in zip(values,counts)}
            logs.append(item)
        summary['diagnostics'].append(dict(run=str(run),accepted=attempt['status']=='accepted',logs=logs))
    save(out/'summary.json',summary)
    shutil.copyfile(source/'ledger.json',out/'ledger.json')
    files=sorted(p for p in source.rglob('*') if p.is_file() and not p.is_symlink())
    (out/'raw_artifacts.sha256').write_text(''.join(f'{digest(p)}  {p}\n' for p in files))
    print(json.dumps(dict(attempts=len(ledger['attempts']),accepted=sum(a['status']=='accepted' for a in ledger['attempts']),raw_files=len(files),summary=str(out/'summary.json'))))

if __name__=='__main__': main()
