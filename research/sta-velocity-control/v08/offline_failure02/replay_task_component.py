"""Audit revised task component against old bytes; NEVER regrade old flights."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
from audit import REPO,digest
from position_log import ULog

spec=importlib.util.spec_from_file_location('v08_revised_task_component',REPO/'research/sta-velocity-control/v08/protocol03b/task.py')
task=importlib.util.module_from_spec(spec);spec.loader.exec_module(task)

def main():
    p=argparse.ArgumentParser();p.add_argument('batches',type=Path,nargs='+');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=dict(success=False,flights=0,old_verdicts_changed=False,component_records=[],skipped=[])
    try:
        for batch in a.batches:
            ledger=json.loads((batch/'ledger.json').read_text())
            for item in ledger['attempts']:
                run=Path(item['directory']);r=json.loads((run/'result.json').read_text())
                events={x['name']:x['timestamp_us'] for x in r['events']}
                if not {'hover_start','hover_end','landed_disarmed'}<=set(events):
                    out['skipped'].append(dict(path=str(run),old_verdict=item['status'],reason='Incomplete historical task, not reconstructed'))
                    continue
                baseline=json.loads((run/'v00_metrics.json').read_text());path=Path(baseline['ulog']['archive'])
                log=ULog(str(path));d=log.get_dataset('sta_velocity_ctrl_status').data
                result=task.check_targets(log,d,events,item['job'])
                record=dict(path=str(run),old_verdict=item['status'],component_valid=True,ulog_sha256=digest(path),task_evidence=result)
                out['component_records'].append(record)
                print(json.dumps(dict(path=str(run),old_verdict=item['status'],component_valid=True,missing_attitude=result['attitude_task_output']['missing_count'])),flush=True)
        out['success']=True
    finally:
        with a.output.open('x') as f:json.dump(out,f,indent=2);f.write('\n')

if __name__=='__main__':main()
