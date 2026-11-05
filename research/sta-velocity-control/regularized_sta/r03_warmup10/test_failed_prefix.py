"""Read-only regression of the exact failed prearm snapshot; no flight."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

r=load('warmup10_readiness',HERE/'readiness.py')
old=load('warmup10_original_prearm',HERE.parent/'r03_prearm04/integration.py')
reference=load('warmup10_unchanged_reference',HERE.parents[1]/'scripts/v04_prearm17.py')
ROOT=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision09/D/batch01/run028')


class ActualPrefix(unittest.TestCase):
    def test_original_exact_prefix_reproduces_rejection(self):
        raw=(ROOT/'log001.ulg').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'7f49dd73f5eb091306872d90946e43176a5c867088a0a0a33eb1ebf3cbace885')
        receipt=[json.loads(x) for x in (ROOT/old.RECEIPT).read_text().splitlines()]
        self.assertEqual(receipt[0]['warmup_reads'],1)
        self.assertEqual(receipt[1]['raw_reader']['snapshot_end_bytes'],101918)
        decoder=old.incremental.Decoder();decoder.feed(raw[:101918])
        view=old.incremental.load('warmup10_position',old.incremental.LEGACY/'position_log.py').PositionLogView
        log=view(decoder.snapshot())
        with self.assertRaisesRegex(ValueError,'Missing attitude boundary predecessor'):reference.reference_row(log)
        # The new readiness condition refuses this known premature snapshot;
        # it does not turn the missing predecessor into a passing safety check.
        readiness=r.Readiness()
        self.assertFalse(readiness.observe(38524000,True)['ready'])
        with self.assertRaisesRegex(ValueError,'Missing attitude boundary predecessor'):reference.reference_row(log)
        result=json.loads((ROOT/'result.json').read_text())
        self.assertFalse(result['success'])
        self.assertEqual([x['name'] for x in result['events']],['ready'])
        self.assertEqual(hashlib.sha256((ROOT/'log001.ulg').read_bytes()).hexdigest(),hashlib.sha256(raw).hexdigest())


if __name__=='__main__':unittest.main(verbosity=2)
