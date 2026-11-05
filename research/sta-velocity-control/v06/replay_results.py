#!/usr/bin/env python3
"""Independent replay for accepted and failed records; never overwrite originals."""
import argparse,json,subprocess,sys
from pathlib import Path
def main():
    p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    rows=[]; evidence=dict(success=False,commands=rows)
    for item in json.loads((a.batch/'ledger.json').read_text())['attempts']:
        run=Path(item['directory']); output=a.output/run.name
        cmd=[sys.executable,str(Path(__file__).parent/'protocol02/analyze.py'),str(run),'--output',str(output)]
        with (a.output/(run.name+'.log')).open('x') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=120)
        result=json.loads((output/'xyz_metrics.json').read_text())
        accepted=item['status']=='accepted'
        row=dict(run=run.name,command=cmd,exit_code=r.returncode,expected_accepted=accepted,actual_accepted=result['accepted'])
        if accepted:row['identical_metrics']=result==json.loads((run/'xyz_metrics.json').read_text())
        else:row['original_failure_retained']=not json.loads((run/'result.json').read_text())['success']
        rows.append(row)
        (a.output/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
        assert r.returncode==(0 if accepted else 1) and result['accepted']==accepted
        assert row.get('identical_metrics',True) and row.get('original_failure_retained',True)
        print(run.name,r.returncode,flush=True)
    evidence['success']=True
    (a.output/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
if __name__=='__main__':main()
