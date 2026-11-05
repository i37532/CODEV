"""Exercise real RI07 runtime parameter/independent-replay transaction offline."""
import contextlib
import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent/'tools'))
import bindings as b
r=b.local('runner');p=b.api()

class Transaction(unittest.TestCase):
    def exercise(self,failure):
        with tempfile.TemporaryDirectory(prefix='ri07-offline-') as temp:
            root=Path(temp);rootfs=root/'rootfs';(rootfs/'eeprom').mkdir(parents=True)
            binary=root/'bin';binary.mkdir();(binary/'px4').write_bytes(b'non-executable test fixture')
            proto=p.load_protocol();proto['artifacts']['new_run_root']=str(root/'FORMAL/batch01')
            proto.update(plugins=str(root/'plugins'),execution_path=str(root/'execution.json'),config_dir=str(root/'config'))
            values={**proto['jobs'][0]['parameters'],'SDLOG_PROFILE':1,'UNRELATED_USER':7.5}
            table={k:'Int32' if type(v) is int else 'Float' for k,v in values.items()}
            param=rootfs/'eeprom/parameters_10016';original=r.historical.encode_bson(values,table);param.write_bytes(original)
            definitions=root/'build/px4_sitl_default/parameters.json';definitions.parent.mkdir(parents=True)
            b.save(definitions,dict(parameters=[dict(name=k,type=table[k],default=v) for k,v in values.items()]))
            qualification=root/'qualification/evidence.json';qualification.parent.mkdir()
            qualified=dict(firmware_sha256=b.digest(binary/'px4'))
            b.save(qualification,qualified);b.save(qualification.parent/'authorization.json',dict(approved=True))
            api=types.SimpleNamespace(require_qualification=lambda *args:qualified,valid_gate=p.valid_gate,
                stage=p.stage,jobs=p.jobs,budget=p.budget,job_protocol=p.job_protocol)
            calls=[];replays=[]
            class Checks:
                def __init__(self,proto,expected,j,*args):self.job=j;self.log_root=root/'fake_ram'
            def flight(run,checks,scenario):
                calls.append(checks.job['id']);run.mkdir()
                current=r.historical.persisted_bson(param.read_bytes())
                self.assertEqual(current['UNRELATED_USER'],7.5);self.assertEqual(current['SDLOG_PROFILE'],3089)
                self.assertEqual(current['MPC_VC_MODE'],checks.job['mode'])
                self.assertEqual(current['MPC_VCT_TEST'],checks.job['parameters']['MPC_VCT_TEST'])
                if failure=='startup':raise RuntimeError('synthetic startup failure')
                if failure=='rewrite':param.write_bytes(b'fake firmware persistent change')
            def analyze(run,proto,j):
                self.assertEqual(param.read_bytes(),original)
                m=dict(job=j,accepted=failure!='analysis');b.save(run/'r03_metrics.json',m);b.save(run/'spectra.json',{})
                return m
            def independent(argv,**kwargs):
                replays.append(argv);source=Path(argv[3]);dest=Path(argv[5]);dest.mkdir(parents=True)
                for name in ('r03_metrics.json','spectra.json'):(dest/name).write_bytes((source/name).read_bytes())
                if failure=='mismatch':b.save(dest/'spectra.json',dict(tampered=True))
                return types.SimpleNamespace(returncode=1 if failure=='replay' else 0)
            restore=b.clone(b.OLD_RUNNER.restore_parameters,active_simulators=lambda:[])
            jobs={j['id']:j for j in proto['jobs']}
            with contextlib.ExitStack() as stack:
                for name,value in dict(ROOTFS=rootfs,BIN=binary,REPO=root,api=lambda:api,active_simulators=lambda:[],
                    restore_parameters=restore,execution_checks_class=lambda:Checks).items():stack.enter_context(patch.object(r,name,value))
                stack.enter_context(patch.object(r,'precheck',return_value=(qualified,dict(control_parameters=values),dict(accepted=True))))
                stack.enter_context(patch.object(r.historical,'git',side_effect=lambda *args:'' if args[0]=='status' else 'a'*40))
                stack.enter_context(patch.object(r.historical,'noise_prefix',side_effect=lambda run:np.array([float(jobs[run.name]['seed'])])))
                stack.enter_context(patch.object(r.historical.shutil,'disk_usage',return_value=types.SimpleNamespace(free=100*1024**3)))
                stack.enter_context(patch.object(b.RAM_LOG,'release_archived'))
                stack.enter_context(patch.object(r.subprocess,'run',side_effect=independent))
                kwargs=dict(single_flight=flight,analyze=analyze,compare=lambda x,y:dict(accepted=True))
                if failure in ('startup','analysis','replay','mismatch'):
                    with self.assertRaises(RuntimeError):r._execute_gate(proto,'a'*40,qualification,**kwargs)
                else:self.assertTrue(r._execute_gate(proto,'a'*40,qualification,**kwargs)['success'])
            self.assertEqual(param.read_bytes(),original)
            ledger=b.read(Path(proto['artifacts']['new_run_root'])/'ledger.json')
            self.assertTrue(ledger['parameter_restore_exact']);self.assertEqual(ledger['remaining_simulators'],[])
            stopped=failure in ('startup','analysis','replay','mismatch')
            self.assertEqual(len(calls),1 if stopped else 200)
            self.assertEqual(len(ledger['unattempted']),199 if stopped else 0)
            self.assertEqual(len(replays),0 if failure in ('startup','analysis') else 1 if stopped else 200)
    def test_actual_parameter_transaction_all200(self):self.exercise(None)
    def test_startup_failure_restores_stops(self):self.exercise('startup')
    def test_analysis_failure_restores_stops(self):self.exercise('analysis')
    def test_replay_failure_stops_before_next(self):self.exercise('replay')
    def test_replay_mismatch_stops_before_next(self):self.exercise('mismatch')
    def test_firmware_parameter_rewrites_restored(self):self.exercise('rewrite')

if __name__=='__main__':unittest.main()
