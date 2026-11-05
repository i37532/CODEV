#!/usr/bin/env python3
"""Default dry-run; at most two separately qualified upstream diagnostics.

Frozen revision06 flight body is privately compiled with one explicit authority
call substitution. Its inverse AST must be identical; old modules/globals are
never modified. Complete old live safeguards and full BSON restoration remain.
"""
import argparse
import ast
from contextlib import ExitStack
import copy
import fcntl
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import textwrap

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
OLD=HERE.parent/'r03_revision06/runner.py'
OLD_SHA='cee57f8e639596f46db52fd1b76b7144a49ee40f2520174de222c181b59ef544'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


if digest(OLD)!=OLD_SHA:raise ValueError('Frozen revision06 runner changed')
base=load('_up08_frozen_runner',OLD)
api=load('_up08_protocol',HERE/'protocol.py')
historical=base.historical
BIN=base.BIN
ROOTFS=base.ROOTFS
save=base.save
active_simulators=base.active_simulators
restore_parameters=base.restore_parameters
append_event=base.append_event
qualification_reference=base.qualification_reference


def bind_flight_body(function):
    """Only the first old authority expression changes; inverse-proved AST."""
    tree=ast.parse(textwrap.dedent(inspect.getsource(function)))
    original=copy.deepcopy(tree)
    old=ast.parse("local_module('protocol').require_execution_authority(checks.job['gate'])").body[0]
    new=ast.parse('_up08_authority(output, checks)').body[0]
    indexes=[i for i,n in enumerate(tree.body[0].body) if ast.dump(n)==ast.dump(old)]
    if indexes!=[2]:raise ValueError('Expected sole frozen flight authority statement changed')
    tree.body[0].body[indexes[0]]=new
    inverse=copy.deepcopy(tree);inverse.body[0].body[indexes[0]]=old
    if ast.dump(inverse)!=ast.dump(original):raise ValueError('Flight body inverse AST differs')
    namespace=dict(function.__globals__)
    namespace.update(_up08_authority=flight_authority,__file__=str(HERE/'runner.py'))
    exec(compile(ast.fix_missing_locations(tree),str(HERE/'runner.py'), 'exec'),namespace)
    return namespace[function.__name__],dict(source_sha256=OLD_SHA,changed_expressions=1,
        inverse_ast_equal=True,runner_identity=str(HERE/'runner.py'),shared_globals_changed=False)


def flight_authority(output,checks):
    api.require_execution_authority()
    checks.require_execution()
    expected=Path(checks.p['artifacts']['new_run_root'])/checks.job['id']
    if Path(output).resolve()!=expected.resolve():raise RuntimeError('Wrong diagnostic run output')


flight_main,FLIGHT_BINDING=bind_flight_body(base.flight_main)


