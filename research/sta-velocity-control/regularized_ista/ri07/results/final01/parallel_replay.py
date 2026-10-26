#!/usr/bin/env python3
"""Bounded post-result decode orchestration; frozen analyzers/rules unchanged.

Never starts a simulator. Each subprocess actually decodes its own original run
into a new directory; neither prior metrics nor receipts substitute for replay.
The frozen replay.verify_complete validates the finished evidence independently.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
STAGE=HERE.parents[1]
sys.path.insert(0,str(STAGE/'tools'))
import bindings as b


def ordered_map(function, items, workers):
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError('Only1..4 read-only decoder workers allowed')
    with ThreadPoolExecutor(max_workers=workers) as pool:
        yield from pool.map(function,items)


def run(output,workers):
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError('Only1..4 workers allowed')
    p,r=b.api(),b.local('replay')
    p.check();protocol=p.load_protocol('FORMAL');p.require_execution_authority('FORMAL')
    batch=Path(protocol['artifacts']['new_run_root']).resolve();output=output.resolve()
    r.require(output.parent==batch.parent and output!=batch,'New sibling replay directory required')
    r.require(not (batch.parent/'gate_pass.json').exists(),'Do not replace existing finalization')
    ledger=b.read(batch/'ledger.json');r.validate_ledger(ledger,protocol)
    reference=b.read(batch/'qualification_reference.json')
    r.require(reference['sha256']==b.digest(reference['path']),'Changed qualification')
    q=p.archive_qualification('FORMAL',ledger['source_head'],reference['path'])
    r.require(q['firmware_sha256']==ledger['firmware_sha256'],'Wrong binary binding')
    originals={item['job']['id']:r.check_result_binding(item,ledger) for item in ledger['attempts']}
    before=r.snapshot(batch);output.mkdir(exist_ok=False)
    summary=dict(stage=p.stage('FORMAL'),revision='ri07',gate='FORMAL',source_head=ledger['source_head'],
        success=False,new_flights=0,replayed=0,commands=[],ledger_sha256=b.digest(batch/'ledger.json'),
        original_input_sha256_before=before,qualified_firmware_sha256=ledger['firmware_sha256'],
        orchestration=dict(workers=workers,source=str(HERE/'parallel_replay.py'),
                           sha256=b.digest(HERE/'parallel_replay.py'),analyzer_changed=False))
    metrics={}
    def decode(item):
        name=item['job']['id'];source=Path(item['directory']);destination=output/name
        command=[sys.executable,'-B',str(STAGE/'tools/analyzer.py'),str(source),'--output',str(destination)]
        log=output/(name+'.log');began=time.monotonic()
        with log.open('xb') as stream:
            completed=subprocess.run(command,cwd=b.REPO,stdout=stream,stderr=subprocess.STDOUT)
        receipt=dict(argv=command,cwd=str(b.REPO),returncode=completed.returncode,
            elapsed_s=time.monotonic()-began,log=str(log),log_sha256=b.digest(log))
        # Persist every subprocess receipt even if another worker fails.
        b.save(output/(name+'_command.json'),receipt)
        if completed.returncode!=0:return name,receipt,None,'Decoder exit nonzero'
        repeated=b.read(destination/'r03_metrics.json')
        if not b.exact(originals[name],repeated):return name,receipt,None,'Metrics differ'
        if b.digest(source/'spectra.json')!=b.digest(destination/'spectra.json'):
            return name,receipt,None,'Spectrum bytes differ'
        return name,receipt,repeated,None
    try:
        errors=[]
        for name,receipt,repeated,error in ordered_map(decode,ledger['attempts'],workers):
            summary['commands'].append(receipt)
            if error:errors.append(dict(id=name,error=error))
            else:
                metrics[name]=repeated;summary['replayed']+=1
            print(name,'replayed' if not error else error,flush=True)
        r.require(not errors,'Read-only replay errors: '+repr(errors))
        summary['pairs']=r.recompute_pairs(ledger,metrics)
        summary['success']=summary['replayed']==200 and len(summary['pairs'])==80
    except BaseException as error:
        summary['error']=repr(error)
    finally:
        summary['original_input_sha256_after']=r.snapshot(batch)
        summary['source_inputs_unchanged']=summary['original_input_sha256_after']==before
        summary['success']=summary['success'] and summary['source_inputs_unchanged']
        b.save(output/'summary.json',summary)
    r.require(summary['success'],'Incomplete parallel replay; original trials unchanged')
    # This is the ORIGINAL frozen verifier, not a relaxed parallel substitute.
    r.verify_complete(output,gate='FORMAL')
    receipt=dict(stage=p.stage('FORMAL'),revision='ri07',gate='FORMAL',accepted=True,
        planned=200,attempts=200,accepted_runs=200,independent_replays=200,paired_checks=80,missing=0,
        source_head=ledger['source_head'],firmware_sha256=ledger['firmware_sha256'],
        ledger_sha256=b.digest(batch/'ledger.json'),replay_summary_path=str(output/'summary.json'),
        replay_summary_sha256=b.digest(output/'summary.json'),parameter_restore_exact=True,
        new_flights_by_replay=0,scope='Iris SITL frozen formal A/B; not real hardware')
    with (batch.parent/'gate_pass.json').open('x') as stream:
        json.dump(receipt,stream,indent=2);stream.write('\n')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args();result=run(args.output,args.workers)
    print(json.dumps(dict(success=result['success'],replayed=result['replayed'],new_flights=0)))
