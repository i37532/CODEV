"""Read-only formal manifest/statistics entry. NEVER starts a simulator."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

REPO=Path('/home/yr/Desktop/Codev-autopilot')
PROTOCOL=REPO/'research/sta-velocity-control/v08/protocol04'
sys.path.insert(0,str(PROTOCOL))
from formal_design import build_manifest,empty_outcomes,SEEDS
from paired_statistics import paired_summary

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def outcome_rows(manifest,outcomes):
    """Only independently analyzed, SHA-bound accepted metrics enter statistics.

    This is aggregation, NOT a replacement for the full per-flight ULog replay.
    Failure/invalid/unattempted remain explicit with reasons and no fake error.
    """
    if len(manifest)!=200 or len(outcomes)!=200:raise ValueError('Exact complete manifest required')
    rows=[];metrics={}
    for job,row in zip(manifest,outcomes):
        if any(row.get(k)!=job[k] for k in ('id','scene','seed','mode')):
            raise ValueError('Wrong/reordered/duplicate outcome')
        status=row.get('status')
        if status not in ('accepted','failed','invalid','unattempted'):raise ValueError('Unknown outcome')
        result={k:row[k] for k in ('id','scene','seed','mode','status')}
        if status!='accepted':
            if not isinstance(row.get('reason'),str) or not row['reason'].strip():raise ValueError('Missing failure/unattempted reason')
            if 'xy_rmse' in row:raise ValueError('Do not invent failed or missing RMSE')
            result['reason']=row['reason']
        else:
            path=Path(row['metrics_path'])
            if not path.is_absolute() or digest(path)!=row['metrics_sha256']:raise ValueError('Changed accepted metrics')
            m=json.loads(path.read_text())
            if m.get('accepted') is not True or m.get('job')!=job:raise ValueError('Unaccepted/wrong formal metrics')
            r=np.asarray(m['diagnostic']['error']['rmse'],dtype=float)
            if r.shape!=(3,) or not np.all(np.isfinite(r)) or np.any(r<0):raise ValueError('Invalid formal errors')
            if not 63.96<=m['diagnostic']['seconds']<=64.04:raise ValueError('Wrong primary time window')
            result['xy_rmse']=float(np.mean(r[:2]));result['xyz_rmse']=r.tolist()
            result['metrics_sha256']=row['metrics_sha256'];result['metrics_path']=str(path)
            metrics[(job['scene'],job['seed'],job['mode'])]=m
        rows.append(result)
    return rows,metrics

def noncommand_checks(metrics):
    result={}
    for scene in ('hover','figure8','heading','force','mass'):
        checks=[]
        for seed in SEEDS:
            if any((scene,seed,mode) not in metrics for mode in (0,1)):continue
            p,e=(metrics[(scene,seed,mode)] for mode in (0,1))
            flags=[]
            for axis,tolerance in enumerate((.02,.02,.01)):
                flags.append(e['diagnostic']['error']['rmse'][axis]<=1.25*p['diagnostic']['error']['rmse'][axis]+tolerance)
                flags.append(e['position_rmse'][axis]<=1.25*p['position_rmse'][axis]+.05)
                for window in ('first_loop','second_loop'):
                    flags.append(e['diagnostic']['windows'][window]['error']['rmse'][axis]<=1.25*p['diagnostic']['windows'][window]['error']['rmse'][axis]+tolerance)
            flags.append(e['yaw_rmse']<=1.25*p['yaw_rmse']+.02)
            checks.append(dict(seed=seed,accepted=bool(all(flags))))
        result[scene]=dict(pairs=checks,all_twenty_pairs_passed=len(checks)==20 and all(x['accepted'] for x in checks))
    return result

def aggregate(manifest,outcomes):
    rows,metrics=outcome_rows(manifest,outcomes)
    result=paired_summary(rows,list(SEEDS));result['development_gates']=noncommand_checks(metrics)
    # Deliberately conservative: incomplete/invalid safety evidence cannot
    # authorize a broad success claim via conditionally accepted pairs alone.
    result['qualified_improvement_scenes']=[s for s in result['numerical_improvement_scenes'] if result['development_gates'][s]['all_twenty_pairs_passed']]
    result['majority_condition_met']=bool(result['complete_manifest_executed'] and result['accepted']==200 and len(result['qualified_improvement_scenes'])>=3)
    result['claim_caveat']='Conditional small-sample bootstrap, imperfectly seeded simulator; never universal superiority or hardware safety'
    return result

def collect(manifest,batch):
    ledger=json.loads((batch/'ledger.json').read_text())
    if ledger['planned']!=200 or len(ledger['attempts'])>200:raise ValueError('Wrong formal batch budget')
    rows=empty_outcomes(manifest)
    stopped=False
    for index,item in enumerate(ledger['attempts']):
        if stopped or item['attempt']!=index+1 or item['job']!=manifest[index]:raise ValueError('Wrong order or continuation after failure')
        row=rows[index];status=item['status']
        if status=='accepted':
            path=Path(item['directory'])/'xyz_metrics.json'
            row.update(status='accepted',metrics_path=str(path),metrics_sha256=item['metrics_sha256'])
            row.pop('reason',None)
        elif status=='failed':
            # Do not guess whether a runner failure means crash or data loss.
            # Preserve exact evidence; a reviewer may label data-invalid with
            # a traceable reason, without changing acceptance or resuming.
            record=json.loads((Path(item['directory'])/'result.json').read_text())
            row.update(status='failed',reason=str(item.get('error') or record.get('error') or 'Mandatory gate failed; inspect original evidence'))
            stopped=True
        else:raise ValueError('Batch still active/unknown state')
    for row in rows[len(ledger['attempts']):]:row['reason']='Frozen job not attempted; stopped or not started, not a simulated outcome'
    outcome_rows(manifest,rows)
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('init');a.add_argument('--selection',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('analyze');a.add_argument('--manifest',type=Path,required=True);a.add_argument('--outcomes',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('collect');a.add_argument('--manifest',type=Path,required=True);a.add_argument('--batch',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.command=='init':
        jobs=build_manifest(json.loads(args.selection.read_text()));args.output.mkdir(parents=True,exist_ok=False)
        for name,data in [('manifest.json',jobs),('outcomes_unattempted.json',empty_outcomes(jobs))]:
            (args.output/name).write_text(json.dumps(data,indent=2)+'\n')
        print('200 registered jobs, ZERO flights. V09 execution is not implemented or authorized here.')
    elif args.command=='collect':
        result=collect(json.loads(args.manifest.read_text()),args.batch)
        with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
        print('Preserved all200 outcomes; run full independent ULog replay before inference')
    else:
        manifest=json.loads(args.manifest.read_text());outcomes=json.loads(args.outcomes.read_text())
        result=aggregate(manifest,outcomes)
        with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
        print(json.dumps(dict(accepted=result['accepted'],complete=result['complete_manifest_executed'],majority_condition_met=result['majority_condition_met'])))

if __name__=='__main__':main()
