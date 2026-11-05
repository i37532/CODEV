"""Preregistered run-level paired statistics; no flight or parameter mutation."""
import numpy as np

SCENES=('hover','figure8','heading','force','mass')

def wilson(accepted,total):
    if not isinstance(total,int) or not isinstance(accepted,int) or total<=0 or not 0<=accepted<=total:
        raise ValueError('Invalid acceptance counts')
    z=1.959963984540054;p=accepted/total;den=1+z*z/total
    center=(p+z*z/(2*total))/den
    half=z*np.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return [float(max(0,center-half)),float(min(1,center+half))]

def paired_summary(rows,seeds):
    """Input rows have scene,seed,mode,status,xy_rmse. Never infer missing success.

    One shared resampling of the seed blocks across scenarios. No frame-level
    pseudo-replication. Missing complete pairs remain NaN; all-empty bootstrap
    samples are counted and omitted with explicit disclosure, not filled zero.
    """
    if len(seeds)!=20 or len(set(seeds))!=20:raise ValueError('Expected twenty registered seed blocks')
    keyset={(s,seed,m) for s in SCENES for seed in seeds for m in (0,1)}
    mapping={}
    for row in rows:
        k=(row['scene'],row['seed'],row['mode'])
        if k not in keyset or k in mapping:raise ValueError('Wrong/duplicate formal job')
        if row['status'] not in ('accepted','failed','invalid','unattempted'):raise ValueError('Unknown formal outcome')
        if row['status']=='accepted':
            value=row['xy_rmse']
            if not np.isfinite(value) or value<0:raise ValueError('Invalid accepted RMSE')
        mapping[k]=row
    if set(mapping)!=keyset:raise ValueError('Missing manifest outcomes; unattempted must be explicit')
    rng=np.random.Generator(np.random.PCG64(48001));indices=rng.integers(0,20,size=(20000,20))
    output=dict(planned=200,scenes={},bootstrap_repetitions=20000,bootstrap_seed=48001,
                independent_units='20 paired IMU seed blocks, imperfect independence; not100 scene/seed IID or sample frames')
    total_accepted=0
    for scene in SCENES:
        pair=[];pid_values=[];accepted={};counts={}
        for mode in (0,1):
            subset=[mapping[(scene,s,mode)] for s in seeds]
            counts[str(mode)]={state:sum(x['status']==state for x in subset) for state in ('accepted','failed','invalid','unattempted')}
            n=counts[str(mode)]['accepted'];total_accepted+=n
            attempted=20-counts[str(mode)]['unattempted']
            # Unattempted jobs are not Bernoulli trials or invented failures.
            accepted[str(mode)]=dict(count=n,planned=20,attempted=attempted,planned_completion_fraction=n/20,
                fraction_of_attempted=n/attempted if attempted else None,
                wilson95=wilson(n,attempted) if attempted else None)
        for seed in seeds:
            p,e=mapping[(scene,seed,0)],mapping[(scene,seed,1)]
            good=p['status']==e['status']=='accepted'
            pair.append(e['xy_rmse']-p['xy_rmse'] if good else np.nan)
            pid_values.append(p['xy_rmse'] if good else np.nan)
        differences=np.array(pair);valid=np.isfinite(differences);n=int(valid.sum())
        result=dict(counts=counts,acceptance=accepted,complete_pairs=n,missing_pair_seeds=[s for s,v in zip(seeds,valid) if not v],
                    inference_available=False,development_noncommand_gates_not_inferred=True)
        if n>=2:
            values=differences[indices];present=np.sum(np.isfinite(values),axis=1)
            bootstrap=np.nansum(values,axis=1)[present>0]/present[present>0]
            mean=float(np.mean(differences[valid]));den=float(np.nanmean(pid_values))
            relative=None if den==0 else -mean/den
            ci95=np.percentile(bootstrap,[2.5,97.5]).tolist();ci99=np.percentile(bootstrap,[.5,99.5]).tolist()
            result.update(inference_available=True,paired_mean_difference_m_s=mean,
                relative_reduction=relative,ci95_descriptive=ci95,ci99_bonferroni5=ci99,
                empty_bootstrap_draws=int(np.count_nonzero(present==0)),
                improvement_numerical_condition=bool(mean<=-.001 and relative is not None and relative>=.10 and ci99[1]<0),
                acceptance_not_lower=bool(accepted['1']['attempted']>0 and accepted['0']['attempted']>0
                    and accepted['1']['fraction_of_attempted']>=accepted['0']['fraction_of_attempted']))
        output['scenes'][scene]=result
    output['accepted']=total_accepted
    output['complete_manifest_executed']=all(r['status']!='unattempted' for r in rows)
    output['majority_claim_requires_separate_noncommand_and_safety_checks']=True
    output['numerical_improvement_scenes']=[s for s,r in output['scenes'].items() if r.get('improvement_numerical_condition') and r.get('acceptance_not_lower')]
    return output

def precision_projection(differences):
    x=np.asarray(differences,dtype=float)
    if x.ndim!=1 or len(x)<2 or not np.all(np.isfinite(x)):raise ValueError('Need independent complete development pairs')
    sd=float(np.std(x,ddof=1))
    return dict(development_pairs=len(x),sd_m_s=sd,n20_approximate_95_halfwidth_m_s=2.093*sd/np.sqrt(20),
                caveat='Small development n, approximate IID-t projection only; not a power guarantee or formal stopping rule')
