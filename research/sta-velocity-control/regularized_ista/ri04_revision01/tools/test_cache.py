"""Repaired cache semantics through the actual new-mode analysis components.

Synthetic fixtures only; no flight, admission, EEPROM or historical edits.
"""
import copy
import unittest
import numpy as np
import test_tools as fixtures

a = fixtures.analyzer


def clipped_fixture():
    x, q, job, _, _ = fixtures.fixture()
    n = len(x['timestamp'])
    steps = np.resize(np.array([8000, 12000], dtype=np.int64), n)
    times = (1000000 + np.cumsum(steps)).astype(np.uint64)
    h = (steps * 1e-6).astype(np.float32)
    for d in (x, q):
        for name in ('timestamp', 'timestamp_sample', 'input_timestamp'):
            d[name] = times.copy()
    for name in ('inner_timestamp', 'inner_check_timestamp'):
        x[name] = times.copy()
    q['ri_cache_sample'] = times.copy()
    for name in ('raw_dt', 'used_dt', 'input_dt'):
        x[name] = h.copy()
    q['h'] = q['ri_h'] = h.copy()
    x['hover_thrust'][100:] = np.float32(.5001)
    x['hover_thrust'][200:] = np.float32(.5002)
    p = job['parameters']
    l1, l2, eps, cap = [np.float32(p['MPC_VC_' + k + '_Z']) for k in ('L1', 'L2', 'EPS', 'NU')]
    nu = np.float32(-3.9998)
    for k in range(n):
        shift = np.float32(0)
        if k:
            shift = np.float32((x['hover_thrust'][k-1] / x['hover_thrust'][k] - np.float32(1))
                * (q['correction[2]'][k-1] + x['a_ff[2]'][k-1] - np.float32(9.80665)))
        x['z_hte_shift'][k] = shift
        nu = np.float32(nu + shift)
        lo, hi = 0., float(x['s[2]'][k])
        for _ in range(70):
            mid = (lo + hi) / 2
            psi, rho = fixtures.bindings.KERNEL.analyzer.shape(np.array([mid]), float(eps))
            residual = mid + float(h[k]) * float(l1) * psi[0] + float(h[k])**2 * float(l2) * rho[0]
            if residual > float(x['s[2]'][k]): hi = mid
            else: lo = mid
        root = np.float32((lo + hi) / 2)
        psi, rho = fixtures.bindings.KERNEL.analyzer.shape(np.array([root], dtype=float), float(eps))
        candidate = np.float32(nu - np.float32(np.float32(h[k] * l2) * np.float32(rho[0])))
        ideal = np.float32(-l1 * np.float32(psi[0]) + candidate)
        applied = np.float32(np.clip(candidate, -cap, cap))
        q['ri_p[2]'][k] = root
        x['nu_before[2]'][k] = nu
        x['nu_ideal[2]'][k] = q['ri_nu_candidate[2]'][k] = candidate
        x['nu_applied[2]'][k] = q['ri_nu_applied[2]'][k] = applied
        x['a_sta[2]'][k] = q['ri_a_ideal[2]'][k] = ideal
        q['ri_a_applied[2]'][k] = q['correction[2]'][k] = ideal
        x['a_req[2]'][k] = x['a_proxy[2]'][k] = q['ri_acc_published[2]'][k] = np.float32(ideal + x['a_ff[2]'][k])
        x['sta_flags'][k] = 8 if applied != candidate else 0
        q['ri_strict_axes'][k] = 0 if applied != candidate else 4
        nu = applied
    for axis in range(3):
        x[f'thrust[{axis}]'] = (x[f'a_proxy[{axis}]'] - (9.80665 if axis == 2 else 0)) * x['hover_thrust'] / 9.80665
        q[f'ri_thrust_published[{axis}]'] = x[f'thrust[{axis}]'].copy()
    return x, q, job, int(times[1]), int(times[-2])


class CacheTests(unittest.TestCase):
    def test_real_components_state_limit_only_and_two_hte_transitions(self):
        x, q, j, start, end = clipped_fixture()
        result, _, _ = a.components(x, q, j, start, end, True)
        self.assertGreater(result['closed_cache_policy']['state_limit_only_cached'], 600)
        self.assertEqual(result['closed_cache_hte']['nonzero_shifts_checked'], 2)
        self.assertTrue(np.any(q['ri_nu_candidate[2]'] != q['ri_nu_applied[2]']))
        self.assertFalse(np.array_equal(q['correction[2]'], q['ri_nu_applied[2]']))

    def test_removed_state_limit_cache_rejected_by_actual_components(self):
        x, q, j, start, end = clipped_fixture()
        q['ri_cache_valid'][99] = q['ri_cache_sample'][99] = 0
        with self.assertRaisesRegex(ValueError, 'cache protection'):
            a.components(x, q, j, start, end, True)

    def test_fake_output_or_outward_protection_cache_rejected(self):
        for flag in (16, 32, 64):
            x, q, j, start, end = fixtures.fixture()
            x['sta_flags'][99] = flag
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                a.components(x, q, j, start, end, False)

    def test_downstream_constraint_cannot_keep_cache(self):
        for bits in (1, 2, 4):
            x, q, j, start, end = fixtures.fixture()
            x['constraint_bits'][99] = bits
            if bits & 6: q['ri_strict_axes'][99] = 0
            with self.subTest(bits=bits), self.assertRaises(ValueError):
                a.components(x, q, j, start, end, False)

    def test_candidate_state_cannot_replace_applied_state(self):
        x, q, j, start, end = clipped_fixture()
        q['ri_nu_applied[2]'] = q['ri_nu_candidate[2]'].copy()
        x['nu_applied[2]'] = q['ri_nu_applied[2]'].copy()
        with self.assertRaises(ValueError): a.components(x, q, j, start, end, True)

    def test_protected_updates_cannot_claim_strict(self):
        x, q, j, start, end = clipped_fixture()
        q['ri_strict_axes'][:] = 4
        with self.assertRaisesRegex(ValueError, 'strict'):
            a.components(x, q, j, start, end, True)

    def test_full_analysis_really_uses_new_policy_layer(self):
        function = a.full_analysis(lambda *args: {})
        self.assertIs(function.__globals__['check_components'], a.components)
        self.assertIs(a.components.__globals__['closed_cache_policy'], a.closed_cache_policy)

    def test_invalid_previous_cache_cannot_explain_nonzero_hte(self):
        x, q, _, _, _ = fixtures.ZContractTests().shifted()
        x['sta_flags'][99] = 16
        q['ri_cache_valid'][99] = q['ri_cache_sample'][99] = 0
        with self.assertRaisesRegex(ValueError, 'without previous closed cache'):
            a.closed_cache_policy(x, q)


if __name__ == '__main__':
    unittest.main(verbosity=2)
