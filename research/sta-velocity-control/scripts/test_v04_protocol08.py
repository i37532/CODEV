"""New batch wiring tests; synthetic flight calls only, no real simulator."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
import numpy as np
import run_v04_protocol08 as runner
from v04_protocol08 import CONFIG, TOKEN, load_protocol, require_authorization
from v04_protocol07 import load_protocol as previous_protocol


class Protocol08Test(unittest.TestCase):
    def test_exact_order_and_unchanged_rules(self):
        p, old = load_protocol(), previous_protocol()
        changed = {'stage','status','seeds','jobs','artifacts','authorization','logcheck_contract'}
        for key in set(old)-changed:
            self.assertEqual(p[key], old[key], key)
        self.assertEqual([(j['seed'],j['mode']) for j in p['jobs']],
                         [(9701,0),(9701,1),(9702,0),(9702,1),(9703,0),(9703,1)])
        self.assertTrue(p['flight_authorized']); self.assertFalse(p['automatic_retry'])

    def test_dryrun_and_wrong_token_cannot_launch(self):
        for token in ('', 'V04-protocol04-series03-six-attempts'):
            with self.assertRaises(RuntimeError): require_authorization(token, load_protocol())
        with tempfile.TemporaryDirectory(prefix='v04-p08-dry-') as tmp:
            out=Path(tmp)/'unused'
            argv=[sys.executable, str(Path(__file__).with_name('run_v04_protocol08.py')),
                  '--output',str(out),'--source-head','not-a-source']
            for extra, code in [([],0),(['--execute'],1)]:
                result=subprocess.run(argv+extra, capture_output=True, text=True)
                self.assertEqual(result.returncode,code,result.stderr);self.assertFalse(out.exists())

    def test_only_registration_paths_excluded_from_seed_history(self):
        import capture_v04_protocol08 as capture
        entries=[dict(path=str(CONFIG/'execution.json')),dict(path='/tmp/real-experiment.json')]
        with patch.object(capture,'seed_audit',return_value=dict(matches=entries,invalid_json=[])):
            result=capture.fresh_seeds()
        self.assertFalse(result['accepted']); self.assertEqual(len(result['matches']),1)

    def test_new_binding_and_old_entry_remains_disabled(self):
        import run_v04_flight09 as flight
        import run_v04_flight06 as draft
        import analyze_v04_protocol08 as analyzer
        from unittest.mock import Mock
        self.assertIs(runner.flight, flight.main)
        self.assertEqual(analyzer.CONFIG, CONFIG)
        self.assertEqual(analyzer.load_protocol(), load_protocol())
        checks=Mock(execution_permitted=True,authorization_token=TOKEN)
        with patch.object(flight.subprocess,'Popen') as spawn:
            with self.assertRaises(RuntimeError): flight.main(checks, CONFIG/'wrong.json')
            with self.assertRaises(RuntimeError): flight.main()
            with self.assertRaises(RuntimeError): draft.main(checks, CONFIG/'execution.json')
            spawn.assert_not_called()

    def test_only_handoff_rules_change(self):
        import copy
        p,old=load_protocol(),previous_protocol()
        height=copy.deepcopy(p['height_task'])
        changed={'command','param5','param6','xy','require'}
        for k in changed: height['reposition'][k]=old['height_task']['reposition'][k]
        self.assertEqual(height,old['height_task'])
        self.assertEqual(p['handoff_design']['wire']['maximum_sends'],1)
        self.assertEqual(p['handoff_design']['projection']['encoding_error_limit_m'],.02)

    def test_authorized_analyzer_uses_repaired_real_handoff_chain(self):
        import test_v04_logcheck07 as fixtures
        import analyze_v04_protocol08 as analyzer
        import analyze_v04_handoff07 as handoff
        fixtures.Logcheck07Test.setUpClass()
        f=fixtures.Logcheck07Test
        u=f.ulog
        result=analyzer.height_evidence(u,f.fixture_run,u.get_dataset('sta_velocity_ctrl_status').data,f.events)
        self.assertIs(analyzer.check_handoff,handoff.check_handoff)
        self.assertEqual(result['handoff']['event_command_rows'],4)
        self.assertEqual(result['handoff']['receiver_expected']['lon'],8.545607799999999)
        self.assertFalse(json.loads((f.fixture_run/'v04_protocol06_metrics.json').read_text())['accepted'])

    def test_historical_job_never_reclassified_by_new_batch_analyzer(self):
        import analyze_v04_protocol08 as analyzer
        from v04_protocol07 import load_protocol as old_protocol
        with tempfile.TemporaryDirectory(prefix='v04-p08-history-') as tmp:
            result=analyzer.analyze(Path(tmp),load_protocol(),old_protocol()['jobs'][0])
            self.assertFalse(result['accepted'])
            self.assertIn('not in the new frozen batch',result['error'])

    def batch(self, fail_at=None, reject=False):
        with tempfile.TemporaryDirectory(prefix='v04-p08-batch-') as tmp:
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
                    fresh_seeds=lambda:dict(accepted=True),load_protocol=lambda:p), \
                    patch.object(runner.socket,'socket'), \
                    patch.object(runner.shutil,'disk_usage',return_value=type('Space',(),{'free':20*1024**3})()), \
                    patch.object(sys,'argv',['runner','--authorization',TOKEN,'--execute','--output',str(root/'series'),'--source-head','source-test']), \
                    redirect_stdout(io.StringIO()):
                if fail_at or reject:
                    with self.assertRaises(RuntimeError):runner.main()
                else:runner.main()
            ledger=json.loads((root/'series/ledger.json').read_text())
            self.assertEqual(param.read_bytes(),b'original-full-eeprom')
            self.assertTrue(ledger['parameter_restore_exact'])
            return calls,ledger

    def test_execution_only_rebinds_batch_not_control_or_log_rules(self):
        scripts = Path(__file__).parent
        for old, new in [('run_v04_protocol07.py','run_v04_protocol08.py'),
                         ('run_v04_flight08.py','run_v04_flight09.py'),
                         ('analyze_v04_protocol07.py','analyze_v04_protocol08.py')]:
            expected = (scripts/old).read_text().replace('v04_protocol07','v04_protocol08')
            expected = expected.replace('protocol07','protocol08').replace('Protocol07','Protocol08')
            expected = expected.replace('run_v04_flight08','run_v04_flight09')
            self.assertEqual(expected, (scripts/new).read_text(), new)

    def test_snapshot_includes_repaired_conversion_and_consumers(self):
        from capture_v04_protocol08 import capture
        assets = capture()['assets']
        for path in ('src/modules/simulator/simulator_mavlink.cpp',
                     'src/lib/drivers/accelerometer/PX4Accelerometer.cpp',
                     'src/modules/sensors/vehicle_imu/VehicleIMU.cpp',
                     'src/modules/sensors/vehicle_imu/Integrator.hpp',
                     'src/modules/ekf2/EKF2Selector.cpp', 'msg/vehicle_imu.msg'):
            self.assertIn(path, assets)
        self.assertEqual(assets['src/modules/simulator/simulator_mavlink.cpp'],
                         'faad1a51786e9ebfbd21bb9ab61f2e895e22e50004e75cf4a7adad81ccf90320')
        for mode in ('pid','esta'):
            self.assertEqual((CONFIG/mode/'frozen.json').read_bytes(),
                             (CONFIG.parent/'protocol07'/mode/'frozen.json').read_bytes())

    def test_six_attempts_three_pairs_and_full_restore(self):
        calls,ledger=self.batch();self.assertEqual(len(calls),6);self.assertTrue(ledger['success'])
        self.assertEqual(len(ledger['pairs']),3)

    def test_first_required_failure_stops_no_retry(self):
        for n in (1,2):
            calls,ledger=self.batch(fail_at=n);self.assertEqual(len(calls),n);self.assertFalse(ledger['success'])
        calls,ledger=self.batch(reject=True);self.assertEqual(len(calls),1);self.assertFalse(ledger['success'])


if __name__=='__main__':unittest.main()
