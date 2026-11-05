#!/usr/bin/env python3
"""Bind the immutable six-log target-only probe to a new R03 qualification.

This is a read-only evidence checker, not another replay and not flight
admission. The public entry is fixed to target_replay02, including the two
historical60s target-component checks; it never relabels those as R03 flights.
"""
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
EXTERNAL=Path('/home/yr/Desktop/codev doc/experiments')
EVIDENCE=EXTERNAL/'VELOCITY-STA-REGULARIZED-20261016/R03/A/target_replay02'
SOURCES=tuple(HERE/name for name in ('analyzer.py','targets.py','test_analysis.py','targets_replay.py'))
FORMAL=EXTERNAL/'VELOCITY-AXIS-ABLATION-20261008/AX05/formal01'
CASES=(('H_PID',FORMAL/'run007'),('H_XYZ',FORMAL/'run008'),
       ('V_PID',FORMAL/'run163'),('V_XYZ',FORMAL/'run165'),
       ('X_60s',EXTERNAL/'VELOCITY-STA-20260926/V04/series15/run01'),
       ('Z_60s',EXTERNAL/'VELOCITY-STA-20260927/Z03/paired01/run01'))


def digest(path):
    with Path(path).open('rb') as stream:
        sha=hashlib.sha256()
        for chunk in iter(lambda:stream.read(1024*1024),b''):sha.update(chunk)
    return sha.hexdigest()


def _unique(pairs):
    out={}
    for key,value in pairs:
        if key in out:raise ValueError('Duplicate evidence JSON key: '+key)
        out[key]=value
    return out


def read(path):
    def invalid(value):raise ValueError('Nonfinite evidence JSON number: '+value)
    result=json.loads(Path(path).read_text(),object_pairs_hook=_unique,parse_constant=invalid)
    if not isinstance(result,dict):raise ValueError('Evidence JSON must be an object: '+str(path))
    return result


def _same(a,b):
    # Preserve boolean/integer/float representation instead of Python's1==True.
    return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)


def _flags(value,*,summary=False):
    if value.get('flight_accepted') is not False or value.get('controller_admission_checked') is not False:
        raise ValueError('Historical target probe must not claim controller/flight acceptance')
    if summary:
        if value.get('success') is not True or value.get('source_unchanged') is not True:
            raise ValueError('Historical target probe is not a successful unchanged result')
        if type(value.get('new_flights')) is not int or value['new_flights']!=0:
            raise ValueError('Historical probe must contain exactly zero new flights')
    elif value.get('component_valid') is not True or value.get('inputs_unchanged') is not True:
        raise ValueError('Historical case is not valid with unchanged inputs')
    if 'error' in value:raise ValueError('Successful probe retains an error field')


def _hashes(value,expected):
    if not isinstance(value,dict) or set(value)!={str(p) for p in expected}:
        raise ValueError('Missing/extra historical fingerprint paths')
    if any(type(sha) is not str or re.fullmatch('[0-9a-f]{64}',sha) is None for sha in value.values()):
        raise ValueError('Malformed historical SHA-256')


def _verify(root,sources,cases):
    """Private dependency seam for synthetic tests; check() fixes all paths."""
    root=Path(root);sources=tuple(Path(p) for p in sources);cases=tuple((label,Path(run)) for label,run in cases)
    if len(cases)!=6 or len({label for label,_ in cases})!=6 or len(sources)!=4 or len(set(sources))!=4:
        raise ValueError('Fixed six-case/four-source design required')
    summary_path=root/'summary.json';index={str(summary_path):digest(summary_path)}
    summary=read(summary_path);_flags(summary,summary=True)
    _hashes(summary.get('source_sha256_before'),sources)
    _hashes(summary.get('source_sha256_after'),sources)
    if summary['source_sha256_before']!=summary['source_sha256_after']:
        raise ValueError('Source changed during historical probe')
    expected_labels=[label for label,_ in cases]
    entries=summary.get('cases')
    if not isinstance(entries,list) or len(entries)!=6 or not all(isinstance(c,dict) for c in entries):
        raise ValueError('Exactly six complete historical cases required')
    if [case.get('label') for case in entries]!=expected_labels:
        raise ValueError('Historical labels/order/count differ from fixed six cases')
    for path,sha in summary['source_sha256_before'].items():
        if digest(path)!=sha:raise ValueError('Historical probe source drift: '+path)
        index[path]=sha
    for entry,(label,run) in zip(entries,cases):
        _flags(entry)
        path=root/(label+'.json');index[str(path)]=digest(path);record=read(path)
        if not _same(record,entry):raise ValueError('Case JSON differs from summary: '+label)
        _flags(record)
        if entry.get('source_run')!=str(run) or not isinstance(entry.get('components'),dict) or not entry['components']:
            raise ValueError('Wrong historical source or missing component evidence: '+label)
        result=read(run/'result.json');logs=result.get('logs')
        if not isinstance(logs,list) or len(logs)!=2 or not all(isinstance(log,dict) for log in logs):
            raise ValueError('Expected startup and complete historical ULogs: '+label)
        archives=[Path(log['archive']) for log in logs]
        if len(set(archives))!=2 or any(not p.is_absolute() or p.parent!=run or p.suffix!='.ulg' for p in archives):
            raise ValueError('Historical ULog paths differ from fixed source: '+label)
        inputs=[run/'job.json',run/'result.json',run/'runtime_parameters_start.json',*archives]
        _hashes(entry.get('input_sha256_before'),inputs);_hashes(entry.get('input_sha256_after'),inputs)
        if entry['input_sha256_before']!=entry['input_sha256_after']:
            raise ValueError('Historical inputs changed during probe: '+label)
        if not _same(entry.get('historical_job'),read(run/'job.json')):
            raise ValueError('Recorded historical job differs: '+label)
        for log,path in zip(logs,archives):
            if log.get('sha256')!=entry['input_sha256_before'][str(path)]:
                raise ValueError('Original result/ULog SHA differs: '+label)
        for path,sha in entry['input_sha256_before'].items():
            if digest(path)!=sha:raise ValueError('Historical input drift: '+path)
            if path in index and index[path]!=sha:raise ValueError('Conflicting shared historical input digest')
            index[path]=sha
    # A second pass catches changes concurrent with JSON parsing/checking; no
    # file is rewritten and each returned digest belongs to the checked input.
    for path,sha in index.items():
        if digest(path)!=sha:raise ValueError('Historical evidence changed during verification: '+path)
    return dict(success=True,cases=6,labels=expected_labels,new_flights=0,
        controller_admission_checked=False,flight_accepted=False,
        summary_path=str(summary_path),fingerprints=index,
        scope='Six old target/P/FF component probes only; not new flights or controller admission')


def check():
    return _verify(EVIDENCE,SOURCES,CASES)


if __name__=='__main__':print(json.dumps(check(),indent=2,ensure_ascii=False))
