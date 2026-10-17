#!/usr/bin/env python3
"""R03 offline regression and optional clean-source gate qualification. Never flies."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
import traceback

_path = Path(__file__).resolve().parent/'protocol.py'
_spec = importlib.util.spec_from_file_location('_r03_revision03_verify_protocol', _path)
_protocol = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_protocol)
for _name in ('HERE','REPO','EXTERNAL','BASE','GATES','AUTHORIZATION','fingerprint','read','git',
              'load_file','load_protocol','require_previous_gates','validate_manifest','REVISION','DATA_STAGE',
              'TOTAL_MAXIMUM_ATTEMPTS','HISTORICAL_ATTEMPTS','NEW_MATRIX_ATTEMPTS','retained_failure','seed_migration'):
    globals()[_name] = getattr(_protocol, _name)
freeze=load_file('_r03_revision03_verify_freeze', HERE/'freeze.py')
historical_probe=load_file('_r03_revision03_historical_probe', HERE.parent/'r03/historical_probe.py')

R02=load_file('r03_prior_verifier',HERE.parent/'r02/verification/verify.py')
HELPER=R02.helper
TARGETS=R02.TESTS


def gate_check(gate):
    source=(REPO/'src/modules/mc_pos_control/PositionControl/PositionControl.cpp').read_text()
    masks=[GATES[g]['axes'] for g in list(GATES)[:list(GATES).index(gate)+1]]
    if freeze.admitted_gate(source)!=gate:
        raise ValueError('Production gate differs from requested qualified masks')
    if '(_regularized_test_admission || regularized_gate_admitted)' not in source and '(regularized_gate_admitted || _regularized_test_admission)' not in source:
        raise ValueError('Unknown admission expression')
    block=source[source.index('void PositionControl::configureVelocityControl'):source.index('void PositionControl::configureVelocityControl')+1900]
    if not re.search(r'#if defined\(CONFIG_ARCH_BOARD_PX4_SITL\).*regularized_gate_admitted.*#endif',block,re.S):
        raise ValueError('Gate is not restricted to the SITL compilation branch')
    consumers=subprocess.check_output(['rg','-l','_regularized_test_admission','src'],cwd=REPO,text=True).splitlines()
    expected={R02.POS+'PositionControl.cpp',R02.POS+'PositionControl.hpp',
              R02.POS+'RegularizedVelocityIntegrationTest.cpp',R02.POS+'RegularizedVelocityParamTest.cpp',
              R02.MODULE+'RegularizedVelocityModuleTest.cpp'}
    if set(consumers)!=expected:
        raise ValueError('Unexpected private admission consumer')
    return dict(gate=gate,admitted_masks=masks,mode=3,divisor=1,sitl_only=True)


def qualification_receipt(evidence, gate, out):
    """Bind explicit new user authority to successful zero-flight qualification.

    A budget alone, a dirty verification, or any old offline receipt is not
    sufficient. This never launches a simulator; the runner checks it again.
    """
    _protocol.require_execution_authority(gate)
    previous=require_previous_gates(gate)
    if (evidence.get('success') is not True or evidence.get('clean') is not True
            or type(evidence.get('new_flights')) is not int or evidence['new_flights'] != 0
            or evidence.get('revision')!=REVISION or evidence.get('stage')!='R03-revision03-'+gate
            or evidence.get('gate')!=gate
            or not _protocol.exact(evidence.get('seed_migration'),seed_migration())
            or not _protocol.exact(evidence.get('previous_gates'),previous)
            or any(evidence.get(key) is not True for key in
                   ('execution_authorized','flight_authorized','execution_ready'))):
        raise ValueError('Only explicitly authorized clean current-revision zero-flight qualification can issue a receipt')
    return dict(approved=True,execution_authorized=True,flight_authorized=True,execution_ready=True,
        stage=evidence['stage'],gate=gate,revision=REVISION,
        source_head=evidence['source_head'],new_matrix_attempts=NEW_MATRIX_ATTEMPTS,
        historical_attempts=HISTORICAL_ATTEMPTS,historical_budget=retained_failure(),seed_migration=seed_migration(),
        execution_sha256=evidence['execution_sha256'],frozen_sha256=evidence['frozen_sha256'],
        firmware_sha256=evidence['firmware_sha256'],qualification_sha256=fingerprint(Path(out)/'evidence.json'),
        maximum_attempts=9,total_maximum_attempts=TOTAL_MAXIMUM_ATTEMPTS,authorization_sha256=fingerprint(AUTHORIZATION),
        basis='Explicit revision03 authority and clean qualified source; nine fresh attempts in this gate, 36 new total plus eight retained; first required failure stops.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate',choices=GATES,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--qualify',action='store_true')
    args=parser.parse_args()
    out=args.output.resolve()
    if out.exists() or EXTERNAL/DATA_STAGE/args.gate not in out.parents:
        raise ValueError('Fresh external gate evidence directory required')
    if args.qualify and git('status','--porcelain'):
        raise ValueError('Qualification requires committed clean source')
    out.mkdir(parents=True)
    env=os.environ.copy()
    removed={k:env.pop(k) for k in list(env) if k.startswith('GTEST_')}
    env['PATH']=str(REPO/'.px4-python/bin')+':'+env['PATH']
    env['PYTHONPATH']=':'.join([str(REPO/'.px4-python'),str(REPO/'research/sta-velocity-control/scripts'),
        '/home/yr/Desktop/codev doc/experiments/M00-20260912/python',env.get('PYTHONPATH','')])
    eeprom=REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    evidence=dict(stage='R03-revision03-'+args.gate,revision=REVISION,gate=args.gate,
        maximum_attempts=9,new_matrix_attempts=NEW_MATRIX_ATTEMPTS,
        historical_attempts=HISTORICAL_ATTEMPTS,total_maximum_attempts=TOTAL_MAXIMUM_ATTEMPTS,
        historical_budget=retained_failure(),seed_migration=seed_migration(),success=False,clean=False,new_flights=0,
        execution_authorized=True,flight_authorized=True,execution_ready=True,
        source_head=git('rev-parse','HEAD'),commands=[],removed_gtest_environment=removed,
        qualification_requested=args.qualify,
        v08_provenance_not_applicable='protocol02.test_tuning.TuningTest.test_original_production_and_launcher_unchanged',
        r02_closed_admission_not_applicable='R03 intentionally admits only the current production gate; prior immutable R02 proof preserved',
        r02_audit_tests_not_applicable=['AuditTest.test_actual_admission_remains_closed',
            'AuditTest.test_unexpected_gate_consumer_rejected'],
        not_executed=['MATLAB','Gazebo flight','parameter write','hardware','R04/R05'])

    def save():
        (out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')

    def run(name,argv,timeout=3600):
        start=time.monotonic()
        with (out/(name+'.log')).open('x') as stream:
            try:
                result=subprocess.run(argv,cwd=REPO,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
                code=result.returncode
            except subprocess.TimeoutExpired:
                code=124
        evidence['commands'].append(dict(name=name,argv=list(map(str,argv)),cwd=str(REPO),
            exit_code=code,wall_seconds=time.monotonic()-start))
        save();print(name,code,flush=True)
        if code:
            raise ValueError(name+' failed; retained '+str(out))
        return (out/(name+'.log')).read_text()

    try:
        _protocol.require_execution_authority(args.gate)
        if git('branch','--show-current')!='research/sta-velocity-regularized':
            raise ValueError('Wrong research branch')
        run('ancestor',['git','merge-base','--is-ancestor',BASE,'HEAD'])
        run('workspace',['git','status','--short'])
        evidence['scope']=freeze.check_scope()
        evidence['admission']=gate_check(args.gate)
        evidence['previous_gates']=require_previous_gates(args.gate)
        evidence['eeprom_before']=fingerprint(eeprom)
        evidence['reference']=R02.check_reference()
        evidence['historical_target_probe']=historical_probe.check()
        validate_manifest()
        if args.qualify:
            snapshot=freeze.check(args.gate)
            evidence['frozen_sha256']=fingerprint(HERE/'gates'/args.gate/'frozen.json')
        else:
            snapshot=freeze.capture(args.gate)
        inputs={str(REPO/name):sha for name,sha in snapshot['assets'].items()}
        inputs.update(snapshot['external_assets'])
        evidence['input_sha256']=inputs
        evidence['execution_sha256']=fingerprint(HERE/'execution.json')
        run('historical_ax01',['python3',str(HELPER.HISTORICAL),'--output',str(out/'historical_ax01')])
        old=read(out/'historical_ax01/evidence.json')
        if not old['success'] or old['v08_provenance_not_applicable']!=evidence['v08_provenance_not_applicable']:
            raise ValueError('Historical functional chain/exclusion mismatch')
        for name in ('test_protocol','test_targets'):
            run('ax02_'+name,['python3',str(HELPER.HISTORICAL.parent.parent/'ax02'/(name+'.py'))])
        run('build_extra',['cmake','--build',str(REPO/'build/px4_sitl_test'),'--target',
            *[kind+'-'+name for name,kind in TARGETS],'--parallel','4'])
        for name,kind in TARGETS:
            run(name,[str(REPO/'build/px4_sitl_test'/(kind+'-'+name)),
                '--gtest_output=xml:'+str(out/(name+'.xml'))],timeout=180)
        run('r01_helpers',['python3',str(HERE.parent/'r01/verification/test_verify.py')])
        helper_test=HERE.parent/'r02/verification/test_verify.py'
        applicable=['test_frozen_reference_matches_git_not_worktree',
                    'test_allowed_production_scope_excludes_upstream_model_and_core',
                    'test_xml_rejects_zero_and_failed_samples']
        run('r02_applicable_helpers',['python3','-c',
            "import importlib.util,unittest; s=importlib.util.spec_from_file_location('prior_audit',"+repr(str(helper_test))+
            "); m=importlib.util.module_from_spec(s);s.loader.exec_module(m);suite=unittest.TestSuite(m.AuditTest(n) for n in "+repr(applicable)+
            "); r=unittest.TextTestRunner(verbosity=2).run(suite);raise SystemExit(not r.wasSuccessful())"])
        run('r02_tools',['python3','-m','unittest','discover','-s',str(HERE.parent/'r02/tools'),'-p','test_*.py','-v'])
        # Separate subprocesses prevent legacy flat-module importer collisions.
        for path in sorted(HERE.glob('test_*.py')):
            run('r03_'+path.stem,['python3',str(path)])
        if not list(HERE.glob('test_*.py')):
            raise ValueError('No R03 tests')
        for name in ('test_incremental','test_integration'):
            run('monitor02_'+name,['python3',str(HERE.parent/'r03_monitor02'/(name+'.py'))])
        evidence['monitor02_historical_replay_scope'] = (
            'Separate immutable external replay receipt; not rerun or recreated by this verifier. '
            'These two commands test the decoder and private class wiring, not new flights.')
        # Preserve old protocol and repair regressions; each runs isolated.
        for path in sorted((HERE.parent/'r03').glob('test_*.py')):
            run('r03_original_'+path.stem,['python3',str(path)])
        run('repair01_tests',['python3',str(HERE.parent/'r03/repair01/test_adapter.py')])
        historical_run=EXTERNAL/'R03/A/batch01/run001'
        diagnostic_records=[]
        for order in ('runner-first','analyzer-first'):
            target=out/('full_chain_'+order)
            run('full_chain_'+order,['python3',str(HERE/'analyzer.py'),str(historical_run),
                '--output',str(target),'--historical-diagnostic','--import-order',order],timeout=600)
            record=read(target/'diagnostic_summary.json')
            if (record.get('diagnostic_checks_complete') is not True or
                    record.get('source_inputs_unchanged') is not True or
                    record.get('historical_acceptance_unchanged') is not True or
                    record.get('accepted') is not False or record.get('flight_accepted') is not False or
                    type(record.get('new_flights')) is not int or record['new_flights']!=0):
                raise ValueError('Historical whole-chain diagnostic is not complete/non-authorizing')
            diagnostic_records.append(target)
        if read(diagnostic_records[0]/'r03_metrics.json') != read(diagnostic_records[1]/'r03_metrics.json') or \
                fingerprint(diagnostic_records[0]/'spectra.json') != fingerprint(diagnostic_records[1]/'spectra.json'):
            raise ValueError('Complete analysis differs with actual import order')
        evidence['full_chain_diagnostic']=dict(orders=['runner-first','analyzer-first'],unique_old_logs=1,
            diagnostic_checks_complete=True,old_acceptance_unchanged=True,new_flights=0)
        run('sitl_build',['make','px4_sitl_default','-j4'])
        run('gazebo_build',['env','DONT_RUN=1','make','px4_sitl_default','gazebo_iris','-j4'])
        evidence['metadata']=R02.check_metadata()
        evidence['cpp_inventory']=HELPER.xml_inventory(out.rglob('*.xml'))
        evidence['python_inventory']=HELPER.python_leaf_counts(out)
        matrix=HELPER.xml_inventory([out/'RegularizedVelocityRegression.xml'])
        if matrix['unique_tests']!=16 or {r['identity'][3] for r in matrix['identities']}!={f'({a}, {s})' for a in range(8) for s in range(2)}:
            raise ValueError('Incomplete fixed legacy matrix')
        evidence['counts']=dict(cpp_unique_tests=evidence['cpp_inventory']['unique_tests'],
            python_tests=evidence['python_inventory']['tests'],fixed_legacy_samples=32768,
            fixed_same_sample_recalculations=256,new_flights=0)
        if evidence['counts']['cpp_unique_tests']<475 or evidence['counts']['python_tests']<709:
            raise ValueError('Regression unexpectedly missing cases')
        for name,sha in inputs.items():
            if fingerprint(name)!=sha:
                raise ValueError('Input changed during verification '+name)
        subs=subprocess.check_output(['git','submodule','status','--recursive'],cwd=REPO,text=True).splitlines()
        if subs!=snapshot['submodules'] or git('submodule','foreach','--recursive','--quiet','git status --porcelain --untracked-files=all'):
            raise ValueError('Submodule changed')
        if fingerprint(eeprom)!=evidence['eeprom_before']:
            raise ValueError('Persistent parameters changed')
        if freeze.check_scope()!=evidence['scope'] or gate_check(args.gate)!=evidence['admission']:
            raise ValueError('Scope/admission changed')
        run('diff_check',['git','diff','--check'])
        evidence['firmware_sha256']=fingerprint(REPO/'build/px4_sitl_default/bin/px4')
        evidence['parameters_sha256']=fingerprint(REPO/'build/px4_sitl_default/parameters.json')
        evidence['clean']=not bool(git('status','--porcelain'))
        if args.qualify:
            if not evidence['clean'] or git('rev-parse','HEAD')!=evidence['source_head']:
                raise ValueError('Source changed during qualification')
            version=(REPO/'build/px4_sitl_default/src/lib/version/build_git_version.h').read_text()
            if evidence['source_head'] not in version:
                raise ValueError('Firmware not rebuilt at current commit')
            freeze.check(args.gate)
        evidence['success']=True
    except BaseException as error:
        evidence.update(error=repr(error),traceback=traceback.format_exc())
        raise
    finally:
        evidence['eeprom_final']=fingerprint(eeprom) if eeprom.exists() else None
        evidence['eeprom_unchanged_at_exit']=evidence.get('eeprom_before')==evidence['eeprom_final']
        evidence['evidence_files']={str(p):fingerprint(p) for p in sorted(out.rglob('*'))
            if p.is_file() and p!=out/'evidence.json' and p.name!='artifacts.sha256'}
        save()
        (out/'artifacts.sha256').write_text(''.join(f'{fingerprint(p)}  {p}\n' for p in sorted(out.rglob('*'))
            if p.is_file() and p.name!='artifacts.sha256'))
    if args.qualify and evidence['success']:
        receipt=qualification_receipt(evidence,args.gate,out)
        with (out/'authorization.json').open('x') as stream:
            json.dump(receipt,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(success=True,output=str(out),counts=evidence['counts']),indent=2))


if __name__=='__main__':
    main()
