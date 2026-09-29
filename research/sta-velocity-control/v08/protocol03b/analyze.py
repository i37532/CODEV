"""New protocol provenance with the same strict V08 per-flight analysis."""
import common
import task  # only this new protocol uses bounded exact downstream evidence
import importlib.util
import runpy
import sys
sys.path.insert(0,str(common.TRAIN))
spec=importlib.util.spec_from_file_location('v08_perflight_analysis',common.TRAIN/'analyze.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
analyze=base.analyze
compare=base.compare
CONFIG=common.CONFIG

if __name__=='__main__':runpy.run_path(str(common.TRAIN/'analyze.py'),run_name='__main__')
