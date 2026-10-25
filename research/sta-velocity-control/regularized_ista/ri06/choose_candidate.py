"""Once-only deterministic selection; never flies or reads holdout."""
import argparse
import json
import math
import importlib.util
from pathlib import Path
_spec=importlib.util.spec_from_file_location('_ri06_choice_protocol',Path(__file__).with_name('protocol.py'))
p=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(p)

def score(metrics):
    if metrics.get('accepted') is not True: return math.inf
    d=metrics['diagnostic'];r=d['error']['rmse'];tv=d['correction_tv_per_second']
    if len(r)!=3 or len(tv)!=3 or not all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in r+tv):
        raise ValueError('Incomplete/nonfinite selection metric')
    j=sum(r)/3
    if not math.isclose(d['J'],j,rel_tol=0,abs_tol=1e-12): raise ValueError('J differs from axis arithmetic mean')
    return j/.01+.1*sum(tv)/3

def choose(rows):
    expected={j['id']:j for gate in ('TH','TV') for j in p.jobs(gate)}
    if len(rows)!=36 or len({r['job']['id'] for r in rows})!=36: raise ValueError('Exactly36 unique training outcomes required')
    values={name:{i:[] for i in range(3)} for name,_ in p.ALGORITHMS}
    for row in rows:
        j=row['job']
        if not p.exact(j,expected.get(j['id'])): raise ValueError('Not a registered training job')
        value=score(row)
        if not math.isfinite(value): raise ValueError('Mandatory failure/no eligible full batch; no fallback selection')
        values[j['candidate']][j['candidate_index']].append(value)
    scores={};indices={}
    for name,sets in values.items():
        if any(len(v)!=4 for v in sets.values()): raise ValueError('Incomplete balanced candidate')
        scores[name]={i:sum(v)/4 for i,v in sets.items()}
        minimum=min(scores[name].values())
        indices[name]=next(i for i in (1,0,2) if scores[name][i]<=minimum+1e-12)
    return dict(accepted=True,indices=indices,scores=scores,training_runs=36,validation_used=0,
                rule=p.design()['score'],input_sha256={})

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true');args=parser.parse_args()
    # This verifies both independent gate replays before reading selection inputs.
    p.require_prior_gate('VH') if (p.HERE/'selection.json').exists() else p.require_prior_gate('TV')
    b=p.load_file('_ri06_select_bindings',p.HERE/'tools/bindings.py');rows=[];inputs={}
    for gate in ('TH','TV'):
        receipt=p.read(p.DATA_ROOT/gate/'gate_pass.json')
        b.local('replay').verify_complete(p.DATA_ROOT/gate/'replay01',gate=gate)
        for f in (p.DATA_ROOT/gate/'gate_pass.json',p.DATA_ROOT/gate/'replay01/summary.json',p.DATA_ROOT/gate/'batch01/ledger.json'):
            inputs[str(f)]=p.fingerprint(f)
        for j in p.jobs(gate):
            f=p.DATA_ROOT/gate/'batch01'/j['id']/'r03_metrics.json';rows.append(p.read(f));inputs[str(f)]=p.fingerprint(f)
    result=choose(rows);result['input_sha256']=inputs;result['source_head']=p.git('rev-parse','HEAD')
    if args.write:
        with (p.HERE/'selection.json').open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
