#!/usr/bin/env python3
"""New validation binding, unchanged V08 runtime plus original paired gates."""
# Must be installed as protocol03/run.py with its own common.py and freeze.
import common
import importlib.util
import json
from pathlib import Path
import sys
sys.path.insert(0,str(common.TRAIN))
spec=importlib.util.spec_from_file_location('v08_training_runtime',common.TRAIN/'run.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
base_analyze=runtime.analyze
accepted={}

def analyze(run,protocol,job):
    result=base_analyze(run,protocol,job)
    if result['accepted']:
        key=(job['task'],job['seed']);group=accepted.setdefault(key,{})
        if job['mode'] in group:raise RuntimeError('Repeated validation algorithm job')
        group[job['mode']]=result
        if set(group)=={0,1}:
            pair=runtime.compare(group[0],group[1])
            runtime.save(run/'validation_pair.json',pair)
            if not pair['accepted']:raise RuntimeError('Frozen validation paired development gate failed')
    return result

runtime.analyze=analyze

if __name__=='__main__':runtime.main()
