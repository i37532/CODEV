import unittest
from unittest.mock import patch
from pathlib import Path
import freeze as f

class Freeze(unittest.TestCase):
    def test_zero_production_scope(self):self.assertEqual(f.scope()['production_changes'],[])
    def test_complete_inherited(self):
        old=f.base();self.assertGreater(len(old['assets']),1000);self.assertEqual(len(old['submodules']),33)
        self.assertEqual(len(old['external_assets']),79)
    def test_current_tools_included(self):
        names=f.names()
        for name in ('protocol.py','tools/runner.py','tools/analyzer.py','choose_candidate.py','receipt.py','test_freeze.py'):
            self.assertIn(f.PREFIX+'/'+name,names)
    def test_own_freeze_and_results_excluded(self):
        self.assertFalse(f.included(f.PREFIX+'/gates/TH/frozen.json'))
        self.assertFalse(f.included(f.PREFIX+'/results/a.json'))
    def test_selected_config_not_excluded(self):self.assertTrue(f.included(f.PREFIX+'/selection.json'))
    def test_no_prod_scope_expansion(self):
        original=f.p.git
        def fake(*args):
            return 'src/modules/mc_pos_control/PositionControl/PositionControl.cpp' if args[:2]==('diff','--name-only') else original(*args)
        with patch.object(f.p,'git',side_effect=fake),self.assertRaises(ValueError):f.scope()
    def test_no_historical_rewrite(self):
        with patch.object(f.p,'git',return_value='research/sta-velocity-control/reports/RI05.md'),self.assertRaises(ValueError):f.scope()

if __name__=='__main__':unittest.main()
