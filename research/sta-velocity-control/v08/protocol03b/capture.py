"""New snapshot; never rewrites the completed training snapshot."""
import common
import importlib.util
spec=importlib.util.spec_from_file_location('v08_validation_capture',common.TRAIN/'capture.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if __name__=='__main__':module.capture()
