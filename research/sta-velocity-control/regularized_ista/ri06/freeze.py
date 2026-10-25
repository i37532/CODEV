"""RI06 full source/asset binding; zero production changes allowed."""
import argparse
import hashlib
import json
from pathlib import Path
import importlib.util

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('_ri06_freeze_api',HERE/'protocol.py')
p=importlib.util.module_from_spec(s);s.loader.exec_module(p)
REPO=p.REPO
OLD=p.load_file('_ri06_prior_freeze',HERE.parent/'ri05/freeze.py')
BASE=HERE.parent/'ri05/gates/D/frozen.json'
BASE_SHA='9a318cd8a58987ef101cd11eb5be1b77c880df9c8bbf02f40354888f887ce10e'
submodules=OLD.submodules
PREFIX=str(HERE.relative_to(REPO))
SNAPSHOT='research/sta-velocity-control/regularized_ista/plan/ri06-entry'

def base():
    if p.fingerprint(BASE)!=BASE_SHA: raise ValueError('Changed accepted RI05 freeze')
    return p.read(BASE)

def scope(source_head=None):
    revisions=[p.ENTRY_HEAD]+([source_head] if source_head else [])
    changed=p.git('diff','--name-only',*revisions).splitlines()
    if source_head is None: changed+=p.git('ls-files','--others','--exclude-standard').splitlines()
    allowed=('research/sta-velocity-control/reports/RI06.md',
             'research/sta-velocity-control/README.md',
             'research/sta-velocity-control/regularized_ista/README_CN.md')
    bad=[n for n in changed if not (n.startswith(PREFIX+'/') or n.startswith(SNAPSHOT+'/') or n in allowed)]
    if bad: raise ValueError('RI06 outside nonproduction scope '+repr(bad))
    return dict(entry_head=p.ENTRY_HEAD,production_changes=[],historical_sources_unchanged=True)

def included(name):
    parts=Path(name).parts
    return not {'__pycache__','gates','results'}.intersection(parts) and Path(name).suffix not in ('.pyc','.pyo')

def names(source_head=None):
    result=set(base()['assets']);result.add(str(BASE.relative_to(REPO)))
    # Complete RI05 code/receipts/report form the entry, not only its preflight freeze.
    result.update(OLD.tree_entries(OLD.git_bytes('ls-tree','-rz',p.ENTRY_HEAD,'--',
        str((HERE.parent/'ri05').relative_to(REPO)), 'research/sta-velocity-control/reports/RI05.md')))
    if source_head:
        rows=OLD.tree_entries(OLD.git_bytes('ls-tree','-rz',source_head,'--',PREFIX,SNAPSHOT))
        result.update(n for n in rows if included(n))
    else:
        for root in (HERE,REPO/SNAPSHOT):
            result.update(str(f.relative_to(REPO)) for f in root.rglob('*') if f.is_file() and included(str(f.relative_to(REPO))))
    return sorted(result)

def capture(gate):
    p.require_execution_authority(gate)
    old=base();sc=scope();subs=submodules()
    if subs!=old['submodules']: raise ValueError('Submodule revision changed')
    assets={n:p.fingerprint(REPO/n) for n in names()}
    for n,sha in old['assets'].items():
        if assets[n]!=sha: raise ValueError('Inherited immutable source changed '+n)
    for n,sha in old['external_assets'].items():
        if p.fingerprint(n)!=sha: raise ValueError('Changed external dependency '+n)
    return dict(stage=p.stage(gate),revision=p.REVISION,gate=gate,entry_head=p.ENTRY_HEAD,
        scope=sc,assets=assets,external_assets=old['external_assets'],submodules=subs,
        inherited_frozen_sha256=BASE_SHA,control_parameters=old['control_parameters'],
        generated_assets=old['generated_assets'],derived_iris_sha256=old['derived_iris_sha256'],
        execution_sha256=p.fingerprint(HERE/'execution.json'),authorization_sha256=p.fingerprint(p.AUTHORIZATION),
        budget=p.budget(gate),jobs=p.jobs(gate),new_flights=0,post_logger_warmup_us=30000000)

def check(gate):
    frozen=p.read(HERE/'gates'/gate/'frozen.json')
    if not p.exact(frozen,capture(gate)): raise ValueError('RI06 frozen source/parameters differ')
    return frozen

def archive_check(gate,source_head,frozen_sha):
    path=HERE/'gates'/gate/'frozen.json';name=str(path.relative_to(REPO))
    raw=OLD.git_bytes('show',source_head+':'+name)
    if hashlib.sha256(raw).hexdigest()!=frozen_sha or p.fingerprint(path)!=frozen_sha:
        raise ValueError('Frozen artifact not committed at claimed source')
    f=json.loads(raw);old=base();scope(source_head)
    OLD.git_bytes('merge-base','--is-ancestor',p.ENTRY_HEAD,source_head)
    modules=OLD.submodule_map(f['submodules']);OLD.verify_gitlinks(source_head,modules)
    if f['submodules']!=old['submodules'] or set(f['assets'])!=set(names(source_head)):
        raise ValueError('Archived source/submodule inventory incomplete')
    if OLD.committed_assets(f['assets'],source_head,modules)!=f['assets']:
        raise ValueError('Archived Git blobs differ')
    for n,sha in old['assets'].items():
        if f['assets'][n]!=sha: raise ValueError('Archived production/historical source changed '+n)
    if f['stage']!=p.stage(gate) or f['entry_head']!=p.ENTRY_HEAD or f['budget']!=p.budget(gate) or f['jobs']!=p.jobs(gate):
        raise ValueError('Archived exact scope/jobs changed')
    if f['external_assets']!=old['external_assets'] or f['generated_assets']!=old['generated_assets']:
        raise ValueError('Archived external/generated assets differ')
    for n,sha in f['external_assets'].items():
        if p.fingerprint(n)!=sha: raise ValueError('External artifact changed')
    return f

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--gate',choices=p.GATES,required=True)
    parser.add_argument('--write',action='store_true')
    parser.add_argument('--refresh-uncommitted',action='store_true',help='Only regenerate an uncommitted preflight artifact; never a flight/source archive')
    args=parser.parse_args()
    f=capture(args.gate) if args.write else check(args.gate)
    if args.write:
        dest=HERE/'gates'/args.gate/'frozen.json';dest.parent.mkdir(parents=True,exist_ok=True)
        if args.refresh_uncommitted:
            tracked=p.git('ls-files','--',str(dest.relative_to(REPO)))
            if tracked or list(p.DATA_ROOT.glob('*/batch*/ledger.json')) or list(p.DATA_ROOT.glob('*/qualification*/authorization.json')):
                raise ValueError('Refuse rewriting tracked/qualified/flown freeze')
        with dest.open('w' if args.refresh_uncommitted else 'x') as stream:json.dump(f,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(gate=args.gate,assets=len(f['assets']),new_flights=0)))
