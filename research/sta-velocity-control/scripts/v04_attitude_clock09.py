"""Opt-in, offline V04 attitude clock policy; no flight authorization.

Only vehicle_attitude instance 0 may have tied publication stamps. All rows
remain intact. A latest-published group is NOT proof of actual consumption.
Existing yaw freshness (20 ms), topic gap (250 ms), count (600), tilt (15 deg)
and yaw (20 deg) limits are reused, not fitted to the series07 failure.
"""
import numpy as np
from analyze_v00 import stats
from analyze_v03 import exact_output_match as legacy_output_match
from v04_heading_stream import data as legacy_data

ATTITUDE_TOPIC = 'vehicle_attitude'
MAX_AGE_US = 20000
MAX_GAP_US = 250000


def clock(values):
    a = np.asarray(values)
    if a.ndim != 1 or not len(a) or a.dtype.kind not in 'iu':
        raise ValueError('Missing/integer clock required')
    if np.any(a <= 0) or int(a.max()) > np.iinfo(np.int64).max:
        raise ValueError('Clock outside positive int64 range')
    return a.astype(np.int64)


def strict_clock(values):
    t = clock(values)
    if np.any(np.diff(t) <= 0):
        raise ValueError('Nonunique/backward association key')
    return t


def unique_previous(source, targets, max_age_us=MAX_AGE_US):
    """Descriptive preceding-row association, never a consumption claim."""
    p = strict_clock(source)
    q = clock(targets)
    i = np.searchsorted(p, q, side='right')-1
    if np.any(i < 0):
        raise ValueError('No preceding evidence')
    ages = q-p[i]
    if np.any(ages > max_age_us):
        raise ValueError('Stale association')
    return i, ages


def exact_output_match(d, output, dtime, pairs, start, end):
    """Do not let intersect1d silently select one of conflicting outputs."""
    strict_clock(d['timestamp'])
    mask = (d['timestamp'] >= start) & (d['timestamp'] < end)
    strict_clock(d[dtime][mask])
    strict_clock(output['timestamp'])
    return legacy_output_match(d, output, dtime, pairs, start, end)


