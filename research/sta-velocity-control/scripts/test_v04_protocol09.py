"""Offline wiring only. Any accepted synthetic fixture is NOT a flight verdict."""
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
from contextlib import redirect_stdout
import numpy as np
from pyulog import ULog
import run_v04_protocol09 as runner
import analyze_v04_protocol09 as analyzer
import v04_live_clock09 as live
import v04_protocol09 as protocol_module
from v04_protocol09 import CONFIG, load_protocol, require_authorization, fingerprint, CHANGED
from v04_protocol08 import load_protocol as old_protocol
from test_v04_attitude_clock09 import heading_fixture, attitude
from test_v04_protocol04 import Log
from replay_v04_clock09 import ROOT, digest, copy_metadata


class Protocol09Test(unittest.TestCase):
    def test_rules_budget_parameters_and_pending_authorization(self):
        p,old=load_protocol(),old_protocol()
        for k in set(old)-CHANGED:self.assertEqual(p[k],old[k],k)
        self.assertEqual([(j['seed'],j['mode']) for j in p['jobs']],
                         [(9801,0),(9801,1),(9802,0),(9802,1),(9803,0),(9803,1)])
        self.assertFalse(p['flight_authorized'])
        for mode in ('pid','esta'):
            self.assertEqual((CONFIG/mode/'frozen.json').read_bytes(),
                             (CONFIG.parent/'protocol08'/mode/'frozen.json').read_bytes())

    def test_new_entry_bindings(self):
        import run_v04_flight10 as flight
        self.assertIs(runner.flight,flight.main)
        self.assertIs(runner.replay,live.replay)
        self.assertEqual(analyzer.CONFIG,CONFIG)
        with patch.object(flight.subprocess,'Popen') as spawn:
            with self.assertRaises(RuntimeError):flight.main()
            spawn.assert_not_called()

    def test_only_intended_runner_changes(self):
        scripts=Path(__file__).parent
        old=(scripts/'run_v04_flight09.py').read_text()
        expected=old.replace('v04_protocol08','v04_protocol09').replace('protocol08','protocol09').replace('Protocol08','Protocol09')
        expected=expected.replace('from v04_handoff06 import','from v04_handoff09 import')
        self.assertEqual(expected,(scripts/'run_v04_flight10.py').read_text())

    def test_handoff_and_height_only_change_explicit_clock_binding(self):
        scripts=Path(__file__).parent
        old=(scripts/'v04_handoff06.py').read_text()
        expected=old.replace('from v04_heading_stream import data, index, row, replay',
            'from v04_heading_stream import data, index, row\nfrom v04_live_clock09 import replay')
        self.assertEqual(expected,(scripts/'v04_handoff09.py').read_text())
        old=(scripts/'analyze_v04_handoff07.py').read_text()
        expected=old.replace('from v04_handoff06 import','from v04_handoff09 import').replace('Offline revision07:','Protocol09 handoff replay:')
        self.assertEqual(expected,(scripts/'analyze_v04_handoff09.py').read_text())
        old=(scripts/'analyze_v04_height_clock09.py').read_text()
        expected=old.replace('from analyze_v04_handoff07 import','from analyze_v04_handoff09 import').replace('Offline clock09 height checks','Protocol09 wired clock09 height checks')
        self.assertEqual(expected,(scripts/'analyze_v04_height_protocol09.py').read_text())

    def test_monitor_really_uses_revised_replay_and_preserves_transport_guard(self):
        # Exercise the runner method, not merely its import binding.
        p=load_protocol();job=p['jobs'][0]
        c=runner.Checks(p,{},job,Path('/tmp/unused'))
        c.reference={'position':{}};c.frozen_yaw={'timestamp':1};c.live=Mock()
        d=dict(requested_mode=0,requested_axes=0,effective_mode=0,effective_axes=0,pending=0,reject=0,
               first_fail=0,retry_result=0,first_input=0,excitation_fault=0,armed=0,enabled=0,
               excitation=0,timestamp=1000000)
        state=dict(status=dict(arming_state=1,nav_state=0),position=dict(timestamp=1000000))
        with tempfile.TemporaryDirectory(prefix='v04-p09-monitor-') as tmp, \
                patch.object(runner.base.Checks,'monitor'),patch.object(runner,'replay') as replay:
            topic=lambda name: d if name=='sta_velocity_ctrl_status' else dict(timestamp=1000000)
            replay.return_value=dict(through_us=996000,ready=False)
            c.monitor('warmup',None,topic,Path(tmp),state)
            replay.assert_called_once_with(c.live.read.return_value,c.reference,frozen=c.frozen_yaw,allow_pending=True)
            replay.return_value=dict(through_us=499999,ready=False)
            with self.assertRaisesRegex(RuntimeError,'transport'):c.monitor('warmup',None,topic,Path(tmp),state)

    def test_dryrun_execute_without_new_receipt_never_mutates(self):
        with tempfile.TemporaryDirectory(prefix='v04-p09-dry-') as tmp:
            out=Path(tmp)/'unused'
            argv=[sys.executable,str(Path(runner.__file__)),'--output',str(out),'--source-head','invalid']
            for extra,code in [([],0),(['--execute'],1),
                    (['--execute','--authorization','V04-protocol08-series07-six-attempts'],1)]:
                r=subprocess.run(argv+extra,capture_output=True,text=True)
                self.assertEqual(r.returncode,code,r.stderr);self.assertFalse(out.exists())

    def test_external_receipt_exact_source_execution_budget_and_explicit_approval(self):
        p=load_protocol()
        with tempfile.TemporaryDirectory(prefix='v04-p09-auth-') as tmp:
            path=Path(tmp)/'receipt.json'
            valid=dict(approved=True,stage=p['stage'],source_head='test-head',
                execution_sha256=fingerprint(CONFIG/'execution.json'),maximum_attempts=6,
                user_approval='SYNTHETIC TEST ONLY, not permission to fly')
            with patch.object(protocol_module.subprocess,'check_output',return_value='test-head\n'):
                path.write_text(json.dumps(valid))
                self.assertEqual(require_authorization(str(path),p),valid)
                for field,value in [('approved',False),('source_head','old'),('execution_sha256','old'),
                        ('maximum_attempts',7),('stage','protocol08'),('user_approval','')]:
                    path.write_text(json.dumps({**valid,field:value}))
                    with self.subTest(field=field),self.assertRaises(RuntimeError):require_authorization(str(path),p)

    def test_seed_audit_only_excludes_own_registration(self):
        import capture_v04_protocol09 as capture
        matches=[dict(path=str(CONFIG/'execution.json')),dict(path='/tmp/real-flight/job.json')]
        with patch.object(capture,'seed_audit',return_value=dict(matches=matches,invalid_json=[])):
            r=capture.fresh_seeds()
        self.assertFalse(r['accepted']);self.assertEqual(len(r['matches']),1)

    def test_live_tail_group_is_unsealed_then_all_rows_preserved(self):
        a=attitude(p=(90000,100000,100000),s=(90000,96000,100000))
        pos=dict(timestamp=np.array([90000,96000,100000],np.uint64))
        log=Log({('vehicle_attitude',0):a,('vehicle_local_position',0):pos})
        self.assertEqual(live.sealed_time(log),96000)
        log.tables[('vehicle_attitude',0)]=attitude()
        self.assertEqual(live.sealed_time(log),100000)
        self.assertEqual(live.AttitudeClockPolicy().window(log.tables[('vehicle_attitude',0)],100000,100000).tolist(),[0,1,2])

    def test_live_no_seal_or_future_requested_interval_rejected(self):
        log=Log({('vehicle_attitude',0):attitude(),
                 ('vehicle_local_position',0):dict(timestamp=np.array([104000],np.uint64))})
        with self.assertRaisesRegex(ValueError,'No sealed'):live.sealed_time(log)
        log,ref=heading_fixture()
        with self.assertRaisesRegex(ValueError,'unsealed'):live.replay(log,ref,end=10**12)

    def test_live_new_policy_has_same_heading_result_through_seal(self):
        from v04_heading_stream import replay
        log,ref=heading_fixture();end=live.sealed_time(log)
        expected=replay(log,ref,end=end,attitude_policy=live.AttitudeClockPolicy())
        actual=live.replay(log,ref)
        self.assertEqual(actual.pop('clock09')['sealed_through_us'],end)
        self.assertEqual(actual,expected)

    def test_live_boundary_first_tied_row_tilt_not_hidden(self):
        log,ref=heading_fixture();a=log.tables[('vehicle_attitude',0)]
        k=len(a['timestamp'])-5;a['timestamp'][k]=a['timestamp'][k+1]
        a['q[0]'][k]=np.cos(.2);a['q[1]'][k]=np.sin(.2)
        with self.assertRaisesRegex(ValueError,'tilt'):live.replay(log,ref)

    def test_live_bad_sample_and_non_attitude_ties_still_rejected(self):
        for name in ('vehicle_attitude','vehicle_local_position'):
            log,ref=heading_fixture();d=log.tables[(name,0)]
            key='timestamp_sample' if name=='vehicle_attitude' else 'timestamp'
            d[key][-3]=d[key][-4]
            with self.subTest(name=name),self.assertRaises(ValueError):live.replay(log,ref)

    def test_new_full_analyzer_refuses_historical_job(self):
        with tempfile.TemporaryDirectory(prefix='v04-p09-old-') as tmp:
            r=analyzer.analyze(Path(tmp),load_protocol(),old_protocol()['jobs'][0])
        self.assertFalse(r['accepted']);self.assertIn('historical results',r['error'])

    def test_final_analyzer_refuses_missing_approval_provenance(self):
        with tempfile.TemporaryDirectory(prefix='v04-p09-noauth-') as tmp:
            path=Path(tmp);(path/'result.json').write_text('{}')
            r=analyzer.analyze(path,load_protocol(),load_protocol()['jobs'][0])
        self.assertFalse(r['accepted']);self.assertIn('authorization.json',r['error'])

    def test_snapshot_includes_new_wiring_policy_and_old_conversion(self):
        from capture_v04_protocol09 import capture
        a=capture()['assets']
        for name in ('run_v04_protocol09','run_v04_flight10','analyze_v04_protocol09',
                     'v04_live_clock09','v04_attitude_clock09','analyze_v04_height_clock09'):
            self.assertIn('research/sta-velocity-control/scripts/'+name+'.py',a)
        self.assertIn('src/modules/simulator/simulator_mavlink.cpp',a)


    def batch(self, fail_at=None, reject=False):
        with tempfile.TemporaryDirectory(prefix='v04-p09-batch-') as tmp:
            root=Path(tmp); conf=root/'config';conf.mkdir();rootfs=root/'rootfs';(rootfs/'eeprom').mkdir(parents=True)
            param=rootfs/'eeprom/parameters_10016';param.write_bytes(b'original-full-eeprom')
            (root/'build/px4_sitl_default/src/lib/version').mkdir(parents=True)
            (root/'build/px4_sitl_default/src/lib/version/build_git_version.h').write_text('source-test')
            (root/'build/px4_sitl_default/parameters.json').write_text('{"parameters": []}')
            plugins=root/'plugins';plugins.mkdir();(plugins/'manifest.json').write_text('{}')
            p=load_protocol();p['plugins']=str(plugins);p['artifacts']['new_run_root']=str(root/'series')
            (conf/'frozen.json').write_text('{"assets":{},"control_parameters":{}}')
            calls=[]
            def git(*args):
                return 'research/sta-velocity-control' if args[0]=='branch' else ('source-test' if args[0]=='rev-parse' else '')
            def flight(**kwargs):
                calls.append(kwargs['checks'].job)
                self.assertEqual(kwargs['scenario_path'],conf/'execution.json')
                if fail_at==len(calls):raise RuntimeError('injected failure')
            def metrics(run,protocol,job):
                return dict(accepted=not reject,job=job,diagnostic=dict(error=dict(rmse=[.01]*3)),position_rmse=[.01]*3,yaw_rmse=.01)
            with patch.multiple(runner,REPO=root,ROOTFS=rootfs,CONFIG=conf,git=git,active_simulators=lambda:[],
                    digest=lambda path:'hash',persisted_bson=lambda data:{},check_parameters=lambda a,b:None,
                    encode_bson=lambda values,types:b'experiment-eeprom',flight=flight,analyze=metrics,
                    noise_prefix=lambda run:np.array([p['jobs'][int(run.name[3:])-1]['seed']],dtype=float),
                    fresh_seeds=lambda:dict(accepted=True),load_protocol=lambda:p,
                    require_authorization=lambda token,protocol:dict(synthetic=True)), \
                    patch.object(runner.socket,'socket'), \
                    patch.object(runner.shutil,'disk_usage',return_value=type('Space',(),{'free':20*1024**3})()), \
                    patch.object(sys,'argv',['runner','--authorization','/tmp/SYNTHETIC-AUTHORIZATION','--execute','--output',str(root/'series'),'--source-head','source-test']), \
                    redirect_stdout(io.StringIO()):
                if fail_at or reject:
                    with self.assertRaises(RuntimeError):runner.main()
                else:runner.main()
            ledger=json.loads((root/'series/ledger.json').read_text())
            self.assertEqual(param.read_bytes(),b'original-full-eeprom')
            self.assertTrue(ledger['parameter_restore_exact'])
            return calls,ledger


    def test_mock_six_attempt_budget_and_eeprom_restore(self):
        calls,ledger=self.batch()
        self.assertEqual(len(calls),6);self.assertEqual(len(ledger['pairs']),3)
        self.assertTrue(ledger['success'])

    def test_mock_first_failure_and_final_rejection_stop_no_retry(self):
        for n in (1,2,6):
            calls,ledger=self.batch(fail_at=n)
            self.assertEqual(len(calls),n);self.assertFalse(ledger['success'])
        calls,ledger=self.batch(reject=True)
        self.assertEqual(len(calls),1);self.assertFalse(ledger['success'])


