"""Offline RI05 dry-run stdout validation and exclusive byte-preserving archive.

This module does not run a runner, migrate/delete files, exempt seed registries,
or grant flight authority. The frozen runner prints JSON followed by a text
trailer: the combined stdout is a .log artifact, never a structured .json file.
"""
import hashlib
import json
import os
from pathlib import Path
import stat

TRAILER = '\nDRY RUN: no process, parameter, output directory or flight changed.\n'
JOB_FIELDS = ('id', 'task', 'seed', 'candidate', 'mode', 'axes', 'divisor', 'main_duration_s')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('Nonfinite JSON constant: ' + value)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def validate_stdout(raw, *, frozen_jobs, stage):
    """Require the exact frozen nine-job summary and exact final dry-run line.

Full frozen job rows may include parameters not printed by the runner. No field
in its printed projection, row order, numeric type or budget may differ.
"""
    if type(raw) is not bytes:
        raise TypeError('Raw stdout must be bytes; do not normalize line endings')
    if stage not in ('RI05-C', 'RI05-D') or not isinstance(frozen_jobs, list) or len(frozen_jobs) != 9:
        raise ValueError('Exact RI05 stage and nine frozen jobs required')
    try:
        expected_jobs = [{key: job[key] for key in JOB_FIELDS} for job in frozen_jobs]
    except (KeyError, TypeError) as error:
        raise ValueError('Incomplete frozen job projection') from error
    expected = dict(stage=stage, planned=9, maximum_attempts=9, jobs=expected_jobs)
    text = raw.decode('utf-8', errors='strict')
    decoder = json.JSONDecoder(object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    summary, end = decoder.raw_decode(text)
    if text[end:] != TRAILER:
        raise ValueError('Missing, changed or extra dry-run trailer bytes')
    if _canonical(summary) != _canonical(expected):
        raise ValueError('Stdout differs from frozen stage/jobs/order/budget')
    return summary


def _parent_directory(path):
    """Pin every parent with directory FDs; never follow any symbolic link."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or not path.name:
        raise ValueError('Explicit absolute destination without parent traversal required')
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parent.parts[1:]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
        return path, descriptor
    except BaseException:
        os.close(descriptor)
        raise


def archive_stdout(raw, destination, *, frozen_jobs, stage):
    """Exclusively create a .log, retaining all original stdout bytes.

No directories are created. Existing files, hard links and symbolic links are
refused. On an I/O failure a partial new artifact is deliberately not deleted;
the caller must preserve/investigate it instead of retrying over the same path.
"""
    validate_stdout(raw, frozen_jobs=frozen_jobs, stage=stage)
    destination = Path(destination)
    if destination.suffix != '.log':
        raise ValueError('Mixed dry-run stdout may only be archived as .log, never .json')
    path, parent = _parent_directory(destination)
    try:
        descriptor = os.open(path.name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(descriptor, 'w+b') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode) or os.fstat(stream.fileno()).st_nlink != 1:
                raise ValueError('Archive must be a new unlinked regular file')
            if stream.write(raw) != len(raw):
                raise OSError('Short archive write; preserve partial artifact')
            stream.flush()
            os.fsync(stream.fileno())
            stream.seek(0)
            if stream.read() != raw:
                raise OSError('Archive read-back differs; preserve artifact')
        os.fsync(parent)
    finally:
        os.close(parent)
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                stage=stage, artifact='mixed_dry_run_stdout', new_flights=0)
