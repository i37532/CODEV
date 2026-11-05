"""Independent vectorized binary64 implicit inclusion solver for real ULog.

Offline bisection, NOT a copy of the production rationalized root.
"""
import numpy as np


def ideal(s, old, h, l1, l2, g):
    s, old, h, l1, l2, g = [np.asarray(v, dtype=np.float64) for v in (s, old, h, l1, l2, g)]
    target = s + h*old
    q = h*h*l2
    sliding = np.abs(target) <= q
    sign = np.sign(target)
    magnitude = np.maximum(np.abs(target)-q, 0)
    lo = np.zeros_like(s)
    hi = np.minimum(np.sqrt(magnitude), magnitude/(h*l1))
    for _ in range(100):
        mid = (lo+hi)/2
        upper = mid*mid+h*l1*mid > magnitude
        hi = np.where(upper, mid, hi)
        lo = np.where(upper, lo, mid)
    root = (lo+hi)/2
    xi = np.where(sliding, target/q, sign)
    nu = np.where(sliding, -s/h, old-h*l2*sign)
    a = np.where(sliding, nu, -l1*root*sign+nu)
    virtual = np.where(sliding, 0, sign*root*root)
    branch = np.where(sliding, 2, np.where(sign>0, 1, 3))
    return dict(a=a, c=a/g, nu=nu, xi=xi, virtual=virtual, branch=branch)
