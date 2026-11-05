#!/usr/bin/env python3
"""Create append-only M10 evidence index/metadata, without Git operations.

Call with a fresh output directory, not the external raw data directory itself.
An index proves file integrity, not experiment acceptance.
"""
import argparse
import hashlib
import json
import importlib.metadata
from pathlib import Path
import subprocess


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def main(root,out):
    root=root.resolve();out=out.resolve()
    if out==root or root in out.parents:raise ValueError('Index output must be outside raw tree')
    out.mkdir(parents=True,exist_ok=False)
    files=[f for f in sorted(root.rglob('*')) if f.is_file() and not f.is_symlink() and '__pycache__' not in f.parts]
    index=out/'artifacts.sha256'
    index.write_text(''.join(f'{sha(f)}  {f}\n' for f in files))
    repo=Path(__file__).resolve().parents[3]
    commands={}
    for name,argv in [('head',['git','rev-parse','HEAD']),('branch',['git','branch','--show-current']),
                      ('status',['git','status','--short']),('submodules',['git','submodule','status','--recursive']),
                      ('compiler',['g++','--version']),('gazebo',['gazebo','--version']),('cpu',['lscpu']),('kernel',['uname','-a'])]:
        r=subprocess.run(argv,cwd=repo,capture_output=True,text=True)
        commands[name]=dict(command=argv,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
    binaries=[repo/'build/px4_sitl_default/bin/px4']
    data=dict(root=str(root),file_count=len(files),bytes=sum(p.stat().st_size for p in files),
              index_sha256=sha(index),environment=commands,binaries={str(p):sha(p) for p in binaries})
    data['python_packages']={name:importlib.metadata.version(name) for name in ('numpy','pyulog','pymavlink')}
    (out/'evidence.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:data[k] for k in ('file_count','bytes','index_sha256')},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.root,a.output)
