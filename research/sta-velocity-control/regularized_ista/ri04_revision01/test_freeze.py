"""Read-only RI04 freeze regressions; no registration, manifest or source writes."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


f = load('_ri04_revision01_freeze_regression', HERE/'freeze.py')
ENTRY = 'bb56d1414cc0e7e196995f9281a0306ca7f46964'
OLD_SOURCE = '74327418e18eafd421e18b48fe3964fdad63cfb5'
OLD_FROZEN_SHA = 'ca23e7b3f08da19e451aa8bdbe943afbf71b40c15b1f04a90cf035042e55d9ad'
EXPECTED_ALLOWED = set()


class FreezeIdentityTests(unittest.TestCase):
    def test_exact_entry_and_inherited_manifest(self):
        self.assertEqual(f.ENTRY_HEAD, ENTRY)
        self.assertEqual(f.BASE_SHA, OLD_FROZEN_SHA)
        old = f.base()
        self.assertEqual(len(old['assets']), 1001)
        self.assertEqual(len(old['external_assets']), 79)
        self.assertEqual(len(old['submodules']), 33)
        self.assertEqual(old['derived_iris_sha256'], f.MODEL_SHA)
        self.assertEqual(old['assets'][f.WORLD], f.WORLD_SHA)

    def test_wrong_entry_rejected(self):
        with patch.object(f.p, 'ENTRY_HEAD', '0'*40), self.assertRaisesRegex(ValueError, 'entry'):
            f.base()

    def test_changed_base_bytes_rejected(self):
        with patch.object(f.p, 'fingerprint', return_value='0'*64), self.assertRaisesRegex(ValueError, 'manifest'):
            f.base()

    def test_no_new_production_paths(self):
        self.assertEqual(f.ALLOWED, EXPECTED_ALLOWED)
        self.assertEqual(len(f.ALLOWED), 0)
        self.assertEqual(len(f.REBOUND), 3)
        self.assertNotIn(f.MODULE+'PositionControl/RegularizedIstaNonSitlTest.cpp', f.ALLOWED)

    def test_current_scope_and_all_defaults(self):
        record = f.scope()
        self.assertEqual(set(record['production_changes']), EXPECTED_ALLOWED)
        self.assertEqual(set(record['allowed_production_changes']), EXPECTED_ALLOWED)
        self.assertTrue(record['immutable_research_unchanged'])
        self.assertEqual(record['parameter_default_count'], 72)
        self.assertEqual(record['parameter_defaults_sha256'],
                         '364eb89c576c09c203af881489f171e101ed92baa4a42e2020005f18d60e4d10')

    def test_scope_rejects_unlisted_production_path(self):
        real = f.git_bytes
        def git(*args, **kwargs):
            if args[:2] == ('diff', '--name-only') and 'src' in args:
                return b'src/modules/forbidden.cpp\n'
            return real(*args, **kwargs)
        with patch.object(f, 'git_bytes', side_effect=git), self.assertRaisesRegex(ValueError, 'scope'):
            f.scope()

    def test_scope_rejects_historical_result_change(self):
        real = f.git_bytes
        def git(*args, **kwargs):
            if args[:2] == ('diff', '--name-only') and f.PRIOR_ROOT in args:
                return (f.PRIOR_ROOT+'/results/summary.json\n').encode()
            return real(*args, **kwargs)
        with patch.object(f, 'git_bytes', side_effect=git), self.assertRaisesRegex(ValueError, 'Historical'):
            f.scope()

    def test_scope_rejects_changed_parameter_definitions(self):
        real = f.git_bytes
        calls = 0
        def git(*args, **kwargs):
            nonlocal calls
            raw = real(*args, **kwargs)
            if args[:1] == ('show',) and args[1].endswith(':'+f.PARAMETERS):
                calls += 1
                if calls == 2:
                    raw += b'\nPARAM_DEFINE_INT32(FORBIDDEN_DEFAULT, 1);\n'
            return raw
        with patch.object(f, 'git_bytes', side_effect=git), self.assertRaisesRegex(ValueError, 'PARAM_DEFINE'):
            f.scope(ENTRY)
        self.assertEqual(calls, 2)

    def test_parameter_comments_not_definitions(self):
        raw = b'/* PARAM_DEFINE_FLOAT(HIDDEN, 1); */\nPARAM_DEFINE_FLOAT(A, 1.f); // end'
        self.assertEqual(f.parameter_definitions(raw), ['PARAM_DEFINE_FLOAT(A,1.f);'])

    def test_missing_real_parameter_definitions_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Missing'):
            f.parameter_definitions(b'// PARAM_DEFINE_FLOAT(A, 1.f);')

    def test_all_prior_ri03_results_and_frozen_in_inventory(self):
        names = f.prior_archive_names()
        self.assertGreater(len(names), 26)
        expected = {'results/summary.json', 'results/ulog_index.json',
                    'results/archive_reference.json', 'results/verification.json',
                    'results/collect.py', 'results/test_collect.py', 'gates/B/frozen.json'}
        self.assertTrue({f.PRIOR_ROOT+'/'+name for name in expected}.issubset(names))
        self.assertTrue(names.issubset(f.required_names(f.base())))
        self.assertIn('research/sta-velocity-control/reports/RI03.md', f.required_names(f.base()))

    def test_missing_prior_result_archive_rejected(self):
        with patch.object(f, 'git_bytes', return_value=b''), self.assertRaisesRegex(ValueError, 'Incomplete'):
            f.prior_archive_names()

    def test_old_snapshots_and_ri03_directory_immutable(self):
        self.assertIn(f.PRIOR_ROOT, f.IMMUTABLE)
        for name in ('v1', 'ri00_entry', 'ri01_entry', 'ri02_entry', 'ri03_entry'):
            self.assertIn('research/sta-velocity-control/regularized_ista/plan/'+name, f.IMMUTABLE)

    def test_new_results_and_manifest_excluded_from_source_walk(self):
        for name in ('gates/B/frozen.json', 'results/summary.json', '__pycache__/p.pyc'):
            self.assertFalse(f.include_source(Path(name)))
        self.assertTrue(f.include_source(Path('tools/runner.py')))

    def test_only_original_generated_iris_is_exception(self):
        self.assertEqual(f.GENERATED_ASSETS, {
            'Tools/sitl_gazebo/models/iris/iris.sdf':
            '366bf1264ce86c0c65b837a5323410c7cd695b0ffa23cdd29e6c52f6315dc00e'})
        self.assertEqual(len(f.GENERATED_SOURCES), 4)
        self.assertTrue(set(f.GENERATED_SOURCES).issubset(f.required_names(f.base())))
        modules = f.submodule_map(f.base()['submodules'])
        self.assertEqual(f.committed_assets(f.GENERATED_ASSETS, ENTRY, modules), f.GENERATED_ASSETS)

    def test_generated_iris_changed_bytes_rejected(self):
        modules = f.submodule_map(f.base()['submodules'])
        with patch.object(f.p, 'fingerprint', return_value='0'*64), self.assertRaisesRegex(ValueError, 'Iris'):
            f.committed_assets(f.GENERATED_ASSETS, ENTRY, modules)

    def test_generated_iris_cannot_be_replaced_by_tracked_blob(self):
        modules = f.submodule_map(f.base()['submodules'])
        name = next(iter(f.GENERATED_ASSETS))
        _, relative = f.owner(name, modules)
        with patch.object(f, 'tree_entries', return_value={relative: ('100644', 'blob', 'abc')}), \
                self.assertRaisesRegex(ValueError, 'Iris'):
            f.committed_assets([name], ENTRY, modules)

    def test_arbitrary_missing_submodule_file_not_exempted(self):
        modules = f.submodule_map(f.base()['submodules'])
        with self.assertRaisesRegex(ValueError, 'committed regular file'):
            f.committed_assets(['Tools/sitl_gazebo/models/iris/ri04_missing_not_generated.sdf'], ENTRY, modules)


class GitParsingTests(unittest.TestCase):
    def test_noncanonical_paths_rejected(self):
        for value in ('../a', '/a', 'a//b', 'a/./b', 'a\\b', '', 123):
            with self.subTest(value=value), self.assertRaises(ValueError):
                f.safe_name(value)
        self.assertEqual(f.safe_name('a/b'), 'a/b')

    def test_nested_submodule_owner(self):
        self.assertEqual(f.owner('a/b/c', {'a': 'x', 'a/b': 'y'}), ('a/b', 'c'))

    def test_duplicate_tree_path_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            f.tree_entries(b'100644 blob abc\ta\0'*2)

    def test_dirty_submodule_rejected(self):
        with self.assertRaises(ValueError):
            f.submodule_map(['+'+'0'*40+' x'])

    def test_wrong_submodule_count_rejected(self):
        with self.assertRaisesRegex(ValueError, '33'):
            f.submodule_map([])

    def test_malformed_batch_rejected(self):
        with patch.object(f, 'git_bytes', return_value=b'bad\n'), self.assertRaises(ValueError):
            f.batch_hashes(f.REPO, ['abc'])

    def test_batch_hashes_exact_binary_payload(self):
        with patch.object(f, 'git_bytes', return_value=b'abc blob 3\nx\ny\n'):
            self.assertEqual(f.batch_hashes(f.REPO, ['abc']), {'abc': f.sha_bytes(b'x\ny')})


class ArchiveTests(unittest.TestCase):
    def test_wrong_archive_source_format_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Full archived'):
            f.archive_check('B', 'short', '0'*64)

    def test_wrong_gate_rejected(self):
        with self.assertRaises(ValueError):
            f.capture('A')

    def test_real_ri03_archive_accepts_current_legal_z_source(self):
        old = load('_ri04_revision01_test_old_archive', HERE.parent/'ri04/freeze.py')
        real = old.git_bytes
        def historical_git(*args, **kwargs):
            self.assertNotIn('HEAD', args)
            self.assertNotEqual(args[:1], ('status',))
            return real(*args, **kwargs)
        with patch.object(old, 'git_bytes', side_effect=historical_git):
            record = old.archive_check('B', OLD_SOURCE, OLD_FROZEN_SHA)
        self.assertEqual(len(record['assets']), 1001)
        self.assertEqual(record['stage'], 'RI04-B')

    def archive_fixture(self, *, missing=False, changed=False):
        """Exercise new archive API without creating its not-yet-frozen files."""
        old = copy.deepcopy(f.base())
        execution = str((HERE/'execution.json').relative_to(f.REPO))
        authority = str(f.p.AUTHORIZATION.relative_to(f.REPO))
        assets = {f.WORLD: f.WORLD_SHA, f.MODEL: f.MODEL_SHA,
                  execution: '1'*64, authority: f.p.AUTHORIZATION_SHA}
        old['assets'] = dict(assets)
        scope = {'fixture_source_scope': True}
        saved = dict(stage='RI04-REVISION01-B', revision=f.p.REVISION, gate='B', entry_head=ENTRY,
            inherited_frozen_sha256=f.BASE_SHA, generated_assets=f.GENERATED_ASSETS,
            external_assets=old['external_assets'], control_parameters=old['control_parameters'],
            derived_iris_sha256=f.MODEL_SHA, budget=f.p.budget('B'), new_flights=0,
            post_logger_warmup_us=30000000, submodules=old['submodules'], scope=scope,
            assets=assets, inherited_assets_count=1001, inherited_rebased_to_entry={},
            execution_sha256=assets[execution], authorization_sha256=assets[authority])
        raw = json.dumps(saved).encode()
        digest = f.sha_bytes(raw)
        source = 'f'*40
        names = list(assets) + (['omitted_source.py'] if missing else [])
        actual = dict(assets)
        if changed:
            actual[execution] = '2'*64
        def git(*args, **kwargs):
            if args == ('merge-base', '--is-ancestor', ENTRY, source):
                return b''
            if args == ('show', source+':'+str((HERE/'gates/B/frozen.json').relative_to(f.REPO))):
                return raw
            raise AssertionError('Unexpected current-HEAD or working-tree lookup '+repr(args))
        with patch.object(f, 'git_bytes', side_effect=git), \
                patch.object(f.p, 'fingerprint', return_value=digest), \
                patch.object(f, 'base', return_value=old), \
                patch.object(f, 'REBOUND', set()), \
                patch.object(f, 'scope', return_value=scope) as scope_mock, \
                patch.object(f, 'verify_gitlinks') as links_mock, \
                patch.object(f, 'committed_asset_names', return_value=names), \
                patch.object(f, 'committed_assets', return_value=actual), \
                patch.object(f, 'external_check'):
            result = f.archive_check('B', source, digest)
            scope_mock.assert_called_once_with(source)
            links_mock.assert_called_once_with(source, f.submodule_map(old['submodules']))
            return result

    def test_new_archive_uses_claimed_git_source_not_current_head(self):
        self.assertEqual(self.archive_fixture()['stage'], 'RI04-REVISION01-B')

    def test_new_archive_rejects_incomplete_source_inventory(self):
        with self.assertRaisesRegex(ValueError, 'inventory is incomplete'):
            self.archive_fixture(missing=True)

    def test_new_archive_rejects_asset_blob_mismatch(self):
        with self.assertRaisesRegex(ValueError, 'Asset blob'):
            self.archive_fixture(changed=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
