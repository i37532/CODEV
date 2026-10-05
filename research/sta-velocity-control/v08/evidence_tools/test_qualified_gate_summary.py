import copy
import json
from pathlib import Path
import tempfile
import unittest
import qualified_gate_summary as summary

ROOT=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V08')

class GateSummaryTests(unittest.TestCase):
    def test_actual_whole_qualified_gates_retain_failure_provenance(self):
        r=summary.summarize([ROOT/'pilots01'])
        self.assertEqual(set(r['scenes']),{'heading','force'})
        self.assertFalse(r['sources'][0]['original_batch_success'])
        self.assertEqual(r['sources'][0]['original_attempts'],13)
        self.assertEqual(r['sources'][0]['retained_whole_gates'],['heading','force'])
        self.assertEqual(r['formal_attempts'],0)
    def test_no_arbitrary_partial_source_or_regraded_failure(self):
        original=json.loads((ROOT/'pilots01/ledger.json').read_text())
        for change in ('source','failed_gate','partial_good_gate','wrong_seed'):
            d=copy.deepcopy(original)
            if change=='source':d['source_head']='unregistered'
            elif change=='failed_gate':d['attempts'][-1]['status']='accepted'
            elif change=='partial_good_gate':d['attempts'][2]['status']='failed'
            else:d['attempts'][0]['job']['seed']=99999
            with tempfile.TemporaryDirectory() as folder:
                p=Path(folder);(p/'ledger.json').write_text(json.dumps(d))
                with self.assertRaises(ValueError):summary.summarize([p])
    def test_validation_stays_separate_and_duplicate_pairs_rejected(self):
        r=summary.summarize([ROOT/'validation02',ROOT/'pilots01'])
        self.assertEqual(set(r['scenes']),{'hover','figure8','heading','force'})
        self.assertEqual(r['scenes']['hover']['seeds'],[40301,40302,40303])
        self.assertEqual(r['scenes']['force']['seeds'],[40201,40202,40203])
        with self.assertRaises(ValueError):summary.summarize([ROOT/'validation02',ROOT/'validation02'])

if __name__=='__main__':unittest.main(verbosity=2)
