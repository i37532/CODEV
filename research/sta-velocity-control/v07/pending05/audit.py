"""Read-only failed-log diagnosis plus explicitly synthetic poll schedules."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import numpy as np
REPO=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(REPO/'research/sta-velocity-control/v07/protocol05'))
from position_live import PositionLiveLog
from landing import LandingMonitor,replay
from pending_poll import drain

ROOT=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V07-LOGFILES/series04/run05')

class Prefix:
    dropouts=[]
    file_corruption=False
    def __init__(self,raw,end):self.raw,self.end=raw,end
    def get_dataset(self,name,multi_instance=0):
        d=self.raw.get_dataset(name,multi_instance=multi_instance).data
        m=d['timestamp']<=self.end
        return SimpleNamespace(data={k:v[m] for k,v in d.items()})

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    path=ROOT/'log001.ulg';before=hashlib.sha256(path.read_bytes()).hexdigest()
    assert before=='9ca12419859af705e5de327827df6e5003e00b77e9267aff68ccd7a214f7c242'
    result=dict(success=False,new_flights=0,source=str(path),sha256=before,
        limitation='Recorded heading watermarks, but reconstructed per-topic prefixes and poll schedules are synthetic; not exact historical byte arrival or a regrading.',timings=[])
    try:
        reader=PositionLiveLog(path);ctx=json.loads((ROOT/'landing_context.json').read_text())
        for i in range(3):
            start=time.monotonic();u=reader.read();parsed=time.monotonic();u.get_dataset('vehicle_local_position');checked=time.monotonic()
            d=u.get_dataset('sta_velocity_ctrl_status').data
            final=replay(u,ctx,int(d['timestamp'][-1]),final=True)
            result['timings'].append(dict(first_scan=i==0,decode_s=parsed-start,position_check_s=checked-parsed,landing_s=time.monotonic()-checked))
        result['final_landing_component']=final
        heading=[json.loads(x) for x in (ROOT/'heading_live.jsonl').read_text().splitlines() if json.loads(x)['phase']=='landing']
        assert len(heading)==2
        result['recorded_polls']=[dict(through_us=x['evidence']['through_us'],age_us=x['age_us'],now_us=x['evidence']['through_us']+x['age_us']) for x in heading]
        assert result['recorded_polls'][1]['now_us']-result['recorded_polls'][0]['now_us']==500000
        first=json.loads((ROOT/'landing10_monitor.jsonl').read_text().splitlines()[0])['diagnostic']
        prefix0=Prefix(u,139176000);prefix1=Prefix(u,139636000)
        k=int(np.flatnonzero(d['timestamp']==139636000)[0]);second={key:values[k].item() for key,values in d.items()}
        wall=[0.];old=LandingMonitor(lambda:wall[0]);old.begin(**ctx)
        assert old.update(prefix0,first,139516000)['pending']
        wall[0]=.500001
        try:old.update(prefix1,second,140016000)
        except ValueError as exc:result['old_schedule_rejection']=str(exc)
        else:raise AssertionError('Expected unchanged deadline rejection')
        assert result['old_schedule_rejection']=='Landing evidence pending timeout'
        wall[0]=0.;new=LandingMonitor(lambda:wall[0]);new.begin(**ctx);records=[]
        def poll(i):
            wall[0]=i*.35
            new.update(prefix0 if i==0 else prefix1,first if i==0 else second,139516000+i*350000)
        drain(new,poll,records.append)
        result['synthetic_immediate_polls']=records
        assert len(records)==2 and not new.failed and not new.last_evidence['pending']
        result['file_unchanged']=hashlib.sha256(path.read_bytes()).hexdigest()==before
        assert result['file_unchanged'];result['success']=True
    finally:(out/'evidence.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
