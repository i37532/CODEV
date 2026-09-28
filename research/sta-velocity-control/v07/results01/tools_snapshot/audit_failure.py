"""Read-only failed flight11 audit. Does not regrade or change frozen checkers."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from pyulog import ULog
ROOT=Path(__file__).resolve().parent
REPO=Path('/home/yr/Desktop/Codev-autopilot')
sys.path.insert(0,str(REPO/'research/sta-velocity-control/v07/protocol01'))
import common
import core
sys.path.insert(0,str(REPO/'research/sta-velocity-control/v06/soft_landing'))
from postland import complete_tail,TOPICS
from landing_health import check_health

run=ROOT/'series01/run11'; record=json.loads((run/'result.json').read_text())
out=ROOT/'failure_audit01'; out.mkdir(exist_ok=False)
entry=max(record['logs'],key=lambda r:r['bytes'])
assert hashlib.sha256(Path(entry['archive']).read_bytes()).hexdigest()==entry['sha256']
u=ULog(entry['archive']); e={x['name']:x['timestamp_us'] for x in record['events']}
result=dict(original_accepted=False,new_flights=0,ulog=entry,dropouts=len(u.dropouts),corrupt=bool(u.file_corruption),
            source_head=record['source_head'],events=e,topics=[])
for name,count in TOPICS.items():
    for inst in range(count):
        d=u.get_dataset(name,inst).data; t=d['timestamp'].astype(np.int64); dt=np.diff(t)
        bad=np.flatnonzero(dt<=0)
        rows=[]
        for k in bad:
            keys=[key for key in d if key!='timestamp']
            changed=[key for key in keys if not np.array_equal(d[key][k:k+1],d[key][k+1:k+2],equal_nan=True)]
            rows.append(dict(index=int(k),timestamp_before=int(t[k]),timestamp_after=int(t[k+1]),delta_us=int(dt[k]),
                             changed_fields=changed,changed_values={key:[float(d[key][k]),float(d[key][k+1])] for key in changed},
                             phase='before landing' if t[k]<e['land_command'] else 'landing or after disarm'))
        result['topics'].append(dict(name=name,instance=inst,samples=len(t),first_us=int(t[0]),last_us=int(t[-1]),
            nonpositive=int((t<=0).sum()),start_missing=bool(t[0]>e['land_command']),end_missing=bool(t[-1]<e['landed_disarmed']),violations=rows))
for label,call in [('frozen_tail',lambda:complete_tail(u,e['land_command'],e['landed_disarmed'])),
                   ('frozen_landing_health',lambda:check_health(u,e['land_command'],e['landed_disarmed']))]:
    try: result[label]=dict(passed=True,evidence=call())
    except Exception as exc: result[label]=dict(passed=False,error=repr(exc))
d=u.get_dataset('sta_velocity_ctrl_status').data; q=u.get_dataset('velocity_ctrl_selection').data
job=json.loads((run/'job.json').read_text())
try:
    result['diagnostic_only']=core.check_diagnostic(d,q,e['hover_start'],e['hover_end'],job)
    result['diagnostic_only_note']='Exploratory component only; no full-chain acceptance or flight regrading.'
except Exception as exc: result['diagnostic_only_error']=repr(exc)
assert not result['frozen_tail']['passed'],'Did not reproduce original tail rejection'
(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(original_accepted=False,violations=[r for r in result['topics'] if r['violations'] or r['nonpositive'] or r['start_missing']],frozen_tail=result['frozen_tail'],landing_health=result['frozen_landing_health'],diagnostic_only_passed='diagnostic_only' in result),indent=2))
