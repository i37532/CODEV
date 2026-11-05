#!/usr/bin/env python3
"""Read-only exploratory diagnostics; never alters frozen acceptance or parameters."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[4]
SOURCE = REPO/'research/sta-velocity-control/regularized_ista/ri04_revision01/results/summary.json'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def local_gains(l1, l2, eps, h):
    values = np.asarray([l1, l2, eps], dtype=float)
    h = np.asarray(h, dtype=float)
    require(np.all(np.isfinite(values)) and np.all(values > 0)
            and np.all(np.isfinite(h)) and np.all(h > 0), 'Invalid gains/period')
    k, i = l1/np.sqrt(eps), l2/eps
    d = 1+h*k+h*h*i
    require(np.all(np.isfinite(d)), 'Nonfinite denominator')
    return k, i, (k+h*i)/d, i/d


def stats(x, w):
    x, w = np.asarray(x, float), np.asarray(w, float)
    require(x.ndim == 1 and x.shape == w.shape and x.size > 1
            and np.all(np.isfinite(x)) and np.all(np.isfinite(w)) and np.all(w > 0), 'Invalid samples/weights')
    mean = float(np.average(x, weights=w))
    variance = float(np.average((x-mean)**2, weights=w))
    return dict(mean=mean, variance=variance, rmse=float(np.sqrt(np.average(x*x, weights=w))),
                max_abs=float(np.max(abs(x))), bias_energy_fraction=mean*mean/(mean*mean+variance) if mean*mean+variance else 0.)


def align(d, q):
    a, b = np.asarray(d['publish_seq']), np.asarray(q['publish_seq'])
    require(np.all(a[1:] > a[:-1]) and np.all(b[1:] > b[:-1]), 'Nonmonotonic or duplicate sequence')
    pos = np.searchsorted(b, a)
    require(np.all(pos < len(b)) and np.array_equal(a, b[pos]), 'Missing exact selection')
    aligned = {k: np.asarray(v)[pos] for k, v in q.items()}
    for key in ('timestamp_sample', 'effective_mode', 'effective_axes'):
        require(np.array_equal(d[key], aligned[key]), 'Callback identity mismatch '+key)
    return aligned


def harmonics(t, error, target, measured, weights):
    # The known enveloped task has 3/32, 4/32, 5/32 Hz components.
    # A descriptive projection, not smoothing for the primary RMSE or a system identification claim.
    basis = np.column_stack([np.ones(len(t))] + [f(2*np.pi*freq*t)
        for freq in (3/32, 4/32, 5/32) for f in (np.cos, np.sin)])
    def fit(y):
        c = np.linalg.lstsq(basis*np.sqrt(weights[:, None]), y*np.sqrt(weights), rcond=None)[0]
        return c, basis@c
    ce, fitted = fit(error)
    cv, _ = fit(measured)
    cr, _ = fit(target)
    denominator, numerator = complex(cr[3], -cr[4]), complex(cv[3], -cv[4])
    require(abs(denominator) > 1e-6, 'Unidentifiable central target harmonic')
    ratio = numerator/denominator
    return dict(frequencies_hz=[3/32,4/32,5/32], projected_error_rmse=stats(fitted,weights)['rmse'],
        residual_error_rmse=stats(error-fitted,weights)['rmse'],
        central_gain=abs(ratio), central_phase_deg=float(np.angle(ratio)*180/np.pi),
        exploratory=True, not_a_counterfactual=True)


def inspect(row):
    from pyulog import ULog
    metric_path = Path(row['metrics_file']['path'])
    require(digest(metric_path) == row['metrics_file']['sha256'], 'Changed frozen metrics')
    metrics = json.loads(metric_path.read_text())
    archive = metrics['ulog']
    path = Path(archive['archive'])
    require(digest(path) == archive['sha256'], 'Changed ULog')
    u = ULog(str(path), message_name_filter_list=['sta_velocity_ctrl_status','velocity_ctrl_selection'])
    require(not u.dropouts and not getattr(u, 'file_corruption', False), 'Corrupt/dropout log')
    d = u.get_dataset('sta_velocity_ctrl_status').data
    q = align(d, u.get_dataset('velocity_ctrl_selection').data)
    result_path = Path(row['result']['path'])
    require(digest(result_path) == row['result']['sha256'], 'Changed frozen result')
    events = {e['name']: e['timestamp_us'] for e in json.loads(result_path.read_text())['events']}
    obs = (d['timestamp'] >= events['hover_start']) & (d['timestamp'] < events['hover_end'])
    x, y = [{k: np.asarray(v)[obs] for k,v in data.items()} for data in (d,q)]
    tm = x['timestamp_sample'].astype(np.int64)
    require(np.all(np.diff(tm) > 0), 'Observation duplicate/backwards sample')
    weights = np.diff(np.r_[tm,tm[-1]+int(np.median(np.diff(tm)))])*1e-6
    main = (x['excitation_time'] >= 0) & (x['excitation_time'] < 32)
    weights = weights[main]
    x,y = [{k:v[main] for k,v in data.items()} for data in (x,y)]
    job = metrics['job']
    require(np.all(x['effective_mode'] == job['mode']) and np.all(x['effective_axes'] == job['axes']), 'Wrong actual mode/axes')
    require(np.all(x['inner_mode'] == 0) and np.all(x['inner_axes'] == 0) and np.all(x['inner_divisor'] == 1), 'Wrong inner loop')
    require(len(weights) == metrics['diagnostic']['samples'], 'Wrong main window')
    error = x['s[2]'].astype(float)
    actual = stats(error,weights)
    for key in ('mean','variance','rmse','max_abs'):
        require(abs(actual[key]-metrics['diagnostic']['error'][key][2]) < 1e-14, 'Frozen metric mismatch '+key)
    p = job['parameters']
    l1,l2,eps = [p['MPC_VC_'+key+'_Z'] for key in ('L1','L2','EPS')]
    h = x['raw_dt'].astype(float)
    k,i,ke,ie = local_gains(l1,l2,eps,h)
    constraints = (x['constraint_bits'] != 0) | ((x['sta_flags'].astype(int) & (8|16|32)) != 0)
    out = dict(id=row['id'],candidate=row['candidate'],seed=row['seed'],samples=len(error),
        recomputed_error=actual, raw_dt_us_histogram={str(int(a)):int(b) for a,b in
            zip(*np.unique(np.rint(h*1e6).astype(int),return_counts=True))},
        layer_s_fraction=float(np.mean(abs(error) <= eps)), constraint_samples=int(constraints.sum()),
        hte_nonzero_samples=int(np.count_nonzero(x['z_hte_shift'])),
        local_gain=dict(rsta_p=float(k),rsta_i=float(i),rista_p_range=[float(ke.min()),float(ke.max())],
            rista_i_range=[float(ie.min()),float(ie.max())]),
        harmonics=harmonics(x['excitation_time'].astype(float),error,x['v_sp[2]'].astype(float),
            x['v[2]'].astype(float),weights),
        source=dict(path=str(path),sha256=archive['sha256'],metrics_sha256=row['metrics_file']['sha256']))
    if job['mode'] in (3,4):
        require(np.all(x['committed_axes']==4) and np.all(y['control_updated']), 'Uncommitted main sample')
        old = x['nu_before[2]'].astype(float)
        new = x['nu_applied[2]'].astype(float)
        observed = y['correction[2]'].astype(float)
        use_p, use_i = (ke,ie) if job['mode']==4 else (k,i)
        layer = abs(error) <= eps
        require(np.all(layer), 'Local formula not valid for whole recorded main window')
        out['local_formula_output_max_abs'] = float(np.max(abs(observed-(old-use_p*error))))
        out['local_formula_state_max_abs'] = float(np.max(abs(new-(old-h*use_i*error))))
        require(out['local_formula_output_max_abs']<2e-6 and out['local_formula_state_max_abs']<2e-7, 'Local model disagrees with actual output')
        if job['mode']==4:
            out['layer_p_fraction'] = float(np.mean(abs(y['ri_p[2]']) <= eps))
            out['strict_implicit_samples'] = int(np.count_nonzero(y['ri_strict_axes'].astype(int)&4))
    require(digest(path)==archive['sha256'] and digest(metric_path)==row['metrics_file']['sha256'], 'Source changed during read')
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    require(not args.output.exists(), 'Output must not exist; old results never overwritten')
    args.output.mkdir(parents=True)
    source_hash=digest(SOURCE)
    summary=json.loads(SOURCE.read_text())
    require(summary['source_head']=='a1c2046d94a6bbf061720385a5ad36110b1d0dc2'
            and len(summary['runs'])==9, 'Unexpected frozen dataset')
    results=[]
    for row in summary['runs']:
        result=inspect(row)
        results.append(result)
        (args.output/(row['id']+'.json')).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        print(json.dumps({k:result[k] for k in ('id','candidate','layer_s_fraction','recomputed_error')}),flush=True)
    require(digest(SOURCE)==source_hash,'Frozen source changed')
    (args.output/'summary.json').write_text(json.dumps(dict(diagnostic_only=True,new_flights=0,
        flight_authorized=False,historical_acceptance_changed=False,source_sha256=source_hash,runs=results),
        indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    main()
