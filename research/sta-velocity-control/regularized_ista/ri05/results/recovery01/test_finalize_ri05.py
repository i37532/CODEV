#!/usr/bin/env python3
"""Tiny receipt fixtures only; no real evidence, ULog, git, build or simulator."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import finalize_ri05 as f

D_SOURCE='d'*40  # Fake recovered commit; no real git, flight or current seed use.
SOURCES={'C':f.C_SOURCE,'D':D_SOURCE}


def raw(value):
    return (json.dumps(value,indent=2)+'\n').encode()


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw(value))


def read(path):
    return json.loads(path.read_text())


def fixture(root, alter_manifest=None):
    data,results=root/'data',root/'results'
    jobs=[]
    params=dict(MPC_VC_MODE=0,MPC_VC_AXES=0,MPC_VC_DIV=1,MPC_VCT_TEST=8,
                MC_RTC_MODE=0,MC_STA_AXES=0,MC_RTC_DIV=1,MC_RATT_TEST=0,MC_STA_TKO_MGT=0)
    params.update({f'FIXTURE_{n:03d}':float(n) for n in range(127-len(params))})
    for gate in ('C','D'):
        for block in range(3):
            order=('PID','RISTA','RSTA') if block==1 else ('PID','RSTA','RISTA')
            for name in order:
                mode=f.MODES[name];axes=0 if mode==0 else (3 if gate=='C' else 7)
                p={**params,'MPC_VC_MODE':mode,'MPC_VC_AXES':axes,'MPC_VCT_TEST':6 if gate=='C' else 8}
                jobs.append(dict(id=f'run{len(jobs)+1:03d}',gate=gate,seed=(83001 if gate=='C' else 83101)+block,
                                 candidate=name,mode=mode,axes=axes,task='H' if gate=='C' else 'V',
                                 divisor=1,main_duration_s=64,parameters=p))
    if alter_manifest:alter_manifest(jobs)
    raw_manifest=raw(jobs)
    frozen=dict(stage='RI05-D',gate='D',revision='ri05',derived_iris_sha256='9'*64,
        assets={f.REL+'/manifest.json':f.digest(raw_manifest)},budget=dict(maximum_attempts=9,
        new_matrix_attempts=9,total_maximum_attempts=18,historical_attempts=0,required_pairs=6,
        required_replays=9,n_per_algorithm=3,logging_profile=3089))
    snapshots={'D':frozen,'C':{**frozen,'stage':'RI05-C','gate':'C'}}
    receipts={}
    for gate in ('C','D'):
        group=[j for j in jobs if j['gate']==gate];fw=('c' if gate=='C' else 'd')*64
        checks={k:True for k in {'yaw'}|{p+str(a) for p in ('velocity_','position_','first_half_velocity_','second_half_velocity_') for a in range(3)}}
        pairs=[dict(gate=gate,seed=j['seed'],candidate=j['candidate'],accepted=True,checks=checks) for j in group if j['mode']]
        ledger=dict(stage='RI05-'+gate,gate=gate,revision='ri05',source_head=SOURCES[gate],firmware_sha256=fw,
            success=True,parameter_restore_exact=True,remaining_simulators=[],unattempted=[],planned=9,
            new_planned=9,total_budget=18,prior_attempts=0,pairs=pairs,
            attempts=[dict(attempt=i,job=j,status='accepted') for i,j in enumerate(group,1)])
        write(data/gate/'batch01/ledger.json',ledger)
        replay=dict(success=True,replayed=9,new_flights=0,source_inputs_unchanged=True,source_head=SOURCES[gate],
            qualified_firmware_sha256=fw,ledger_sha256=f.digest(raw(ledger)),pairs=pairs,
            original_input_sha256_before={'files':{},'links':{}},original_input_sha256_after={'files':{},'links':{}},
            commands=[{'returncode':0} for _ in range(9)])
        replay_path=data/gate/'replay01/summary.json';write(replay_path,replay)
        receipt=dict(stage='RI05-'+gate,gate=gate,source_head=SOURCES[gate],firmware_sha256=fw,accepted=True,
            planned=9,attempts=9,accepted_runs=9,independent_replays=9,paired_checks=6,missing=0,
            parameter_restore_exact=True,new_flights_by_replay=0,ledger_sha256=f.digest(raw(ledger)),
            replay_summary_sha256=f.digest(raw(replay)),replay_summary_path=str(replay_path))
        write(data/gate/'gate_pass.json',receipt);receipts[gate]=receipt
        counts=dict(planned=9,attempted=9,takeoff_commanded=9,airborne_confirmed=9,airborne_unknown=0,
            declared_accepted=9,accepted_verified=9,failed=0,unattempted=0,missing_accepted=0,
            independent_replays=9,paired_risk_checks=6)
        rows=[dict(id=j['id'],seed=j['seed'],candidate=j['candidate'],attempted=True,declared_status='accepted',
                   included_in_accepted_means=True,airborne={'confirmed':True},landed_disarmed_observed=True,evidence_issues=[]) for j in group]
        q=dict(source_head=SOURCES[gate],firmware_sha256=fw,success=True,approved=True,clean=True,commands=[{'exit_code':0}])
        full_q={**q,'gate':gate,'new_flights':0,'frozen_sha256':f.digest(raw(snapshots[gate]))}
        qpath=data/gate/('qualification01' if gate=='C' else 'qualification02')/'evidence.json'
        write(qpath,full_q)
        qref=dict(path=str(qpath),sha256=f.digest(raw(full_q)))
        write(data/gate/'batch01/qualification_reference.json',qref)
        write(qpath.parent/'authorization.json',dict(approved=True,gate=gate,stage='RI05-'+gate,
            source_head=SOURCES[gate],firmware_sha256=fw,qualification_sha256=qref['sha256'],
            frozen_sha256=full_q['frozen_sha256'],maximum_attempts=9,total_maximum_attempts=18))
        summary=dict(stage='RI05-'+gate,gate=gate,status='passed',gate_passed=True,collection_ok=True,issues=[],
            source_head=SOURCES[gate],firmware_sha256=fw,gate_receipt=receipt,counts=counts,
            parameter_restore_exact=True,remaining_simulators=[],runs=rows,independent_numeric_pairs=pairs,qualification=q,
            prior_gate_receipt=receipts.get('C') if gate=='D' else None)
        write(results/gate/'summary.json',summary)
        write(results/gate/'ulog_index.json',dict(log_count=9,verified_count=9,files=[dict(verified=True,
            gate=gate,job_id=j['id'],source_head=SOURCES[gate],firmware_sha256=fw) for j in group]))
    blobs={f.REL+'/manifest.json':raw_manifest,**{f.REL+'/gates/'+g+'/frozen.json':raw(s) for g,s in snapshots.items()}}
    def loader(source,path):
        if source not in (SOURCES['C'],SOURCES['D'],f.STOPPED_D_SOURCE):raise ValueError('Wrong committed source')
        return blobs[path]
    return results,data,loader


class FinalizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ri05-final-fixture-');self.root=Path(self.tmp.name)
        self.results,self.data,self.loader=fixture(self.root)
        self.output=self.root/'new-output'

    def tearDown(self):self.tmp.cleanup()

    def run_check(self):return f.run(self.results,self.data,self.output,loader=self.loader,d_source=D_SOURCE)

    def mutate(self,path,fn):
        value=read(path);fn(value);write(path,value)

    def reject(self):
        with self.assertRaises((ValueError,KeyError,FileNotFoundError)):self.run_check()
        self.assertFalse(self.output.exists())

    def test_complete_exports_three_full_configs_without_flight_authority(self):
        receipt=self.run_check();self.assertEqual(receipt['total_accepted'],18)
        q=read(self.output/'qualified_xyz.json');self.assertFalse(q['new_flight_authorization'])
        self.assertEqual(set(q['configurations']),{'PID','RSTA','RISTA'})
        for config in q['configurations'].values():
            self.assertEqual(len(config['parameters']),127);self.assertEqual(config['parameters']['MPC_VCT_TEST'],8)
            self.assertEqual(config['cross_seed_parameter_difference_keys'],[])
        self.assertEqual(q['configurations']['PID']['source_job_id'],'run010')
        self.assertEqual(q['configurations']['RSTA']['source_job_id'],'run011')
        self.assertEqual(q['configurations']['RISTA']['source_job_id'],'run012')

    def test_c_and_d_versions_preserved_separately(self):
        r=self.run_check();self.assertNotEqual(r['per_gate']['C']['source_head'],r['per_gate']['D']['source_head'])

    def test_d_missing_refuses_without_output(self):
        (self.results/'D/summary.json').unlink();self.reject()

    def test_d_partial_refuses_without_output(self):
        self.mutate(self.results/'D/summary.json',lambda d:d.update(gate_passed=False,status='partial_or_not_finalized'));self.reject()

    def test_c_partial_also_refuses(self):
        self.mutate(self.results/'C/summary.json',lambda d:d['counts'].update(accepted_verified=8));self.reject()

    def test_stale_gate_hash_rejected(self):
        self.mutate(self.data/'D/batch01/ledger.json',lambda d:d.update(total_budget=19));self.reject()

    def test_wrong_source_rejected(self):
        self.mutate(self.results/'D/summary.json',lambda d:d.update(source_head='0'*40));self.reject()

    def test_firmware_mismatch_rejected(self):
        self.mutate(self.results/'D/summary.json',lambda d:d.update(firmware_sha256='0'*64));self.reject()

    def test_restore_false_rejected(self):
        self.mutate(self.results/'D/summary.json',lambda d:d.update(parameter_restore_exact=False));self.reject()

    def test_unknown_airborne_not_accepted(self):
        self.mutate(self.results/'D/summary.json',lambda d:d['runs'][0]['airborne'].update(confirmed=None));self.reject()

    def test_wrong_predecessor_receipt_rejected(self):
        self.mutate(self.results/'D/summary.json',lambda d:d['prior_gate_receipt'].update(source_head='0'*40));self.reject()

    def test_failed_pair_rejected(self):
        self.mutate(self.results/'D/summary.json',lambda d:d['independent_numeric_pairs'][0]['checks'].update(yaw=False));self.reject()

    def test_unverified_ulog_index_rejected(self):
        self.mutate(self.results/'D/ulog_index.json',lambda d:d['files'][0].update(verified=False));self.reject()

    def test_qualification_failure_rejected(self):
        self.mutate(self.results/'D/summary.json',lambda d:d['qualification']['commands'][0].update(exit_code=1));self.reject()

    def test_cross_seed_parameter_change_rejected(self):
        def alter(jobs):jobs[13]['parameters']['FIXTURE_000']=999.
        self.results,self.data,self.loader=fixture(self.root/'modified',alter)
        self.reject()

    def test_missing_task_parameter_rejected(self):
        def alter(jobs):
            for j in jobs:
                if j['gate']=='D':j['parameters'].pop('MPC_VCT_TEST')
        self.results,self.data,self.loader=fixture(self.root/'modified',alter);self.reject()

    def test_unexpected_per_algorithm_tuning_rejected(self):
        def alter(jobs):
            for j in jobs:
                if j['gate']=='D' and j['candidate']=='RISTA':j['parameters']['FIXTURE_000']=999.
        self.results,self.data,self.loader=fixture(self.root/'modified',alter);self.reject()

    def test_changed_seed_not_accepted(self):
        def alter(jobs):jobs[13]['seed']=99999
        self.results,self.data,self.loader=fixture(self.root/'modified',alter);self.reject()

    def test_manifest_hash_mismatch_rejected(self):
        old=self.loader
        def loader(source,path):
            value=json.loads(old(source,path))
            if path.endswith('/manifest.json'):value[0]['extra']='tamper'
            return raw(value)
        self.loader=loader;self.reject()

    def test_output_not_overwritten(self):
        self.output.mkdir();keep=self.output/'keep';keep.write_text('user')
        with self.assertRaises(ValueError):self.run_check()
        self.assertEqual(keep.read_text(),'user')

    def test_no_output_inside_original_data(self):
        self.output=self.data/'new';self.reject()

    def test_all_input_bytes_remain_unchanged(self):
        before={str(p):p.read_bytes() for p in self.root.rglob('*.json')}
        self.run_check()
        self.assertEqual(before,{p:Path(p).read_bytes() for p in before})

    def test_old_prestart_source_rejected_before_reading_or_output(self):
        with self.assertRaisesRegex(ValueError,'recovered D flight source'):
            f.run(self.results,self.data,self.output,loader=self.loader,d_source=f.STOPPED_D_SOURCE)
        self.assertFalse(self.output.exists())

    def test_full_d_source_is_required(self):
        for bad in (None,'',D_SOURCE[:10],f.C_SOURCE,'z'*40):
            with self.subTest(source=bad),self.assertRaises(ValueError):
                f.run(self.results,self.data,self.output,loader=self.loader,d_source=bad)
        self.assertFalse(self.output.exists())

    def test_original_manifest_cannot_be_replaced_during_recovery(self):
        old=self.loader
        def loader(source,path):
            blob=old(source,path)
            return blob+b'\n' if source==f.STOPPED_D_SOURCE and path.endswith('/manifest.json') else blob
        self.loader=loader;self.reject()

    def test_original_d_freeze_cannot_be_replaced(self):
        old=self.loader
        def loader(source,path):
            blob=old(source,path)
            return blob+b'\n' if source==f.STOPPED_D_SOURCE and path.endswith('/gates/D/frozen.json') else blob
        self.loader=loader;self.reject()

    def test_c_manifest_must_bind_same_parameter_source(self):
        old=self.loader
        def loader(source,path):
            blob=old(source,path)
            return blob+b'\n' if source==f.C_SOURCE and path.endswith('/manifest.json') else blob
        self.loader=loader;self.reject()

    def test_stopped_qualification_directory_rejected(self):
        self.mutate(self.data/'D/batch01/qualification_reference.json',
            lambda d:d.update(path=str(self.data/'D/qualification01/evidence.json')))
        self.reject()

    def test_external_actual_qualification_hash_checked(self):
        self.mutate(self.data/'D/qualification02/evidence.json',lambda d:d.update(clean=False));self.reject()

    def test_actual_qualification_reference_cannot_leave_gate(self):
        self.mutate(self.data/'D/batch01/qualification_reference.json',
            lambda d:d.update(path=str(self.data/'C/qualification01/evidence.json')))
        self.reject()

    def test_qualification_authorization_old_source_rejected(self):
        self.mutate(self.data/'D/qualification02/authorization.json',lambda d:d.update(source_head=f.STOPPED_D_SOURCE));self.reject()

    def test_qualification_authorization_budget_increase_rejected(self):
        self.mutate(self.data/'D/qualification02/authorization.json',lambda d:d.update(total_maximum_attempts=19));self.reject()

    def test_ulog_index_requires_all_nine_job_identities(self):
        self.mutate(self.results/'D/ulog_index.json',lambda d:d['files'][0].update(job_id='run011'));self.reject()


if __name__=='__main__':unittest.main(verbosity=2)
