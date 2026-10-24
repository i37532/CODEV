#!/usr/bin/env python3
"""Seal only NEW offline evidence; preserve original flight artifacts unchanged."""
import json
from pathlib import Path
from verify import DATA, HERE, digest, validate_candidate


def save(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value,indent=2,allow_nan=False)+'\n')


def main():
    output=HERE/'results'
    if output.exists(): raise ValueError('Result bundle exists; never overwrite')
    model=json.loads((DATA/'model01/summary.json').read_text())
    validate_candidate(json.loads((HERE/'candidate.json').read_text()),model)
    checks=json.loads((DATA/'checks02/verification.json').read_text())
    if not checks['success'] or any(c['exit_code'] for c in checks['commands']):
        raise ValueError('Incomplete verification')
    for key in ('sources',):
        for obj in (model,checks):
            for path,sha in obj[key].items():
                if digest(Path(path))!=sha: raise ValueError('Verified source changed '+path)
    logs=json.loads((DATA/'logs01/summary.json').read_text())
    if len(logs['runs'])!=9 or logs['new_flights']!=0: raise ValueError('Wrong diagnostic dataset')
    for row in logs['runs']:
        if digest(Path(row['source']['path']))!=row['source']['sha256']: raise ValueError('Changed ULog')
    index=DATA/'archive_index.json'
    if index.exists(): raise ValueError('Archive already sealed')
    files=[]
    for path in sorted(DATA.rglob('*')):
        if path.is_symlink(): raise ValueError('Unexpected link in new offline evidence')
        if path.is_file(): files.append(dict(path=str(path),sha256=digest(path),bytes=path.stat().st_size))
    save(index,dict(new_flights=0,files=files,excludes=['archive_index.json (self)']))
    output.mkdir()
    save(output/'diagnostics.json',logs)
    save(output/'model.json',model)
    save(output/'verification.json',checks)
    save(output/'archive_reference.json',dict(path=str(index),sha256=digest(index),file_count=len(files),
        restriction='Exploratory offline development only; no new flight acceptance or reusable authority'))
    print(json.dumps(dict(files=len(files),index_sha256=digest(index),new_flights=0)))


if __name__=='__main__':main()
