#!/usr/bin/env python3
"""Index one explicitly selected I02 attempt without modifying raw evidence."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--attempt',required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); root=a.root.resolve(); run=root/a.attempt; out=a.output.resolve()
    if root == out or root in out.parents: raise ValueError('output must be outside indexed root')
    evidence=json.loads((run/'evidence.json').read_text())
    assert evidence['success'] and evidence['existing']['success'] and not evidence['flight_executed'] and not evidence['gazebo_started']
    files=sorted(path for path in root.rglob('*') if path.is_file())
    lines=[f'{digest(path)}  {path}\n' for path in files]
    existing_cpp=sum(value['tests'] for key,value in evidence['existing']['tests'].items() if not key.startswith('python'))
    existing_python=sum(value['tests'] for key,value in evidence['existing']['tests'].items() if key.startswith('python'))
    summary=dict(success=True,parent=evidence['head'],branch=evidence['branch'],submodules=evidence['submodules'],
                 final_attempt=str(run),raw_root=str(root),artifacts=len(files),artifact_bytes=sum(path.stat().st_size for path in files),
                 index_sha256=hashlib.sha256(''.join(lines).encode()).hexdigest(),source_hashes=evidence['source_hashes'],
                 new_cpp=21,proper_kernel_cpp=evidence['tests']['ProperIstaRateControl']['tests'],existing_cpp=existing_cpp,
                 total_cpp=21+evidence['tests']['ProperIstaRateControl']['tests']+existing_cpp,
                 existing_python=existing_python,logger_format_length=evidence['logger_format_length'],
                 firmware_sha256=evidence['firmware_sha256'],new_kernel_in_final_firmware=False,
                 flight_executed=False,gazebo_started=False,matlab_executed=False,
                 commands=evidence['commands'])
    out.mkdir(parents=True,exist_ok=False)
    (out/'artifacts.sha256').write_text(''.join(lines))
    (out/'evidence.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps({key:summary[key] for key in ('total_cpp','existing_python','artifacts','artifact_bytes','index_sha256')},indent=2))


if __name__ == '__main__': main()
