#!/usr/bin/env python3
"""Tiny synthetic fixtures only. Never reads real experiment or ULog files."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import collect_ri05 as c


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(root, gate='C', attempted=9, failed=False):
    base, batch = root/gate, root/gate/'batch01'
    batch.mkdir(parents=True)
    source, firmware, param = 'a'*40, 'b'*64, 'c'*64
    jobs = []
    for block in range(3):
        order = [('PID',0), ('RSTA',3), ('RISTA',4)] if block != 1 else [('PID',0), ('RISTA',4), ('RSTA',3)]
        for candidate, mode in order:
            jobs.append(dict(id=f'run{len(jobs)+1+(9 if gate=="D" else 0):03d}', gate=gate,
                seed=(83001 if gate=='C' else 83101)+block, candidate=candidate, mode=mode,
                task='H' if gate=='C' else 'V', axes=0 if mode==0 else (3 if gate=='C' else 7),
                divisor=1, main_duration_s=64, parameters={'MPC_VCT_TEST':6 if gate=='C' else 8}))
    write(batch/'protocol.json', dict(jobs=jobs))
    qpath = base/'qualification02/evidence.json'
    write(qpath, dict(source_head=source, firmware_sha256=firmware, success=True, approved=True,
                     commands=[{'exit_code':0}], counts={'cpp':711,'python':904}))
    write(batch/'qualification_reference.json', dict(path=str(qpath),sha256=sha(qpath)))
    ledger = dict(stage='RI05-'+gate, revision='ri05', gate=gate, source_head=source, firmware_sha256=firmware,
        planned=9,total_budget=18,new_planned=9,prior_attempts=0, attempts=[],pairs=[],
        original_parameter_sha256=param,parameter_restore_exact=True,remaining_simulators=[],
        success=attempted==9 and not failed,unattempted=[j['id'] for j in jobs[attempted:]])
    for index, job in enumerate(jobs[:attempted]):
        run = batch/job['id']; run.mkdir()
        logs=[]
        for name in ('startup.ulg','main.ulg'):
            path=run/name; path.write_bytes((job['id']+name).encode())
            logs.append(dict(archive=str(path),source='/dev/shm/old/'+name,sha256=sha(path),bytes=path.stat().st_size,
                             durable_copy_verified=True,volatile_source_retained=True))
        n = .01 + .001*(index//3)
        window=dict(error=dict(rmse=[n,n*2,n*3],mean=[.001]*3,variance=[.0001]*3,std=[.01]*3,max_abs=[.1]*3),
            J=n*2,seconds=64,samples=6400,actual_updates=6400,iae_m=[.1]*3,
            correction_tv=[10.,20.,30.],correction_tv_per_second=[1.,2.,3.],
            acceleration_tv=[11.,21.,31.],acceleration_tv_per_second=[1.1,2.1,3.1],
            normalized_thrust_tv=[.1,.2,.3],normalized_thrust_tv_per_second=[.01,.02,.03],
            constraint_fraction=.02,maximum_continuous_constraint_s=.05,
            nu_peak={} if job['mode']==0 else {'X':.1,'Y':.2,**({'Z':.3} if gate=='D' else {})})
        diagnostic=copy.deepcopy(window)
        diagnostic['windows']={k:{**copy.deepcopy(window),'seconds':32} for k in ('first_half','second_half')}
        metrics=dict(accepted=True,job=job,diagnostic=diagnostic,position_rmse=[.1,.2,.3],height=dict(rmse=.2,mean=.01,std=.19,max_abs=.5),
            yaw_rmse=.01,spectral_summary=dict(update_hz=100,common_0_7hz_rms=[.1,.2,.3],notes=['frozen']),
            flight=dict(sample_hz=100,cadence={'flight_accepted':False,'actual_mode':job['mode']}),
            observation=dict(sample_hz=100), lifecycle=dict(hte_shift_count=1,hte_shift_max_abs=.01,actual_algorithms=[job['mode']]),
            host_cost={p:{'median_us':1.,'p95_us':2.,'p99_us':3.,'max_us':4.} for p in ('path_ns','module_ns')},
            binding=dict(source_head=source,firmware_sha256=firmware,stage='RI05-'+gate,revision='ri05'))
        write(run/'r03_metrics.json',metrics); write(run/'spectra.json',{'tiny_fixture':[1,2,3]})
        write(run/'parameter_restore.json',dict(source_head=source,job_id=job['id'],gate=gate,
            original_parameter_sha256=param,restored_parameter_sha256=param,parameter_restore_exact=True,
            remaining_simulators=[],stopped_before_restore=True))
        write(run/'result.json',dict(source_head=source,binary_sha256=firmware,success=True,logs=logs,
            events=[{'name':n,'timestamp_us':i} for i,n in enumerate(('takeoff_command','hover_start','hover_end','landed_disarmed'))]))
        with (run/'samples.jsonl').open('w') as stream:
            for z,armed,landed in ((0,1,True),(-2.5,2,False),(0,1,True)):
                stream.write(json.dumps(dict(position=dict(z=z,timestamp=1000),status=dict(arming_state=armed),land=dict(landed=landed)))+'\n')
        status='failed' if failed and index==attempted-1 else 'accepted'
        ledger['attempts'].append(dict(attempt=index+1,job=job,directory=str(run),status=status,metrics_sha256=sha(run/'r03_metrics.json')))
    metrics={j['id']:read(batch/j['id']/'r03_metrics.json') for j in jobs[:attempted]}
    for item in ledger['attempts']:
        job=item['job']
        if job['mode'] and item['status']=='accepted':
            pid=next(j for j in jobs if j['seed']==job['seed'] and j['mode']==0)
            ledger['pairs'].append(c.pair_risk(metrics[pid['id']],metrics[job['id']]))
    write(batch/'ledger.json',ledger)
    if ledger['success']:
        make_replay(root,gate)
    return jobs


def make_replay(root,gate):
    base=root/gate; batch=base/'batch01'; replay=base/'replay01'; replay.mkdir(exist_ok=True)
    ledger=read(batch/'ledger.json'); commands=[]
    for item in ledger['attempts']:
        name=item['job']['id']; run=batch/name; destination=replay/name; destination.mkdir(exist_ok=True)
        for filename in ('r03_metrics.json','spectra.json'):
            (destination/filename).write_bytes((run/filename).read_bytes())
        log=replay/(name+'.log'); log.write_text('synthetic decoder exit 0\n')
        commands.append(dict(argv=['/usr/bin/python3','-B','/repo/ri05/tools/analyzer.py',str(run),'--output',str(destination)],
                             returncode=0,log=str(log),log_sha256=sha(log)))
    snapshot=c.Evidence().tree(batch)
    summary=dict(stage=ledger['stage'],revision='ri05',gate=gate,source_head=ledger['source_head'],
        qualified_firmware_sha256=ledger['firmware_sha256'],success=True,new_flights=0,replayed=9,
        source_inputs_unchanged=True,ledger_sha256=sha(batch/'ledger.json'),commands=commands,pairs=ledger['pairs'],
        original_input_sha256_before=snapshot,original_input_sha256_after=snapshot)
    write(replay/'summary.json',summary)
    write(base/'gate_pass.json',dict(stage=ledger['stage'],revision='ri05',gate=gate,accepted=True,
        planned=9,attempts=9,accepted_runs=9,independent_replays=9,paired_checks=6,missing=0,
        source_head=ledger['source_head'],firmware_sha256=ledger['firmware_sha256'],ledger_sha256=sha(batch/'ledger.json'),
        replay_summary_path=str(replay/'summary.json'),replay_summary_sha256=sha(replay/'summary.json'),
        parameter_restore_exact=True,new_flights_by_replay=0))


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ri05-collector-fixture-')
        self.root=Path(self.tmp.name)/'data'
        self.output=Path(self.tmp.name)/'output'
        self.jobs=fixture(self.root)
        self.batch=self.root/'C/batch01'

    def tearDown(self):
        self.tmp.cleanup()

    def collect(self,gate='C'):
        return c.collect(gate,self.output,self.root)

    def mutate(self,path,fn):
        value=read(path);fn(value);write(path,value)

    def test_complete_xy_gate(self):
        result=self.collect()
        self.assertTrue(result['gate_passed'],result['issues'])
        self.assertEqual(result['counts']['airborne_confirmed'],9)
        self.assertEqual(result['counts']['independent_replays'],9)
        self.assertEqual(result['counts']['paired_risk_checks'],6)

    def test_complete_xyz_gate_is_separate(self):
        fixture(self.root,'D');result=self.collect('D')
        self.assertTrue(result['gate_passed'],result['issues'])
        self.assertEqual(result['milestone_gate'],'B')
        self.assertEqual(result['runs'][0]['id'],'run010')

    def test_all_logs_not_only_main_indexed(self):
        self.collect();index=read(self.output/'ulog_index.json')
        self.assertEqual(index['log_count'],18);self.assertEqual(index['verified_count'],18)
        self.assertTrue(any(x['actual']['path'].endswith('startup.ulg') for x in index['files']))

    def test_aggregate_is_per_run_and_half_windows_exist(self):
        result=self.collect();s=result['groups']['PID']['statistics']
        self.assertAlmostEqual(s['diagnostic.error.rmse']['mean'][0],.011)
        self.assertEqual(s['diagnostic.error.rmse']['n'],3)
        self.assertIn('diagnostic.windows.first_half.error.rmse',s)
        self.assertNotIn('diagnostic.nu_peak.X',s)

    def test_partial_failed_preserves_missing_without_zero(self):
        root=Path(self.tmp.name)/'partial';fixture(root,attempted=2,failed=True)
        result=c.collect('C',self.output,root)
        self.assertFalse(result['gate_passed']);self.assertTrue(result['collection_ok'],result['issues'])
        self.assertEqual(result['counts']['failed'],1);self.assertEqual(result['counts']['unattempted'],7)
        self.assertEqual(result['groups']['RSTA']['statistics'],{})
        self.assertEqual(result['groups']['RISTA']['accepted_for_descriptive_means'],0)

    def test_missing_replay_and_receipt_not_a_pass(self):
        (self.root/'C/gate_pass.json').unlink()
        (self.root/'C/replay01/summary.json').unlink()
        result=self.collect()
        self.assertFalse(result['gate_passed']);self.assertTrue(result['collection_ok'],result['issues'])
        self.assertEqual(result['status'],'partial_or_not_finalized')

    def test_partial_failed_replay_is_retained(self):
        (self.root/'C/gate_pass.json').unlink()
        self.mutate(self.root/'C/replay01/summary.json',lambda d:d.update(success=False,replayed=4,error='fixture'))
        result=self.collect()
        self.assertFalse(result['gate_passed']);self.assertTrue(result['collection_ok'],result['issues'])
        self.assertEqual(result['replay']['summary']['error'],'fixture')

    def test_takeoff_command_not_airborne(self):
        path=self.batch/'run001/samples.jsonl'
        path.write_text(json.dumps(dict(position=dict(z=0),status=dict(arming_state=2),land=dict(landed=True)))+'\n')
        result=self.collect()
        self.assertEqual(result['counts']['takeoff_commanded'],9)
        self.assertEqual(result['counts']['airborne_confirmed'],8)
        self.assertEqual(result['counts']['airborne_unknown'],1)
        self.assertFalse(result['gate_passed'])

    def test_missing_samples_unknown_not_zero(self):
        (self.batch/'run001/samples.jsonl').unlink()
        result=self.collect()
        self.assertIsNone(result['runs'][0]['airborne']['confirmed'])
        self.assertFalse(result['gate_passed'])

    def test_ulog_corruption_detected(self):
        (self.batch/'run003/main.ulg').write_bytes(b'changed')
        result=self.collect();self.assertFalse(result['collection_ok'])
        self.assertTrue(any('ULog digest' in x for x in result['issues']))

    def test_metrics_digest_corruption_detected(self):
        self.mutate(self.batch/'run002/r03_metrics.json',lambda d:d.update(yaw_rmse=.02))
        result=self.collect();self.assertFalse(result['gate_passed'])
        self.assertTrue(any('Metrics SHA' in x for x in result['issues']))

    def test_wrong_metrics_binding_detected(self):
        self.mutate(self.batch/'run002/r03_metrics.json',lambda d:d['binding'].update(source_head='d'*40))
        result=self.collect();self.assertFalse(result['gate_passed'])
        self.assertTrue(any('qualification binding' in x for x in result['issues']))

    def test_missing_required_metric_not_imputed(self):
        self.mutate(self.batch/'run003/r03_metrics.json',lambda d:d.pop('position_rmse'))
        result=self.collect();self.assertFalse(result['gate_passed'])
        self.assertFalse(result['runs'][2]['included_in_accepted_means'])

    def test_scalar_rmse_cannot_masquerade_as_vector(self):
        self.mutate(self.batch/'run003/r03_metrics.json',lambda d:d['diagnostic']['error'].update(rmse=.01))
        result=self.collect();self.assertFalse(result['gate_passed'])
        self.assertFalse(result['runs'][2]['included_in_accepted_means'])

    def test_seed_order_corruption_is_rejected(self):
        self.mutate(self.batch/'protocol.json',lambda d:d['jobs'][0].update(seed=99999))
        result=self.collect();self.assertFalse(result['gate_passed'])
        self.assertTrue(any('scope/seed/order' in x for x in result['issues']))

    def test_d_requires_bound_c_receipt(self):
        fixture(self.root,'D');(self.root/'C/gate_pass.json').unlink()
        result=self.collect('D');self.assertFalse(result['gate_passed'])
        self.assertTrue(any('Missing required JSON' in x for x in result['issues']))

    def test_nonfinite_primary_stat_is_invalid(self):
        self.mutate(self.batch/'run001/r03_metrics.json',lambda d:d['diagnostic']['error'].update(rmse=[float('nan'),1,1]))
        result=self.collect();self.assertFalse(result['gate_passed'])
        self.assertFalse(result['runs'][0]['included_in_accepted_means'])
        self.assertIn('nonfinite_float',(self.output/'summary.json').read_text())

    def test_nonfinite_diagnostic_display_is_tagged_not_imputed(self):
        self.assertEqual(c.view({'x':float('inf')}),{'x':{'nonfinite_float':'Infinity'}})
        self.assertEqual(c.view({'x':float('-inf')}),{'x':{'nonfinite_float':'-Infinity'}})

    def test_existing_output_not_overwritten(self):
        self.output.mkdir();(self.output/'keep').write_text('mine')
        with self.assertRaises(ValueError):self.collect()
        self.assertEqual((self.output/'keep').read_text(),'mine')

    def test_output_under_source_is_rejected(self):
        with self.assertRaises(ValueError):c.collect('C',self.root/'C/results',self.root)

    def test_running_gate_refuses_heavy_hash(self):
        self.mutate(self.batch/'ledger.json',lambda d:d['attempts'][-1].update(status='running'))
        with self.assertRaisesRegex(ValueError,'running'):self.collect()
        self.assertFalse(self.output.exists())

    def test_live_simulator_marker_refuses_collection(self):
        self.mutate(self.batch/'ledger.json',lambda d:d.update(remaining_simulators=[123]))
        with self.assertRaisesRegex(ValueError,'cleanup'):self.collect()

    def test_parameter_restore_mismatch_detected(self):
        self.mutate(self.batch/'run003/parameter_restore.json',lambda d:d.update(restored_parameter_sha256='d'*64))
        result=self.collect();self.assertFalse(result['gate_passed'])
        self.assertTrue(any('restore mismatch' in x for x in result['issues']))

    def test_stale_receipt_sha_detected(self):
        self.mutate(self.root/'C/gate_pass.json',lambda d:d.update(ledger_sha256='0'*64))
        result=self.collect();self.assertFalse(result['gate_passed'])

    def test_bad_replay_command_detected(self):
        self.mutate(self.root/'C/replay01/summary.json',lambda d:d['commands'][0].update(returncode=1))
        result=self.collect();self.assertFalse(result['gate_passed'])
        self.assertTrue(any('Replay command mismatch' in x for x in result['issues']))

    def test_replay_snapshot_catches_changed_sidecar(self):
        (self.batch/'extra.txt').write_text('new file')
        result=self.collect();self.assertFalse(result['gate_passed'])
        self.assertTrue(any('input inventory' in x for x in result['issues']))

    def test_relative_change_zero_reference_not_divided(self):
        rows=[dict(id='a',seed=1,candidate='RSTA',included_in_accepted_means=True,statistics={'diagnostic.error.rmse':[0,1,2]}),
              dict(id='b',seed=1,candidate='RISTA',included_in_accepted_means=True,statistics={'diagnostic.error.rmse':[1,2,3]})]
        self.assertIsNone(c.descriptive_pairs(rows)[0]['relative_change_percent'][0])

    def test_collector_does_not_rewrite_inputs(self):
        before=c.Evidence().tree(self.root)
        self.collect()
        self.assertEqual(before,c.Evidence().tree(self.root))

    def test_evidence_inventory_includes_sidecars(self):
        self.collect();paths=[x['path'] for x in read(self.output/'evidence_index.json')['files']]
        self.assertIn(str(self.batch/'run001/samples.jsonl'),paths)
        self.assertIn(str(self.batch/'run001/parameter_restore.json'),paths)
        self.assertIn(str(self.root/'C/qualification02/evidence.json'),paths)

    def test_all_zero_metric_is_valid_not_missing(self):
        issues=[];m=read(self.batch/'run001/r03_metrics.json')
        m['diagnostic']['error']['rmse']=[0.,0.,0.]
        result=c.statistics_view(m,issues)
        self.assertEqual(result['diagnostic.error.rmse'],[0.,0.,0.]);self.assertEqual(issues,[])

    def test_cost_units_and_position_scope_disclosed(self):
        result=self.collect();notes=' '.join(result['notes'])
        self.assertIn('microsecond',notes);self.assertIn('preceding measurement',notes)
        self.assertIn('not same-sample',notes)


if __name__=='__main__':
    unittest.main(verbosity=2)
