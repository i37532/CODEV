#!/usr/bin/env python3
"""Negative and non-double-counting tests for R01 evidence bookkeeping only."""
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import verify


class VerificationEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def xml(self, name='one', cases=('A',), **attrs):
        root = ET.Element('testsuites', dict(tests=str(len(cases)), failures='0', errors='0', disabled='0'))
        root.attrib.update(attrs)
        suite = ET.SubElement(root, 'testsuite', name='Fixture')
        for case in cases:
            ET.SubElement(suite, 'testcase', classname='Fixture', name=case, status='run', result='completed')
        path = self.root / (name + '.xml')
        ET.ElementTree(root).write(path)
        return path

    def python_evidence(self, folder, names):
        folder.mkdir(parents=True, exist_ok=True)
        commands = []
        for name, count in names:
            commands.append(dict(name=name, argv=['python3', name + '.py'], exit_code=0))
            (folder / (name + '.log')).write_text('test_example ... ok\n\nRan %d tests in 0.001s\n\nOK\n' % count)
        (folder / 'evidence.json').write_text(json.dumps(dict(commands=commands, python_tests=99999)))

    def test_nonzero_completed_xml(self):
        result = verify.xml_inventory([self.xml(cases=('A', 'B'))])
        self.assertEqual(result['unique_tests'], 2)
        self.assertEqual(result['executed_xml_cases'], 2)

    def test_repeat_xml_counted_once_not_nested_sum(self):
        paths = [self.xml('first'), self.xml('repeat')]
        result = verify.xml_inventory(paths)
        self.assertEqual(result['unique_tests'], 1)
        self.assertEqual(result['executed_xml_cases'], 2)
        self.assertEqual(len(result['repeated_identities']), 1)

    def test_zero_and_mismatched_count_rejected(self):
        for path in (self.xml('empty', ()), self.xml('wrong_count', tests='3')):
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                verify.xml_inventory([path])

    def test_failure_error_disabled_rejected(self):
        for attr in ('failures', 'errors', 'disabled'):
            with self.subTest(attr=attr), self.assertRaises(RuntimeError):
                verify.xml_inventory([self.xml(attr, **{attr: '1'})])

    def test_skipped_and_notrun_rejected(self):
        for kind in ('skipped', 'notrun'):
            path = self.xml(kind)
            tree = ET.parse(path)
            case = next(tree.getroot().iter('testcase'))
            if kind == 'skipped':
                ET.SubElement(case, 'skipped')
            else:
                case.set('status', 'notrun')
            tree.write(path)
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                verify.xml_inventory([path])

    def test_duplicate_within_xml_rejected(self):
        with self.assertRaises(RuntimeError):
            verify.xml_inventory([self.xml(cases=('A', 'A'))])

    def test_python_leaf_counts_ignore_nested_summary_totals(self):
        self.python_evidence(self.root, [('outer', 3)])
        self.python_evidence(self.root / 'inner', [('inner', 4)])
        self.assertEqual(verify.python_leaf_counts(self.root)['tests'], 7)

    def test_wrapper_escaped_summary_not_counted(self):
        self.python_evidence(self.root, [('real', 2), ('wrapper', 100)])
        (self.root / 'wrapper.log').write_text(json.dumps(dict(stdout='Ran 100 tests in 0.1s\nOK\n')))
        self.assertEqual(verify.python_leaf_counts(self.root)['tests'], 2)

    def test_python_zero_ambiguous_failed_and_skipped_rejected(self):
        for kind in ('zero', 'two', 'failed', 'skipped'):
            with self.subTest(kind=kind):
                folder = self.root / kind
                self.python_evidence(folder, [('test', 0 if kind == 'zero' else 1)])
                path = folder / 'test.log'
                if kind == 'two':
                    path.write_text(path.read_text() * 2)
                elif kind == 'failed':
                    path.write_text(path.read_text().replace('OK', 'FAILED (errors=1)'))
                elif kind == 'skipped':
                    path.write_text(path.read_text().replace('OK', 'OK (skipped=1)'))
                with self.assertRaises(RuntimeError):
                    verify.python_leaf_counts(folder)

    def test_allowed_isolated_kernel_only(self):
        result = verify.production_scope([verify.PREFIX + 'CMakeLists.txt'], verify.CORE_FILES)
        self.assertEqual(len(result['actual_changed']), 4)

    def test_unrelated_production_changes_rejected(self):
        for path in ('src/modules/mc_pos_control/PositionControl/PositionControl.cpp',
                     'src/modules/mc_pos_control/mc_pos_control_params.c', 'sitl/worlds/empty_grey.world'):
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                verify.production_scope([path], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
