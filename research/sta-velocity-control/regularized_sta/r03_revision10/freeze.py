"""Freeze the D-only runner fix; preserve original revision09 ABC identity."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('_revision10_freeze_protocol',HERE/'protocol.py')
p=importlib.util.module_from_spec(s);s.loader.exec_module(p)
REPO=p.REPO
up=p.load_file('_revision10_upstream_freeze',HERE.parent/'r03_upstream08/freeze.py')


def scope():
    if p.git('diff','--name-only',p.ENTRY_HEAD,'--',*up.PRODUCTION) or p.git('ls-files','--others','--exclude-standard','--',*up.PRODUCTION):
        raise ValueError('Revision10 permits no production changes after the qualified UP08 fix')
    up.check()
    return dict(entry_head=p.ENTRY_HEAD,production_changes=[],upstream_frozen_sha256=p.fingerprint(up.HERE/'frozen.json'))


def submodules():return up.submodules()


def capture(gate):
    p.valid_gate(gate);p.require_execution_authority(gate);audit=scope()
    old=p.read(p.PREVIOUS/'gates/A/frozen.json');assets=dict(old['assets'])
    for gate_name in 'ABCD':
        path=p.PREVIOUS/'gates'/gate_name/'frozen.json'
        assets[str(path.relative_to(REPO))]=p.fingerprint(path)
    assets[str((up.HERE/'frozen.json').relative_to(REPO))]=p.fingerprint(up.HERE/'frozen.json')
    for path in HERE.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and 'gates' not in path.relative_to(HERE).parts:
            assets[str(path.relative_to(REPO))]=p.fingerprint(path)
    for path in (HERE.parent/'plan/r03_revision10_entry').glob('*.md'):
        assets[str(path.relative_to(REPO))]=p.fingerprint(path)
    for path in (HERE.parent/'r03_warmup10').glob('*.py'):
        assets[str(path.relative_to(REPO))]=p.fingerprint(path)
    assets[str(p.AUTHORIZATION.relative_to(REPO))]=p.fingerprint(p.AUTHORIZATION)
    return dict(stage='R03-revision10-'+gate,revision=p.REVISION,gate=gate,scope=audit,
        assets=assets,external_assets=old['external_assets'],submodules=submodules(),
        control_parameters=old['control_parameters'],derived_iris_sha256=old['derived_iris_sha256'],
        execution_sha256=p.fingerprint(HERE/'execution.json'),authorization_sha256=p.AUTHORIZATION_SHA,
        budget=p.budget(gate),historical_budget=p.retained_history(),diagnostic_replay=p.diagnostic_replay_binding(),
        new_flights=0,same_source_all36=False,retained_abc=p.retained_abc(),post_logger_warmup_us=30000000)


def check(gate):
    saved=p.read(HERE/'gates'/gate/'frozen.json');actual=capture(gate)
    if not p.exact(saved,actual):raise ValueError('Frozen revised matrix assets/protocol changed')
    return saved


def archive_check(gate,source_head,sha):
    path=HERE/'gates'/gate/'frozen.json'
    if p.fingerprint(path)!=sha:raise ValueError('Archived frozen manifest changed')
    saved=p.read(path)
    committed=subprocess.check_output(['git','show',source_head+':'+str(path.relative_to(REPO))],cwd=REPO)
    if hashlib.sha256(committed).hexdigest()!=sha:raise ValueError('Frozen manifest not from claimed source')
    listing=subprocess.check_output(['git','ls-tree','-r',source_head],cwd=REPO,text=True)
    objects={line.split('\t',1)[1]:line.split()[2] for line in listing.splitlines() if '\t' in line}
    subroots=[line.split('\t',1)[1] for line in listing.splitlines() if line.startswith('160000 ')]
    for name,expected in saved['assets'].items():
        raw=(REPO/name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Archived source asset changed '+name)
        oid=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if name in objects and oid!=objects[name]:raise ValueError('Source asset not committed at claimed HEAD '+name)
        if name not in objects and not any(name.startswith(root+'/') for root in subroots):
            if not name.startswith('build/'):raise ValueError('Uncommitted asset '+name)
    for name,expected in saved['external_assets'].items():
        if p.fingerprint(name)!=expected:raise ValueError('Archived external dependency changed '+name)
    return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.add_argument('--gate',choices=p.GATES,required=True)
    args=parser.parse_args();record=check(args.gate) if args.check else capture(args.gate)
    if not args.check:
        dest=HERE/'gates'/args.gate/'frozen.json';dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open('x') as f:json.dump(record,f,indent=2);f.write('\n')
    print(json.dumps(dict(gate=args.gate,assets=len(record['assets']),new_flights=0)))
