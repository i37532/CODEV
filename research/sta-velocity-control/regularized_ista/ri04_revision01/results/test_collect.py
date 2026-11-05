"""Result-only serialization safeguards; not flight/numerical acceptance tests."""
import math
import copy
from pathlib import Path
import tempfile
import unittest

import collect


class CollectionTests(unittest.TestCase):
    def test_type_strict_comparison(self):
        self.assertFalse(collect.exact({'x': 1}, {'x': 1.0}))
        self.assertFalse(collect.exact([1], [True]))
        self.assertTrue(collect.exact([math.inf, 0.1], [math.inf, 0.1]))

    def test_only_known_unlimited_diagnostics_allowed(self):
        value = {'height_task': {'heading': {'latest_position': {'vxy_max': math.inf}}}}
        collect.check_nonfinite(value, diagnostic=True)
        with self.assertRaises(AssertionError):
            collect.check_nonfinite(value)
        for value in ({'rmse': math.inf}, {'height_task': {'unknown': math.inf}}, {'rmse': math.nan}):
            with self.assertRaises(AssertionError):
                collect.check_nonfinite(value, diagnostic=True)

    def test_finite_values_unchanged(self):
        value = {'x': [0.0, -1.25, 7, True, None]}
        self.assertEqual(collect.json_view(value), value)

    def test_nonfinite_are_distinct_explicit_tags(self):
        for value, name in ((math.inf, 'Infinity'), (-math.inf, '-Infinity'), (math.nan, 'NaN')):
            with self.subTest(name=name):
                self.assertEqual(collect.json_view(value), {'nonfinite_float': name})

    def test_original_is_not_mutated(self):
        value = {'limits': [math.inf, 3.5]}
        self.assertEqual(collect.json_view(value)['limits'][1], 3.5)
        self.assertTrue(math.isinf(value['limits'][0]))

    def test_saved_summary_is_strict_json_and_repeatable(self):
        with tempfile.TemporaryDirectory(prefix='ri04-revision01-result-test-') as directory:
            path = Path(directory) / 'summary.json'
            value = {'limit': math.inf, 'rmse': 0.03}
            collect.save(path, value)
            raw = path.read_bytes()
            collect.save(path, value)
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(collect.read(path), {'limit': {'nonfinite_float': 'Infinity'}, 'rmse': 0.03})

    def test_changed_result_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(prefix='ri04-revision01-result-test-') as directory:
            path = Path(directory) / 'summary.json'
            collect.save(path, {'rmse': 0.1})
            with self.assertRaises(AssertionError):
                collect.save(path, {'rmse': 0.0})
            self.assertEqual(collect.read(path), {'rmse': 0.1})


class LedgerTests(unittest.TestCase):
    def ledger(self):
        modes = [0,3,4,0,4,3,0,3,4]
        return dict(stage='RI04-REVISION01-B',revision='ri04_revision01',
            source_head='a1c2046d94a6bbf061720385a5ad36110b1d0dc2',
            planned=9,total_budget=12,new_planned=9,prior_attempts=3,
            attempts=[dict(status='accepted',job=dict(id=f'run{i:03d}',gate='B',task='Z',
                mode=m,axes=0 if m==0 else 4)) for i,m in enumerate(modes,1)])

    def test_current_budget_identity_passes(self):
        collect.validate_current_ledger(self.ledger())

    def test_old_budget_source_revision_rejected(self):
        for key,value in (('total_budget',9),('prior_attempts',0),('source_head','0'*40),('revision','ri04')):
            row=self.ledger(); row[key]=value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                collect.validate_current_ledger(row)

    def test_incomplete_failed_and_wrong_axes_rejected(self):
        for kind in ('missing','failed','axes'):
            row=self.ledger()
            if kind=='missing': row['attempts'].pop()
            elif kind=='failed': row['attempts'][2]['status']='failed'
            else: row['attempts'][2]['job']['axes']=7
            with self.subTest(kind=kind), self.assertRaises(AssertionError):
                collect.validate_current_ledger(row)

    def test_reordered_job_cannot_be_relabelled(self):
        row=self.ledger(); row['attempts'].reverse()
        with self.assertRaises(AssertionError): collect.validate_current_ledger(row)


class ArchiveSchemaTests(unittest.TestCase):
    def test_absolute_list_schema(self):
        import verify
        root=Path('/tmp/ri04-archive-schema')
        row=dict(path=str(root/'a'),bytes=1,sha256='a'*64)
        self.assertEqual(verify.archive_rows(dict(scope=str(root),files=[row],symlinks={}),root),([row],{}))

    def test_relative_dictionary_schema(self):
        import verify
        root=Path('/tmp/ri04-archive-schema')
        item=dict(bytes=1,sha256='a'*64)
        self.assertEqual(verify.archive_rows(dict(root=str(root),files={'a':item},links={}),root),
            ([dict(path=str(root/'a'),**item)],{}))

    def test_wrong_root_and_escape_rejected(self):
        import verify
        root=Path('/tmp/ri04-archive-schema')
        for row in (dict(root='/tmp/foreign',files={},links={}),
                    dict(root=str(root),files={'../escape':{}},links={}),
                    dict(scope=str(root),files=[dict(path='/tmp/foreign')],symlinks={})):
            with self.assertRaises(AssertionError): verify.archive_rows(row,root)

    def test_original_index_not_mutated(self):
        import verify
        root=Path('/tmp/ri04-archive-schema')
        row=dict(root=str(root),files={'a':dict(bytes=1,sha256='a'*64)},links={})
        before=copy.deepcopy(row)
        verify.archive_rows(row,root)
        self.assertEqual(row,before)


if __name__ == '__main__':
    unittest.main()
