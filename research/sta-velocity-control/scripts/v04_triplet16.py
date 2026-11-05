"""Navigator publication candidates scoped to the actual target-use window.

Retain the whole dataset. Validate structural/time integrity everywhere. An
equal-time group is ambiguous if ANY field differs bitwise. Such a group must
not supply the entry predecessor, any in-window target, or the closing boundary.
Outside groups are recorded as unresolved, never described as consumed/unique.
"""
import numpy as np


def triplet_data(log, start, end):
    if not np.isfinite(start) or not np.isfinite(end) or not 0 < start < end:
        raise ValueError('Invalid triplet use window')
    d = log.get_dataset('position_setpoint_triplet').data
    t = d['timestamp']
    if (not len(t) or not np.issubdtype(t.dtype, np.integer) or np.any(t <= 0)
            or np.any(t > np.iinfo(np.int64).max)):
        raise ValueError('Empty/invalid triplet publication clock')
    if any(len(x) != len(t) for x in d.values()):
        raise ValueError('Misaligned triplet field')
    delta = np.diff(t.astype(np.int64))
    if np.any(delta < 0):
        raise ValueError('Reversed triplet publication clock')
    predecessor = int(np.searchsorted(t, start, side='right')) - 1
    if predecessor < 0:
        raise ValueError('Missing entry triplet predecessor')
    # Include the ENTIRE predecessor group, not just searchsorted's last row.
    left = int(np.searchsorted(t, t[predecessor], side='left'))
    # End-boundary groups are also checked, although target matching remains
    # half-open. Never split an equal-time group at either window boundary.
    right = int(np.searchsorted(t, end, side='right'))
    evidence = dict(window_start_us=int(start), window_end_us=int(end),
                    predecessor_group_us=int(t[left]), retained_rows=len(t),
                    checked_rows=right-left, unresolved_outside_groups=[])
    edges = np.r_[0, np.flatnonzero(delta != 0)+1, len(t)]
    for a, b in zip(edges[:-1], edges[1:]):
        if b-a < 2:
            continue
        changed = [key for key, x in d.items()
                   if any(x[a:a+1].tobytes() != x[j:j+1].tobytes() for j in range(a+1, b))]
        if not changed:
            continue
        if a < right and b > left:
            raise ValueError('Ambiguous consumed/boundary triplet field '+changed[0])
        evidence['unresolved_outside_groups'].append(dict(
            timestamp_us=int(t[a]), first_row=int(a), row_count=int(b-a), changed_fields=changed,
            reason='superseded before entry' if b <= left else 'after closing boundary'))
    return d, evidence
