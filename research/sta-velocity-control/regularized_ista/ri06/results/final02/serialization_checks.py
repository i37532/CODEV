"""Explicit result-layer tests; outside archived qualification suite inventory."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import unittest

s = importlib.util.spec_from_file_location('_ri06_result_export', Path(__file__).with_name('export.py'))
e = importlib.util.module_from_spec(s)
s.loader.exec_module(e)


def fixture(path, value):
    root = {'rows': [{}]}
    node = root['rows'][0]
    for key in path[:-1]:
        node[key] = {}
        node = node[key]
    node[path[-1]] = value
    return root


class Serialization(unittest.TestCase):
    def test_finite_unchanged(self):
        x = dict(J=.003,values=[0,1,-2.5],accepted=True)
        self.assertEqual(e.encode(x),x)
    def test_twelve_exact_paths(self):
        self.assertEqual(len(e.ALLOWED),12)
        for path in e.ALLOWED:
            with self.subTest(path=path):
                raw=fixture(path,math.inf);self.assertEqual(e.decode(e.encode(raw)),raw)
    def test_unknown_path_rejected(self):
        with self.assertRaises(ValueError):e.encode(fixture(('height_task','unknown','vxy_max'),math.inf))
    def test_science_metric_rejected(self):
        with self.assertRaises(ValueError):e.encode({'rows':[{'J':math.inf}]})
    def test_parameter_rejected(self):
        with self.assertRaises(ValueError):e.encode({'formal':{'parameters':{'vxy_max':math.inf}}})
    def test_nan_rejected_even_at_allowed_path(self):
        with self.assertRaises(ValueError):e.encode(fixture(next(iter(e.ALLOWED)),math.nan))
    def test_negative_infinity_rejected(self):
        with self.assertRaises(ValueError):e.encode(fixture(next(iter(e.ALLOWED)),-math.inf))
    def test_root_infinity_rejected(self):
        with self.assertRaises(ValueError):e.encode(math.inf)
    def test_existing_marker_rejected(self):
        with self.assertRaises(ValueError):e.encode({e.MARKER:'+Infinity'})
    def test_decode_unknown_path_rejected(self):
        with self.assertRaises(ValueError):e.decode({'J':{e.MARKER:'+Infinity'}})
    def test_bad_marker_rejected(self):
        with self.assertRaises(ValueError):e.decode(fixture(next(iter(e.ALLOWED)),{e.MARKER:'NaN'}))
    def test_no_input_mutation(self):
        raw=fixture(next(iter(e.ALLOWED)),math.inf);before=copy.deepcopy(raw);e.encode(raw)
        self.assertEqual(raw,before)
    def test_strict_json_roundtrip(self):
        raw=fixture(next(iter(e.ALLOWED)),math.inf)
        result=json.loads(json.dumps(e.encode(raw),allow_nan=False))
        self.assertEqual(e.decode(result),raw)
    def test_change_inventory(self):
        path=next(iter(e.ALLOWED));changes=[];e.encode(fixture(path,math.inf),changes=changes)
        self.assertEqual(changes,[['rows',0,*path]])


if __name__=='__main__':unittest.main()
