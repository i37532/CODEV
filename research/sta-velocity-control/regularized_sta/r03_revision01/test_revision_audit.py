"""Independent revision-boundary audit; read-only source, synthetic receipts.

No simulator/build/parameter writes or seed registration. The replay check
uses temporary synthetic bytes and mocked analyzer subprocesses, not ULogs.
"""
import copy
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ENTRY = '561d70c6ad368357542a9864a675030634391290'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


p = load('revision_audit_protocol', HERE/'protocol.py')
qualification_tests = load('revision_audit_qualification_fixture', HERE/'test_protocol.py')


class RevisionAuditTest(unittest.TestCase):
    def test_qualification_and_authority_reject_numeric_type_aliases(self):
        cases = [('q','success',1),('q','clean',1),('q','new_flights',False),('q','new_flights',0.0),
                 ('q','maximum_attempts',9.0),('q','historical_attempts',True),
                 ('q','new_matrix_attempts',36.0),('q','total_maximum_attempts',37.0),
                 ('receipt','approved',1),('receipt','maximum_attempts',9.0),
                 ('receipt','historical_attempts',True),('receipt','new_matrix_attempts',36.0),
                 ('receipt','total_maximum_attempts',37.0)]
        for target,key,value in cases:
            fixture = qualification_tests.QualificationTest();fixture.setUp()
            getattr(fixture,target)[key] = value
            with self.subTest(target=target,key=key),self.assertRaises(ValueError):fixture.invoke()

    def test_nested_history_flags_cannot_impersonate_counts(self):
        for target,key,value in [('q','attempts',True),('q','accepted',False),
                                 ('receipt','attempts',1.0),('receipt','accepted',0.0)]:
            fixture = qualification_tests.QualificationTest();fixture.setUp()
            setattr(fixture,target,copy.deepcopy(getattr(fixture,target)))
            getattr(fixture,target)['historical_budget'][key] = value
            with self.subTest(target=target,key=key),self.assertRaises(ValueError):fixture.invoke()

    def test_freeze_ignores_generic_protocol_cache(self):
        poison = types.SimpleNamespace(HERE=Path('/wrong-old-stage'),REVISION='r03')
        before = list(sys.path)
        with patch.dict(sys.modules,{'protocol':poison}):
            module = load('revision_audit_poison_freeze',HERE/'freeze.py')
            self.assertEqual(module.HERE,HERE)
            self.assertEqual(Path(module._protocol.__file__).resolve(),HERE/'protocol.py')
            self.assertEqual(module.TOTAL_MAXIMUM_ATTEMPTS,37)
            self.assertIs(sys.modules['protocol'],poison)
        self.assertEqual(sys.path,before)

    def test_verifier_ignores_generic_protocol_and_freeze_cache(self):
        poison = types.SimpleNamespace(HERE=Path('/wrong-old-stage'),REVISION='r03')
        before = list(sys.path)
        with patch.dict(sys.modules,{'protocol':poison,'freeze':poison}):
            module = load('revision_audit_poison_verify',HERE/'verify.py')
            self.assertEqual(module.HERE,HERE)
            self.assertEqual(Path(module._protocol.__file__).resolve(),HERE/'protocol.py')
            self.assertEqual(Path(module.freeze.__file__).resolve(),HERE/'freeze.py')
            self.assertEqual(module.freeze.HERE,HERE)
            self.assertIs(sys.modules['protocol'],poison);self.assertIs(sys.modules['freeze'],poison)
        self.assertEqual(sys.path,before)

    def test_actual_prior_trees_and_retained_source_match_git_entry(self):
        module = load('revision_audit_actual_freeze',HERE/'freeze.py')
        allowed = module.check_scope()
        self.assertTrue(set(allowed).issubset(module.ALLOWED))
        trees = ['research/sta-velocity-control/regularized_sta/'+name for name in ('r01','r02','r03')]
        self.assertEqual(subprocess.check_output(['git','diff','--name-only',ENTRY,'--',*trees],cwd=REPO,text=True),'')
        self.assertEqual(subprocess.check_output(['git','ls-files','--others','--exclude-standard','--',*trees],cwd=REPO,text=True),'')
        historical = p.retained_failure();ledger = p.read(historical['ledger_path'])
        self.assertEqual(historical['source_head'],ledger['source_head'])
        self.assertEqual(historical['source_head'],'f0d07dbbfb1695b59a9e4e1653ac447e05c1afd9')
        self.assertEqual(subprocess.check_output(['git','cat-file','-t',historical['source_head']],cwd=REPO,text=True).strip(),'commit')
        self.assertEqual(p.design()['revision_entry_head'],ENTRY)

    def test_prior_tracked_or_untracked_source_change_rejected(self):
        module = load('revision_audit_old_scope',HERE/'freeze.py')
        for operation in ('diff','ls-files'):
            def git(*args):
                if args[0] == operation and any('/regularized_sta/r03' in str(value) for value in args):
                    return 'research/sta-velocity-control/regularized_sta/r03/analyzer.py'
                return ''
            with self.subTest(operation=operation),patch.object(module,'git',side_effect=git):
                with self.assertRaisesRegex(ValueError,'Immutable prior'):module.check_scope()

    def test_unapproved_production_changes_or_new_files_rejected(self):
        module = load('revision_audit_production_scope',HERE/'freeze.py')
        for operation in ('diff','ls-files'):
            def git(*args):
                if args[0] == operation and not any('/regularized_sta/' in str(value) for value in args):
                    return 'src/modules/land_detector/MulticopterLandDetector.cpp'
                return ''
            with self.subTest(operation=operation),patch.object(module,'git',side_effect=git):
                with self.assertRaisesRegex(ValueError,'Unexpected R03 production'):module.check_scope()

    def test_actual_gate_is_one_precise_authorized_prefix(self):
        module = load('revision_audit_gate_verify',HERE/'verify.py')
        source = (REPO/'src/modules/mc_pos_control/PositionControl/PositionControl.cpp').read_text()
        expression = re.search(r'const bool regularized_gate_admitted = ([^;]+);',source)[1]
        masks = set(map(int,re.findall(r'axes == (\d+)',expression)))
        selected = [gate for index,gate in enumerate(p.GATES)
                    if masks == {p.GATES[g]['axes'] for g in list(p.GATES)[:index+1]}]
        self.assertEqual(len(selected),1)
        result = module.gate_check(selected[0]);self.assertEqual(set(result['admitted_masks']),masks)
        self.assertEqual(result['divisor'],1);self.assertTrue(result['sitl_only'])
        for gate in set(p.GATES)-set(selected):
            with self.subTest(gate=gate),self.assertRaises(ValueError):module.gate_check(gate)

    def test_all_scientific_protocol_values_and_per_job_parameters_unchanged(self):
        old = load('revision_audit_old_protocol',HERE.parent/'r03/protocol.py')
        ignored = {'stage','config_dir','execution_path','qualification_path','revision',
                   'historical_attempts','historical_budget','new_matrix_attempts',
                   'total_maximum_attempts','seeds','jobs','authorization'}
        for gate in p.GATES:
            previous,current = old.load_protocol(gate),p.load_protocol(gate)
            for a,b in zip(previous['jobs'],current['jobs']):
                self.assertEqual({k:v for k,v in a.items() if k!='seed'},
                                 {k:v for k,v in b.items() if k not in ('revision','seed')})
            for value in (previous,current):
                for key in ignored:value.pop(key,None)
                value['artifacts'].pop('new_run_root')
                value['excitation'].pop('definition_file')
                value['gate_config'].pop('seeds')
                value['pair_gate'].pop('maximum_candidate_flights_before_reauthorization')
            with self.subTest(gate=gate):
                self.assertEqual(json.dumps(previous,sort_keys=True,allow_nan=False),
                                 json.dumps(current,sort_keys=True,allow_nan=False))

    def test_unregistered_historical_batch_or_journal_is_not_ignored(self):
        original = Path.glob
        for pattern in ('*/batch*/ledger.json','*/batch*/journal.jsonl'):
            def glob(path,requested):
                result = list(original(path,requested))
                if path == p.EXTERNAL/'R03' and requested == pattern:
                    result.append(path/'B/batch01'/Path(requested).name)
                return iter(result)
            with self.subTest(pattern=pattern),patch.object(Path,'glob',glob):
                with self.assertRaisesRegex(ValueError,'Historical R03'):p.retained_failure()

    def test_previous_gate_replay_does_not_depend_on_current_git_head(self):
        module = load('revision_audit_replay_fixture',HERE/'test_replay.py')
        fixture = module.EvidenceTest();fixture.setUp()
        try:
            with patch.object(module.r.protocol,'git',side_effect=AssertionError('No current HEAD dependency')):
                fixture.complete()
                with patch.object(module.r.protocol,'load_file',return_value=module.r):
                    checked = module.r.protocol.require_previous_gates('B')
                self.assertEqual(len(checked),1);self.assertEqual(checked[0]['gate'],'A')
        finally:
            fixture.doCleanups()


if __name__ == '__main__':
    unittest.main()
