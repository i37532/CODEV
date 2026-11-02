import copy
import unittest
from unittest.mock import patch
import analyze_results as a


class ResultsTests(unittest.TestCase):
    def test_reject_incomplete_matrix(self):
        with self.assertRaises(ValueError): a.qualified_rows(dict(quick_stage='comparison',jobs=[]))

    def test_reject_wrong_order_without_reading_logs(self):
        m=dict(quick_stage='comparison',jobs=[dict(system=s) for s in reversed(a.ORDER)])
        with self.assertRaises(ValueError): a.qualified_rows(m)

    def test_reject_failed_run_before_plot_or_log_access(self):
        m=dict(quick_stage='comparison',data_root='/tmp/no-flights',jobs=[dict(system=s,id=str(i)) for i,s in enumerate(a.ORDER)])
        with patch.object(a.Path,'read_text',return_value='{"success":false}'),patch.object(a,'audit_native_log') as decode:
            with self.assertRaises(ValueError): a.qualified_rows(m)
            decode.assert_not_called()

    def test_response_is_ramp_metric_not_assumed_ranking(self):
        t=a.np.arange(-.1,31,.1);u=a.np.clip(t/16,0,1);h=2.5*u*u*u*(10-15*u+6*u*u)
        r=a.response_metrics(t,h,a.np.zeros(len(t)),2.5,30)
        self.assertGreater(r['rise_10_90_s'],0)
        self.assertEqual(r['overshoot_m'],0)


if __name__=='__main__':unittest.main()
