"""Read-only historical task component replay, never changes full verdicts."""
import hashlib
import json
from pathlib import Path
import sys
from pyulog import ULog
import numpy as np
REPO=Path('/home/yr/Desktop/Codev-autopilot')
sys.path.insert(0,str(REPO/'research/sta-velocity-control/v07/protocol07'))
from task import check_targets
ROOT=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    out=ROOT/'target_audit';out.mkdir(exist_ok=False)
    evidence=dict(success=False,new_flights=0,runs=[],historical_verdicts_unchanged=True)
    try:
        for number in range(1,7):
            ledger=json.loads((REPO/f'research/sta-velocity-control/v07/results{number:02}/ledger.json').read_text())
            for a in ledger['attempts']:
                r=Path(a['directory']);result=json.loads((r/'result.json').read_text());events={x['name']:x['timestamp_us'] for x in result['events']}
                if 'hover_end' not in events:continue
                before={p.name:sha(p) for p in (r/'result.json',r/'xyz_metrics.json') if p.exists()}
                raw=max(result['logs'],key=lambda x:x['bytes']);assert sha(raw['archive'])==raw['sha256']
                u=ULog(raw['archive']);d=u.get_dataset('sta_velocity_ctrl_status').data
                row=dict(batch=number,run=r.name,old_status=a['status'],ulog=raw,component_only=True)
                try:row['task_targets']=check_targets(u,d,events,a['job']);row['component_accepted']=True
                except ValueError as exc:row.update(component_accepted=False,error=str(exc))
                assert {name:sha(r/name) for name in before}==before
                assert sha(raw['archive'])==raw['sha256']
                evidence['runs'].append(row);print(number,r.name,row['component_accepted'],row.get('error'),flush=True)
        evidence['accepted_components']=sum(x['component_accepted'] for x in evidence['runs'])
        evidence['success']=bool(evidence['runs'] and all(x['component_accepted'] for x in evidence['runs']))
        assert evidence['success']
    finally:(out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')

if __name__=='__main__':main()
