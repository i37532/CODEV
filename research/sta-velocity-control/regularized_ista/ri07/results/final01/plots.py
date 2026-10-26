#!/usr/bin/env python3
"""Descriptive plots of all preregistered cells, not selected winning runs."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

COLORS={'PID':'#3b6fb6','RSTA':'#de8a23','RISTA':'#31996a'}
LABELS={'PID':'pid','RSTA':'STA','RISTA':'ISTA'}


def generate(package, out):
    out.mkdir(exist_ok=False)
    summaries=package['group_summary']; files=[]
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':130})
    def cell(group,task,candidate):
        return next(r for r in summaries if (r['group'],r['task'],r['candidate'])==(group,task,candidate))
    def save(fig,name):
        fig.savefig(out/name,dpi=180,bbox_inches='tight');plt.close(fig)
        p=out/name;files.append(dict(path=name,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size))
    fig,axes=plt.subplots(1,2,figsize=(11.5,4.4))
    for ax,group in zip(axes,('A','B')):
        names=('RSTA','RISTA') if group=='A' else ('PID','RSTA','RISTA'); width=.72/len(names)
        for i,name in enumerate(names):
            positions=np.arange(2)+(i-(len(names)-1)/2)*width
            values=[cell(group,t,name)['J_mean'] for t in ('H','V')]
            ax.bar(positions,values,width=width*.92,color=COLORS[name],label=LABELS[name])
            for x,y in zip(positions,values):ax.text(x,y,f'{y:.5f}',ha='center',va='bottom',fontsize=8)
        ax.set(xticks=[0,1],xticklabels=['H: horizontal 8','V: 8 + vertical'],ylabel='Mean J (m/s)',
               title=group+(': same parameters' if group=='A' else ': equal-budget tuning'))
        ax.set_ylim(0,ax.get_ylim()[1]*1.35);ax.legend()
    fig.suptitle('RI07 formal: mean XYZ velocity RMSE; n=20 paired blocks per cell')
    fig.tight_layout();save(fig,'01_J_means.png')
    fig,axes=plt.subplots(2,2,figsize=(11.5,7.6))
    for row,group in enumerate(('A','B')):
        for col,task in enumerate(('H','V')):
            ax=axes[row,col];names=('RSTA','RISTA') if group=='A' else ('PID','RSTA','RISTA');width=.72/len(names)
            for i,name in enumerate(names):
                ax.bar(np.arange(3)+(i-(len(names)-1)/2)*width,cell(group,task,name)['velocity_rmse_mean'],
                       width=width*.92,color=COLORS[name],label=LABELS[name])
            ax.set(xticks=[0,1,2],xticklabels=['X','Y','Z'],ylabel='Velocity RMSE (m/s)',title=f'{group} / {task}');ax.legend()
    fig.suptitle('Per-axis error: all20 formal runs in every cell');fig.tight_layout();save(fig,'02_XYZ_RMSE.png')
    fig,ax=plt.subplots(figsize=(11.5,5.4));labels=[];entries=[]
    for group in ('A','B'):
        for r in package['statistics'][group]['primary']['primary_ci']:
            entries.append(r);labels.append(group+' / '+r['comparison'].replace('RISTA','ISTA').replace('RSTA','STA').replace('PID','pid'))
    for i,r in enumerate(entries):
        lo,hi=r['family95_bonferroni'];mu=r['mean_difference']
        ax.plot([lo,hi],[i,i],color='#3b6fb6',linewidth=3);ax.scatter([mu],[i],color='#172b4d',s=26,zorder=3)
    ax.axvline(0,color='#777777',linewidth=1)
    ax.set(yticks=range(8),yticklabels=labels,xlabel='Paired J difference (m/s); negative favours first algorithm',
           title='8 preregistered comparisons: family95 Bonferroni bootstrap intervals')
    ax.invert_yaxis();fig.tight_layout();save(fig,'03_paired_intervals.png')
    fig,axes=plt.subplots(2,2,figsize=(11.5,7.6))
    for col,task in enumerate(('H','V')):
        for i,name in enumerate(('PID','RSTA','RISTA')):
            r=cell('B',task,name)
            axes[0,col].bar(np.arange(3)+(i-1)*.24,r['correction_tv_per_s_mean'],width=.22,color=COLORS[name],label=LABELS[name])
            axes[1,col].bar(i,r['host_kernel_mean_run_percentiles_us'][1],color=COLORS[name],width=.65)
        axes[0,col].set(xticks=[0,1,2],xticklabels=['X','Y','Z'],ylabel='Correction TV / second',title='B / '+task)
        axes[0,col].legend();axes[1,col].set(xticks=[0,1,2],xticklabels=['pid','STA','ISTA'],ylabel='Mean run kernel p95 (us)')
    fig.suptitle('B group control burden: TV is NOT energy; host timing is NOT board CPU')
    fig.tight_layout();save(fig,'04_control_burden.png')
    (out/'index.json').write_text(json.dumps(dict(files=files,source_samples=200,new_flights=0),indent=2)+'\n')
    return files


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    print(json.dumps(generate(json.loads(args.package.read_text()),args.output),indent=2))
