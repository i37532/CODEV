"""One-topic publication-clock policy. Retain every logged row, never deduplicate.

Navigator stamps this event-driven topic with hrt_absolute_time(), without a
sensor sample clock. Equal publication times are unambiguous ONLY when every
logged field is bitwise identical. Other topics keep their original rules.
"""
import numpy as np


def triplet_data(log):
    d = log.get_dataset('position_setpoint_triplet').data
    t = d['timestamp']
    if not len(t) or not np.issubdtype(t.dtype, np.integer) or np.any(t <= 0):
        raise ValueError('Empty/invalid triplet publication clock')
    delta = np.diff(t.astype(np.int64))
    if np.any(delta < 0): raise ValueError('Reversed triplet publication clock')
    for key, values in d.items():
        if len(values) != len(t): raise ValueError('Misaligned triplet field ' + key)
    for right in np.flatnonzero(delta == 0) + 1:
        for key, values in d.items():
            # Includes all previous/current/next fields, NaN payloads and signed
            # zero. No approximate equality or "last duplicate wins" shortcut.
            if values[right-1:right].tobytes() != values[right:right+1].tobytes():
                raise ValueError('Ambiguous equal-time triplet field ' + key)
    return d