class FullChain09Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record=json.loads((ROOT/'results06/run01.json').read_text())
        cls.entry=max(cls.record['logs'],key=lambda e:e['bytes'])
        if digest(cls.entry['archive'])!=cls.entry['sha256']:raise ValueError('Frozen input changed')
        cls.source=Path(cls.entry['archive']).parent
        cls.log=ULog(cls.entry['archive'])

    def full(self, mutation=None):
        import analyze_v00
        import analyze_v04_core04 as core
        u=copy.deepcopy(self.log)
        if mutation:mutation(u)
        with tempfile.TemporaryDirectory(prefix='v04-p09-SYNTHETIC-') as tmp:
            run=Path(tmp)/'run';copy_metadata(self.source,run)
            p=load_protocol();job=p['jobs'][0];p['startup_overrides'].update(job['parameters'])
            r=copy.deepcopy(self.record)
            r.update(source_head='SYNTHETIC',scenario_path=str(CONFIG/'execution.json'),
                     scenario_sha256=fingerprint(CONFIG/'execution.json'))
            (run/'result.json').write_text(json.dumps(r));(run/'job.json').write_text(json.dumps(job))
            approval=dict(approved=True,source_head='SYNTHETIC',execution_sha256=r['scenario_sha256'],
                stage=p['stage'],maximum_attempts=6,user_approval='SYNTHETIC OFFLINE FIXTURE')
            (run/'authorization.json').write_text(json.dumps(approval))
            original_config=analyze_v00.CONFIG
            read=lambda path:u if str(path)==self.entry['archive'] else ULog(path)
            with patch.object(analyze_v00,'ULog',side_effect=read),patch.object(core,'ULog',side_effect=read),patch.object(analyzer,'ULog',side_effect=read):
                result=analyzer.analyze(run,p,job)
            self.assertEqual(analyze_v00.CONFIG,original_config)
            self.assertTrue((run/'v04_protocol09_metrics.json').exists())
        self.assertFalse(json.loads((self.source/'v04_protocol06_metrics.json').read_text())['accepted'])
        return result

    @staticmethod
    def tie(u):
        a=u.get_dataset('vehicle_attitude').data
        k=int(np.searchsorted(a['timestamp'],60e6))
        a['timestamp'][k]=a['timestamp'][k+1]
        return a,k

    def test_complete_chain_no_tie_positive_synthetic(self):
        r=self.full();self.assertTrue(r['accepted'],r.get('error'))
        self.assertIn('height_task',r);self.assertIn('local_output',r);self.assertIn('exit',r)

    def test_complete_chain_ties_do_not_change_main_metrics(self):
        old=self.full();new=self.full(self.tie)
        self.assertTrue(new['accepted'],new.get('error'))
        self.assertEqual(old['diagnostic'],new['diagnostic'])
        self.assertEqual(old['position_rmse'],new['position_rmse'])

    def test_complete_chain_first_tie_unsafe_rejected(self):
        def mutate(u):
            a,k=self.tie(u);a['q[0]'][k]=np.cos(.2);a['q[1]'][k]=np.sin(.2);a['q[2]'][k]=a['q[3]'][k]=0
        r=self.full(mutate);self.assertFalse(r['accepted']);self.assertIn('tilt',r['error'])

    def test_complete_chain_first_tie_reset_rejected(self):
        def mutate(u):
            a,k=self.tie(u);a['quat_reset_counter'][k]+=1
        r=self.full(mutate);self.assertFalse(r['accepted']);self.assertIn('reset',r['error'])

    def test_complete_chain_duplicate_output_rejected(self):
        def mutate(u):
            d=u.get_dataset('vehicle_attitude_setpoint').data;k=int(np.searchsorted(d['timestamp'],60e6))
            for key,v in list(d.items()):d[key]=np.insert(v,k,v[k])
        r=self.full(mutate);self.assertFalse(r['accepted']);self.assertRegex(r['error'],'Nonunique|nonmonotonic')

    def test_complete_chain_wrong_inner_mode_rejected(self):
        def mutate(u):
            d=u.get_dataset('sta_velocity_ctrl_status').data;k=int(np.searchsorted(d['timestamp'],60e6));d['inner_mode'][k]=1
        r=self.full(mutate);self.assertFalse(r['accepted'])

    def test_real_ulog_partial_tied_group_then_append_no_rows_lost(self):
        from v04_heading_stream import LiveLog
        record=json.loads((ROOT/'results08/run01.json').read_text())
        entry=max(record['logs'],key=lambda e:e['bytes'])
        self.assertEqual(digest(entry['archive']),entry['sha256'])
        raw=Path(entry['archive']).read_bytes()
        ref=json.loads((Path(entry['archive']).parent/'height_reference.json').read_text())
        frozen=json.loads((Path(entry['archive']).parent/'task_yaw.json').read_text())
        # Audited second tied record offset; also exercise an incomplete ULog frame.
        with tempfile.TemporaryDirectory(prefix='v04-p09-tail-') as tmp:
            path=Path(tmp)/'growing.ulg';cut=18472270
            path.write_bytes(raw[:cut+1]);reader=LiveLog(path)
            prefix=reader.read();a=live.AttitudeClockPolicy().data(prefix)
            self.assertEqual(int(a['timestamp'][-1]),60128000)
            before=live.replay(prefix,ref,frozen=frozen)
            self.assertLess(before['through_us'],60128000)
            with path.open('ab') as stream:stream.write(raw[cut+1:])
            complete=reader.read();after=live.replay(complete,ref,frozen=frozen)
            self.assertGreater(after['through_us'],60128000)
            a=live.AttitudeClockPolicy().data(complete)
            self.assertEqual(a['timestamp_sample'][a['timestamp']==60128000].tolist(),[60124000,60128000])
            for key,values in ULog(entry['archive']).get_dataset('vehicle_attitude').data.items():
                np.testing.assert_array_equal(values,a[key])
        self.assertFalse(record['success'])


if __name__=='__main__':unittest.main()
