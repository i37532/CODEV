"""Prearm prefix counterfactuals; no historical acceptance changes or flight."""
import argparse
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from pyulog import ULog
from v04_heading_stream import TOPICS, complete_prefix
from v04_live_clock09 import reference_row as old_reference, replay, sealed_time
from v04_prearm17 import reference_row
from v04_task04 import freeze_reference


class Prefix:
    def __init__(self,u,cut):
        self.dropouts=[];self.file_corruption=False
        self.tables={(x.name,x.multi_id):{k:v[x.data['timestamp']<=cut] for k,v in x.data.items()}
                     for x in u.data_list if 'timestamp' in x.data}
    def get_dataset(self,name,instance=0):return SimpleNamespace(data=self.tables[(name,instance)])


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    r=json.loads((a.run/'result.json').read_text());entry=max(r['logs'],key=lambda x:x['bytes'])
    raw=Path(entry['archive']);sha=lambda:hashlib.sha256(raw.read_bytes()).hexdigest()
    assert sha()==entry['sha256']
    u=ULog(str(raw),message_name_filter_list=TOPICS)
    if u.dropouts or u.file_corruption:raise ValueError('Corrupt original log')
    ready=next(e['timestamp_us'] for e in r['events'] if e['name']=='ready')
    # Enumerated publication prefixes, not a fabricated exact captured live tail.
    times=u.get_dataset('vehicle_attitude').data['timestamp']
    # This failed run never armed; include the recorded preparation tail after
    # the ready marker as CLI/ULog reads take real time. Not a flyable extension.
    status=u.get_dataset('vehicle_status').data
    if np.any(status['arming_state'] != 1):
        raise ValueError('This diagnostic requires a wholly disarmed log')
    cuts=np.unique(times[times>=ready-200000])
    rows=[]
    for cut in cuts:
        prefix=Prefix(u,int(cut));item=dict(cut_us=int(cut),sealed_us=sealed_time(prefix))
        for label,choose in [('old',old_reference),('new',reference_row)]:
            try:
                ref=freeze_reference(choose(prefix));e=replay(prefix,ref)
                item[label]=dict(accepted=True,reference_us=int(ref['position']['timestamp']),
                                 checked_attitude_records=e['clock09']['checked_attitude_records'])
            except (ValueError,KeyError,IndexError) as exc:item[label]=dict(accepted=False,error=str(exc))
        rows.append(item)
    byte_rows=[];raw_bytes=raw.read_bytes()
    for cut in range(max(16,(len(raw_bytes)-256000)//4096*4096),len(raw_bytes),4096):
        prefix=ULog(io.BytesIO(complete_prefix(raw_bytes[:cut])),message_name_filter_list=TOPICS)
        item=dict(byte_prefix=cut)
        for label,choose in [('old',old_reference),('new',reference_row)]:
            try:
                ref=freeze_reference(choose(prefix));replay(prefix,ref)
                item[label]=dict(accepted=True,reference_us=int(ref['position']['timestamp']))
            except (ValueError,KeyError,IndexError) as exc:item[label]=dict(accepted=False,error=str(exc))
        byte_rows.append(item)
    e=dict(kind='counterfactual_prefix_diagnosis_not_reacceptance',raw_sha256=sha(),
           exact_failed_live_prefix_not_saved=True,rows=rows,
           byte_prefixes=byte_rows,
           old_rejected=sum(not x['old']['accepted'] for x in rows),
           new_rejected=sum(not x['new']['accepted'] for x in rows),
           old_byte_prefix_rejected=sum(not x['old']['accepted'] for x in byte_rows),
           new_byte_prefix_rejected=sum(not x['new']['accepted'] for x in byte_rows))
    (a.output/'evidence.json').write_text(json.dumps(e,indent=2)+'\n')
    assert sha()==entry['sha256']
    print(json.dumps({k:v for k,v in e.items() if k not in ('rows','byte_prefixes')}))


if __name__=='__main__':main()
