"""Result-only certificate tests; not controller or flight tests."""
import copy
import unittest
import audit_results as audit


def fixture():
    jobs = audit.read(audit.ROOT / 'ax04' / 'manifest.json')
    qualification = dict(source_head='qualified-source', firmware_sha256='qualified-firmware')
    checks = {k: True for k in {'yaw'} | {f'{prefix}{i}' for prefix in
        ('velocity_', 'position_', 'first_loop_velocity_', 'second_loop_velocity_') for i in range(3)}}
    ledger = dict(**qualification, planned=320, success=True, parameter_restore_exact=True,
        remaining_simulators=[], H_gate='accepted160_140pairs', V_gate='accepted160_140pairs',
        attempts=[dict(attempt=i, status='accepted', job=copy.deepcopy(j)) for i, j in enumerate(jobs, 1)],
        pairs=[dict(**{k:j[k] for k in ('task','seed','candidate','axes','divisor')},
            accepted=True, checks=checks.copy()) for j in jobs if j['axes']])
    return ledger, jobs, qualification


class AuditTest(unittest.TestCase):
    def test_complete(self):
        self.assertTrue(audit.validate_complete(*fixture()))

    def test_pair_arrival_order_independent(self):
        x, j, q = fixture(); x['pairs'].reverse()
        self.assertTrue(audit.validate_complete(x, j, q))

    def reject(self, change):
        x, j, q = fixture(); change(x)
        with self.assertRaises(ValueError): audit.validate_complete(x, j, q)

    def test_missing_attempt(self):
        self.reject(lambda x: x['attempts'].pop())

    def test_reordered_attempt(self):
        self.reject(lambda x: x['attempts'].reverse())

    def test_failed_attempt(self):
        self.reject(lambda x: x['attempts'][0].update(status='failed'))

    def test_changed_job(self):
        self.reject(lambda x: x['attempts'][0]['job'].update(seed=99999))

    def test_changed_source_or_firmware(self):
        for k in ('source_head', 'firmware_sha256'):
            with self.subTest(k=k): self.reject(lambda x: x.update({k:'other'}))

    def test_missing_or_duplicate_pair(self):
        self.reject(lambda x: x['pairs'].pop())
        self.reject(lambda x: x['pairs'].__setitem__(0, x['pairs'][1]))

    def test_failed_pair_check(self):
        self.reject(lambda x: x['pairs'][0]['checks'].update(yaw=False))

    def test_missing_pair_check(self):
        self.reject(lambda x: x['pairs'][0]['checks'].pop('yaw'))

    def test_cleanup_and_gates(self):
        for k, v in [('parameter_restore_exact', False), ('remaining_simulators', [1]),
                ('H_gate', None), ('V_gate', None), ('success', False), ('planned', 48)]:
            with self.subTest(k=k): self.reject(lambda x: x.update({k:v}))


if __name__ == '__main__': unittest.main()
