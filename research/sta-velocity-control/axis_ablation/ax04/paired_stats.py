"""Run/seed-level paired inference. Never regard high-rate frames as n."""
import math
from statistics import NormalDist
import numpy as np
from design import NAMES, MASKS, SEEDS, BOOTSTRAPS, BOOTSTRAP_SEED, SIGN_DRAWS, SIGN_SEED, MIN_PRACTICAL


def wilson(accepted, total):
    if total == 0:
        return None
    z = 1.959963984540054
    p = accepted/total
    den = 1+z*z/total
    center = (p+z*z/(2*total))/den
    half = z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return [max(0., center-half), min(1., center+half)]


def infer(values, indices, signs, family=14):
    x = np.asarray(values, dtype=float)
    valid = np.isfinite(x)
    n = int(valid.sum())
    out = dict(n=n, missing_pair_seeds=[s for s, ok in zip(SEEDS, valid) if not ok], inference_available=False)
    if n:
        out['mean_difference_m_s'] = float(x[valid].mean())
    if n < 2:
        return out
    # Joint twenty-block draws; missing cells remain missing. A draw without
    # any complete pair is explicitly counted, never assigned an error zero.
    sampled = x[indices]
    counts = np.isfinite(sampled).sum(axis=1)
    means = np.nansum(sampled, axis=1)[counts > 0] / counts[counts > 0]
    ci95 = np.quantile(means, [.025, .975], method='linear').tolist()
    tail = .05 / (2 * family)
    ci_family = np.quantile(means, [tail, 1-tail], method='linear').tolist()
    observed = abs(float(x[valid].mean()))
    perm = np.abs((signs[:, valid] * x[valid]).mean(axis=1))
    p = (1 + np.count_nonzero(perm >= observed - 1e-15)) / (1 + len(perm))
    out.update(inference_available=True, ci95_descriptive=ci95,
               ci_bonferroni14=ci_family, interval_confidence=1-.05/family,
               empty_bootstrap_draws=int((counts == 0).sum()),
               signflip_p_exploratory=float(p), signflip_p_bonferroni14_exploratory=float(min(1, family*p)),
               signflip_assumption='symmetry/exchangeability is not guaranteed by controller assignment; sensitivity only')
    return out


def contrasts(cube):
    """cube[task,seed,configuration]; incomplete factorial blocks stay NaN."""
    result = {}
    for ti, task in enumerate(('H', 'V')):
        x = cube[ti]
        full = np.all(np.isfinite(x), axis=1)
        expressions = {'Z_given_XY': x[:, 7]-x[:, 4],
                       'XY_interaction_given_Z_PID': x[:, 4]-x[:, 1]-x[:, 2]+x[:, 0]}
        for axis, bit in (('X', 1), ('Y', 2), ('Z', 4)):
            on = [i for i, name in enumerate(NAMES) if MASKS[name] & bit]
            off = [i for i, name in enumerate(NAMES) if not MASKS[name] & bit]
            expressions['factorial_average_'+axis] = x[:, on].mean(axis=1)-x[:, off].mean(axis=1)
        # Difference-of-differences averaged over the third factor.
        for label, a, b in (('XY', 1, 2), ('XZ', 1, 4), ('YZ', 2, 4)):
            weights = np.array([(1 if MASKS[k] & a else -1)*(1 if MASKS[k] & b else -1)/2 for k in NAMES])
            expressions['factorial_interaction_'+label] = x @ weights
        weights = np.array([np.prod([1 if MASKS[k] & bit else -1 for bit in (1,2,4)]) for k in NAMES])
        expressions['factorial_interaction_XYZ'] = x @ weights
        result[task] = {}
        for label, values in expressions.items():
            # Conditional two-group contrast may use complete pairs; all
            # interactions, including conditional XY, require all eight cells.
            good = np.isfinite(values) if label == 'Z_given_XY' else full
            result[task][label] = dict(n=int(good.sum()),
                mean_difference_m_s=float(values[good].mean()) if good.any() else None,
                used_seeds=[s for s, ok in zip(SEEDS, good) if ok], exploratory=True)
    return result


