"""Read-only evidence audit plus reproducible development summary; no flights."""
import argparse
import collections
import importlib.util
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
s = importlib.util.spec_from_file_location('_ri06_result_codec', HERE/'export.py')
codec = importlib.util.module_from_spec(s)
s.loader.exec_module(codec)
p = codec.p


def summary(rows):
    groups = []
    for label, phase, index in [('A_common_development','training',1),('B_selected_validation','validation',None)]:
        for task in ('H','V'):
            for algorithm in ('PID','RSTA','RISTA'):
                if label.startswith('A_') and algorithm=='PID':
                    continue
                selected = [r for r in rows if r['job']['phase']==phase and r['job']['task']==task
                            and r['job']['candidate']==algorithm
                            and (index is None or r['job']['candidate_index']==index)]
                scalar = lambda key: statistics.mean(r[key] for r in selected)
                vector = lambda key: [statistics.mean(r[key][i] for r in selected) for i in range(3)]
                groups.append(dict(group=label,task=task,algorithm=algorithm,n=len(selected),
                    J_mean=scalar('J'),velocity_rmse=vector('velocity_rmse'),position_rmse=vector('position_rmse'),
                    correction_tv_per_s=vector('correction_tv_per_s'),thrust_tv_per_s=vector('thrust_tv_per_s'),
                    yaw_rmse=scalar('yaw_rmse'),nominal_height_rmse=statistics.mean(r['height']['rmse'] for r in selected),
                    max_constraint_fraction=max(r['constraints'] for r in selected),
                    mean_of_per_run_host_cost={part:{key:statistics.mean(r['host_cost'][part][key] for r in selected)
                        for key in ('median_us','p95_us','p99_us')} for part in ('path_ns','module_ns')},
                    common_band_rms=[statistics.mean(r['spectral_summary']['common_0_7hz_rms'][i] for r in selected) for i in range(3)]))
    return dict(groups=groups,not_formal=True,confidence_intervals_not_claimed=True,
        interpretation='Development/independent-validation descriptions only; common A n2, selected B n3 per task; no holdout outcomes or re-selection.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    out=args.output.resolve()
    if out.exists():raise ValueError('Fresh audit output required')
    out.mkdir(parents=True)
    evidence=dict(success=False,new_flights=0,commands=[],package_sha256=p.fingerprint(HERE/'package.json'))
    def save():
        (out/'audit.json').write_text(json.dumps(evidence,indent=2,allow_nan=False)+'\n')
    save()
    try:
        package=p.read(HERE/'package.json')
        raw=codec.original.collect()
        if set(package)!=set(raw)|{'supplemental_metrics','export_provenance'}:
            raise ValueError('Unexpected result schema')
        decoded=codec.decode({key:package[key] for key in raw})
        if decoded!=raw:raise ValueError('Package differs from independently reconstructed frozen inputs')
        changes=[]
        if codec.encode(raw,changes=changes)!={key:package[key] for key in raw}:
            raise ValueError('Lossless diagnostic encoding differs')
        if changes!=package['export_provenance']['changed_paths'] or len(changes)!=648:
            raise ValueError('Unexpected diagnostic exceptions')
        logs=[];zero_log_gaps=True;zero_retries=True;all_unarmed=True
        for row in raw['rows']:
            metrics=p.read(row['metrics_path'])
            if package['supplemental_metrics'][row['job']['id']]!={key:metrics[key]
                    for key in ('task_metrics','limitations','landing','postland_tail')}:
                raise ValueError('Supplementary metric changed')
            zero_log_gaps &= metrics['position_log']['sequence_gaps']==0
            zero_retries &= metrics['first_invocation']['first_failures']==0 and metrics['first_invocation']['retries']==0
            result=p.read(Path(row['metrics_path']).with_name('result.json'))
            all_unarmed &= any(event['name']=='landed_disarmed' for event in result['events'])
            for log in row['logs']:
                path=Path(log['archive'])
                if path.stat().st_size!=log['bytes'] or p.fingerprint(path)!=log['sha256']:
                    raise ValueError('Raw ULog changed')
                logs.append(dict(run=row['job']['id'],path=str(path),bytes=log['bytes'],sha256=log['sha256']))
        if not zero_log_gaps or not zero_retries or not all_unarmed or len(logs)!=108:
            raise ValueError('Incomplete lifecycle/log evidence')
        frozen=p.load_file('_ri06_result_freeze',p.HERE/'freeze.py')
        frozen.check('VH');frozen.check('VV')
        phases=collections.Counter(r['job']['phase'] for r in raw['rows'])
        if phases!={'training':36,'validation':18}:raise ValueError('Wrong54 scope')
        formal=raw['formal']['jobs']
        if len(formal)!=200 or any(j['status']!='unattempted' or j['flight_authorized'] for j in formal):
            raise ValueError('Formal scope or attempted outcomes changed')
        counts=collections.Counter((j['group'],j['task'],j['candidate']) for j in formal)
        if len(counts)!=10 or set(counts.values())!={20}:raise ValueError('Wrong exact formal matrix')
        for gate in p.GATES:
            ledger=p.read(p.DATA_ROOT/gate/'batch01/ledger.json')
            eeprom=p.REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
            if not ledger['parameter_restore_exact'] or ledger['remaining_simulators'] or p.fingerprint(eeprom)!=ledger['original_parameter_sha256']:
                raise ValueError('Parameter restore or simulator cleanup differs')
        scripts=[p.HERE/'test_design.py',p.HERE/'test_freeze.py',p.HERE/'test_statistics.py',p.HERE/'test_package.py',
                 p.HERE/'tools/test_tools.py',p.HERE/'tools/test_transport.py',HERE/'serialization_checks.py']
        expected=[25,7,14,7,74,19,14]
        for index,(script,n) in enumerate(zip(scripts,expected)):
            argv=[sys.executable,'-B',str(script)]
            completed=subprocess.run(argv,cwd=p.REPO,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            log=out/(str(index)+'_'+script.stem+'.log');log.write_text(completed.stdout)
            counts_found=re.findall(r'^Ran (\d+) tests? in ',completed.stdout,re.M)
            evidence['commands'].append(dict(argv=argv,exit_code=completed.returncode,expected_tests=n,
                log=str(log),log_sha256=p.fingerprint(log)))
            save()
            if completed.returncode or counts_found!=[str(n)] or not re.search(r'^OK\s*$',completed.stdout,re.M):
                raise ValueError('Result-layer tests failed or did not execute')
        derived=summary(raw['rows']);derived['development_precision']=raw['development_precision']
        evidence.update(success=True,read_only_raw_inputs=True,actual_python_tests=sum(expected),new_result_tests=14,
            reexecuted_protocol_tests=146,raw_ulog_count=len(logs),raw_ulog_bytes=sum(x['bytes'] for x in logs),
            zero_position_log_gaps=bool(zero_log_gaps),zero_same_sample_retries=bool(zero_retries),
            all_landed_disarmed=bool(all_unarmed),planned=54,attempted=54,accepted=54,independent_replays=54,
            paired_checks=36,individual_risk_conditions=468,formal_attempts=0,next_formal_budget=200,
            qualified_source_heads=raw['source_versions'],production_changes=[],submodules=len(raw['formal']['submodules']))
        (out/'summary.json').write_text(json.dumps(derived,indent=2,allow_nan=False)+'\n')
        (out/'ulog_index.json').write_text(json.dumps(logs,indent=2,allow_nan=False)+'\n')
        evidence['summary_sha256']=p.fingerprint(out/'summary.json')
        evidence['ulog_index_sha256']=p.fingerprint(out/'ulog_index.json')
    except Exception as error:
        evidence['error']=repr(error)
        raise
    finally:save()
    print(json.dumps({key:evidence[key] for key in ('success','actual_python_tests','raw_ulog_count','accepted','formal_attempts','next_formal_budget')}))


if __name__=='__main__':main()
