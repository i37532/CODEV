"""Independent final raw-log coverage audit; never edits flight data."""
import hashlib
import json
from pathlib import Path
import sys
import re
import numpy as np
from pyulog import ULog
REPO=Path('/home/yr/Desktop/Codev-autopilot')
sys.path.insert(0,str(REPO/'research/sta-velocity-control/v07/protocol06'))
from position_log import PositionLogView
from ram_log import validate
ROOT=Path(__file__).resolve().parent

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    ledger=json.loads((ROOT/'series06/ledger.json').read_text())
    out=ROOT/'recording_audit06';out.mkdir(exist_ok=False)
    evidence=dict(complete=False,new_flights=0,runs=[])
    try:
        for a in ledger['attempts']:
            r=Path(a['directory']);result=json.loads((r/'result.json').read_text())
            assert len(result['logs'])==2
            ram=json.loads((r/'ram_log_root.json').read_text())
            ramroot=validate(Path(ram['path']))
            assert result['explicit_environment']['PX4_SITL_LOG_DIR']==str(ramroot)
            for raw in result['logs']:
                assert sha(Path(raw['archive']))==raw['sha256']
                source=Path(raw['source'])
                assert ramroot in source.parents and sha(source)==raw['sha256']
                assert raw['durable_copy_verified'] and raw['volatile_source_retained']
                assert source.stat().st_size==raw['bytes']==Path(raw['archive']).stat().st_size
            commands=[json.loads(line) for line in (r/'commands.jsonl').read_text().splitlines()]
            starts=[x for x in commands if Path(x['cmd'][0]).name=='px4-logger' and x['cmd'][1:2]==['start']]
            assert len(starts)==1 and starts[0]['returncode']==0
            assert starts[0]['cmd'][1:]==['start','-b','256','-r','1000','-f']
            entry=max(result['logs'],key=lambda d:Path(d['archive']).stat().st_size)
            assert re.fullmatch(r'sess[0-9]{3,}/log[0-9]{3}\.ulg',str(Path(entry['source']).relative_to(ramroot)))
            if a['status']!='accepted' and not result['success']:
                p=Path(entry['archive']);u=ULog(str(p))
                evidence['runs'].append(dict(run=r.name,accepted=False,job=a['job'],file=str(p),sha256=sha(p),
                    error=result.get('error'),dropouts=[vars(x) for x in u.dropouts],file_corruption=u.file_corruption,
                    raw_missing_timestamps=[],raw_missing_consumed=[],position_evidence={'records':0},
                    note='Failed run: do not apply successful-run completeness assertions or regrade.'))
                continue
            polls=[json.loads(x) for x in (r/'landing_pending_poll.jsonl').read_text().splitlines()]
            assert polls and all('error' not in x for x in polls)
            for i,x in enumerate(polls):
                assert 1<=x['poll']<=8 and x['host_end']>=x['host_start']
                if i:
                    prev=polls[i-1]
                    assert x['host_start']>=prev['host_end'] and x['raw_offset']>=prev['raw_offset']
                    assert x['poll']==(prev['poll']+1 if prev['evidence']['pending'] else 1)
                    if x['poll']>1:assert x['pending_since']==prev['pending_since_after']
            assert not polls[-1]['evidence']['pending']
            pending_summary=dict(polls=len(polls),extra_polls=sum(x['poll']>1 for x in polls),
                pending_events=sum(bool(x['evidence']['pending']) for x in polls),max_poll_index=max(x['poll'] for x in polls),
                max_poll_seconds=max(x['host_end']-x['host_start'] for x in polls),
                maximum_resolution_to_record_s=max([x['host_end']-x['pending_since'][1] for x in polls if x['pending_since']]+[0]),
                note='Original validator enforces both500ms deadlines; host_end includes subsequent record preparation and is not its exact internal check instant.')
            p=Path(entry['archive']);before=sha(p);assert before==entry['sha256']
            u=ULog(str(p));view=PositionLogView(u);view.get_dataset('vehicle_local_position')
            old=u.get_dataset('vehicle_local_position').data
            new=u.get_dataset('vehicle_local_position_log').data
            d=u.get_dataset('sta_velocity_ctrl_status').data
            st=u.get_dataset('logger_status').data
            missing=new['timestamp'][~np.isin(new['timestamp'],old['timestamp'])]
            counters=np.unique(st['num_messages']).tolist();assert counters==[256]
            assert not u.dropouts and not u.file_corruption and not np.any(st['dropouts'])
            assert p.stat().st_size<=128*1024*1024
            observed=PositionLogView(u).get_dataset('vehicle_local_position').data
            assert len(observed['timestamp'])==len(new['timestamp'])
            evidence['runs'].append(dict(run=r.name,accepted=a['status']=='accepted',job=a['job'],
                file=str(p),sha256=before,bytes=p.stat().st_size,position_evidence=view.position_log_evidence,
                logger_start_argv=starts[0]['cmd'],session_path=entry['source'],startup_and_session_logs_preserved=True,
                pending_poll=pending_summary,
                private_tmpfs_root=str(ramroot),both_logs_durable_and_ram_originals_verified=True,
                raw_missing_timestamps=missing.tolist(),raw_missing_consumed=np.isin(missing,d['input_timestamp']).tolist(),
                registered_topic_counts=counters,active_topic_ids=len(u.data_list),maximum_message_id=max(x.msg_id for x in u.data_list),
                logger_aggregate_message_gaps_max=int(st['message_gaps'].max()),
                note='Aggregate gaps include unrelated unqueued topics; mandatory position/diagnostic sequence and health coverage checked separately.',
                file_unchanged=sha(p)==before))
            assert evidence['runs'][-1]['file_unchanged']
            print(r.name,'raw missing',len(missing),'queued records',len(new['timestamp']),flush=True)
        evidence['complete']=bool(ledger['success'] and len(evidence['runs'])==18 and all(x['accepted'] for x in evidence['runs']))
        evidence['raw_missing_total']=sum(len(x['raw_missing_timestamps']) for x in evidence['runs'])
        evidence['raw_missing_consumed_total']=sum(sum(x['raw_missing_consumed']) for x in evidence['runs'])
        evidence['queued_records_total']=sum(x['position_evidence']['records'] for x in evidence['runs'])
    finally:
        (out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({k:v for k,v in evidence.items() if k!='runs'}))

if __name__=='__main__':main()
