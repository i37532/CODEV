#!/usr/bin/env python3
"""Install pinned plotting wheels into a new external directory, never system Python."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    command=[sys.executable,'-m','pip','install','--target',str(out/'python'),'--only-binary=:all:',
             'matplotlib==3.8.4','numpy==1.26.4','contourpy==1.2.1','cycler==0.12.1','fonttools==4.51.0',
             'kiwisolver==1.4.5','packaging==24.0','pillow==10.3.0','pyparsing==3.1.2','python-dateutil==2.9.0.post0','six==1.16.0']
    with (out/'install.log').open('w') as stream:
        r=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
    (out/'command.json').write_text(json.dumps(dict(command=command,returncode=r.returncode),indent=2)+'\n')
    raise SystemExit(r.returncode)
