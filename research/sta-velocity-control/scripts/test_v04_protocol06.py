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
import run_v04_protocol06 as runner
from v04_protocol06 import CONFIG, TOKEN, load_protocol, require_authorization
from v04_protocol05 import load_protocol as previous_protocol


class Protocol06Test(unittest.TestCase):
    def test_exact_order_and_unchanged_rules(self):
        p, old = load_protocol(), previous_protocol()
        changed = {'stage','status','flight_authorized','seeds','jobs','artifacts','authorization','handoff_contract','height_task','handoff_design'}
        for key in set(old)-changed:
            self.assertEqual(p[key], old[key], key)
        self.assertEqual([(j['seed'],j['mode']) for j in p['jobs']],
                         [(9501,0),(9501,1),(9502,0),(9502,1),(9503,0),(9503,1)])
        self.assertTrue(p['flight_authorized']); self.assertFalse(p['automatic_retry'])

    def test_dryrun_and_wrong_token_cannot_launch(self):
        for token in ('', 'V04-protocol04-series03-six-attempts'):
            with self.assertRaises(RuntimeError): require_authorization(token, load_protocol())
        with tempfile.TemporaryDirectory(prefix='v04-p06-dry-') as tmp:
            out=Path(tmp)/'unused'
            argv=[sys.executable, str(Path(__file__).with_name('run_v04_protocol06.py')),
                  '--output',str(out),'--source-head','not-a-source']
            for extra, code in [([],0),(['--execute'],1)]:
                result=subprocess.run(argv+extra, capture_output=True, text=True)
                self.assertEqual(result.returncode,code,result.stderr);self.assertFalse(out.exists())

    def test_only_registration_paths_excluded_from_seed_history(self):
        import capture_v04_protocol06 as capture
        entries=[dict(path=str(CONFIG/'execution.json')),dict(path='/tmp/real-experiment.json')]
        with patch.object(capture,'seed_audit',return_value=dict(matches=entries,invalid_json=[])):
            result=capture.fresh_seeds()
        self.assertFalse(result['accepted']); self.assertEqual(len(result['matches']),1)

    def test_new_binding_and_old_entry_remains_disabled(self):
        import run_v04_flight07 as flight
        import run_v04_flight06 as draft
        import analyze_v04_protocol06 as analyzer
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

    def test_authorized_analyzer_uses_verified_handoff_chain(self):
        import test_v04_handoff06 as fixtures
        import analyze_v04_protocol06 as analyzer
        from unittest.mock import patch
        with patch('analyze_v04_flight06.height_evidence',analyzer.height_evidence):
            result=fixtures.Handoff06Test().chain()
        self.assertIn('handoff',result)

    def batch(self, fail_at=None, reject=False):
        with tempfile.TemporaryDirectory(prefix='v04-p06-batch-') as tmp:
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

    def test_six_attempts_three_pairs_and_full_restore(self):
        calls,ledger=self.batch();self.assertEqual(len(calls),6);self.assertTrue(ledger['success'])
        self.assertEqual(len(ledger['pairs']),3)

    def test_first_required_failure_stops_no_retry(self):
        for n in (1,2):
            calls,ledger=self.batch(fail_at=n);self.assertEqual(len(calls),n);self.assertFalse(ledger['success'])
        calls,ledger=self.batch(reject=True);self.assertEqual(len(calls),1);self.assertFalse(ledger['success'])


if __name__=='__main__':unittest.main()