class Checks(base.Checks):
    def require_execution(self):
        api.require_execution_authority()
        canonical=api.load_protocol()
        if not any(api.exact(self.job,j) for j in canonical['jobs']):raise RuntimeError('Unregistered diagnostic job')
        expected={**canonical,'qualification_path':str(self.qualification_path.resolve()),
                  'startup_overrides':{**canonical['startup_overrides'],**self.job['parameters']}}
        if not api.exact(self.p,expected):raise RuntimeError('Noncanonical per-job diagnostic protocol')
        root=Path(canonical['artifacts']['new_run_root']);ledger=api.read(root/'ledger.json')
        rows=ledger.get('attempts',[])
        if (not 1<=len(rows)<=2 or not api.exact([x.get('job') for x in rows],canonical['jobs'][:len(rows)])
                or rows[-1].get('status')!='running' or not api.exact(rows[-1].get('job'),self.job)
                or any(x.get('status')!='diagnostic_complete' for x in rows[:-1])
                or ledger.get('source_head')!=self.source_head or ledger.get('revision')!=api.REVISION
                or any(not api.exact(ledger.get(k),v) for k,v in api.budget().items())
                or self.backup.resolve()!=(root/'original_parameters.bson').resolve()
                or ledger.get('original_parameter_sha256')!=digest(self.backup)):
            raise RuntimeError('Flight is not the exact already-ledgered diagnostic attempt')
        return api.require_qualification(self.source_head,self.qualification_path)

    def prepare_environment(self,output):
        # Only the version-specific proof front-end is new. Model/log/seed body
        # below preserves the frozen implementation, covered by AST tests.
        qualified=self.require_execution()
        authorization=json.loads((self.qualification_path.parent/'authorization.json').read_text())
        if any(not api.exact(authorization.get(k),v) for k,v in api.authorization_binding(qualified,self.qualification_path).items()):
            raise RuntimeError('Wrong finite diagnostic authority receipt')
        save(output/'authorization.json',authorization);save(output/'qualification.json',qualified)
        qualification_reference(output,self.qualification_path);save(output/'run_protocol.json',self.p)
        (output/'original_parameters.bson').write_bytes(self.backup.read_bytes())
        self.log_root=base.ram_log.create()
        save(output/'ram_log_root.json',dict(path=str(self.log_root),filesystem='tmpfs',owner=base.os.geteuid(),
            minimum_free_bytes=512*1024**2,volatile_before_archive=True,originals_retained_until_durable_archive=True))
        model_dir=output/'models/iris';model_dir.mkdir(parents=True)
        original=REPO/'Tools/sitl_gazebo/models/iris/iris.sdf'
        tree=historical.ET.ElementTree(historical.derive(historical.ET.parse(original).getroot()))
        imu=tree.getroot().find("model/plugin[@name='rotors_gazebo_imu_plugin']")
        if imu is None:raise RuntimeError('Missing original IMU plugin')
        imu.set('filename',str(self.plugins/'libm10_imu.so'))
        tree.write(model_dir/'iris.sdf',encoding='utf-8',xml_declaration=True)
        with (model_dir/'iris.sdf').open('ab') as stream:stream.write(b'\n')
        historical.shutil.copyfile(model_dir/'iris.sdf',model_dir/'iris-gen.sdf')
        historical.shutil.copyfile(original.parent/'model.config',model_dir/'model.config')
        (model_dir/'meshes').symlink_to(original.parent/'meshes',target_is_directory=True)
        historical.verify_model(output,self.plugins)
        if digest(model_dir/'iris.sdf')!=self.frozen['derived_iris_sha256']:raise RuntimeError('R03 qualified contact/IMU asset mismatch')
        save(output/'job.json',self.job)
        save(output/'model_manifest.json',dict(original=digest(original),derived=digest(model_dir/'iris.sdf'),
            only_change='Already-qualified compliant contact and original seeded IMU filename',
            seed_scope='IMU only; no independence claim for GPS/barometer/magnetometer/scheduling'))
        return dict(GAZEBO_MODEL_PATH=str(output/'models')+':'+str(REPO/'Tools/sitl_gazebo/models'),
            GAZEBO_PLUGIN_PATH=str(REPO/'build/px4_sitl_default/build_gazebo'),LD_LIBRARY_PATH='',
            M10_IMU_SEED=str(self.job['seed']),M10_IMU_LOG=str(output/'imu_innovations.csv'),
            PX4_SIM_SPEED_FACTOR='1',PX4_SITL_LOG_DIR=str(self.log_root))


def execution_checks_class():
    path=HERE.parent/'r03_prearm04/integration.py'
    if digest(path)!='161dd6273e37dc625472c389278df12cfd2153d3f459e0da37fc86c0c2453235':
        raise ValueError('Frozen prearm integration changed')
    return load('_up08_prearm',path).make_checks(Checks)


