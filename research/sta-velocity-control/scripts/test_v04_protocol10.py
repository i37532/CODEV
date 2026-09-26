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
import run_v04_protocol10 as runner
import analyze_v04_protocol10 as analyzer
import v04_live_clock09 as live
import v04_protocol10 as protocol_module
from v04_protocol10 import CONFIG, load_protocol, require_authorization, fingerprint, CHANGED
from v04_protocol09 import load_protocol as old_protocol
from test_v04_attitude_clock09 import heading_fixture, attitude
from test_v04_protocol04 import Log
from replay_v04_clock09 import ROOT, digest, copy_metadata


class Protocol10Test(unittest.TestCase):
    def test_rules_budget_and_parameters_unchanged(self):
        p, old = load_protocol(), old_protocol()
        for k in set(old)-CHANGED: self.assertEqual(p[k], old[k], k)
        self.assertEqual([(j['seed'],j['mode']) for j in p['jobs']],
                         [(9901,0),(9901,1),(9902,0),(9902,1),(9903,0),(9903,1)])
        for mode in ('pid','esta'):
            self.assertEqual((CONFIG/mode/'frozen.json').read_bytes(),
                             (CONFIG.parent/'protocol09'/mode/'frozen.json').read_bytes())

    def test_entry_guard_and_landing_bindings(self):
        import run_v04_flight12 as flight
        from v04_monitor10 import Checks
        self.assertIs(runner.flight, flight.main)
        self.assertIs(runner.Checks.monitor, Checks.monitor)
        self.assertIs(runner.Checks.start_heading, Checks.start_heading)
        self.assertIs(runner.Checks.begin_landing, Checks.begin_landing)
        self.assertIs(runner.Checks.landing_complete, Checks.landing_complete)
        with patch.object(flight.subprocess,'Popen') as spawn, patch.object(flight.mavutil,'mavlink_connection') as connect:
            with self.assertRaises(RuntimeError): flight.main()
            spawn.assert_not_called(); connect.assert_not_called()

    def test_only_flight_authorization_binding_changed(self):
        scripts=Path(__file__).parent
        old=(scripts/'run_v04_flight11.py').read_text()
        guard=(scripts/'run_v04_flight10.py').read_text()
        guard=guard[guard.index('    # This entry alone'):guard.index('    parser = argparse.ArgumentParser()',guard.index('def main('))]
        expected=old.replace('Offline landing10 integration, disabled before any side effects;',
                             'Protocol10 authorized landing10 integration;')
        expected=expected.replace('    raise RuntimeError("Offline landing repair only; new frozen batch and authorization required")\n',
                                  guard.replace('protocol09','protocol10'))
        self.assertEqual(expected,(scripts/'run_v04_flight12.py').read_text())

    def test_seed_audit_excludes_only_approved_design_not_real_job(self):
        import capture_v04_protocol10 as capture
        allowed=[CONFIG/'execution.json',CONFIG/'seed_audit.json',
                 CONFIG.parent/'landing10/proposal.json',CONFIG.parent/'landing10/seed_audit.json']
        matches=[dict(path=str(p)) for p in allowed]+[dict(path='/tmp/real-flight/job.json')]
        with patch.object(capture,'seed_audit',return_value=dict(matches=matches,invalid_json=[])) as audit:
            r=capture.fresh_seeds()
        audit.assert_called_once_with([9901,9902,9903])
        self.assertFalse(r['accepted']); self.assertEqual(len(r['design_registrations']),4)
        self.assertEqual(r['matches'],[dict(path='/tmp/real-flight/job.json')])

    def test_receipt_exact_new_source_budget_and_provenance(self):
        p=load_protocol()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'receipt.json'
            valid=dict(approved=True,stage=p['stage'],source_head='test-head',
                       execution_sha256=fingerprint(CONFIG/'execution.json'),maximum_attempts=6,
                       user_approval='SYNTHETIC ONLY')
            with patch.object(protocol_module.subprocess,'check_output',return_value='test-head\n'):
                path.write_text(json.dumps(valid)); self.assertEqual(require_authorization(str(path),p),valid)
                for field,value in [('approved',False),('source_head','old'),('execution_sha256','old'),
                                    ('stage','V04-protocol09-series08'),('maximum_attempts',7),('user_approval','')]:
                    path.write_text(json.dumps({**valid,field:value}))
                    with self.subTest(field=field),self.assertRaises(RuntimeError): require_authorization(str(path),p)

    def test_dry_run_and_no_receipt_have_no_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'unused'
            argv=[sys.executable,runner.__file__,'--output',str(out),'--source-head','invalid']
            for extra,code in [([],0),(['--execute'],1)]:
                r=subprocess.run(argv+extra,capture_output=True,text=True)
                self.assertEqual(r.returncode,code,r.stderr); self.assertFalse(out.exists())

    def batch(self, **kwargs):
        import test_v04_protocol09 as previous
        with patch.object(previous,'runner',runner), patch.object(previous,'load_protocol',load_protocol):
            return previous.Protocol09Test.batch(self,**kwargs)

    def test_mock_six_attempts_and_parameter_restore(self):
        calls,ledger=self.batch()
        self.assertEqual(len(calls),6); self.assertEqual(len(ledger['pairs']),3)
        self.assertTrue(ledger['success']); self.assertTrue(ledger['parameter_restore_exact'])

    def test_mock_stop_first_failure_and_final_rejection(self):
        for n in (1,2,6):
            calls,ledger=self.batch(fail_at=n)
            self.assertEqual(len(calls),n); self.assertFalse(ledger['success'])
        calls,ledger=self.batch(reject=True)
        self.assertEqual(len(calls),1); self.assertFalse(ledger['success'])

    def test_new_analyzer_refuses_old_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=analyzer.analyze(Path(tmp),load_protocol(),old_protocol()['jobs'][0])
        self.assertFalse(r['accepted']); self.assertIn('historical results',r['error'])

    def test_new_checks_environment_uses_new_authorization(self):
        p=load_protocol(); c=runner.Checks(p,{},p['jobs'][0],Path('/tmp/unused'))
        c.authorization_token='new-receipt'
        with tempfile.TemporaryDirectory() as tmp,patch.object(runner,'require_authorization',side_effect=RuntimeError('new binding')) as check:
            with self.assertRaisesRegex(RuntimeError,'new binding'): c.prepare_environment(Path(tmp))
            check.assert_called_once_with('new-receipt',p)
            self.assertEqual(list(Path(tmp).iterdir()),[])


