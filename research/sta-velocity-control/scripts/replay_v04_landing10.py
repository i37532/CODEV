#!/usr/bin/env python3
"""Eight old batches, read-only source and isolated outputs; no historical regrade."""
import argparse
import json
from pathlib import Path
import subprocess
import time
from pyulog import ULog
from replay_v04_clock09 import ROOT, digest, copy_metadata, outcome
from v04_landing10 import replay
from v04_live_clock09 import replay as heading_replay
from v04_landing_live10 import LandingLiveLog
from analyze_v04_landing10 import analyze_offline
from v04_protocol09 import load_protocol


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve()
    records=[ROOT/'results01/run01_result.json']+[ROOT/f'results{n:02d}/run01.json' for n in range(3,10)]
    originals={};jobs=[]
    for file in records:
        record=json.loads(file.read_text());entry=max(record['logs'],key=lambda e:e['bytes'])
        source=Path(entry['archive']).parent
        if out==source or source in out.parents or out in source.parents:raise ValueError('Overlapping output')
        if digest(entry['archive'])!=entry['sha256']:raise ValueError('Old ULog modified')
        originals[str(file)]=digest(file)
        for item in source.rglob('*'):
            if item.is_file():originals[str(item)]=digest(item)
        jobs.append((record,entry,source))
    out.mkdir(parents=True,exist_ok=False)
    result=dict(kind='offline_component_replay_only',accepted=False,new_flights=0,
                historical_acceptance_changed=False,runs=[],input_fingerprints=originals)
    for number,(record,entry,source) in enumerate(jobs,1):
        target=out/f'series{number:02d}';copy_metadata(source,target)
        u=ULog(entry['archive']);events={e['name']:e['timestamp_us'] for e in record['events']}
        item=dict(series=number,raw_sha256=entry['sha256'],historical_success=record['success'],accepted=False)
        item['new_full_chain']=analyze_offline(target,load_protocol(),json.loads((target/'job.json').read_text()))
        # No fabricated context is supplied to full acceptance. Historical host event
        # is only a lower-bound proxy for this separately named component replay.
        if all(k in events for k in ('hover_start','hover_end','land_command')):
            commands=[json.loads(line) for line in (source/'commands.jsonl').read_text().splitlines()]
            land=[c for c in commands if c['cmd'][-2:]==['mode','auto:land']]
            if len(land)!=1 or land[0]['returncode']!=0:raise ValueError('No unique old CLI command')
            context=dict(hover_start_us=events['hover_start'],hover_end_us=events['hover_end'],
                         command_lower_us=events['land_command'],cli_success=True)
            through=int(u.get_dataset('sta_velocity_ctrl_status').data['timestamp'][-1])
            item['derived_context_for_component_only']=context
            item['landing_component']=outcome(lambda:replay(u,context,through,final=True))
            started=time.monotonic();reader=LandingLiveLog(entry['archive']);live=reader.read()
            item['reader_full_file_wall_s']=time.monotonic()-started
            item['live_component']=outcome(lambda:replay(live,context,through))
        else:
            item['landing_component']=dict(check_passed=False,not_executed='No complete observation/landing command')
        ref=source/'height_reference.json';frozen=source/'task_yaw.json'
        if ref.exists():
            item['heading_reset_component']=outcome(lambda:heading_replay(u,json.loads(ref.read_text()),
                frozen=json.loads(frozen.read_text()) if frozen.exists() else None))
        if item['new_full_chain']['accepted'] or item['new_full_chain']['full_chain_passed']:
            raise ValueError('Historical attempt cannot pass new full chain')
        result['runs'].append(item)
    for path,sha in originals.items():
        if digest(path)!=sha:raise ValueError('Original input changed')
    result['original_files_unchanged']=len(originals)
    result['source_head']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    (out/'evidence.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'original_artifacts.sha256').write_text(''.join(f'{sha}  {p}\n' for p,sha in sorted(originals.items())))
    print(json.dumps(dict(runs=len(jobs),original_files_unchanged=len(originals),new_flights=0,accepted=False)))


if __name__=='__main__':main()