def validate_jobs(p):
    if any(not api.exact(p.get(k),v) for k,v in api.budget().items()) or p.get('revision')!=api.REVISION:
        raise RuntimeError('Wrong bounded diagnostic budget/revision')
    jobs=p['jobs']
    if len(jobs)!=2 or [j['id'] for j in jobs]!=['diag001','diag002'] or [j['mode'] for j in jobs]!=[0,1] or [j['axes'] for j in jobs]!=[0,7]:
        raise RuntimeError('Only PID then legacy XYZ ESTA diagnostics are allowed')
    if len({j['seed'] for j in jobs})!=1 or any(j['gate']!='D' or j['phase']!='diagnostic' or j['revision']!=api.REVISION for j in jobs):
        raise RuntimeError('Wrong diagnostic scope/paired seed')
    if any(type(j['seed']) is not int or j['seed']<=0 or len(j['parameters'])!=127 or j['parameters']['MPC_VCT_TEST']!=8 or j['divisor']!=1 for j in jobs):
        raise RuntimeError('Wrong exact diagnostic task/parameters')


def verify_history(p):
    h=api.retained_history()
    if not api.exact(p.get('historical_budget'),h) or not api.exact(p.get('retained_abc'),api.retained_abc()):
        raise RuntimeError('Retained history changed')
    if any(not api.exact(h.get(k),v) for k,v in dict(attempts=52,takeoffs=51,accepted=46,failed=6,accepted_for_new_matrix=0).items()):
        raise RuntimeError('Wrong retained counts')
    return h


def preflight(p,source_head,q):
    if historical.git('branch','--show-current')!='research/sta-velocity-regularized' or historical.git('rev-parse','HEAD')!=source_head:
        raise RuntimeError('Wrong branch/source')
    if historical.git('status','--porcelain') or historical.git('submodule','foreach','--recursive','--quiet','git status --porcelain'):
        raise RuntimeError('Dirty worktree/submodule')
    rows=historical.git('submodule','status','--recursive').splitlines()
    if len(rows)!=33 or any(s[:1] in ('+','-','U') for s in rows):raise RuntimeError('Wrong33 recursive submodules')
    if active_simulators():raise RuntimeError('Existing simulator')
    if historical.shutil.disk_usage(ROOTFS).free<12*1024**3:raise RuntimeError('Archive/replay reserve below12GiB')
    if (ROOTFS/'etc/logging/logger_topics.txt').exists() or any((REPO/'Tools/sitl_gazebo/models/iris').glob('*-gen.sdf')):
        raise RuntimeError('Custom logging/model override')
    for port in (14550,11345):
        with historical.socket.socket(historical.socket.AF_INET,historical.socket.SOCK_DGRAM if port==14550 else historical.socket.SOCK_STREAM) as sock:sock.bind(('127.0.0.1',port))
    frozen=api.read(Path(p['config_dir'])/'frozen.json')
    for name,value in frozen['assets'].items():
        if digest(REPO/name)!=value:raise RuntimeError('Frozen source changed: '+name)
    for name,value in frozen.get('external_assets',{}).items():
        if digest(name)!=value:raise RuntimeError('External frozen input changed')
    historical.require_passive(REPO/'research/sta-velocity-control/v06/soft_landing/offline03/evidence.json')
    historical.require_qualification(REPO/'research/sta-velocity-control/v06/soft_landing/qualified_contact.json')
    historical.validate_receiver_profile()
    plugins=Path(p['plugins'])
    for name,value in api.read(plugins/'manifest.json').items():
        if digest(name)!=value:raise RuntimeError('Plugin changed')
    if source_head not in (REPO/'build/px4_sitl_default/src/lib/version/build_git_version.h').read_text() or digest(BIN/'px4')!=q['firmware_sha256']:
        raise RuntimeError('Unqualified firmware/version')
    return frozen,plugins


