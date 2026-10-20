#!/usr/bin/env python3
"""Two upstream diagnostics, never R03 acceptance. Frozen scientific checks retained."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent


def load(name,path):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def read(path):return json.loads(Path(path).read_text())


def exact(a,b):
    return json.dumps(a,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(b,sort_keys=True,separators=(',',':'),allow_nan=False)


# Seal the actual scientific adapter, not only its filename. It already seals
# numeric05 and the complete private height -> handoff -> XYZ target chain.
SCIENCE=HERE.parent/'r03_revision06/analyzer.py'
if __name__=='__main__' and '--historical-diagnostic' in sys.argv[1:]:
    _order=argparse.ArgumentParser(add_help=False)
    _order.add_argument('--import-order',default='runner-first')
    _args,_unknown=_order.parse_known_args()
    if _args.import_order=='runner-first':
        load('_upstream08_early_runner',HERE/'runner.py')
# Source hash is frozen by freeze.py before qualification. This loader also
# verifies the immutable committed revision06 identity, independent of freeze.
import subprocess
_committed=subprocess.check_output(['git','show','09c96f3cd0481f8b6672aa047cd7d49ffd21fc03:'+str(SCIENCE.relative_to(HERE.parents[3]))],cwd=HERE.parents[3])
if hashlib.sha256(_committed).hexdigest()!=digest(SCIENCE):
    raise ValueError('Immutable revision06 analysis changed')
old=load('_upstream08_science',SCIENCE)
timing=load('_upstream08_timing',HERE/'timing.py')


def api():return load('_upstream08_analysis_protocol',HERE/'protocol.py')


def provenance(run,p,job):
    a=api();a.require_execution_authority();frozen=a.load_protocol()
    excluded={'startup_overrides','qualification_path'}
    if (not exact({k:v for k,v in p.items() if k not in excluded},{k:v for k,v in frozen.items() if k not in excluded})
            or not any(exact(job,j) for j in frozen['jobs'])
            or not exact(p['startup_overrides'],{**frozen['startup_overrides'],**job['parameters']})):
        raise ValueError('Wrong diagnostic protocol/job/parameter overlay')
    run=Path(run).resolve();expected=(Path(p['artifacts']['new_run_root'])/job['id']).resolve()
    if run!=expected:raise ValueError('Diagnostic archive outside exact fresh attempt')
    record=read(run/'result.json');qp=Path(p['qualification_path']).resolve()
    q=a.require_qualification(record['source_head'],qp)
    approval=read(run/'authorization.json')
    if not exact(approval,a.authorization_binding(q,qp)):
        raise ValueError('Diagnostic authorization does not match qualified source')
    if not exact(read(run/'run_protocol.json'),p) or not exact(read(run/'job.json'),job):
        raise ValueError('Saved diagnostic inputs differ')
    qr=read(run/'qualification_reference.json')
    if Path(qr.get('path','')).resolve()!=qp or qr.get('sha256')!=digest(qp):
        raise ValueError('Diagnostic qualification reference changed')
    if (record.get('binary_sha256')!=q['firmware_sha256'] or
            record.get('scenario_sha256')!=digest(p['execution_path']) or
            record.get('scenario_path')!=p['execution_path']):
        raise ValueError('Diagnostic source/binary/scenario changed')
    logs=record.get('logs',[])
    if (not logs or len({x['archive'] for x in logs})!=len(logs)
            or any(Path(x['archive']).resolve().parent!=run for x in logs)):
        raise ValueError('Unowned or duplicate diagnostic logs')
    restore=read(run/'parameter_restore.json')
    expected_restore=dict(parameter_restore_exact=True,remaining_simulators=[],stopped_before_restore=True,
        source_head=q['source_head'],gate=job['gate'],job_id=job['id'],
        original_parameter_sha256=digest(run/'original_parameters.bson'),
        restored_parameter_sha256=digest(run/'original_parameters.bson'))
    if any(not exact(restore.get(k),v) for k,v in expected_restore.items()):
        raise ValueError('Diagnostic parameter restore/cleanup incomplete')
    for name in ('runtime_parameters_start.json','runtime_parameters_end.json'):
        if read(run/name).get('SDLOG_PROFILE')!=3089:
            raise ValueError('Diagnostic logger mask not applied/retained')
    return a.qualification_binding(q['source_head'])


def non_accepting(value,complete):
    out=copy.deepcopy(value)
    out.update(diagnostic_only=True,accepted=False,flight_accepted=False,
        accepted_for_R03=0,r03_gate_pass=False,scientific_checks_complete=bool(value.get('accepted')),
        diagnostic_checks_complete=bool(complete))
    return out


def analyze(run,p,job):
    run=Path(run);provenance(run,p,job)  # No output writes for a foreign/legacy run.
    prep={}
    def bound(r,protocol,j):
        b=provenance(r,protocol,j);prep.update(old.prearm_evidence(r));return b
    def diagnostic_save(path,value):
        if Path(path).resolve().parent!=run.resolve():raise ValueError('Unowned scientific output')
        # Intermediate baseline outputs are explicitly diagnostic too.
        out=non_accepting(value,False) if isinstance(value,dict) and 'accepted' in value else value
        old._inherited.save(path,out)
    science=old.full_analysis(bound,save=diagnostic_save)(run,p,job)
    result=non_accepting(science,False)
    result['prearm_preparation']=prep
    result['candidate_numeric_binding']=old.NUMERIC_BINDING
    result['handoff_dependency_binding']=old.HANDOFF_BINDING
    if science.get('accepted') is True:
        try:
            events={e['name']:e['timestamp_us'] for e in read(run/'result.json')['events']}
            log=old._inherited.ULog(science['ulog']['archive'])
            result['upstream_timing']=timing.inspect_log(log,events['takeoff_command'],events['landed_disarmed'])
            result['diagnostic_checks_complete']=True
        except (ValueError,KeyError,TypeError,IndexError) as error:
            result['error']='Additional timing evidence: '+str(error)
    old._inherited.save(run/'diagnostic_metrics.json',result)
    return result


def compare(pid,candidate):
    protocol=api();jobs=protocol.load_protocol()['jobs']
    for value in (pid,candidate):
        job=value.get('job',{})
        if job.get('mode') not in (0,1) or not any(exact(job,j) for j in jobs):
            raise ValueError('Pair is outside the exact PID/ESTA diagnostic manifest')
        if (value.get('diagnostic_checks_complete') is not True or value.get('accepted') is not False
                or not exact(value.get('accepted_for_R03'),0) or value.get('r03_gate_pass') is not False
                or value.get('scientific_checks_complete') is not True
                or value.get('flight_accepted') is not False
                or value.get('prearm_preparation',{}).get('valid') is not True
                or not exact(value.get('candidate_numeric_binding'),old.NUMERIC_BINDING)
                or not exact(value.get('handoff_dependency_binding'),old.HANDOFF_BINDING)):
            raise ValueError('Only completed, non-accepting diagnostics may be compared')
        binding=value.get('binding',{})
        if (binding.get('revision')!='r03_upstream08' or binding.get('diagnostic_only') is not True
                or binding.get('count_as_R03_acceptance') is not False
                or any(not exact(binding.get(k),v) for k,v in protocol.budget().items())):
            raise ValueError('Foreign diagnostic binding')
    # The immutable scientific predicate expects an accepted input. The private
    # transient views mean "all scientific checks passed", NOT R03 acceptance;
    # no such view is returned, saved, or added to the R03 attempt accounting.
    a=copy.deepcopy(pid);b=copy.deepcopy(candidate);a['accepted']=b['accepted']=True
    risk=old._inherited.compare(a,b)
    return dict(development_risk_passed=risk['accepted'],checks=risk['checks'],
        diagnostic_only=True,accepted=False,accepted_for_R03=0,r03_gate_pass=False,
        criterion=risk['criterion'])


def historical(source,dest,order):
    """Exercise the same full_analysis, retaining the historical failure verdict."""
    source,dest=Path(source).resolve(),Path(dest).resolve()
    if dest.exists() or source==dest or source in dest.parents:
        raise ValueError('Fresh separate historical diagnostic output required')
    if order=='runner-first':load('_upstream08_historical_runner',HERE/'runner.py')
    elif order!='analyzer-first':raise ValueError('Invalid import order')
    job=read(source/'job.json');p=old.replay_protocol(source,job)
    before={str(x):digest(x) for x in source.rglob('*') if x.is_file()}
    metrics_path=source/'r03_metrics.json'
    if metrics_path.exists():
        original=read(metrics_path)
    else:
        record=read(source/'result.json')
        if record.get('success') is not False:
            raise ValueError('Missing historical metrics requires an explicitly failed result')
        original=dict(accepted=False,error=record.get('error'))
    old._handoff.copy_sidecars(source,dest)
    copied=old._handoff.copied_input_binding(source,dest)
    def save(path,value):
        if Path(path).resolve().parent!=dest:raise ValueError('Unexpected historical output')
        out=non_accepting(value,False) if isinstance(value,dict) and 'accepted' in value else value
        old._inherited.save(dest/Path(path).name,out)
    def original_provenance(run,protocol,j):
        if Path(run).resolve()!=dest:raise ValueError('Historical analysis must use copied sidecars')
        return old.provenance(source,protocol,j)
    result=old.full_analysis(original_provenance,save=save)(dest,p,job)
    complete=result.get('accepted') is True
    # run030 must remain invalid. Its missing landed_disarmed event is not
    # synthesized and no tail samples or reset events are discarded.
    if complete is not original['accepted']:
        raise ValueError('Historical scientific pass/fail changed')
    after={str(x):digest(x) for x in source.rglob('*') if x.is_file()}
    if before!=after:raise ValueError('Historical input mutated')
    record=dict(diagnostic_only=True,accepted=False,accepted_for_R03=0,new_flights=0,
        source_directory=str(source),original_accepted=original['accepted'],
        scientific_checks_complete=complete,source_inputs_unchanged=True,
        historical_acceptance_unchanged=True,original_error=original.get('error'),
        replay_error=result.get('error'),fingerprints=before,copied_sidecars=copied)
    old._inherited.save(dest/'evidence.json',record)
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--historical-diagnostic',action='store_true')
    parser.add_argument('--import-order',choices=['runner-first','analyzer-first'],default='runner-first')
    args=parser.parse_args()
    if not args.historical_diagnostic:raise ValueError('Use the qualified two-attempt runner for prospective analysis')
    print(json.dumps(historical(args.run,args.output,args.import_order),indent=2))
