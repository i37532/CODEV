import copy
import json
from pathlib import Path
import unittest

from prepare import SOURCE, draft


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads(SOURCE.read_text())

    def test_eight_order_and_zero_attempts(self):
        result = draft(self.source)
        self.assertEqual(result['max_attempts'], 8)
        self.assertEqual([(j['task'], j['system']) for j in result['jobs']],
                         [(t, a) for t in ('position', 'velocity')
                          for a in ('PID', 'STA2', 'RSTA', 'RISTA')])
        self.assertTrue(all(j['status'] == 'unattempted' for j in result['jobs']))
        self.assertEqual(result['new_flight_samples'], 0)

    def test_no_old_result_reuse(self):
        result = draft(self.source)
        self.assertNotIn('result_path', json.dumps(result))
        self.assertEqual(result['status'], 'draft_not_flight_qualified')

    def test_parameters_exact_and_source_not_mutated(self):
        before = copy.deepcopy(self.source)
        result = draft(self.source)
        for job in result['jobs']:
            name = 'Upstream STA2' if job['system'] == 'STA2' else job['system']
            old = next(j for j in self.source['jobs'] if j['label'] == name)
            self.assertEqual(job['parameters'], old['parameters'])
            self.assertEqual(job['expected_parameters'], old['expected_parameters'])
        result['jobs'][0]['parameters']['MIS_TAKEOFF_ALT'] = 99
        self.assertEqual(self.source, before)

    def test_duplicate_or_missing_system_rejected(self):
        self.source['jobs'][0]['label'] = 'PID'
        with self.assertRaises(ValueError):
            draft(self.source)

    def test_wrong_rate_or_div_rejected(self):
        for key in ('MC_RTC_MODE', 'MC_STA_AXES', 'MC_RTC_DIV', 'MC_RATT_TEST', 'MPC_VC_DIV'):
            source = copy.deepcopy(self.source)
            job = next(j for j in source['jobs'] if j['label'] == 'RSTA')
            job['parameters'][key] = 9
            with self.assertRaises(ValueError):
                draft(source)

    def test_wrong_algorithm_axes_and_task_rejected(self):
        for key in ('MPC_VC_MODE', 'MPC_VC_AXES', 'MPC_VCT_TEST'):
            source = copy.deepcopy(self.source)
            job = next(j for j in source['jobs'] if j['label'] == 'RISTA')
            job['parameters'][key] = 9
            with self.assertRaises(ValueError):
                draft(source)

    def test_budget_and_stop_are_not_optimisation(self):
        result = draft(self.source)
        self.assertTrue(result['stop_on_first_failure'])
        self.assertFalse(result['automatic_retry'])
        self.assertFalse(result['retuning'])


if __name__ == '__main__':
    unittest.main()