def execute(p,source_head,qualification_path,*,single_flight=flight_main,analyze=None,compare=None):
    bound=str(Path(qualification_path).resolve())
    try:
        if not api.exact({**p,'qualification_path':bound},{**api.load_protocol(),'qualification_path':bound}):
            raise RuntimeError('Caller altered frozen canonical diagnostic protocol')
    except (ValueError,TypeError) as error:raise RuntimeError('Invalid canonical protocol') from error
    validate_jobs(p);api.require_execution_authority();h=verify_history(p)
    q=api.require_qualification(source_head,qualification_path)
    p={**p,'qualification_path':bound};output=Path(p['artifacts']['new_run_root']);root=output.parent
    if output.exists() or list(root.parent.glob('diagnostic*/batch*')):raise RuntimeError('No diagnostic resume/overwrite/retry')
    root.mkdir(parents=True,exist_ok=True)
    with ExitStack() as stack:
        lock_paths=[Path(b['root'])/'.runner.lock' for b in h['batches']]+[root/'.runner.lock']
        for path in dict.fromkeys(x.resolve() for x in lock_paths):
            lock=stack.enter_context(path.open('a'))
            try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as error:raise RuntimeError('Another batch owns simulator/EEPROM') from error
        frozen,plugins=preflight(p,source_head,q)
        audit=api.fresh_seeds()
        if not audit.get('accepted'):raise RuntimeError('Seed conflict before diagnostic launch')
        if output.exists() or list(root.parent.glob('diagnostic*/batch*')):raise RuntimeError('Diagnostic batch appeared while acquiring lock')
        param=ROOTFS/'eeprom/parameters_10016';original=param.read_bytes()
        values=historical.persisted_bson(original)
        definitions=api.read(REPO/'build/px4_sitl_default/parameters.json')['parameters']
        defaults={d['name']:d['default'] for d in definitions};types={d['name']:d['type'] for d in definitions}
        historical.check_parameters({**defaults,**values},frozen['control_parameters'])
        before=int(values.get('SDLOG_PROFILE',defaults['SDLOG_PROFILE']))|16|1024
        if before!=p['logging_profile_before'] or before|2048!=p['logging_profile_after']:raise RuntimeError('Frozen original profile changed')
        output.mkdir();backup=output/'original_parameters.bson';backup.write_bytes(original)
        with backup.open('rb') as stream:base.os.fsync(stream.fileno())
        for name,value in {'protocol.json':p,'qualification.json':q,'authorization.json':api.read(Path(bound).parent/'authorization.json'),'seed_audit_before_launch.json':audit}.items():save(output/name,value)
        qualification_reference(output,bound)
        ledger=dict(stage=api.STAGE,revision=api.REVISION,source_head=source_head,**api.budget(),
            historical_budget=h,retained_abc=p['retained_abc'],planned=2,attempts=[],success=False,
            accepted_for_R03=0,r03_gate_pass=False,applied_profile=p['logging_profile_after'],
            original_parameter_sha256=digest(backup),original_parameter_backup=str(backup),
            firmware_sha256=q['firmware_sha256'])
        journal=output/'journal.jsonl';save(output/'ledger.json',ledger);results=[];prefix=None
        if analyze is None or compare is None:
            analysis=load('_up08_analysis',HERE/'analyzer.py');analyze=analyze or analysis.analyze;compare=compare or analysis.compare
        try:
            for index,job in enumerate(p['jobs'],1):
                verify_history(p);api.require_qualification(source_head,bound)
                if active_simulators() or historical.git('status','--porcelain') or historical.git('rev-parse','HEAD')!=source_head:
                    raise RuntimeError('Source/process changed before attempt')
                if historical.shutil.disk_usage(ROOTFS).free<10*1024**3 or historical.shutil.disk_usage('/dev/shm').free<512*1024**2:
                    raise RuntimeError('Insufficient per-attempt capacity')
                if param.read_bytes()!=original:raise RuntimeError('Previous full parameters not restored')
                run=output/job['id'];item=dict(attempt=index,job=job,directory=str(run),status='running')
                ledger['attempts'].append(item);append_event(journal,dict(event='attempt',**item));save(output/'ledger.json',ledger)
                try:
                    actual={**p,'startup_overrides':{**p['startup_overrides'],**job['parameters']}}
                    applied={**values,**actual['startup_overrides'],'SDLOG_PROFILE':p['logging_profile_after']}
                    expected={**frozen['control_parameters'],**actual['startup_overrides'],'SYS_AUTOSTART':10016,'SDLOG_PROFILE':p['logging_profile_after']}
                    try:
                        param.write_bytes(historical.encode_bson(applied,types))
                        checks=execution_checks_class()(actual,expected,job,plugins,Path(bound),source_head,backup)
                        checks.execution_permitted=True;checks.pid_parameters_modified=True
                        single_flight(run,checks,Path(p['execution_path']))
                    finally:
                        restored=restore_parameters(param,original,run,backup,source_head,job)
                        append_event(journal,dict(event='restore',**restored))
                    base.ram_log.release_archived(run,checks.log_root)
                    if digest(BIN/'px4')!=q['firmware_sha256']:raise RuntimeError('Firmware changed in diagnostic')
                    result=analyze(run,actual,job)
                    if (result.get('diagnostic_checks_complete') is not True or result.get('scientific_checks_complete') is not True
                            or result.get('accepted') is not False or result.get('flight_accepted') is not False
                            or type(result.get('accepted_for_R03')) is not int or result['accepted_for_R03']!=0
                            or not api.exact(result.get('job'),job)):
                        raise RuntimeError('Complete nonaccepting diagnostic checks failed')
                    current=historical.noise_prefix(run)
                    if prefix is not None and float(base.np.max(base.np.abs(prefix-current)))>=1e-10:raise RuntimeError('Paired IMU innovations differ')
                    prefix=current
                    if results:
                        pair=compare(results[0],result);save(run/'diagnostic_pair.json',pair)
                        if pair.get('development_risk_passed') is not True or pair.get('accepted') is not False:raise RuntimeError('Original paired risk check failed')
                    results.append(result);item.update(status='diagnostic_complete',accepted_for_R03=0)
                    item['metrics_sha256']=digest(run/'diagnostic_metrics.json')
                    append_event(journal,dict(event='diagnostic_complete',job_id=job['id'],accepted_for_R03=0,metrics_sha256=item['metrics_sha256']))
                except BaseException as error:
                    item.update(status='failed',error=repr(error));append_event(journal,dict(event='failed',job_id=job['id'],error=repr(error)));raise
                finally:save(output/'ledger.json',ledger)
            ledger['success']=len(results)==2
        finally:
            if not active_simulators():param.write_bytes(original)
            ledger.update(parameter_restore_exact=param.read_bytes()==original,remaining_simulators=active_simulators(),
                          unattempted=[j['id'] for j in p['jobs'][len(ledger['attempts']):]])
            append_event(journal,dict(event='diagnostic_end',success=ledger['success'],attempts=len(ledger['attempts']),
                parameter_restore_exact=ledger['parameter_restore_exact'],remaining_simulators=ledger['remaining_simulators'],accepted_for_R03=0))
            save(output/'ledger.json',ledger)
        if not ledger['success'] or not ledger['parameter_restore_exact'] or ledger['remaining_simulators']:raise RuntimeError('Incomplete diagnostic cleanup')
        return ledger


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true');parser.add_argument('--qualification',type=Path)
    args=parser.parse_args(argv);p=api.load_protocol()
    if not args.execute:
        print(json.dumps(dict(dry_run=True,new_flights=0,stage=api.STAGE,budget=api.budget(),jobs=p['jobs']),indent=2));return 0
    execute(p,api.git('rev-parse','HEAD'),args.qualification or Path(p['qualification_path']));return 0


if __name__=='__main__':raise SystemExit(main())
