"""Publish compact PV01 evidence; preserve all earlier attempts outside git."""
import argparse
import xml.etree.ElementTree as ET
from common import *

def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--output',type=Path)
    p.add_argument('--repo-output',type=Path,default=HERE/'results')
    args=p.parse_args()
    if not args.execute:print('dry-run: export final02/build03 evidence and all attempt fingerprints');return
    out=fresh(args.output);dest=args.repo_output.resolve()
    assert dest.parent==HERE and not dest.exists()
    final=json.loads((ROOT/'final02/evidence.json').read_text());build=json.loads((ROOT/'build03/evidence.json').read_text())
    model=json.loads((ROOT/'final02/model/summary.json').read_text());entry=json.loads((ROOT/'entry01/entry.json').read_text())
    assert final['success'] and build['success'] and model['success']
    for path,item in entry['preserved_files'].items():assert sha(Path(path))==item['sha256']
    codec=load('pv01_bson_reader',REPO/'research/sta-velocity-control/scripts/capture_v00.py')
    saved=REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    defaults={n.attrib['name']:float(n.attrib['default']) for n in ET.parse(REPO/'build/px4_sitl_default/parameters.xml').iter('parameter')}
    overrides=codec.persisted_bson(saved.read_bytes());values={**defaults,**overrides}
    required=dict(MC_RTC_MODE=0,MC_STA_AXES=0,MC_RTC_DIV=1,MC_RATT_TEST=0,MC_STA_TKO_MGT=0,
                  MPC_VC_MODE=0,MPC_VC_AXES=0,MPC_VC_DIV=1)
    assert {k:values[k] for k in required}==required
    commands=[]
    for path in sorted(ROOT.rglob('*.command.json')):
        receipt=json.loads(path.read_text())
        # Reviewer archival receipts have their own schema; still indexed below.
        if 'log' in receipt and 'sha256' in receipt:
            assert sha(Path(receipt['log']))==receipt['sha256']
            commands.append(dict(receipt,receipt_file=str(path)))
    summary=dict(passed=True,flight_qualified=False,stage='PV01',entry_head=BASE,
        cpp_tests=790,cpp_selector_checks=6,cpp_total_checks=796,python_tests=67,
        normal=model['normal'],numeric=model['numeric'],terminals=model['terminals'],
        trajectories=52,trajectory_updates=sum(x['updates'] for x in model['rows']),
        complete=52,numerical_rejections=0,expected_infeasible_tracking_cases=4,
        rows=model['rows'],cadence=model['cadence'],new_flights=0,new_flight_seeds=0,
        matlab_executed=False,finite_diagnostic_prng=1012026,
        repeat_policy='model02 and final02/model repeat the SAME finite matrix, not added independent samples',
        numerical_grid_note='121 valid candidates; one true range rejection. Not 122 convergence tests.',
        scientific_note='lag/noise degradation remains; no flight, fair-optimization, or superiority claim')
    failures=[
        dict(path='model01/summary.json',exit_code=1,reason='Decimal default precision abs() misclassified FLT_MAX endpoint; independent reference fixed, core unchanged'),
        dict(path='build01',exit_code=1,reason='commands key duplicated in Python dict initialization before receipt; original tool output only, empty directory retained'),
        dict(path='build02/evidence.json',exit_code=1,nested_make_exit_code=2,reason='PX4 -Wfloat-equal rejected intentional exact comparison in new test; only new test flags corrected'),
        dict(path='final01/evidence.json',exit_code=1,reason='old probe environment PROPER_VELOCITY_LIBRARY omitted: 18 run, 10 errors; fixed frozen-library wiring'),
        dict(path='final02/pv01-core-IkdK0f/BUILD_AND_RESULTS_CN.md',reason='standalone initial no-RTTI link failure; initial37 tests 3 reference/fixture failures; final39 and UBSan39 pass; repeats not summed'),
        dict(path='final02/pv01-math-review-LWKhGZ/unsupported_brief_help.log',exit_code=0,tests=0,reason='unsupported old gtest help option; NOT counted as tests')]
    evidence=dict(success=True,final=final,build=build,commands=commands,failures_preserved=failures,
        offline_parameters=dict(required=required,persisted_overrides=overrides,runtime_verified=False,
            note='Defaults plus BSON saved overrides only; no PX4 process launched'),
        current_sources=fingerprint([p for p in HERE.iterdir() if p.is_file()]+[CONTROL/n for n in
            ('CMakeLists.txt','ProperIstaVelocityControl.cpp','ProperIstaVelocityControl.hpp','ProperIstaVelocityControlTest.cpp')]),
        no_scope_extension=True)
    archive=fingerprint(p for p in ROOT.rglob('*') if p.is_file() and out not in p.parents)
    evidence['archive']=dict(root=str(ROOT),files=len(archive),bytes=sum(x['bytes'] for x in archive.values()))
    dest.mkdir(exist_ok=False)
    for name,data in (('summary.json',summary),('evidence.json',evidence),('archive_index.json',archive)):
        save(out/name,data);save(dest/name,data);assert sha(out/name)==sha(dest/name)
    save(out/'publication.json',dict(success=True,files=fingerprint(dest.iterdir())))
    print(json.dumps(dict(success=True,archive_files=len(archive),bytes=evidence['archive']['bytes'],
        cpp=796,python=67,objects=52,updates=summary['trajectory_updates'],new_flights=0)))

if __name__=='__main__':main()
