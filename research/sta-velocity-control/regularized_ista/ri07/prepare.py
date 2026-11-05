"""Create exact new RI07 transport manifest, never modify RI06 protocol."""
import json
from pathlib import Path
import protocol as p

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')

if __name__=='__main__':
    write(p.HERE/'execution.json',dict(stage=p.stage(),revision=p.REVISION,package_sha256=p.PACKAGE_SHA,
        executable_source_head=p.EXECUTABLE_HEAD,jobs=p.jobs(),budget=p.budget(),
        order='Exact RI06 final02 sequence; A80 then B120; task and algorithm order unchanged',
        first_failure='Stop entire batch, no retry/replacement/tuning/threshold change',
        ri06_reference_firmware_sha256=p.formal()['firmware_sha256'],
        firmware_policy='User-authorized metadata-only rebuild at clean RI07 tools commit; one qualified binary for all200'))
    print('Created exact RI07 transport registration; 200 unattempted; no flight')
