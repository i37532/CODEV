#!/usr/bin/env python3
"""Offline complete-chain comparison against immutable accepted revision10 logs.

This deliberately cannot create accepted flight/gate/qualification receipts.
Original provenance and all scientific predicates run; only audited timestamp
bindings change. Scientific outputs must remain equal on untied old records.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import traceback

HERE=Path(__file__).resolve().parent


def load(name,path):
    s=importlib.util.spec_from_file_location('_position11_diagnostic_'+name,path)
    m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def bindings(original):
    a=load('adapter',HERE/'adapter.py')
    heading=a.build_heading()
    r02,components=a.bind_components(original._numeric_r02,original._components)
    return a,dict(height_evidence=a.bind_height(original._height,heading),
        r02=r02,check_components=components,check_targets=a.bind_targets(original.targets),
        exact_output_match=a.callbacks.exact_output_match,AttitudeClockPolicy=a.build_attitude_policy())


def run(source,output):
    source,output=Path(source).resolve(),Path(output).resolve()
    job=json.loads((source/'job.json').read_text())
    if job['revision'] not in ('r03_revision09','r03_revision10'):
        raise ValueError('This audit only supports original revision09/10 inputs')
    old=load('original',HERE.parent/job['revision']/'analyzer.py')
    raw_replay=load('snapshot',HERE.parent/job['revision']/'replay.py')
    before=raw_replay.raw_snapshot(source)
    old_metrics=json.loads((source/'r03_metrics.json').read_text())
    if old_metrics.get('accepted') is not True: raise ValueError('Accepted historical comparator required; no failed-log reclassification')
    protocol=old.replay_protocol(source,job)
    old._handoff.copy_sidecars(source,output)
    a,overrides=bindings(old)
    def provenance(run,p,j):
        if Path(run)!=output: raise ValueError('Wrong diagnostic output')
        old._handoff.copied_input_binding(source,output)
        return old.provenance(source,p,j)
    def save(path,value):
        if Path(path).name=='r03_metrics.json': value=old._handoff.diagnostic_payload(value)
        old._inherited.save(path,value)
    result=dict(diagnostic_only=True,accepted=False,flight_accepted=False,new_flights=0,
        historical_acceptance_unchanged=False,source=str(source),output=str(output),success=False,
        input_sha256_before=before)
    try:
        fn=a.bind_analysis(old._inherited.analyze,provenance=provenance,save=save,**overrides)
        metrics=fn(output,protocol,job)
        result['complete_checks']=metrics.get('accepted') is True
        result['error']=metrics.get('error')
        result['metrics_equal']={key:metrics.get(key)==old_metrics.get(key) for key in
            ('diagnostic','spectral_summary','host_cost','position_rmse','yaw_rmse','height','lifecycle',
             'pid_reconstruction','actual_output','rate_actuator','landing','landing_health','mixer')}
        result['spectrum_equal']=a.digest(output/'spectra.json')==a.digest(source/'spectra.json') if (output/'spectra.json').exists() else False
        result['success']=result['complete_checks'] and all(result['metrics_equal'].values()) and result['spectrum_equal']
    except Exception as exc:
        result.update(success=False,error=repr(exc),traceback=traceback.format_exc())
    result['input_sha256_after']=raw_replay.raw_snapshot(source)
    result['historical_acceptance_unchanged']=before==result['input_sha256_after']
    result['success']=result['success'] and result['historical_acceptance_unchanged']
    (output/'diagnostic_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();result=run(args.source,args.output)
    print(json.dumps({k:v for k,v in result.items() if not k.startswith('input_sha256')},indent=2))
    raise SystemExit(0 if result['success'] else 1)
