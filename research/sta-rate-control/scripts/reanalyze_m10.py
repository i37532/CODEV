#!/usr/bin/env python3
"""Explicit versioned offline reanalysis. Never rerun a flight or erase evidence."""
import argparse
import contextlib
import hashlib
import json
from pathlib import Path
import shutil
from analyze_m10 import analyze


def main(root,version):
    records=sorted(root.glob('*.execution.json'))
    for record in records:
        label=record.name.removesuffix('.execution.json');run=root/label
        reviewed=root/(label+'.adjudication.json')
        if reviewed.exists() and json.loads(reviewed.read_text()).get('retained_prearm_gap'):
            decision=json.loads(reviewed.read_text())
            assert hashlib.sha256((run/'m10_analysis.json').read_bytes()).hexdigest()==decision['new_analysis_sha256']
            print(label,'retained invalid pre-arm gap; no imputation/reflight',flush=True)
            continue
        if not json.loads((run/'result.json').read_text())['success']:continue
        archive=run/('analysis_before_'+version);archive.mkdir(exist_ok=False)
        for name in ('m10_analysis.json','m09_analysis.json','m09_spectra.npz','analysis_details.log',
                     'metrics.json','ulog_initial_parameters.json','ulog_topic_inventory.json'):
            if (run/name).exists():shutil.copyfile(run/name,archive/name)
        with (run/('reanalysis_'+version+'.log')).open('w') as stream,contextlib.redirect_stdout(stream):
            result=analyze(run)
        adjudication=dict(reason=version,original_execution=str(record),flight_repeated=False,
                          analysis_resolved_without_reflight=bool(result['success']),
                          retained_control_failure=result.get('failure_class')=='control_boundary',
                          archived_originals={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in archive.iterdir()},
                          new_analysis_sha256=hashlib.sha256((run/'m10_analysis.json').read_bytes()).hexdigest())
        (root/(label+'.adjudication.json')).write_text(json.dumps(adjudication,indent=2)+'\n')
        print(label,result['success'],flush=True)
        if not result['success'] and result.get('failure_class')!='control_boundary':
            raise RuntimeError('Reanalysis has unresolved infrastructure/data/flight failure; do not resume')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--version',required=True)
    a=p.parse_args();main(a.root.resolve(),a.version)
