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
