import unittest
import numpy as np
from analyze_v03 import check_diagnostic, exact_output_match, check_inner_evidence


class DiagnosticTest(unittest.TestCase):
    def data(self):
        n = 6000; t = np.arange(n,dtype=np.int64)*10000+1000000
        d = {k:np.zeros(n) for k in ('requested_mode','requested_axes','effective_mode','effective_axes',
            'pending','reject','active_axes','inner_mode','inner_axes','timing','failsafe','fault','constraint_bits',
            'clock','controller_time_us','module_time_us')}
        d.update({k:np.ones(n) for k in ('inner_divisor','inner_valid','pid_calls','updated','valid','enabled','armed')})
        d.update(timestamp=t,timestamp_sample=t.copy(),input_timestamp=t.copy(),output_timestamp=t.copy(),
                 publish_seq=np.arange(n),update_seq=np.arange(n),raw_dt=np.full(n,.01),
                 input_dt=np.full(n,.01),used_dt=np.full(n,.01))
        d.update(inner_timestamp=t-4000,inner_check_timestamp=t.copy(),inner_seq=np.arange(n)*2,
                 inner_reads=np.full(n,2))
        et = np.arange(n)*.01-10
        d['excitation_time'] = et
        d['excitation'] = np.where((et>0)&(et<32),.2*np.sin(2*np.pi*et/8)*np.sin(np.pi*et/32)**2,0)
        for field in ('s','v','v_sp','a_req','a_proxy','thrust'):
            for i in range(3): d[f'{field}[{i}]'] = np.zeros(n)
        for field in ('nu_before','nu_ideal','nu_applied','a_sta'):
            for i in range(3): d[f'{field}[{i}]'] = np.full(n,np.nan)
        d['hover_thrust'] = np.full(n,.5)
        d['thrust[2]'][:] = -.5
        return d

    def test_complete(self):
        r = check_diagnostic(self.data(),1000000,61000000)
        self.assertEqual(r['n'],6000); self.assertEqual(r['excitation_samples'],3200)

    def test_wrong_modes_inner_rejected(self):
        for field in ('requested_mode','requested_axes','effective_mode','effective_axes','inner_mode','inner_axes','pending','reject'):
            d = self.data(); d[field][100] = 1
            with self.subTest(field=field), self.assertRaises(ValueError): check_diagnostic(d,1000000,61000000)

    def test_fault_invalid_duplicate_call(self):
        for field,value in (('pid_calls',2),('inner_valid',0),('inner_divisor',4),('fault',1),('timing',1),('valid',0)):
            d = self.data(); d[field][100] = value
            with self.subTest(field=field), self.assertRaises(ValueError): check_diagnostic(d,1000000,61000000)

    def test_missing_sample(self):
        d = {k:np.delete(v,100) for k,v in self.data().items()}
        with self.assertRaises(ValueError): check_diagnostic(d,1000000,61000000)

    def test_timestamp_and_actual_dt(self):
        for field in ('timestamp','timestamp_sample','input_timestamp','raw_dt','used_dt'):
            d = self.data(); d[field][100] = 0
            with self.subTest(field=field), self.assertRaises(ValueError): check_diagnostic(d,1000000,61000000)

    def test_wrong_command_state_and_fake_sta(self):
        for field in ('excitation','s[0]','nu_ideal[0]'):
            d = self.data(); d[field][100] = 1
            with self.subTest(field=field), self.assertRaises(ValueError): check_diagnostic(d,1000000,61000000)

    def test_partial_window(self):
        with self.assertRaises(ValueError): check_diagnostic(self.data(),1000000,31000000)

    def test_missing_window_edge(self):
        for trim in (slice(100,None),slice(None,-100)):
            d = {k:v[trim] for k,v in self.data().items()}
            with self.assertRaises(ValueError): check_diagnostic(d,1000000,61000000)

    def test_downstream_partial_exact_match(self):
        d = self.data(); out = {'timestamp':d['timestamp'][1:], 'vx':d['v_sp[0]'][1:].copy()}
        r = exact_output_match(d,out,'output_timestamp',[('v_sp[0]','vx')],1000000,61000000)
        self.assertEqual(r['matched'],5999); self.assertEqual(r['denominator'],6000)
        out['vx'][0] = 1
        with self.assertRaises(ValueError): exact_output_match(d,out,'output_timestamp',[('v_sp[0]','vx')],1000000,61000000)

    def test_downstream_coverage_failure(self):
        d = self.data(); out = {'timestamp':d['timestamp'][::2], 'vx':d['v_sp[0]'][::2]}
        with self.assertRaises(ValueError): exact_output_match(d,out,'output_timestamp',[('v_sp[0]','vx')],1000000,61000000)

    def test_proxy_and_constraint_bound(self):
        for field in ('a_proxy[0]','constraint_bits'):
            d = self.data(); d[field][:] = 1
            with self.subTest(field=field), self.assertRaises(ValueError): check_diagnostic(d,1000000,61000000)

    def test_claimed_valid_but_really_stale_inner(self):
        for offset in (100000,124000,-1):
            d=self.data(); d['inner_timestamp']=d['inner_check_timestamp']-offset
            with self.subTest(offset=offset), self.assertRaises(ValueError): check_inner_evidence(d)

    def test_unbounded_inner_drain(self):
        d=self.data(); d['inner_reads'][10]=33
        with self.assertRaises(ValueError): check_inner_evidence(d)
