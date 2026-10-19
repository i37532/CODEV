#!/usr/bin/env python3
"""Zero-flight PREARM04 offline regression; never issues qualification/authority.

The pinned old receipt is data, not permission. Its 43 command signatures must
equal the independently constructed offline allowlist below. Only declared
output path operands are rebound. The old verifier's main and qualification
receipt functions are never called. Default behavior is a read-only plan.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
REGULARIZED = HERE.parent
EXTERNAL = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016')
OUTPUT_ROOT = EXTERNAL/'R03_PREARM04-20261019'
OLD_OUTPUT = EXTERNAL/'R03_revision03/A/qualification01'
OLD_RECEIPT = OLD_OUTPUT/'evidence.json'
OLD_RECEIPT_SHA256 = 'eb0d3932a5b26f52bb8c4e878322918f78bb51679e1abf5697facb4fa0cf5ac0'
NEW_TESTS = ('test_adversarial.py', 'test_integration.py', 'test_replay.py')
EXPECTED_TARGETS = (
    ('RegularizedStaVelocityControl', 'unit'), ('RegularizedVelocityRegression', 'unit'),
    ('RegularizedVelocityIntegration', 'unit'), ('RegularizedVelocityParam', 'functional'),
    ('RegularizedVelocityModule', 'functional'), ('ControllerSelection', 'unit'),
    ('StaProtection', 'unit'), ('StaAxesApplication', 'unit'), ('TakeoffNuManager', 'unit'),
    ('IstaRateControl', 'unit'), ('IstaIntegration', 'unit'), ('ControlDecimation', 'unit'),
    ('ProperIstaRateControl', 'unit'), ('ProperIstaIntegration', 'unit'),
    ('ProperIstaProtection', 'unit'), ('VelocityAblationTask', 'unit'))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prior = load('prearm04_read_only_prior_helpers', REGULARIZED/'r03_revision03/verify.py')
helper = prior.HELPER


def require(value, message):
    if not value:
        raise ValueError(message)


def fingerprint(path):
    return helper.sha(path)


def read(path):
    return json.loads(Path(path).read_text())


def exact_old_allowlist(out):
    """Explicit offline signatures; no shell, flight main or authorization CLI."""
    old = REGULARIZED/'r03_revision03'
    entries = []
    def add(name, argv):
        entries.append(dict(name=name, argv=list(map(str, argv))))
    add('ancestor', ['git', 'merge-base', '--is-ancestor',
                     '080528bd30f4a8b7816f5097d789fc71e56ecefe', 'HEAD'])
    add('workspace', ['git', 'status', '--short'])
    add('historical_ax01', ['python3', REPO/'research/sta-velocity-control/axis_ablation/ax01/verify.py',
                            '--output', out/'historical_ax01'])
    for name in ('test_protocol', 'test_targets'):
        add('ax02_'+name, ['python3', REPO/'research/sta-velocity-control/axis_ablation/ax02'/(name+'.py')])
    add('build_extra', ['cmake', '--build', REPO/'build/px4_sitl_test', '--target',
                       *[kind+'-'+name for name, kind in EXPECTED_TARGETS], '--parallel', '4'])
    for name, kind in EXPECTED_TARGETS:
        add(name, [REPO/'build/px4_sitl_test'/(kind+'-'+name),
                   '--gtest_output=xml:'+str(out/(name+'.xml'))])
    add('r01_helpers', ['python3', REGULARIZED/'r01/verification/test_verify.py'])
    applicable = ['test_frozen_reference_matches_git_not_worktree',
                  'test_allowed_production_scope_excludes_upstream_model_and_core',
                  'test_xml_rejects_zero_and_failed_samples']
    code = ("import importlib.util,unittest; s=importlib.util.spec_from_file_location('prior_audit',"+
            repr(str(REGULARIZED/'r02/verification/test_verify.py'))+
            "); m=importlib.util.module_from_spec(s);s.loader.exec_module(m);suite=unittest.TestSuite(m.AuditTest(n) for n in "+
            repr(applicable)+
            "); r=unittest.TextTestRunner(verbosity=2).run(suite);raise SystemExit(not r.wasSuccessful())")
    add('r02_applicable_helpers', ['python3', '-c', code])
    add('r02_tools', ['python3', '-m', 'unittest', 'discover', '-s', REGULARIZED/'r02/tools', '-p', 'test_*.py', '-v'])
    for name in ('test_analysis', 'test_protocol', 'test_replay', 'test_revision_audit', 'test_runner'):
        add('r03_'+name, ['python3', old/(name+'.py')])
    for name in ('test_incremental', 'test_integration'):
        add('monitor02_'+name, ['python3', REGULARIZED/'r03_monitor02'/(name+'.py')])
    for name in ('test_analysis', 'test_historical_probe', 'test_protocol', 'test_replay', 'test_runner'):
        add('r03_original_'+name, ['python3', REGULARIZED/'r03'/(name+'.py')])
    add('repair01_tests', ['python3', REGULARIZED/'r03/repair01/test_adapter.py'])
    for order in ('runner-first', 'analyzer-first'):
        add('full_chain_'+order, ['python3', old/'analyzer.py', EXTERNAL/'R03/A/batch01/run001',
                                 '--output', out/('full_chain_'+order),
                                 '--historical-diagnostic', '--import-order', order])
    add('sitl_build', ['make', 'px4_sitl_default', '-j4'])
    add('gazebo_build', ['env', 'DONT_RUN=1', 'make', 'px4_sitl_default', 'gazebo_iris', '-j4'])
    add('diff_check', ['git', 'diff', '--check'])
    return entries


def rebase_output_argument(value, out):
    old = str(OLD_OUTPUT)
    if value == old or value.startswith(old+'/'):
        return str(out)+value[len(old):]
    prefix = '--gtest_output=xml:'
    if value.startswith(prefix+old+'/'):
        return prefix+str(out)+value[len(prefix+old):]
    require(old not in value, 'Undeclared output substitution position')
    return value


def command_plan(out):
    require(fingerprint(OLD_RECEIPT) == OLD_RECEIPT_SHA256, 'Pinned old command receipt changed')
    require(tuple(prior.TARGETS) == EXPECTED_TARGETS, 'Old helper test target list changed')
    old = read(OLD_RECEIPT)
    require(old.get('success') is True and len(old.get('commands', [])) == 43,
            'Expected complete old 43-command receipt')
    actual = []
    for row in old['commands']:
        require(row.get('cwd') == str(REPO) and row.get('exit_code') == 0,
                'Historical command receipt is incomplete or changed')
        actual.append(dict(name=row['name'], argv=row['argv']))
    require(actual == exact_old_allowlist(OLD_OUTPUT), 'Old command differs from explicit offline allowlist')
    result = [dict(name=row['name'], argv=[rebase_output_argument(arg, out) for arg in row['argv']])
              for row in actual]
    require(result == exact_old_allowlist(out), 'Output rebasing exceeds declared operands')
    for name in NEW_TESTS:
        result.append(dict(name='prearm04_'+Path(name).stem, argv=['python3', str(HERE/name)]))
    require(len(result) == 46 and len({row['name'] for row in result}) == 46,
            'Missing/duplicate verification command')
    return result


def validate_output(out):
    require(out != OUTPUT_ROOT and OUTPUT_ROOT in out.parents and not out.exists(),
            'Require a fresh output directory strictly below '+str(OUTPUT_ROOT))
    require(REPO != out and REPO not in out.parents, 'Output must be external')


def schema_check(plan, out):
    """Non-executing plan checks, including path-boundary negative cases."""
    require(plan[:43] == exact_old_allowlist(out), 'Historical signatures mismatch')
    require([row['argv'] for row in plan[43:]] ==
            [['python3', str(HERE/name)] for name in NEW_TESTS], 'New test signatures mismatch')
    require(plan[41]['argv'] == ['env', 'DONT_RUN=1', 'make', 'px4_sitl_default', 'gazebo_iris', '-j4'],
            'Gazebo build must not run')
    for value in ('--output='+str(OLD_OUTPUT)+'/unexpected',
                  'print('+repr(str(OLD_OUTPUT))+')', str(OLD_OUTPUT)+'-sibling/file'):
        try:
            rebase_output_argument(value, out)
        except ValueError:
            continue
        raise ValueError('Unsafe output rebasing accepted '+value)
    return dict(old_commands=43, new_test_commands=3, total_commands=46,
                signature_check=True, undeclared_path_substitutions_rejected=3,
                source_receipt_sha256=OLD_RECEIPT_SHA256,
                missing_new_tests=[name for name in NEW_TESTS if not (HERE/name).is_file()],
                new_flights=0, execution_authorized=False, flight_authorized=False,
                execution_ready=False, qualification_requested=False)


def submodules():
    lines = subprocess.check_output(['git', 'submodule', 'status', '--recursive'], cwd=REPO, text=True).splitlines()
    require(len(lines) == 33 and all(line.startswith(' ') for line in lines), 'Submodule versions/status differ')
    require(not prior.git('submodule', 'foreach', '--recursive', '--quiet',
                          'git status --porcelain --untracked-files=all'), 'Dirty submodule')
    return lines


def local_inputs():
    return {str(path): fingerprint(path) for path in sorted(HERE.rglob('*'))
            if path.is_file() and '__pycache__' not in path.parts}


def verify_diagnostics(out):
    locations = [out/('full_chain_'+order) for order in ('runner-first', 'analyzer-first')]
    for folder in locations:
        record = read(folder/'diagnostic_summary.json')
        require(all(record.get(key) is True for key in ('diagnostic_checks_complete',
                    'source_inputs_unchanged', 'historical_acceptance_unchanged')),
                'Incomplete historical full-chain diagnostic')
        require(record.get('accepted') is False and record.get('flight_accepted') is False and
                type(record.get('new_flights')) is int and record['new_flights'] == 0,
                'Historical diagnostic must not grant acceptance/flight')
    require(read(locations[0]/'r03_metrics.json') == read(locations[1]/'r03_metrics.json') and
            fingerprint(locations[0]/'spectra.json') == fingerprint(locations[1]/'spectra.json'),
            'Historical full-chain checks differ by import order')
    return dict(import_orders=['runner-first', 'analyzer-first'], unique_old_logs=1,
                complete=True, historical_acceptance_unchanged=True, new_flights=0,
                provenance_copies='Any copied old authorization remains original failed-run provenance; no new authority.')


def execute(out, plan):
    validate_output(out)
    check = schema_check(plan, out)
    require(not check['missing_new_tests'], 'New test scripts are not complete')
    require(set(path.name for path in HERE.glob('test_*.py')) == set(NEW_TESTS),
            'Unexpected/missing PREARM04 test script; freeze exact command list first')
    out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    removed = {key: env.pop(key) for key in list(env) if key.startswith('GTEST_')}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PATH'] = str(REPO/'.px4-python/bin')+':'+env['PATH']
    env['PYTHONPATH'] = ':'.join([str(REPO/'.px4-python'),
        str(REPO/'research/sta-velocity-control/scripts'),
        '/home/yr/Desktop/codev doc/experiments/M00-20260912/python', env.get('PYTHONPATH', '')])
    eeprom = REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'
    evidence = dict(schema=1, stage='R03-PREARM04-OFFLINE', success=False, exit_code=None,
        execution_authorized=False, flight_authorized=False, execution_ready=False,
        qualification_requested=False, qualified=False, new_flights=0, new_flight_authorizations=0,
        historical_acceptance_unchanged=True, commands=[], plan=plan, plan_schema=check,
        removed_gtest_environment=removed, source_head=prior.git('rev-parse', 'HEAD'),
        source_receipt=dict(path=str(OLD_RECEIPT), sha256=OLD_RECEIPT_SHA256,
                            role='Command data only; no inherited authority'),
        v08_provenance_not_applicable='protocol02.test_tuning.TuningTest.test_original_production_and_launcher_unchanged',
        r02_closed_admission_not_applicable='Existing frozen R03 A admits only MODE3/AXES1 in SITL; immutable R02 proof is retained.',
        r02_audit_tests_not_applicable=['AuditTest.test_actual_admission_remains_closed',
                                      'AuditTest.test_unexpected_gate_consumer_rejected'],
        not_executed=['MATLAB', 'SITL/Gazebo flight', 'parameter write', 'new seed registration',
                      'flight authorization', 'new qualification', 'hardware', 'R03 B/C/D', 'R04/R05'])
    inputs = {}
    def save():
        (out/'evidence.json').write_text(json.dumps(evidence, indent=2)+'\n')
    def run(row):
        began = time.monotonic()
        timeout = 180 if row['name'] in {name for name, _ in EXPECTED_TARGETS} else \
                  600 if row['name'].startswith('full_chain_') else 3600
        code, timed_out = None, False
        log = out/(row['name']+'.log')
        try:
            with log.open('x') as stream:
                try:
                    result = subprocess.run(row['argv'], cwd=REPO, env=env, stdout=stream,
                                            stderr=subprocess.STDOUT, timeout=timeout)
                    code = result.returncode
                except subprocess.TimeoutExpired:
                    code, timed_out = 124, True
        finally:
            evidence['commands'].append(dict(**row, cwd=str(REPO), exit_code=code,
                timeout=timed_out, wall_seconds=time.monotonic()-began))
            save()
        print(row['name'], code, flush=True)
        require(code == 0, 'Offline command failed; preserved '+str(log))
    try:
        require(prior.git('branch', '--show-current') == 'research/sta-velocity-regularized', 'Wrong branch')
        frozen = prior.freeze.check('A')
        evidence['old_frozen_A_checked'] = True
        evidence['old_frozen_A_sha256'] = fingerprint(REGULARIZED/'r03_revision03/gates/A/frozen.json')
        evidence['admission_before'] = prior.gate_check('A')
        evidence['scope_before'] = prior.freeze.check_scope()
        evidence['submodules_before'] = submodules()
        require(evidence['submodules_before'] == frozen['submodules'], 'Frozen submodule versions differ')
        evidence['eeprom_before'] = fingerprint(eeprom)
        evidence['workspace_before'] = prior.git('status', '--porcelain')
        evidence['reference'] = prior.R02.check_reference()
        evidence['historical_target_probe'] = prior.historical_probe.check()
        prior.validate_manifest()
        inputs = {str(REPO/name): digest for name, digest in frozen['assets'].items()}
        inputs.update(frozen['external_assets'])
        inputs[str(OLD_RECEIPT)] = OLD_RECEIPT_SHA256
        evidence['new_inputs_before'] = local_inputs()
        inputs.update(evidence['new_inputs_before'])
        evidence['input_sha256_before'] = inputs
        save()
        for row in plan:
            run(row)
        old_chain = read(out/'historical_ax01/evidence.json')
        require(old_chain.get('success') is True and old_chain.get('v08_provenance_not_applicable') ==
                evidence['v08_provenance_not_applicable'], 'Historical chain/exclusion mismatch')
        evidence['full_chain_diagnostic'] = verify_diagnostics(out)
        evidence['metadata'] = prior.R02.check_metadata()
        evidence['cpp_inventory'] = helper.xml_inventory(out.rglob('*.xml'))
        evidence['python_inventory'] = helper.python_leaf_counts(out)
        matrix = helper.xml_inventory([out/'RegularizedVelocityRegression.xml'])
        require(matrix['unique_tests'] == 16 and
                {tuple(row['identity'])[3] for row in matrix['identities']} ==
                {f'({axis}, {sequence})' for axis in range(8) for sequence in range(2)} and
                all('Two2048SampleSequencesPreserveR01OutputAndStateExactly' in row['identity'][1]
                    for row in matrix['identities']), 'Fixed sequence matrix not actually completed')
        evidence['counts'] = dict(cpp_unique_tests=evidence['cpp_inventory']['unique_tests'],
            python_tests=evidence['python_inventory']['tests'], fixed_legacy_samples=32768,
            fixed_same_sample_recalculations=256, new_flights=0,
            policy='Unique completed XML identities and direct leaf unittest summaries; excludes earlier dev runs.')
        require(evidence['counts']['cpp_unique_tests'] == 475 and
                evidence['counts']['python_tests'] > 1143, 'Offline suite missing/changed counted tests')
        direct = {Path(row['log']).name: row['tests'] for row in evidence['python_inventory']['direct_logs']}
        require(all(direct.get('prearm04_'+Path(name).stem+'.log', 0) > 0 for name in NEW_TESTS),
                'A new test command ran zero actual tests')
        require(len(evidence['commands']) == 46 and all(row['exit_code'] == 0 for row in evidence['commands']),
                'Incomplete command execution')
        evidence['input_sha256_after'] = {name: fingerprint(name) for name in inputs}
        require(evidence['input_sha256_after'] == inputs, 'Input changed during offline verification')
        require(local_inputs() == evidence['new_inputs_before'], 'New input file set changed')
        evidence['submodules_after'] = submodules()
        require(evidence['submodules_after'] == evidence['submodules_before'], 'Submodule changed')
        require(fingerprint(eeprom) == evidence['eeprom_before'], 'Persistent parameters changed')
        require(prior.R02.check_reference() == evidence['reference'], 'Reference changed')
        require(prior.freeze.check_scope() == evidence['scope_before'] and
                prior.gate_check('A') == evidence['admission_before'], 'Scope/admission changed')
        prior.freeze.check('A')
        require(prior.git('rev-parse', 'HEAD') == evidence['source_head'], 'HEAD changed during offline verification')
        evidence['workspace_after'] = prior.git('status', '--porcelain')
        evidence['firmware_sha256'] = fingerprint(REPO/'build/px4_sitl_default/bin/px4')
        evidence['parameters_metadata_sha256'] = fingerprint(REPO/'build/px4_sitl_default/parameters.json')
        require(not (out/'authorization.json').exists() and not (out/'gate_pass.json').exists(),
                'Unexpected new authority artifact')
        evidence.update(success=True, exit_code=0)
    except BaseException as exc:
        evidence.update(error=repr(exc), traceback=traceback.format_exc(), exit_code=1)
        raise
    finally:
        evidence['eeprom_final'] = fingerprint(eeprom) if eeprom.is_file() else None
        evidence['eeprom_unchanged_at_exit'] = evidence.get('eeprom_before') == evidence['eeprom_final']
        # These fields are invariant even when a historical helper fails.
        evidence.update(execution_authorized=False, flight_authorized=False, execution_ready=False,
                        qualification_requested=False, qualified=False, new_flights=0,
                        new_flight_authorizations=0)
        save()
        (out/'artifacts.sha256').write_text(''.join(f'{fingerprint(path)}  {path}\n'
            for path in sorted(out.rglob('*')) if path.is_file() and path.name != 'artifacts.sha256'))
    print(json.dumps(dict(success=True, offline_only=True, execution_authorized=False,
                         flight_authorized=False, output=str(out), counts=evidence['counts']), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Fresh directory under the dedicated external PREARM04 root')
    parser.add_argument('--execute', action='store_true', help='Run offline tests/builds only; never a flight')
    parser.add_argument('--plan-json', action='store_true', help='Print the exact allowlisted plan without execution')
    parser.add_argument('--check-plan', action='store_true', help='Check signatures/schema/path boundaries without execution')
    args = parser.parse_args()
    require(not args.execute or (args.output is not None and not args.plan_json and not args.check_plan),
            '--execute requires --output and cannot combine with plan-only modes')
    out = (args.output or OUTPUT_ROOT/'PLAN_ONLY_NOT_CREATED').resolve()
    validate_output(out)
    plan = command_plan(out)
    checked = schema_check(plan, out)
    if args.execute:
        execute(out, plan)
    else:
        document = dict(offline_only=True, output=str(out), checks=checked,
                        commands=plan if args.plan_json else None)
        print(json.dumps(document, indent=2))


if __name__ == '__main__':
    main()
