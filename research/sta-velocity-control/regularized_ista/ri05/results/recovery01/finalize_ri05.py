#!/usr/bin/env python3
"""Small read-only RI05 receipt verification and qualified XYZ export.

No runner imports, ULog decoding, simulator or parameter writes. Small JSON
receipts are hashed; ULog hashes are inherited from the completed collector.
All checks finish before a NEW output directory is created. No flight authority
is created by this descriptive export.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

REPO = Path('/home/yr/Desktop/Codev-autopilot')
REL = 'research/sta-velocity-control/regularized_ista/ri05'
DATA = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI05')
C_SOURCE = '3e633a0d2aba1326d3f79b0033f59787cc479c44'
STOPPED_D_SOURCE = '6faad54e1ea1041c144d79c97df9475a19b90290'
MODES = {'PID':0,'RSTA':3,'RISTA':4}
CAP = 8*1024*1024  # Receipt JSON only, never a ULog or recursive evidence tree.


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def exact(a,b):
    return json.dumps(a,sort_keys=True,separators=(',',':'),allow_nan=False) == json.dumps(b,sort_keys=True,separators=(',',':'),allow_nan=False)


def read_json(path, refs):
    path=Path(path)
    require(path.suffix=='.json' and path.stat().st_size<=CAP,'Only bounded JSON receipts may be read: '+str(path))
    raw=path.read_bytes()
    refs[str(path)]=dict(path=str(path.resolve()),bytes=len(raw),sha256=digest(raw))
    return json.loads(raw)


def committed_blob(repo, source, relative):
    return subprocess.check_output(['git','show',source+':'+relative],cwd=repo)


def verify(results, data, loader, d_source):
    require(isinstance(d_source,str) and re.fullmatch('[0-9a-f]{40}',d_source)
            and d_source not in (C_SOURCE,STOPPED_D_SOURCE),
            'Explicit recovered D flight source required; old prestart qualification is not flight evidence')
    sources={'C':C_SOURCE,'D':d_source}
    refs={}
    raw_manifest=loader(d_source,REL+'/manifest.json')
    raw_frozen=loader(d_source,REL+'/gates/D/frozen.json')
    require(raw_manifest==loader(STOPPED_D_SOURCE,REL+'/manifest.json'),
            'Recovery changed the original committed eighteen-job manifest')
    require(raw_frozen==loader(STOPPED_D_SOURCE,REL+'/gates/D/frozen.json'),
            'Recovery changed the frozen D source/control/parameter contract')
    manifest=json.loads(raw_manifest); frozen=json.loads(raw_frozen)
    require(isinstance(manifest,list) and len(manifest)==18,'Frozen manifest must have exactly 18 jobs')
    require(frozen['stage']=='RI05-D' and frozen['gate']=='D' and frozen['revision']=='ri05','Wrong D frozen snapshot')
    require(frozen['assets'][REL+'/manifest.json']==digest(raw_manifest),'Committed D manifest/freeze hash differs')
    require(frozen['budget']==dict(maximum_attempts=9,new_matrix_attempts=9,total_maximum_attempts=18,
        historical_attempts=0,required_pairs=6,required_replays=9,n_per_algorithm=3,logging_profile=3089),'Wrong frozen budget')
    gates={}; ledgers={}
    for gate in ('C','D'):
        require(loader(sources[gate],REL+'/manifest.json')==raw_manifest,
                'C/D do not share the original exact manifest')
        gate_frozen_raw=loader(sources[gate],REL+'/gates/'+gate+'/frozen.json')
        gate_frozen=json.loads(gate_frozen_raw)
        require(gate_frozen['gate']==gate and gate_frozen['stage']=='RI05-'+gate
                and gate_frozen['assets'][REL+'/manifest.json']==digest(raw_manifest),
                'Per-gate frozen snapshot or parameter manifest differs')
        s=read_json(results/gate/'summary.json',refs)
        receipt=read_json(data/gate/'gate_pass.json',refs)
        ledger=read_json(data/gate/'batch01/ledger.json',refs)
        replay_path=Path(receipt['replay_summary_path'])
        require(replay_path.parent.parent.resolve()==(data/gate).resolve(),'Replay path outside its gate')
        replay=read_json(replay_path,refs)
        index=read_json(results/gate/'ulog_index.json',refs)
        require(s['status']=='passed' and s['gate_passed'] is True and s['collection_ok'] is True and s['issues']==[],gate+' is not fully passed')
        require(exact(s['gate_receipt'],receipt),'Compact/external gate receipt differs: '+gate)
        for record in (s,receipt,ledger):
            require(record['source_head']==sources[gate],gate+' source version differs')
            require(record['firmware_sha256']==s['firmware_sha256'],gate+' firmware binding differs')
            require(record['stage']=='RI05-'+gate and record.get('gate')==gate,gate+' identity differs')
        fw=s['firmware_sha256']
        require(isinstance(fw,str) and len(fw)==64 and all(c in '0123456789abcdef' for c in fw),'Missing firmware SHA')
        expected_counts=dict(planned=9,attempted=9,takeoff_commanded=9,airborne_confirmed=9,airborne_unknown=0,
            declared_accepted=9,accepted_verified=9,failed=0,unattempted=0,missing_accepted=0,independent_replays=9,paired_risk_checks=6)
        require(exact(s['counts'],expected_counts),'Incomplete per-gate count receipt: '+gate)
        for key,value in dict(accepted=True,planned=9,attempts=9,accepted_runs=9,independent_replays=9,
                              paired_checks=6,missing=0,parameter_restore_exact=True,new_flights_by_replay=0).items():
            require(type(receipt.get(key)) is type(value) and receipt[key]==value,'Invalid gate receipt '+gate+':'+key)
        require(receipt['ledger_sha256']==refs[str(data/gate/'batch01/ledger.json')]['sha256'],'Stale gate ledger SHA')
        require(receipt['replay_summary_sha256']==refs[str(replay_path)]['sha256'],'Stale gate replay SHA')
        require(ledger['success'] is True and ledger['parameter_restore_exact'] is True and ledger['remaining_simulators']==[]
                and ledger['unattempted']==[] and ledger['planned']==ledger['new_planned']==9
                and ledger['total_budget']==18 and ledger['prior_attempts']==0,'Incomplete ledger/restore/budget')
        require(s['parameter_restore_exact'] is True and s['remaining_simulators']==[],'Compact cleanup differs')
        jobs=[j for j in manifest if j['gate']==gate]
        require(len(jobs)==9 and len(ledger['attempts'])==9 and len(s['runs'])==9,'Nine unique trials required')
        for i,(job,item,row) in enumerate(zip(jobs,ledger['attempts'],s['runs']),1):
            require(item['attempt']==i and item['status']=='accepted' and exact(item['job'],job),'Wrong attempted job/order')
            require(row['id']==job['id'] and row['seed']==job['seed'] and row['candidate']==job['candidate']
                    and row['attempted'] is True and row['declared_status']=='accepted'
                    and row['included_in_accepted_means'] is True and row['airborne']['confirmed'] is True
                    and row['landed_disarmed_observed'] is True and row['evidence_issues']==[],'Incomplete run receipt')
        require(replay['success'] is True and replay['replayed']==9 and replay['new_flights']==0
                and replay['source_inputs_unchanged'] is True and replay['source_head']==sources[gate]
                and replay['qualified_firmware_sha256']==fw
                and replay['ledger_sha256']==receipt['ledger_sha256']
                and exact(replay['original_input_sha256_before'],replay['original_input_sha256_after'])
                and len(replay['commands'])==9 and all(c['returncode']==0 for c in replay['commands']), 'Incomplete independent replay')
        require(exact(s['independent_numeric_pairs'],ledger['pairs']) and exact(ledger['pairs'],replay['pairs']),'Paired decisions differ')
        required={'yaw'}|{p+str(a) for p in ('velocity_','position_','first_half_velocity_','second_half_velocity_') for a in range(3)}
        require(len(ledger['pairs'])==6,'Six risk comparisons required')
        identities=[]
        for pair in ledger['pairs']:
            require(pair['gate']==gate and pair['accepted'] is True and set(pair['checks'])==required
                    and all(v is True for v in pair['checks'].values()),'Incomplete/failed individual risk checks')
            identities.append((pair['seed'],pair['candidate']))
        require(sorted(identities)==sorted((j['seed'],j['candidate']) for j in jobs if j['mode']),'Duplicate/missing risk pair')
        q=s['qualification']
        require(q['source_head']==sources[gate] and q['firmware_sha256']==fw and q['success'] is True
                and q['approved'] is True and q['clean'] is True and q['commands']
                and all(x['exit_code']==0 for x in q['commands']),'Qualification receipt differs')
        qref=read_json(data/gate/'batch01/qualification_reference.json',refs)
        qpath=Path(qref['path']).resolve()
        require(qpath.parent.parent==(data/gate).resolve() and qpath.name=='evidence.json',
                'Qualification must be a direct qualification directory inside its gate')
        require(gate!='D' or qpath.parent.name!='qualification01',
                'Stopped D qualification01 must not be reused after recovery')
        full_q=read_json(qpath,refs)
        require(qref['sha256']==refs[str(qpath)]['sha256'], 'Stale actual qualification reference')
        require(exact(q,{key:full_q.get(key) for key in q}), 'Compact qualification differs from original')
        require(full_q['gate']==gate and full_q['new_flights']==0
                and full_q['frozen_sha256']==digest(gate_frozen_raw),
                'Actual qualification gate/freeze differs')
        qa=read_json(qpath.parent/'authorization.json',refs)
        expected=dict(approved=True,gate=gate,stage='RI05-'+gate,source_head=sources[gate],
            firmware_sha256=fw,qualification_sha256=qref['sha256'],
            frozen_sha256=digest(gate_frozen_raw),maximum_attempts=9,total_maximum_attempts=18)
        require(all(exact(qa.get(key),value) for key,value in expected.items()),
                'Actual qualification authorization binding differs')
        require(index['log_count']>0 and index['verified_count']==index['log_count']==len(index['files'])
                and all(x['verified'] is True and x['gate']==gate and x['source_head']==sources[gate]
                        and x['firmware_sha256']==fw for x in index['files']),'ULog verification index incomplete')
        require({x['job_id'] for x in index['files']}=={j['id'] for j in jobs},
                'ULog index does not cover every accepted job')
        gates[gate]=dict(source_head=sources[gate],firmware_sha256=fw,counts=s['counts'],gate_receipt=receipt,
                         qualification_reference=qref,
                         recorded_verified_ulogs=index['verified_count'],new_ulog_hash_checks=0)
        ledgers[gate]=ledger
    d_summary=read_json(results/'D/summary.json',refs)
    require(exact(d_summary['prior_gate_receipt'],gates['C']['gate_receipt']),'D lacks exact prior C acceptance')
    d_jobs=[j for j in manifest if j['gate']=='D']
    configurations={}
    shared_keys=None
    for name,mode in MODES.items():
        selected=[j for j in d_jobs if j['candidate']==name]
        require(len(selected)==3 and [j['seed'] for j in selected]==[83101,83102,83103],'Wrong D paired seeds')
        first=selected[0]; parameters=first['parameters']
        require(len(parameters)==127 and all(type(v) in (float,int) and math.isfinite(v) for v in parameters.values()),'Need complete finite 127 parameters')
        require(all(exact(parameters,j['parameters']) for j in selected),'Cross-seed flight parameter change is not allowed')
        expected=dict(MPC_VC_MODE=mode,MPC_VC_AXES=0 if mode==0 else 7,MPC_VC_DIV=1,MPC_VCT_TEST=8,
                      MC_RTC_MODE=0,MC_STA_AXES=0,MC_RTC_DIV=1,MC_RATT_TEST=0,MC_STA_TKO_MGT=0)
        require(all(parameters.get(k)==v for k,v in expected.items()),'Wrong accepted XYZ/rate/default task profile')
        if shared_keys is None: shared_keys=set(parameters)
        require(set(parameters)==shared_keys,'Parameter key set differs across algorithms')
        configurations[name]=dict(source_job_id=first['id'],accepted_job_ids=[j['id'] for j in selected],
            accepted_seeds=[j['seed'] for j in selected],parameters=parameters,parameter_count=127,
            cross_seed_parameter_difference_keys=[],seed_parameter_allowlist=[],
            seed_transport='job.seed -> M10_IMU_SEED environment; no seed parameter in the 127-key map')
    base=configurations['PID']['parameters']
    for name in ('RSTA','RISTA'):
        different={k for k in base if base[k]!=configurations[name]['parameters'][k]}
        require(different=={'MPC_VC_MODE','MPC_VC_AXES'},'Unexpected cross-algorithm parameter differences')
    qualified=dict(stage='RI05',status='qualified_fixed_parameter_xyz_development',gate='D',new_flight_authorization=False,
        source_head=d_source,firmware_sha256=gates['D']['firmware_sha256'],configurations=configurations,
        model_sha256=frozen['derived_iris_sha256'],frozen_manifest_git_blob=dict(source=d_source,path=REL+'/manifest.json',sha256=digest(raw_manifest)),
        original_manifest_source=STOPPED_D_SOURCE,
        frozen_D_git_blob=dict(source=d_source,path=REL+'/gates/D/frozen.json',sha256=digest(raw_frozen)),
        scope='Only the completed Iris Gazebo SITL V/TEST8 fixed-parameter development scenario; not a vehicle-ready deployment file.',
        warnings=['All 127 parameters retained, including task/test parameters. Do not blindly import on hardware.',
                  'No new flight, seed, budget, tuning or real-hardware authority is granted.',
                  'Original position P, attitude/rate PID, DIV1 and existing protections/model remain required.',
                  'No ULog decoding or ULog hashing is performed here; completed collector/replay receipts are prerequisites.',
                  'Qualified does not mean best tuned or statistically superior. C and D source/firmware differ and are reported separately.'])
    receipt=dict(stage='RI05',passed=True,total_planned=18,total_attempted=18,total_accepted=18,total_missing=0,
        per_gate=gates,new_flights=0,new_ulog_decodes=0,new_ulog_hash_checks=0,new_flight_authorization=False,
        source_receipts=refs,scope='Offline cross-receipt check and descriptive accepted-configuration export only')
    return receipt,qualified


def run(results,data,output,repo=REPO,loader=None,*,d_source):
    results,data,output=Path(results).resolve(),Path(data).resolve(),Path(output).resolve()
    require(not output.exists(),'Output already exists; refusing overwrite')
    for protected in (data,results/'C',results/'D'):
        require(output!=protected and protected not in output.parents and output not in protected.parents,'Output overlaps input evidence')
    receipt,qualified=verify(results,data,loader or (lambda source,relative:committed_blob(repo,source,relative)),d_source)
    output.mkdir(parents=True,exist_ok=False)
    for name,value in (('final_acceptance.json',receipt),('qualified_xyz.json',qualified)):
        with (output/name).open('x') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,default=REPO/REL/'results')
    p.add_argument('--data-root',type=Path,default=DATA)
    p.add_argument('--repo',type=Path,default=REPO)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--d-source',required=True,help='Full actually flown recovered D source SHA, not the prestart source')
    a=p.parse_args()
    try:
        r=run(a.results,a.data_root,a.output,a.repo,d_source=a.d_source)
    except (ValueError,KeyError,OSError,subprocess.CalledProcessError) as error:
        print(json.dumps(dict(passed=False,new_flights=0,error=repr(error)),ensure_ascii=False));raise SystemExit(1)
    print(json.dumps(dict(passed=r['passed'],total_accepted=r['total_accepted'],output=str(a.output),new_flight_authorization=False)))
