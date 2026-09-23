#!/usr/bin/env python3
"""Read structured seed assignments, not coincident numeric signal values."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); args=p.parse_args()
    out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    roots=['/home/yr/Desktop/Codev-autopilot/research','/home/yr/Desktop/codev doc/experiments','/home/yr/Desktop/codev doc/plan']
    files=subprocess.check_output(['rg','--files','-g','*.json',*roots],text=True).splitlines()
    seeds={9101,9102,9103}; matches=[]; invalid=[]; empty_diagnostics=[]; count=0
    def numbers(x):
        if isinstance(x,int) and not isinstance(x,bool): return {x}
        if isinstance(x,list): return set().union(*(numbers(y) for y in x))
        return set()
    def walk(x,path,trail=''):
        if isinstance(x,dict):
            for k,v in x.items():
                found=seeds & numbers(v) if 'seed' in k.lower() else set()
                if found: matches.append(dict(path=path,field=trail+k,seeds=sorted(found)))
                walk(v,path,trail+k+'.')
        elif isinstance(x,list):
            for i,v in enumerate(x): walk(v,path,trail+str(i)+'.')
    for name in files:
        if '/sta-velocity-control/v04/' in name or '/VELOCITY-STA-20260923/V04/' in name: continue
        raw=Path(name).read_bytes()
        if name=='/home/yr/Desktop/codev doc/experiments/M06-20260916/c02_regression_roll_diagnostic.json' and raw==b'':
            empty_diagnostics.append(dict(path=name,bytes=0,sha256=hashlib.sha256(raw).hexdigest(),
                reason='Audited pre-existing empty diagnostic, not a seed registry; preserved unchanged'))
            continue
        try: data=json.loads(raw)
        except (ValueError,UnicodeError): invalid.append(name); continue
        count+=1; walk(data,name)
    result=dict(seeds=sorted(seeds),files_parsed=count,matches=matches,invalid_json=invalid,
        empty_diagnostics=empty_diagnostics,roots=roots,
        excluded='new V04 protocol and new 2026-09-23 V04 data (including prior audit attempt)',accepted=not matches and not invalid)
    (out/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2)); raise SystemExit(0 if result['accepted'] else 1)


if __name__=='__main__': main()
