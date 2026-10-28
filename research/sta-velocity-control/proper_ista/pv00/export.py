"""Publish compact offline evidence, preserving every external attempt."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from common import HERE, REPO, ROOT, fingerprint, fresh, module, save, sha
from collect import check_entry


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True,help='new external publication directory')
    p.add_argument('--repo-output',type=Path,required=True,help='new compact results directory')
    args=p.parse_args()
    out=fresh(args.output)
    dest=args.repo_output.resolve()
    if HERE not in dest.parents or dest.exists():
        raise ValueError('new results under pv00 required')
    evidence=json.loads((ROOT/'closeout02/evidence.json').read_text())
    assert evidence['success'] and not evidence['flight_qualified']
    check_entry()
    entry2=json.loads((ROOT/'audit02/entry.json').read_text())
    for name,record in entry2['input_files'].items():
        assert sha(name)==record['sha256'],name

    codec=module('pv00_parameter_reader',REPO/'research/sta-velocity-control/scripts/capture_v00.py')
    parameter_file=REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    defaults={x.attrib['name']:float(x.attrib['default'])
              for x in ET.parse(REPO/'build/px4_sitl_default/parameters.xml').iter('parameter')}
    overrides=codec.persisted_bson(parameter_file.read_bytes())
    values={**defaults,**overrides}
    required=dict(MC_RTC_MODE=0,MC_STA_AXES=0,MC_RTC_DIV=1,MC_RATT_TEST=0,
                  MC_STA_TKO_MGT=0,MPC_VC_DIV=1,MPC_VC_MODE=0,MPC_VC_AXES=0)
    assert {k:values[k] for k in required}==required
    evidence['offline_parameters']=dict(required=required,persisted_overrides=overrides,
        runtime_verified=False,note='Defaults plus saved overrides; no new PX4 process was launched.')

    original=json.loads((ROOT/'original01/summary.json').read_text())
    diag=json.loads((ROOT/'diagnostic01/summary.json').read_text())
    numeric=json.loads((ROOT/'numerical01/summary.json').read_text())
    commands=list(original['commands'])
    for path in sorted(ROOT.rglob('*.command.json')):
        commands.append(dict(json.loads(path.read_text()),receipt=str(path)))
    assert all(row['exit_code']==0 and sha(row['log'])==row['sha256'] for row in commands)
    for name,count in (('audit02/pv00_tests.log',22),('audit02/analysis_tests.log',6),
                       ('original01/python_tests.log',18)):
        log=(ROOT/name).read_text()
        assert re.search(rf'Ran {count} tests? in ',log) and '\nOK\n' in log
    cpp_log=(ROOT/'original01/existing_cpp.log').read_text()
    counts=list(map(int,re.findall(r'\[==========\] (\d+) tests? from .* ran\.',cpp_log)))
    binaries=[Path(s) for s in re.findall(r'Test command: (\S+)',cpp_log)]
    assert len(counts)==len(binaries)==24 and sum(counts)==473
    assert 'Tests run: 6, passed: 6, failed: 0' in (ROOT/'closeout02/selector_tests.log').read_text()
    evidence['test_inventory']=dict(cpp_existing=473,cpp_existing_targets=24,cpp_bridge=72,
        cpp_selector=6,cpp_total=551,python_probe=18,python_analysis=6,python_pv00=22,
        python_total=46,ctest_binaries_not_rebuilt=True,matlab_rerun=False,firmware_rebuilt=False,
        unit_test_binaries=fingerprint(binaries))
    evidence['commands']=commands
    evidence['entry']=entry2
    evidence['source_commits']={
        'ProperIstaRateControl.cpp':'3afe4fb98bf48473917da7a6c55e96ae40e82aca',
        'i01/audit.py':'547d324f6528a2fc05651574e5dd3ec5cb44e7de',
        'historical_probe':'bbc5396c272666bd20f526a54113e9698e87c16b'}
    evidence['current_research_sources']=fingerprint(p for p in HERE.iterdir() if p.is_file())
    evidence['superseded_audit']=dict(path=str(ROOT/'closeout01/evidence.json'),
        reason='Format-length audit incorrectly stripped padding; 1454/997 replaced by 1475/1018. No scientific result changed.')
    summary=dict(offline_audit_passed=True,flight_qualified=False,
        trajectories=213,complete=201,numerical_stops=12,new_flights=0,new_seeds=0,
        original_rows=original['rows'],original_theory_checks=original['theory_checks'],
        diagnostic_rows=diag['rows'],linear_mechanism=diag['linear_mechanism'],
        exact_stops=numeric['stops'],numeric_grid_cases=122,
        scientific_note='Includes 12 infeasible clipping counterexamples; completion is not convergence or flight qualification.')
    paths=[p for p in ROOT.rglob('*') if p.is_file() and out not in p.parents]
    archive=fingerprint(paths)
    evidence['archive']=dict(files=len(archive),bytes=sum(x['bytes'] for x in archive.values()),
        root=str(ROOT),publication_directory_excluded=True)
    dest.mkdir(parents=True,exist_ok=False)
    for name,data in (('evidence.json',evidence),('summary.json',summary),('archive_index.json',archive)):
        save(out/name,data)
        save(dest/name,data)
        assert sha(out/name)==sha(dest/name)
    save(out/'publication.json',dict(success=True,files=fingerprint(dest.iterdir())))
    print(json.dumps(dict(success=True,archive_files=len(archive),cpp=551,python=46,
                          source_output=str(out),repository_output=str(dest))))


if __name__=='__main__': main()
