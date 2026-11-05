"""Collect explicit320 outcomes after independent replay; never executes flights."""
import argparse
import json
from pathlib import Path
from common import jobs, design, fingerprint, qualification, CONFIG
from design import empty_outcomes
from package import outcome_rows


def collect(batch, replay):
    ledger_path=batch/'ledger.json';ledger=json.loads(ledger_path.read_text())
    evidence=json.loads((replay/'evidence.json').read_text())
    if (ledger.get('planned')!=320 or ledger.get('source_head')!=qualification()['source_head']
        or not ledger.get('parameter_restore_exact') or ledger.get('remaining_simulators')
        or not evidence.get('success') or evidence.get('flights_run')!=0
        or evidence.get('ledger_sha256')!=fingerprint(ledger_path)):
        raise ValueError('Unqualified, active, unrestored batch or wrong independent replay')
    manifest=jobs();outcomes=empty_outcomes(design());stopped=False
    if len(ledger['attempts'])>320:raise ValueError('Exceeded frozen budget')
    accepted_indices=[]
    for i,item in enumerate(ledger['attempts']):
        if stopped or item['attempt']!=i+1 or item['job']!=manifest[i]:raise ValueError('Wrong order or continued after failure')
        row=outcomes[i];run=Path(item['directory'])
        if item['status']=='accepted':
            source=run/'xyz_metrics.json';repeat=replay/run.name/'xyz_metrics.json'
            if fingerprint(source)!=item['metrics_sha256']:raise ValueError('Changed original metrics')
            accepted_indices.append(i+1)
            row.update(status='accepted',metrics_path=str(source),metrics_sha256=fingerprint(source),
                replay_metrics_path=str(repeat),replay_metrics_sha256=fingerprint(repeat))
            row.pop('reason')
        elif item['status']=='failed':
            row.update(status='failed',reason=item.get('error') or 'Required gate failed; inspect preserved raw evidence')
            stopped=True
        else:raise ValueError('Batch still running/unknown outcome; do not invent completion')
    commands=evidence['commands']
    if ([x['attempt'] for x in commands]!=accepted_indices
        or any(x['exit_code']!=0 or not x.get('metrics_values_identical') for x in commands)):
        raise ValueError('Incomplete independent replay')
    for row in outcomes[len(ledger['attempts']):]:
        row['reason']='Frozen job unattempted after stop/not started; not a flight outcome'
    outcome_rows(outcomes)
    return outcomes


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch',type=Path,required=True);p.add_argument('--replay',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    rows=collect(a.batch.resolve(),a.replay.resolve())
    with a.output.open('x') as stream:json.dump(rows,stream,indent=2);stream.write('\n')
    print('Preserved all320 outcomes; no retries or invented missing errors')


if __name__=='__main__':main()