class AttitudeClockPolicy:
    """Explicit opt-in. Default old analyzers and every old runner stay strict."""
    def data(self, log, name=ATTITUDE_TOPIC, instance=0):
        if name != ATTITUDE_TOPIC:
            return legacy_data(log, name, instance)
        if instance != 0:
            raise ValueError('Attitude clock whitelist is public instance 0 only')
        d = log.get_dataset(name, instance).data
        self.validate(d)
        return d

    def validate(self, d):
        p = clock(d['timestamp'])
        s = strict_clock(d['timestamp_sample'])
        if s.shape != p.shape or any(np.asarray(v).shape != p.shape for v in d.values()):
            raise ValueError('Malformed attitude columns')
        if np.any(np.diff(p) < 0):
            raise ValueError('Backward attitude publication')
        if np.any(s > p):
            raise ValueError('Future attitude sample')
        if np.any(p-s > MAX_AGE_US):
            raise ValueError('Stale attitude sample at publication')
        for key in [f'{f}[{i}]' for f in ('q', 'delta_q_reset') for i in range(4)]:
            if not np.all(np.isfinite(d[key])):
                raise ValueError('Nonfinite attitude '+key)
        c = np.asarray(d['quat_reset_counter'])
        if c.dtype.kind not in 'iu' or np.any(c < 0) or np.any(c > 255):
            raise ValueError('Invalid quaternion reset counter')
        return p, s

    def window(self, d, start, end):
        """Closed safety window plus complete previous group for reset evidence.

        Both boundary groups are intact. No records after end are borrowed.
        A strict predecessor is required: otherwise the opening reset edge is
        unobservable. The predecessor is for evidence, not metric weighting.
        """
        p, s = self.validate(d)
        if not 0 < start <= end:
            raise ValueError('Invalid attitude interval')
        before = int(np.searchsorted(p, start, side='left'))-1
        if before < 0:
            raise ValueError('Missing attitude boundary predecessor')
        first = int(np.searchsorted(p, p[before], side='left'))
        stop = int(np.searchsorted(p, end, side='right'))
        ix = np.arange(first, stop)
        if len(ix) < 2 or not np.any(p[ix] >= start):
            raise ValueError('Missing attitude interval')
        if start-s[before] > MAX_AGE_US or end-s[ix[-1]] > MAX_AGE_US:
            raise ValueError('Stale attitude window boundary')
        if np.any(np.diff(p[ix]) > MAX_GAP_US) or np.any(np.diff(s[ix]) > MAX_GAP_US):
            raise ValueError('Attitude publication/sample gap')
        return ix

    def reset_indices(self, d, start, end):
        ix = self.window(d, start, end)
        changed = ix[1:][np.diff(d['quat_reset_counter'][ix].astype(np.int64)) != 0]
        return changed[d['timestamp'][changed] >= start]

    def candidates(self, d, query):
        """Every member of the latest published group, including at equality."""
        p, s = self.validate(d)
        q = clock(np.atleast_1d(query))
        groups = []
        for t in q:
            last = int(np.searchsorted(p, t, side='right'))-1
            if last < 0:
                raise ValueError('No preceding attitude')
            first = int(np.searchsorted(p, p[last], side='left'))
            ix = np.arange(first, last+1)
            # Every possible row must be fresh by BOTH clocks.
            if np.any(t-p[ix] > MAX_AGE_US) or np.any(t-s[ix] > MAX_AGE_US):
                raise ValueError('Stale attitude candidate group')
            groups.append(ix)
        return groups

    def unique_index(self, d, query):
        groups = self.candidates(d, query)
        if any(len(g) != 1 for g in groups):
            raise ValueError('Ambiguous attitude association; no consumed-sample key')
        return np.array([g[0] for g in groups])

    def topic_rates(self, d, mask):
        """Publish gaps and sample rate reported separately; 0 publish gap kept."""
        p, s = self.validate(d)
        p, s = p[mask], s[mask]
        if len(p) < 2:
            raise ValueError('Missing attitude rate window')
        def summarize(t):
            dt = np.diff(t)*1e-6
            elapsed = int(t[-1])-int(t[0])
            return dict(n=len(t), hz=(len(t)-1)*1e6/elapsed if elapsed else None,
                        dt_min_s=float(dt.min()), dt_median_s=float(np.median(dt)),
                        dt_max_s=float(dt.max()), dt_p95_s=float(np.percentile(dt, 95)))
        pub, sample = summarize(p), summarize(s)
        covered = (len(p) >= 600 and np.max(np.diff(p)) <= MAX_GAP_US
                   and np.max(np.diff(s)) <= MAX_GAP_US)
        return dict(publication=pub, sample=sample,
                    equal_publish=int(np.count_nonzero(np.diff(p) == 0)),
                    max_publish_age_us=int(np.max(p-s))), bool(covered)

    def yaw_metrics(self, d, target, start, end):
        """Original descriptive per-record RMSE; no dt weighting or deduplication.

        Targets are paired at publication time as before. Every tied attitude
        row is evaluated; no attitude row is chosen as a consumer surrogate.
        """
        self.window(d, start, end)
        p = d['timestamp']
        m = (p >= start) & (p < end)
        if not np.any(m):
            raise ValueError('Empty attitude metric window')
        j, age = unique_previous(target['timestamp'], p[m])
        q = np.column_stack([d[f'q[{i}]'][m] for i in range(4)])
        yaw = np.arctan2(2*(q[:,0]*q[:,3]+q[:,1]*q[:,2]), 1-2*(q[:,2]**2+q[:,3]**2))
        errors = np.angle(np.exp(1j*(yaw-target['yaw_body'][j])))
        return dict(stats=stats(errors), records=len(errors), max_target_age_us=int(age.max()),
                    pairing='unique preceding target at publication; not proven consumed',
                    weighting='one per recorded attitude row; historical yaw convention')

    def safety(self, d, target, start, end, *, check_yaw=True):
        """Closed safety interval incl. predecessor and ALL tied boundary rows."""
        ix = self.window(d, start, end)
        q = np.column_stack([d[f'q[{i}]'][ix] for i in range(4)])
        tilt = np.rad2deg(np.arccos(np.clip(1-2*(q[:,1]**2+q[:,2]**2), -1, 1)))
        j, _ = unique_previous(target['timestamp'], d['timestamp'][ix])
        yaw = np.arctan2(2*(q[:,0]*q[:,3]+q[:,1]*q[:,2]), 1-2*(q[:,2]**2+q[:,3]**2))
        errors = np.angle(np.exp(1j*(yaw-target['yaw_body'][j])))
        if not np.all(np.isfinite(errors)):
            raise ValueError('Nonfinite yaw target/error')
        if np.any(tilt > 15):
            raise ValueError('Attitude tilt exceeds existing 15 deg bound')
        if check_yaw and np.any(np.abs(errors) > np.deg2rad(20)):
            raise ValueError('Yaw exceeds existing 20 deg bound')
        return dict(records=len(ix), max_tilt_deg=float(tilt.max()),
                    max_yaw_error_rad=float(np.abs(errors).max()),
                    yaw_bound_checked=check_yaw,
                    reset_indices=self.reset_indices(d, start, end).tolist())
