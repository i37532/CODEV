import ast
import copy
import inspect
import json
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from common import REPO,CONFIG,load_protocol,jobs
from cli_clock import receipt, require_fresh, audit_commands,TOPICS
from v04_task04 import scalars
import monitor
import run


def raw(topic='sta_velocity_ctrl_status',timestamp=113508000,age='0.008000'):
    return f'TOPIC: {topic}\n timestamp: {timestamp}  ({age} seconds ago)\n'


def timed(data,topic):
    return {**data,'_clock':receipt('listener',[topic,'-n','1'],raw(topic,int(data['timestamp'])),1,1000001)}


class ClockTests(unittest.TestCase):
    def test_sim_age_exact_boundary(self):
        for value in ('0.000000','0.999999','1.000000'):
            self.assertIsNotNone(receipt('listener',['sta_velocity_ctrl_status','-n','1'],raw(age=value),0,1))
        with self.assertRaises(ValueError):receipt('listener',['sta_velocity_ctrl_status','-n','1'],raw(age='1.000001'),0,1)

    def test_separate_host_duration_boundary(self):
        r=receipt('listener',['sta_velocity_ctrl_status','-n','1'],raw(),1,1000000001)
        self.assertEqual(r['host_elapsed_ns'],1000000000)
        with self.assertRaises(ValueError):receipt('listener',['sta_velocity_ctrl_status','-n','1'],raw(),1,1000000002)

    def test_invalid_clock_future_missing_duplicate(self):
        for text in (raw(timestamp=0),raw(age='-0.000001'),raw(age='nan'),raw(age='18446744073709.551616'),raw()+raw()):
            with self.assertRaises(ValueError):receipt('listener',['sta_velocity_ctrl_status','-n','1'],text,0,1)
        for start,end in ((2,1),(-1,2),(0,1.5)):
            with self.assertRaises(ValueError):receipt('listener',['sta_velocity_ctrl_status','-n','1'],raw(),start,end)

    def test_topic_whitelist_not_blanket_clock_relaxation(self):
        self.assertIsNone(receipt('listener',['vehicle_status','-n','1'],'unknown',0,2000000000))
        with self.assertRaises(ValueError):receipt('listener',['vehicle_attitude','-n','1'],raw(),0,1)
        self.assertIsNone(receipt('listener',['sta_velocity_ctrl_status','-n','1'],'never published',0,1))
        with self.assertRaises(RuntimeError):require_fresh({})

    def test_exchange_tampering_rejected(self):
        d=timed(dict(timestamp=113508000),'sta_velocity_ctrl_status');require_fresh(d)
        for key,value in [('timestamp_us',3),('age_at_print_us',1000001),('host_elapsed_ns',-1),('host_end_ns',0)]:
            x=copy.deepcopy(d);x['_clock'][key]=value
            with self.assertRaises(RuntimeError):require_fresh(x)

    def fixture(self):
        rate=dict(timestamp=112324000,publish_seq=1,requested_mode=0,requested_axes=0,effective_mode=0,
                  effective_axes=0,div_req=1,div_eff=1,fault=0,abort_requested=0,termination=0)
        diag=dict(timestamp=113508000,requested_mode=1,requested_axes=3,effective_mode=1,effective_axes=3,
                  pending=0,reject=0,armed=0,enabled=0,first_fail=0,retry_result=0,first_input=0,
                  excitation_fault=0,excitation=0,excitation_y=0,excitation_z=0)
        state=dict(position=dict(timestamp=112320000),status=dict(arming_state=1,nav_state=4))
        c=run.Checks(load_protocol(),{},next(j for j in jobs() if j['mode']==1),Path('/unused'))
        topics={'sta_rate_ctrl_status':timed(rate,'sta_rate_ctrl_status'),'sta_velocity_ctrl_status':timed(diag,'sta_velocity_ctrl_status')}
        return c,state,topics

    def test_actual_nonlanding_monitor_cross_read_fixture(self):
        c,state,topics=self.fixture()
        self.assertGreater(topics['sta_velocity_ctrl_status']['timestamp']-state['position']['timestamp'],1000000)
        with tempfile.TemporaryDirectory() as root:
            c.monitor('warmup',None,topics.__getitem__,Path(root),state)
            self.assertTrue((Path(root)/'protocol09_monitor.jsonl').is_file())
            # Unchanged repeated-rate protection still rejects.
            with self.assertRaises(RuntimeError):c.monitor('warmup',None,topics.__getitem__,Path(root),state)

    def test_actual_monitor_inner_fault_and_missing_receipt(self):
        for kind in ('rate_fault','velocity_receipt','wrong_mode'):
            c,state,topics=self.fixture()
            if kind=='rate_fault':topics['sta_rate_ctrl_status']['fault']=1
            if kind=='velocity_receipt':topics['sta_velocity_ctrl_status'].pop('_clock')
            if kind=='wrong_mode':topics['sta_velocity_ctrl_status']['effective_axes']=7
            with tempfile.TemporaryDirectory() as root,self.assertRaises(RuntimeError):
                c.monitor('warmup',None,topics.__getitem__,Path(root),state)

    def test_actual_landing_monitor_transport_and_history_unchanged(self):
        for age in (500000,500001,-1):
            c,state,topics=self.fixture();c.reference={'ready':True}
            class Live:
                def read(self):return 'raw_history'
            class Landing:
                def update(self,*args):return {'pending':False}
            c.landing_live=Live();c.landing=Landing()
            topics['vehicle_local_position']={'timestamp':113900000}
            with tempfile.TemporaryDirectory() as root,patch.object(monitor,'replay',return_value=dict(through_us=113900000-age)) as check:
                if age==500000:
                    monitor.Checks.monitor(c,'landing',None,topics.__getitem__,Path(root),state)
                    self.assertEqual(check.call_args.args[0],'raw_history')
                else:
                    with self.assertRaises(ValueError):monitor.Checks.monitor(c,'landing',None,topics.__getitem__,Path(root),state)

    def test_envelope_body_equal_except_named_clock_repair(self):
        from run_v00 import Checks as Old
        new=inspect.getsource(monitor.Checks._base_monitor)
        old=inspect.getsource(Old.monitor)
        new=new.replace('def _base_monitor(', 'def monitor(').replace('        require_fresh(d)\n','')
        new=new.replace("if d['publish_seq'] == self.last_seq:","if abs(pos['timestamp'] - d['timestamp']) > 1e6 or d['publish_seq'] == self.last_seq:")
        self.assertEqual(ast.dump(ast.parse(textwrap.dedent(new))),ast.dump(ast.parse(textwrap.dedent(old))))

    def test_full_chain_receipt_replay_rejects_tampering_and_missing(self):
        records=[]
        for i,topic in enumerate(sorted(TOPICS)):
            start=i*1000;end=start+100;text=raw(topic)
            records.append(dict(cmd=['/bin/px4-listener',topic,'-n','1'],returncode=0,stdout=text,
                host_start_ns=start,host_end_ns=end,host_elapsed_ns=100,
                clock=receipt('listener',[topic,'-n','1'],text,start,end)))
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'commands.jsonl'
            path.write_text(''.join(json.dumps(x)+'\n' for x in records))
            self.assertEqual(sum(audit_commands(path)['counts'].values()),4)
            for variant in (records[:-1],list(reversed(records))):
                path.write_text(''.join(json.dumps(x)+'\n' for x in variant))
                with self.assertRaises(ValueError):audit_commands(path)
            records[0]['clock']['age_at_print_us']=0
            path.write_text(''.join(json.dumps(x)+'\n' for x in records))
            with self.assertRaises(ValueError):audit_commands(path)

    def test_analyzer_calls_clock_audit_before_accept(self):
        import analyze
        source=inspect.getsource(analyze.analyze)
        self.assertLess(source.index("audit_commands(run/'commands.jsonl')"),source.index("out['accepted']=bool(base_accepted)"))


if __name__=='__main__':unittest.main(verbosity=2)
