"""RI05 replaces RI04 current-head scope tests; archived contracts stay pinned."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('_ri05_freeze_tests',HERE/'freeze.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)


class FreezeTests(unittest.TestCase):
    def test_current_scope_and_defaults(self):
        value=f.scope()
        self.assertGreater(value['parameter_default_count'],0)
        self.assertTrue(set(value['production_changes']).issubset(f.ALLOWED))

    def test_allowed_source_exactseven(self):
        self.assertEqual(len(f.ALLOWED),7)
        self.assertNotIn('src/modules/ekf2/EKF2.cpp',f.ALLOWED)
        self.assertNotIn(f.MODULE+'PositionControl/RegularizedIstaVelocityControl.cpp',f.ALLOWED)

    def test_inherited_accepted_inventory(self):
        old=f.base();self.assertEqual(len(old['assets']),1049)
        self.assertEqual(len(old['external_assets']),79);self.assertEqual(len(old['submodules']),33)

    def test_sources_have_model_and_generators(self):
        names=f.required_names(f.base())
        self.assertIn(f.WORLD,names);self.assertIn(f.MODEL,names)
        self.assertTrue(set(f.GENERATED_SOURCES).issubset(names))

    def test_sourcefiles_no_results_or_own_freeze(self):
        for value in ('results/a.json','gates/C/frozen.json','__pycache__/a.pyc'):
            self.assertFalse(f.include_source(Path(value)))
        self.assertTrue(f.include_source(Path('tools/analyzer.py')))

    def test_no_path_escape(self):
        for name in ('../x','/tmp/x','x/../y','a\\b',''):
            with self.subTest(name=name),self.assertRaises(ValueError):f.safe_name(name)

    def test_comments_do_not_change_defaults(self):
        a=b'PARAM_DEFINE_INT32(X,0); // old comment'
        b=b'/* new metadata */ PARAM_DEFINE_INT32 ( X , 0 );'
        self.assertEqual(f.parameter_definitions(a),f.parameter_definitions(b))
        self.assertNotEqual(f.parameter_definitions(a),f.parameter_definitions(b'PARAM_DEFINE_INT32(X,1);'))

    def test_unknown_production_path_rejected(self):
        original=f.git_bytes
        def fake(*args,**kwargs):
            if args[:2]==('diff','--name-only') and 'src' in args:return b'src/modules/ekf2/EKF2.cpp\n'
            return original(*args,**kwargs)
        with patch.object(f,'git_bytes',side_effect=fake),self.assertRaisesRegex(ValueError,'scope exceeded'):f.scope()

    def test_historical_change_rejected(self):
        original=f.git_bytes
        def fake(*args,**kwargs):
            if args[:2]==('diff','--name-only') and 'research/sta-rate-control' in args:return b'research/sta-rate-control/x\n'
            return original(*args,**kwargs)
        with patch.object(f,'git_bytes',side_effect=fake),self.assertRaisesRegex(ValueError,'Historical research'):f.scope()

    def test_d_capture_requires_c_gate(self):
        with patch.object(f.p,'require_execution_authority'),patch.object(f.p,'require_prior_gate',side_effect=PermissionError('C notpassed')):
            with self.assertRaisesRegex(PermissionError,'C notpassed'):f.capture('D')

    def test_unsafe_submodule_identity_rejected(self):
        with self.assertRaises(ValueError):f.submodule_map(['+'+'a'*40+' src/lib/x'])

    def test_current_source_inventory_contains_tooling(self):
        names=f.asset_names(f.base())
        for path in ('protocol.py','freeze.py','receipt.py','tools/runner.py','tools/analyzer.py','tools/replay.py','test_protocol.py'):
            self.assertIn(str((HERE/path).relative_to(f.REPO)),names)


if __name__=='__main__':unittest.main()
