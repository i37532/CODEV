"""Freeze pilot code plus the EXACT external library/dependencies used in flight."""
import common
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import importlib

def main():
    spec=importlib.util.spec_from_file_location('v08_pilot_base_capture',common.TRAIN/'capture.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.capture()
    d=common.design();library=Path(d['force_library'])
    if common.fingerprint(library)!=d['force_library_sha256']:raise RuntimeError('Wrong force library')
    built=json.loads(Path(d['force_build_evidence']).read_text())
    if not built['success'] or built['new_flights']!=0:raise RuntimeError('Missing offline force build')
    for name in ('ForcePlugin.cpp','ForceWave.hpp'):
        source=common.CONFIG/name
        if built['sha256'].get(str(source))!=common.fingerprint(source):raise RuntimeError('Library was built from another source '+name)
    ground=json.loads(Path(d['ground_probe_evidence']).read_text())
    if not ground['success'] or ground['flights']!=0 or ground['px4_started'] or len(ground['probes'])!=2:
        raise RuntimeError('Missing zero-flight actual model probe')
    for item in ground['probes']:
        if item['controlled_stop_exit_code'] not in (0,-2):raise RuntimeError('Unqualified component teardown')
    output=subprocess.check_output(['ldd',str(library)],text=True)
    paths={library,Path(d['force_build_evidence']),Path(d['ground_probe_evidence'])}
    for line in output.splitlines():
        if 'not found' in line:raise RuntimeError('Missing force dependency')
        for value in re.findall(r'(?:=>\s+)?(/[^\s]+)',line):
            path=Path(value)
            if path.is_file():paths.add(path)
    frozen=json.loads((common.CONFIG/'frozen.json').read_text())
    frozen['assets'].update({str(p):common.fingerprint(p) for p in sorted(paths)})
    frozen['v08_force_library']=dict(path=str(library),sha256=common.fingerprint(library),ldd=output,
        dependencies=len(paths),build_evidence=d['force_build_evidence'],ground_probe_evidence=d['ground_probe_evidence'])
    python_modules={}
    for name in ('numpy','numpy.core._multiarray_umath','pyulog','pyulog.core','pymavlink','pymavlink.mavutil'):
        package=importlib.import_module(name);path=Path(package.__file__).resolve()
        python_modules[name]=dict(path=str(path),version=getattr(package,'__version__',None),sha256=common.fingerprint(path))
        frozen['assets'][str(path)]=common.fingerprint(path)
    frozen['v08_python_modules']=python_modules
    (common.CONFIG/'frozen.json').write_text(json.dumps(frozen,indent=2)+'\n')
    print(json.dumps(dict(assets=len(frozen['assets']),force_dependencies=len(paths))))

if __name__=='__main__':main()
