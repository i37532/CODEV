"""Pilot whitelist only; historical training checks remain intact."""
import common
import task
import importlib.util
import json
from pathlib import Path
import shutil
import sys
CONFIG=common.CONFIG
sys.path.insert(0,str(common.TRAIN))
import scenario
spec=importlib.util.spec_from_file_location('v08_pilot_base_analysis',common.TRAIN/'analyze.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
compare=base.compare

def verify_model(run,plugins,replay=False):
    job=json.loads((run/'job.json').read_text())
    return scenario.verify_model(run,plugins,Path(common.design()['force_library']),job,replay=replay)

base.verify_model=verify_model

def analyze(run,protocol,job):
    result=base.analyze(run,protocol,job)
    if result['accepted']:
        result['accepted']=False
        try:
            record=json.loads((run/'result.json').read_text())
            sources={Path(x['archive']).parent for x in record['logs']}
            if len(sources)!=1:raise ValueError('Ambiguous raw pilot source')
            source=next(iter(sources))
            baseline=json.loads((run/'v00_metrics.json').read_text())
            u=base.ULog(baseline['ulog']['archive']);d=u.get_dataset('sta_velocity_ctrl_status').data
            events={x['name']:x['timestamp_us'] for x in record['events']}
            result['loaded_model']=scenario.loaded_model(source,job)
            result['force']=scenario.force_evidence(source,job,d,events)
            result['accepted']=True
        except (ValueError,KeyError,OSError) as exc:result['error']=str(exc)
        base.save(run/'xyz_metrics.json',result)
    return result

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();source=args.run.resolve();target=args.output.resolve()
    if source==target or source in target.parents:raise ValueError('Independent replay directory required')
    target.mkdir(parents=True,exist_ok=False)
    for item in source.iterdir():
        if item.is_file() and item.suffix in ('.json','.jsonl','.txt','.log'):shutil.copyfile(item,target/item.name)
    job=json.loads((target/'job.json').read_text());p=common.load_protocol();p['startup_overrides'].update(job['parameters'])
    result=analyze(target,p,job);print(json.dumps(result,indent=2));raise SystemExit(0 if result['accepted'] else 1)
