#!/usr/bin/env python3
"""Prepare an auditable remaining-budget ledger. Never launches simulation."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I05R/RC-formal03')
JOBS_SHA = 'faf1291ebde477e38b16d99b4a86ab488f12cf56c5a0d51dd77be0ab889db275'
PROGRESS_SHA = '5e2c20ef7343601a9ef9dfc7bede87afd250918f466a8e41c680381b27551d38'


def prepare():
    for name, expected in [('jobs.json', JOBS_SHA), ('progress.json', PROGRESS_SHA)]:
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Prior ledger changed: '+name)
    jobs = json.loads((ROOT/'jobs.json').read_text())
    progress = json.loads((ROOT/'progress.json').read_text())['rows']
    assert len(jobs) == 18 and len(progress) == 1
    assert (jobs[0]['algorithm'],jobs[0]['seed'],jobs[0]['divisor']) == ('esta',7001,1)
    assert progress[0]['success'] is False
    pending = []
    for index, job in enumerate(jobs[1:],1):
        pending.append(dict(original_index=index, algorithm=job['algorithm'],mode=job['mode'],
            axes=job['parameters']['MC_STA_AXES'],divisor=job['divisor'],seed=job['seed'],
            immutable_original_job_sha256=hashlib.sha256(json.dumps(job,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            status='not_started',new_attempts_allowed=1))
    return dict(protocol='RC_CONTINUATION_LOGGING_V1_CN.md',scope='development admission with disclosed amended analysis',
        original_root=str(ROOT),original_jobs_sha256=JOBS_SHA,original_progress_sha256=PROGRESS_SHA,
        original_budget=18,already_attempted=1,remaining_budget=17,new_flight_budget=0,
        new_flight_budget_note='No additional attempts beyond the original 18; the remaining 17 are unexecuted.',
        previous_run=dict(original_index=0,algorithm='esta',seed=7001,divisor=1,
            original_acceptance=False,revised_acceptance=None,disposition='offline amended assessment first; never refly or overwrite'),
        continuation_directory=str(ROOT.parent/'RC-formal03-continuation01'),
        execution_source_head=None,execution_source_note='Must bind to a clean implementation/protocol commit before execution.',
        pending=pending)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    ledger=prepare()
    with args.output.open('x') as stream:
        json.dump(ledger,stream,indent=2,ensure_ascii=False)
        stream.write('\n')
    print('Verified original hashes; prepared 17 pending jobs; no flight started.')
