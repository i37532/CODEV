import unittest
from interface import configuration, analyze_trace, NAMES


def fixture():
    rows = []
    for mask in range(8):
        for i in range(5):
            rows.append(dict(mask=mask, timestamp=1000000+i*10000, sample=1000000+i*10000, seq=i+1,
                mode=int(mask!=0), axes=mask, requested=mask, reject=0, pending=0, valid=1, fault=0,
                inner=0, inner_axes=0, inner_div=1, inner_valid=1, active=mask, committed=mask,
                pid=7^mask, phase=3 if mask&4 else 0, nu=[0. if mask&(1<<i) else None for i in range(3)]))
    return rows


class Interface(unittest.TestCase):
    def test_all_eight_configs_same_per_axis_gains_and_rate_pid(self):
        baseline=configuration('pid')['parameters']
        for name, mask in NAMES.items():
            c=configuration(name); self.assertFalse(c['flight_enabled']); p=c['parameters']
            self.assertEqual(p['MPC_VC_AXES'],mask)
            self.assertEqual({k:v for k,v in p.items() if k not in ('MPC_VC_MODE','MPC_VC_AXES')},
                             {k:v for k,v in baseline.items() if k not in ('MPC_VC_MODE','MPC_VC_AXES')})
            self.assertEqual([p[k] for k in ('MC_RTC_MODE','MC_STA_AXES','MC_RTC_DIV','MC_RATT_TEST','MC_STA_TKO_MGT')],[0,0,1,0,0])
    def test_invalid_name_never_falls_back_to_x(self):
        for name in ('2','unknown','roll','XYZ','ista',''):
            with self.assertRaises(ValueError): configuration(name)
    def test_real_contract_fixture(self):
        self.assertTrue(analyze_trace(fixture())['accepted'])
    def test_wrong_mode_axis_pid_reject_pending_inner_fault(self):
        for key in ('mode','axes','requested','pid','reject','pending','inner','inner_axes','inner_div','fault','inner_valid'):
            d=fixture(); d[12][key]+=1
            with self.subTest(key=key),self.assertRaises(ValueError): analyze_trace(d)
    def test_missing_duplicate_reverse_and_long_sample(self):
        for mutation in ('drop','duplicate','reverse','long'):
            d=fixture()
            if mutation=='drop': del d[12]
            elif mutation=='duplicate': d[12]['sample']=d[11]['sample']
            elif mutation=='reverse': d[12]['timestamp']=d[11]['timestamp']-1
            else: d[12]['sample']+=100000
            with self.subTest(mutation=mutation),self.assertRaises(ValueError): analyze_trace(d)
    def test_handover_not_counted_as_normal(self):
        d=fixture()
        for r in d:
            if r['mask']&4 and r['seq']==1:
                r.update(phase=2,pid=7,committed=0,active=0)
        self.assertTrue(analyze_trace(d)['accepted'])
        for r in d:
            if r['mask']==5: r.update(phase=2,pid=7,committed=0,active=0)
        with self.assertRaises(ValueError): analyze_trace(d)
    def test_unselected_or_partial_commit(self):
        for value in (1,7,0):
            d=fixture(); d[12]['committed']=value
            with self.assertRaises(ValueError): analyze_trace(d)
    def test_empty_or_unknown_group(self):
        for d in ([],fixture()[:5],fixture()+[dict(fixture()[0],mask=8)]):
            with self.assertRaises(ValueError): analyze_trace(d)
    def test_nan_state_and_invalid_phase(self):
        d=fixture(); d[12]['nu'][1]=float('nan')
        with self.assertRaises(ValueError): analyze_trace(d)
        d=fixture(); d[27]['phase']=4
        with self.assertRaises(ValueError): analyze_trace(d)


if __name__ == '__main__': unittest.main()
