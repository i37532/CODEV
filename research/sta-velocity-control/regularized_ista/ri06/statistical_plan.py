"""Preregistered RI07 analysis primitives, no flight or holdout data access.

Columns within A or B share a seed block, including both tasks. A/B have
independent block sets. Bonferroni family size remains eight even if missing.
Intervals use the common complete blocks within each group; available-pair
descriptions are also reported, never zero-imputed. Small-n coverage is not
guaranteed by percentile bootstrap.
"""
import numpy as np

BOOTSTRAP_REPLICATES=200000
BOOTSTRAP_SEED=86001
SIGN_REPLICATES=100000
SIGN_SEED=86002
FAMILY=8
MIN_PRACTICAL_DIFFERENCE=.0005
COMPARISONS={'A':['H:RISTA-RSTA','V:RISTA-RSTA'],
             'B':['H:RSTA-PID','H:RISTA-PID','H:RISTA-RSTA',
                  'V:RSTA-PID','V:RISTA-PID','V:RISTA-RSTA']}

def validate(differences,group):
    if group not in COMPARISONS:raise ValueError('Unknown comparison group')
    a=np.asarray(differences,dtype=float)
    if a.shape!=(20,len(COMPARISONS[group])) or np.any(np.isinf(a)):
        raise ValueError('Exactly20 preregistered blocks; missing=NaN, not infinity/zero fill')
    return a

def summarize(differences,group,*,replicates=BOOTSTRAP_REPLICATES,seed=BOOTSTRAP_SEED):
    a=validate(differences,group)
    if type(replicates) is not int or replicates<1:raise ValueError('Positive bootstrap repetitions required')
    available=[]
    for i,label in enumerate(COMPARISONS[group]):
        v=a[np.isfinite(a[:,i]),i]
        available.append(dict(comparison=label,n=len(v),mean_difference=float(v.mean()) if len(v) else None))
    mask=np.all(np.isfinite(a),axis=1);complete=a[mask];n=len(complete)
    result=dict(group=group,planned_blocks=20,available_pairs=available,common_complete_blocks=n,
        included_blocks=(np.flatnonzero(mask)+1).tolist(),family_size=FAMILY,
        missing_policy='Groupwise common-complete blocks for correlated CIs; available-pair descriptions separate; selection bias possible',
        primary_ci=None,bootstrap_replicates=replicates,bootstrap_seed=seed,
        small_n_warning='Finite-sample percentile coverage and power not guaranteed; never add samples after holdout')
    if n<2:return result
    # Separate group streams; the SAME sampled indices apply to all H/V columns.
    rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed,0 if group=='A' else 1])))
    means=np.empty((replicates,a.shape[1]))
    for lo in range(0,replicates,10000):
        count=min(10000,replicates-lo)
        means[lo:lo+count]=complete[rng.integers(0,n,size=(count,n))].mean(axis=1)
    intervals=np.quantile(means,[.025,.975,.05/(2*FAMILY),1-.05/(2*FAMILY)],axis=0)
    result['primary_ci']=[dict(comparison=label,n=n,mean_difference=float(complete[:,i].mean()),
        ci95=intervals[:2,i].tolist(),family95_bonferroni=intervals[2:,i].tolist(),
        practical_threshold=MIN_PRACTICAL_DIFFERENCE,
        adjusted_interval_below_zero=bool(intervals[3,i]<0),
        adjusted_interval_below_practical=bool(intervals[3,i]<-MIN_PRACTICAL_DIFFERENCE))
        for i,label in enumerate(COMPARISONS[group])]
    return result

def exploratory_sign_flip(differences,group,*,replicates=SIGN_REPLICATES,seed=SIGN_SEED):
    a=validate(differences,group);a=a[np.all(np.isfinite(a),axis=1)]
    if len(a)<2:return None
    if type(replicates) is not int or replicates<1:raise ValueError('Positive sign repetitions required')
    rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed,0 if group=='A' else 1])))
    actual=np.abs(a.mean(axis=0));exceed=np.zeros(a.shape[1],dtype=np.int64)
    for lo in range(0,replicates,10000):
        count=min(10000,replicates-lo)
        signs=2*rng.integers(0,2,size=(count,len(a)))-1
        values=np.abs(np.mean(a[None,:,:]*signs[:,:,None],axis=1))
        exceed+=np.sum(values>=actual,axis=0)
    return dict(p_two_sided=((exceed+1)/(replicates+1)).tolist(),n=len(a),replicates=replicates,
        seed=seed,exploratory=True,assumption='Sign symmetry/exchangeability not guaranteed by simulation pairing')

def precision_estimate(differences):
    a=np.asarray(differences,dtype=float)
    if a.ndim!=1 or not np.all(np.isfinite(a)):raise ValueError('Finite development paired differences required')
    if len(a)<2:return dict(n=len(a),halfwidth_n20=None)
    sd=float(a.std(ddof=1))
    return dict(n=len(a),paired_sd=sd,halfwidth_n20=2.093024054*sd/np.sqrt(20),
                caveat='Plug-in t19 planning illustration only; tiny/selected development sample, not power proof')