def summarize(rows, *, repetitions=BOOTSTRAPS, sign_draws=SIGN_DRAWS):
    expected = {(t, s, c) for t in ('H','V') for s in SEEDS for c in NAMES}
    mapping = {}
    states = ('accepted', 'failed', 'invalid', 'unattempted')
    cube = np.full((2, 20, 8), np.nan)
    axes = np.full((2, 20, 8, 3), np.nan)
    counts = {}
    for row in rows:
        key = row['task'], row['seed'], row['candidate']
        if key not in expected or key in mapping or row['status'] not in states:
            raise ValueError('Wrong, duplicate or unknown outcome')
        if row['status'] == 'accepted':
            a = np.asarray(row['rmse_m_s'], dtype=float)
            if a.shape != (3,) or not np.all(np.isfinite(a)) or np.any(a < 0):
                raise ValueError('Invalid accepted error')
            ti, si, ci = ('H','V').index(key[0]), SEEDS.index(key[1]), NAMES.index(key[2])
            cube[ti, si, ci] = a.mean()
            axes[ti, si, ci] = a
        elif 'rmse_m_s' in row or not row.get('reason'):
            raise ValueError('Missing reason or fabricated failed/missing error')
        mapping[key] = row
    if set(mapping) != expected:
        raise ValueError('All320 outcomes, including unattempted, must be explicit')
    # Same bootstrap indices and sign vector for every contrast/task.
    rng = np.random.Generator(np.random.PCG64(BOOTSTRAP_SEED))
    indices = rng.integers(0, 20, size=(repetitions, 20))
    signs = np.random.Generator(np.random.PCG64(SIGN_SEED)).choice(np.array([-1,1], dtype=np.int8), size=(sign_draws,20))
    comparisons = {}
    descriptions = {}
    for ti, task in enumerate(('H','V')):
        for ci, name in enumerate(NAMES):
            subset = [mapping[task, s, name] for s in SEEDS]
            count = {state: sum(x['status'] == state for x in subset) for state in states}
            attempted = 20-count['unattempted']
            counts[task+'/'+name] = {**count, 'planned':20, 'attempted':attempted,
                'accepted_fraction_of_attempted':count['accepted']/attempted if attempted else None,
                'wilson95_descriptive':wilson(count['accepted'],attempted),
                'completion_fraction':count['accepted']/20}
            valid = np.isfinite(cube[ti,:,ci])
            descriptions[task+'/'+name] = dict(n=int(valid.sum()),
                xyz_rmse_mean=axes[ti,valid,ci].mean(axis=0).tolist() if valid.any() else None,
                J_mean=float(cube[ti,valid,ci].mean()) if valid.any() else None)
            if ci == 0:
                continue
            delta = cube[ti,:,ci]-cube[ti,:,0]
            result = infer(delta, indices, signs)
            good = np.isfinite(delta)
            pid = float(cube[ti,good,0].mean()) if good.any() else None
            result['relative_reduction_on_same_pairs'] = -float(delta[good].mean())/pid if pid else None
            result['practical_point_condition'] = bool(good.any() and result['mean_difference_m_s'] <= -MIN_PRACTICAL
                and pid and result['relative_reduction_on_same_pairs'] >= .10)
            result['qualified_improvement'] = bool(result['n'] == 20 and result['practical_point_condition']
                and result.get('ci_bonferroni14', [None, 1])[1] < 0
                and all(mapping[task,s,name]['status'] == mapping[task,s,'PID']['status'] == 'accepted' for s in SEEDS))
            comparisons[task+'/'+name+'-PID'] = result
    return dict(planned=320, accepted=sum(x['status']=='accepted' for x in rows),
        attempted=sum(x['status']!='unattempted' for x in rows), complete_all_accepted=all(x['status']=='accepted' for x in rows),
        counts=counts, descriptive=descriptions, primary_comparisons=comparisons,
        exploratory=contrasts(cube), bootstrap=dict(repetitions=repetitions, seed=BOOTSTRAP_SEED, joint_blocks=20,
            method='percentile linear quantile; conditional approximate coverage, not guaranteed FWER'),
        randomization=dict(repetitions=sign_draws, seed=SIGN_SEED, role='exploratory symmetric sign-flip sensitivity only'),
        minimum_practical=dict(absolute_m_s=MIN_PRACTICAL, relative=.10, rule='both point conditions and adjusted CI upper<0; all20 accepted pairs'),
        caveat='Accepted-pair selection bias, imperfect IMU-only independence, small-n/bootstrap tail uncertainty; no mandatory winner or universal ranking')


def precision(development):
    """n=3 development, not formal data. No SciPy dependency or power claim."""
    result = {}
    z = NormalDist().inv_cdf(1-.05/28)
    for task in ('H','V'):
        rows = [r for r in development['runs'] if r['task'] == task]
        seeds = sorted({r['seed'] for r in rows})
        if len(seeds) != 3 or len(rows) != 24:
            raise ValueError('Incomplete AX03 development task')
        index = {(r['seed'],r['candidate']): np.mean(r['rmse_m_s']) for r in rows}
        for name in NAMES[1:]:
            d = np.array([index[s,name]-index[s,'PID'] for s in seeds])
            sd = float(np.std(d, ddof=1))
            # For normal IID pairs df=2: chi-square quantile is -2 ln(1-p).
            low = sd*math.sqrt(2/(-2*math.log(.025)))
            high = sd*math.sqrt(2/(-2*math.log(.975)))
            result[task+'/'+name] = dict(development_n=3, differences_m_s=d.tolist(), sd_m_s=sd,
                sd_normal_iid_95_interval=[low,high],
                n20_t19_95_halfwidth=2.093024054*sd/math.sqrt(20),
                n20_normal_bonferroni14_halfwidth=z*sd/math.sqrt(20),
                n20_normal_bonferroni14_halfwidth_using_sd_upper=z*high/math.sqrt(20))
    return dict(fixed_n=20, attempts=320, comparisons=result,
        rationale='Budget fixed at20 blocks; projections use only development n3. Strongly uncertain and potentially optimistic, not guaranteed power; never add formal samples after viewing outcomes',
        assumptions='Normal/IID approximations for precision sensitivity only; H/V use distinct development seeds, same formal blocks; IMU-only randomness and order effects limit inference')
