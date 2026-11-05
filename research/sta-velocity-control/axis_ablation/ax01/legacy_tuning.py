"""Run applicable V08 functional tests, with ONE explicit provenance exclusion.

The excluded assertion requires ALL production code byte-identical to V07,
incompatible with AX01. It failed in offline01 and remains unchanged on disk.
This is not verification of the frozen V08 source, nor a changed flight gate.
"""
from pathlib import Path
import sys
import unittest

source = Path(__file__).resolve().parents[2]/'v08/protocol02'
sys.path.insert(0, str(source))
import test_tuning

name = 'test_original_production_and_launcher_unchanged'
all_tests = unittest.defaultTestLoader.loadTestsFromTestCase(test_tuning.TuningTest)
excluded = [t for t in all_tests if t._testMethodName == name]
assert len(excluded) == 1
print('NOT APPLICABLE (not a pass): '+excluded[0].id(), flush=True)
suite = unittest.TestSuite(t for t in all_tests if t._testMethodName != name)
assert suite.countTestCases() == all_tests.countTestCases()-1 and suite.countTestCases() > 0
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
