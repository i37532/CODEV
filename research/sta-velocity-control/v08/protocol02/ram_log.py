"""Private tmpfs live ULog, durable checked copies AFTER owned PX4 shutdown.

No deletion of RAM originals. Volatile before archival: not a crash-safe flight
recorder or hardware recommendation. Default project logging stays unchanged.
"""
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import json


def validate(root):
    root=Path(root);info=root.lstat()
    if (root.parent!=Path('/dev/shm') or not re.fullmatch(r'px4-v07-[A-Za-z0-9_-]+',root.name)
            or not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o077
            or root.resolve()!=root):
        raise ValueError('Invalid private RAM log root')
    fs=subprocess.check_output(['stat','-f','-c','%T',str(root)],text=True).strip()
    if fs!='tmpfs':raise ValueError('Research RAM log root is not tmpfs')
    return root


def create():
    if shutil.disk_usage('/dev/shm').free<512*1024**2:
        raise RuntimeError('Insufficient private tmpfs capacity')
    return validate(Path(tempfile.mkdtemp(prefix='px4-v07-',dir='/dev/shm')))


def paths(root):
    root=validate(root)
    if any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('Symlink in owned RAM log root')
    items=sorted(root.glob('**/*.ulg'))
    for p in items:
        if p.is_symlink() or not p.is_file() or root not in p.resolve().parents:
            raise ValueError('RAM log path escaped owned root')
    return items


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def archive(source,destination,root):
    source=Path(source);destination=Path(destination)
    if source not in paths(root):raise ValueError('Not an owned RAM log')
    before=digest(source)
    with source.open('rb') as src,destination.open('xb') as dst:
        shutil.copyfileobj(src,dst,1024*1024);dst.flush();os.fsync(dst.fileno())
    fd=os.open(str(destination.parent),os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    if digest(source)!=before or digest(destination)!=before:
        raise RuntimeError('RAM log archive fingerprint changed')
    return dict(source=str(source),archive=str(destination),sha256=before,
                bytes=destination.stat().st_size,durable_copy_verified=True,volatile_source_retained=True)


def release_archived(run, root):
    """Only redundant copies from this exact V08 invocation, after shutdown.

    Raw bytes remain in exclusive, fsynced disk archives. No pre-existing RAM
    roots or failed/partial archives are collected. Audit receipt records removal.
    """
    from flight import active_simulators
    run=Path(run); root=validate(root)
    if active_simulators(): raise RuntimeError('Cannot release a live recording')
    receipt=json.loads((run/'ram_log_root.json').read_text())
    if receipt['path']!=str(root) or 'originals_retained_until_durable_archive' not in receipt:
        raise ValueError('Not this V08 invocation')
    logs=json.loads((run/'result.json').read_text())['logs']
    if not logs or {Path(x['source']) for x in logs}!=set(paths(root)):
        raise ValueError('Incomplete archive list')
    for item in logs:
        destination=Path(item['archive'])
        if (destination.is_symlink() or destination.parent!=run or not item.get('durable_copy_verified')
                or digest(item['source'])!=item['sha256'] or digest(destination)!=item['sha256']):
            raise ValueError('Unverified archive; retain RAM originals')
    evidence=dict(released=[],reason='V08 redundant tmpfs copies after durable original-byte archival',raw_archives_preserved=True)
    for item in logs:
        Path(item['source']).unlink()
        evidence['released'].append(dict(source=item['source'],archive=item['archive'],sha256=item['sha256']))
    (run/'ram_release.json').write_text(json.dumps(evidence,indent=2)+'\n')
