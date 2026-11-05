#!/usr/bin/env python3
"""Independent result recomputation from raw per-run metrics; zero flights."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ri07_audit_collector',HERE/'collect.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


def audit(package):
    for path,expected in package['inputs'].items():
        c.require(c.b.digest(path)==expected,'Changed pinned input: '+path)
    for entry in package['logs']:
        c.verify_log(dict(archive=entry['path'],bytes=entry['bytes'],sha256=entry['sha256']))
    raw={}
    for row in package['rows']:
        m=c.b.read(row['metadata']['metrics_path']);j=m['job'];d=m['diagnostic']
        c.require(d['J']==row['J'] and d['error']['rmse']==row['velocity_rmse'],'Changed science metric')
        c.require(math.isclose(math.fsum(d['error']['rmse'])/3,d['J'],abs_tol=1e-15),'J reconstruction mismatch')
        c.require(j['parameters']==package['parameters'][j['group']+'/'+j['task']+'/'+j['candidate']]['parameters'],
                  'Parameter group mismatch')
        c.require(j['parameters_sha256']==hashlib.sha256(json.dumps(j['parameters'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                  'Parameter SHA mismatch')
        key=(j['group'],j['block'],j['task'],j['candidate']);c.require(key not in raw,'Duplicate raw observation')
        raw[key]=m
    c.require(len(raw)==200,'Incomplete200 raw members')
    for group,labels in c.stats.COMPARISONS.items():
        # Independently assemble the full block matrix; do not reuse paired_matrices.
        a=[]
        for block in range(1,21):
            values=[]
            for label in labels:
                task,comparison=label.split(':');later,earlier=comparison.split('-')
                values.append(raw[group,block,task,later]['diagnostic']['J']-raw[group,block,task,earlier]['diagnostic']['J'])
            a.append(values)
        c.require(a==package['paired_differences'][group],'Paired matrix recomputation differs')
        repeated=dict(primary=c.stats.summarize(a,group),exploratory_sign_flip=c.stats.exploratory_sign_flip(a,group))
        c.require(repeated==package['statistics'][group],'Preregistered statistics recomputation differs')
    for row in package['group_summary']:
        values=[m for key,m in raw.items() if (key[0],key[2],key[3])==(row['group'],row['task'],row['candidate'])]
        c.require(len(values)==row['n']==20,'Wrong group sample count')
        c.require(math.isclose(math.fsum(m['diagnostic']['J'] for m in values)/20,row['J_mean'],abs_tol=1e-15),
                  'Group mean differs')
        for axis in range(3):
            c.require(math.isclose(math.fsum(m['diagnostic']['error']['rmse'][axis] for m in values)/20,
                                 row['velocity_rmse_mean'][axis],abs_tol=1e-15),'Axis mean differs')
    batch=Path(c.b.api().load_protocol()['artifacts']['new_run_root'])
    snapshot=c.b.local('replay').snapshot(batch)
    c.require(hashlib.sha256(c.strict(snapshot).encode()).hexdigest()==package['original_snapshot_sha256'],
              'Original batch changed since collection')
    c.b.api().check()
    return dict(passed=True,raw_metrics=200,raw_logs=len(package['logs']),verified_bytes=package['log_bytes'],
                paired_matrices=2,primary_comparisons=8,statistical_recompute_exact=True,
                group_summaries=10,inputs=len(package['inputs']),new_flights=0,
                collector_sha256=c.b.digest(HERE/'collect.py'),audit_sha256=c.b.digest(__file__))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    value=audit(c.b.read(args.package));value['package_sha256']=c.b.digest(args.package)
    c.write_new(args.output,value);print(c.strict(value))
