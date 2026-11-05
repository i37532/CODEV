"""Own a unique PX4 session log, independent of GPS/RTC second naming."""
import re
import time


def restart(cli):
    cli('logger','stop')
    time.sleep(1.1)  # Existing stop barrier, not a filename collision workaround.
    cli('logger','start','-b','256','-r','1000','-f')  # No -t: new sessNNN directory.


def owned_log(root, before):
    paths=set(root.glob('**/*.ulg'))-before
    if len(paths)!=1:
        raise RuntimeError('Need exactly one owned restarted logger file')
    path=paths.pop()
    if path.is_symlink() or not path.is_file() or not re.fullmatch(r'sess[0-9]{3,}/log[0-9]{3}\.ulg',path.relative_to(root).as_posix()):
        raise RuntimeError('Not a unique session logger file')
    if path.resolve().parent.parent!=root.resolve():
        raise RuntimeError('Session log escapes owned root')
    return path
