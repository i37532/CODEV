"""Read-only paired clock-policy audit. Never regrade historical runs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from pyulog import ULog

REPO=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(REPO/'research/sta-velocity-control/v07/protocol02'))
import common
sys.path.insert(0,str(REPO/'research/sta-velocity-control/v06/soft_landing'))
import imu_health
import landing_health
import postland


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    root=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260928')
    directories=[*sorted((root/'V07/series01').glob('run[0-9][0-9]')),
                 *sorted((root/'V06/series03').glob('run[0-9][0-9]')),
                 root/'V06/series02/run09']
    evidence=dict(success=False,new_flights=0,historical_regrading=False,runs=[])
    def call(function,*args):
        try:return dict(passed=True,value=function(*args))
        except (ValueError,KeyError,IndexError) as exc:return dict(passed=False,error=str(exc))
    try:
        for directory in directories:
            files=[p for p in directory.iterdir() if p.is_file() and p.suffix in ('.json','.jsonl','.ulg')]
            hashes={str(p):sha(p) for p in files}
            record=json.loads((directory/'result.json').read_text());entry=max(record['logs'],key=lambda r:r['bytes'])
            assert sha(Path(entry['archive']))==entry['sha256']
            u=ULog(entry['archive']); events={e['name']:e['timestamp_us'] for e in record['events']}
            complete='landed_disarmed' in events
            start=events['land_command'];end=events.get('landed_disarmed',int(u.get_dataset('sensor_accel',0).data['timestamp'][-1])-4000)
            r=dict(path=str(directory),original_success=record['success'],complete_landing=complete,ulog=entry,
                   dropouts=len(u.dropouts),corrupt=bool(u.file_corruption),accepted=False,
                   note='Component audit only; original result and missing events remain unchanged.',clock=[])
            for i in range(3):
                d=u.get_dataset('vehicle_imu',i).data;p,s=imu_health.clock(d)
                ties=np.flatnonzero(np.diff(p)==0)
                r['clock'].append(dict(instance=i,rows=len(p),sample_strict=True,
                    ties=[dict(index=int(k),publication_us=int(p[k]),sample_us=[int(s[k]),int(s[k+1])]) for k in ties]))
            r['old_health']=call(landing_health.check_health,u,start,end)
            r['new_health']=call(imu_health.check_health,u,start,end)
            r['old_tail']=call(postland.complete_tail,u,start,end)
            r['new_tail']=call(imu_health.complete_tail,u,start,end)
            for p,h in hashes.items():assert sha(Path(p))==h
            r['input_hashes']=hashes;evidence['runs'].append(r)
            print(directory,r['old_health'].get('error','pass'),'->',r['new_health'].get('error','pass'),flush=True)
            if record['success']:assert r['new_health']['passed'],r
            if directory==root/'V06/series02/run09':
                assert not r['new_health']['passed'] and 'clipping' in r['new_health']['error']
            if directory==root/'V07/series01/run11':
                assert r['old_health']['passed'] is False
                assert sum(len(c['ties']) for c in r['clock'])==1
        assert len(evidence['runs'])==30
        evidence['success']=True
    finally:(out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')

if __name__=='__main__':main()
