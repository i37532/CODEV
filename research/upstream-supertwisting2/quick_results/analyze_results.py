#!/usr/bin/env python3
"""Read-only comparison and archive. Never starts or retries a flight."""
import argparse
import json
from pathlib import Path
import shutil
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'tools'))
sys.path.insert(0,str(HERE.parent/'quick_check'))
from analyze import audit_native_log
from analyze_response import response_metrics
from run_hover import digest, require

ROOT=Path('/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-QUICK-20261102')
ORDER=('PID','STA2','RSTA','RISTA')
LABELS={'PID':'PID','STA2':'STA2 + IMU fix','RSTA':'RSTA','RISTA':'RISTA'}
COLORS=('#0072B2','#D55E00','#009E73','#CC79A7')


def qualified_rows(manifest):
    require(manifest['quick_stage']=='comparison' and len(manifest['jobs'])==4,'Not four comparison jobs')
    require(tuple(j['system'] for j in manifest['jobs'])==ORDER,'Wrong system order')
    rows=[]
    for job in manifest['jobs']:
        d=Path(manifest['data_root'])/'runs'/job['id']
        result=json.loads((d/'result.json').read_text())
        require(result.get('success') is True and result.get('independent_replay_passed') is True
                and result.get('parameter_restore_exact') is True and result.get('remaining_simulators')==[],
                'Rejected or incomplete run: '+job['id'])
        require(all(result[k]==job[k] for k in ('id','system','task')),'Wrong result identity')
        for log in result['logs']: require(digest(log['archive'])==log['sha256'],'ULog changed')
        source=max(result['logs'],key=lambda r:r['bytes'])
        origin=json.loads((d/'origin.json').read_text())
        metrics=audit_native_log(source['archive'],result['events'],origin,job,d/'ros/sent.jsonl')
        require(metrics==json.loads((d/'metrics.json').read_text()),'Fresh replay differs')
        require(metrics==json.loads((d/'independent_replay.json').read_text()),'Prior independent replay differs')
        events={e['name']:e['timestamp_us'] for e in result['events']}
        trace=metrics['trace'];t=np.array(trace['time_s']);xyz=np.array(trace['displacement']);vel=np.array(trace['velocity'])
        response=response_metrics(t,-xyz[:,2],-vel[:,2],2.5,(events['descend_start']-events['climb_start'])*1e-6)
        response.update(climb_to_hover_entry_s=(events['hover_start']-events['climb_start'])*1e-6,
                        land_to_disarm_s=(events['landed_disarmed']-events['land_command'])*1e-6,
                        input_kind='16 s quintic position ramp; not controller step response')
        rows.append(dict(system=job['system'],label=LABELS[job['system']],id=job['id'],source=source,
                         directory=str(d),result_sha256=digest(d/'result.json'),response=response,metrics=metrics))
    return rows


def plots(rows,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    files=[]
    for quantity,ylabels in [('velocity',('X velocity / m/s','Y velocity / m/s','Upward velocity / m/s')),
                              ('displacement',('X displacement / m','Y displacement / m','Height above own origin / m'))]:
        fig,axes=plt.subplots(3,1,figsize=(10,8),sharex=True,constrained_layout=True)
        for r,color in zip(rows,COLORS):
            tr=r['metrics']['trace'];values=np.asarray(tr[quantity])
            for i,ax in enumerate(axes):
                ax.plot(tr['time_s'],values[:,i]*(-1 if i==2 else 1),color=color,label=r['label'],lw=1.3)
        for ax,label in zip(axes,ylabels):
            require(len(ax.lines)==4,'Only four actual-state curves permitted')
            ax.set_ylabel(label);ax.grid(alpha=.2)
        axes[0].legend(ncol=4,fontsize=9)
        axes[0].set_title('Takeoff - hover 10 s - landing | one accepted run per system')
        axes[-1].set_xlabel('Time since climb target starts / s')
        for ext in ('png','svg'):
            path=out/('actual_'+quantity+'_xyz.'+ext);fig.savefig(path,dpi=170);files.append(path)
        plt.close(fig)
    return files


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    require(not args.output.exists(),'Do not overwrite comparison evidence')
    manifest_path=ROOT/'comparison/manifest.json';manifest=json.loads(manifest_path.read_text())
    rows=qualified_rows(manifest)
    require(all(json.loads((Path(r['directory'])/'result.json').read_text())['manifest_sha256']==digest(manifest_path)
                for r in rows),'Wrong source manifest')
    args.output.mkdir(parents=True)
    figures=plots(rows,args.output)
    summary=dict(scope='Exploratory system comparison, n=1; not gain tuning or causal algorithm ranking',
                 manifest_sha256=digest(manifest_path),source_script_sha256=digest(__file__),
                 figures=[dict(path=p.name,sha256=digest(p)) for p in figures],runs=[])
    for row in rows:
        directory=Path(row['directory']);dest=args.output/row['id'];dest.mkdir()
        for name in ('result.json','metrics.json','independent_replay.json','origin.json','job.json','parameter_backup.json'):
            shutil.copy2(directory/name,dest/name)
        summary['runs'].append({k:v for k,v in row.items() if k!='metrics'} | {
            'hover_metrics':row['metrics']['phase_metrics'],
            'maximum_tilt_deg':row['metrics']['maximum_tilt_deg'],
            'maximum_native_position_gap_s':row['metrics']['maximum_native_position_gap_s']})
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