class FullChain10Test(unittest.TestCase):
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
            events={e['name']:e['timestamp_us'] for e in r['events']}
            (run/'landing_context.json').write_text(json.dumps(dict(hover_start_us=events['hover_start'],
                hover_end_us=events['hover_end'],command_lower_us=events['land_command'],cli_success=True)))
            original_config=analyze_v00.CONFIG
            read=lambda path:u if str(path)==self.entry['archive'] else ULog(path)
            with patch.object(analyze_v00,'ULog',side_effect=read),patch.object(core,'ULog',side_effect=read),patch.object(analyzer,'ULog',side_effect=read):
                result=analyzer.analyze(run,p,job)
            self.assertEqual(analyze_v00.CONFIG,original_config)
            self.assertTrue((run/'v04_protocol10_metrics.json').exists())
        self.assertFalse(json.loads((self.source/'v04_protocol06_metrics.json').read_text())['accepted'])
        return result

    def test_complete_chain_positive_synthetic(self):
        r=self.full(); self.assertTrue(r['accepted'],r.get('error'))
        for name in ('landing10','height_task','local_output','exit'): self.assertIn(name,r)

    def test_wrong_command_rejected_by_landing_component(self):
        def mutate(u):
            d=u.get_dataset('vehicle_command').data
            i=np.flatnonzero((d['command']==176)&(d['param3']==6))[0]
            d['target_component'][i]=0
        r=self.full(mutate)
        self.assertFalse(r['accepted']); self.assertIn('target_component',r['error'])

    def test_reset_and_wrong_inner_still_rejected(self):
        for topic,field in [('vehicle_attitude','quat_reset_counter'),('sta_velocity_ctrl_status','inner_mode')]:
            def mutate(u):
                d=u.get_dataset(topic).data;i=np.searchsorted(d['timestamp'],60e6);d[field][i]+=1
            self.assertFalse(self.full(mutate)['accepted'])

if __name__=='__main__': unittest.main()
