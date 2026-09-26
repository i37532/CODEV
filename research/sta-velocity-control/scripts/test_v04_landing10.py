"""Landing association regressions; all mocks/ULog replays are offline only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import numpy as np
from pyulog import ULog
from test_v04_protocol04 import Log
from v04_landing10 import LandingMonitor, LandingPending, replay, healthy, validate_context
from v04_monitor10 import Checks
from v04_protocol09 import load_protocol, CONFIG, fingerprint
from replay_v04_clock09 import ROOT, copy_metadata, digest
import analyze_v04_landing10 as full


def fixture():
    ts = np.array([1000000, 61000000, 61100000, 61104000, 61108000], dtype=np.uint64)
    d = dict(timestamp=ts, excitation_fault=np.array([0, 0, 0, 2, 2]), excitation=np.zeros(5),
             armed=np.ones(5), enabled=np.ones(5))
    for key in ('first_fail','first_input','retry_result','fault','sta_fault','failsafe','timing','inner_mode',
                'inner_axes','config_pending'):
        d[key] = np.zeros(5, dtype=int)
    for key in ('inner_divisor','inner_valid','pid_calls','valid'):
        d[key] = np.ones(5, dtype=int)
    status = dict(timestamp=np.array([1000000, 61104000], dtype=np.uint64),
                  nav_state_timestamp=np.array([900000, 61104000], dtype=np.uint64),
                  nav_state=np.array([4, 18]), failsafe=np.zeros(2), failure_detector_status=np.zeros(2))
    command = {k:np.array([v]) for k,v in dict(timestamp=61100000,command=176,
             param1=1,param2=4,param3=6,target_system=1,target_component=1).items()}
    log = Log({('sta_velocity_ctrl_status',0):d,('vehicle_status',0):status,('vehicle_command',0):command})
    ctx = dict(hover_start_us=1000000, hover_end_us=61000000, command_lower_us=61000000, cli_success=True)
    return log, ctx


def last(log):
    return {k:v[-1].item() for k,v in log.get_dataset('sta_velocity_ctrl_status').data.items()}


class Landing10Test(unittest.TestCase):
    def test_same_time_transition_and_old_status_regression(self):
        log,ctx=fixture();r=replay(log,ctx,61108000,final=True)
        self.assertEqual(r['classification']['expected_planned_landing_gate'],2)
        self.assertFalse(r['consumed_status_proven'])

    def test_future_status_not_borrowed_for_earlier_gate(self):
        log,ctx=fixture();s=log.tables[('vehicle_status',0)];s['timestamp'][-1]=61104001;s['nav_state_timestamp'][-1]=61104001
        with self.assertRaisesRegex(ValueError,'past/equal'):replay(log,ctx,61108000)

    def test_missing_transition_pending_live_not_final(self):
        log,ctx=fixture();log.tables[('vehicle_status',0)]={k:v[:1] for k,v in log.tables[('vehicle_status',0)].items()}
        with self.assertRaises(LandingPending):replay(log,ctx,61108000)
        with self.assertRaises(ValueError):replay(log,ctx,61108000,final=True)

    def test_delayed_transition_resolves_without_changing_raw(self):
        log,ctx=fixture();original=copy.deepcopy(log);status=log.tables[('vehicle_status',0)]
        log.tables[('vehicle_status',0)]={k:v[:1] for k,v in status.items()}
        clock=[0.];m=LandingMonitor(lambda:clock[0]);m.begin(**ctx)
        self.assertTrue(m.update(log,last(log),61108000)['pending'])
        log.tables[('vehicle_status',0)]=status;clock[0]=.1
        self.assertFalse(m.update(log,last(log),61208000)['pending'])
        for key,values in original.tables[('sta_velocity_ctrl_status',0)].items():
            np.testing.assert_array_equal(log.tables[('sta_velocity_ctrl_status',0)][key],values)

    def test_timeout_exact_boundary_and_one_us_beyond(self):
        for elapsed,ok in [(500000,True),(500001,False)]:
            log,ctx=fixture();status=log.tables[('vehicle_status',0)];log.tables[('vehicle_status',0)]={k:v[:1] for k,v in status.items()}
            m=LandingMonitor(lambda:0);m.begin(**ctx);m.update(log,last(log),61108000)
            # Keep stream current: the first unresolved gate must not get a new deadline.
            d=log.tables[('sta_velocity_ctrl_status',0)]
            for key,v in list(d.items()):d[key]=np.append(v,61108000+elapsed if key=='timestamp' else v[-1])
            if ok:self.assertTrue(m.update(log,last(log),61108000+elapsed)['pending'])
            else:
                with self.assertRaisesRegex(ValueError,'timeout'):m.update(log,last(log),61108000+elapsed)
                self.assertTrue(m.failed)

    def test_wall_timeout_even_with_paused_simulator(self):
        log,ctx=fixture();log.tables[('vehicle_status',0)]={k:v[:1] for k,v in log.tables[('vehicle_status',0)].items()}
        wall=[0.];m=LandingMonitor(lambda:wall[0]);m.begin(**ctx);m.update(log,last(log),61108000)
        wall[0]=.500001
        with self.assertRaisesRegex(ValueError,'timeout'):m.update(log,last(log),61108000)

    def test_real_fault_never_hidden_by_pending(self):
        for field,value in [('excitation_fault',3),('first_fail',1),('retry_result',1),('fault',1),
                            ('sta_fault',1),('failsafe',1),('timing',1),('inner_mode',1),('valid',0)]:
            log,ctx=fixture();log.tables[('vehicle_status',0)]={k:v[:1] for k,v in log.tables[('vehicle_status',0)].items()}
            log.tables[('sta_velocity_ctrl_status',0)][field][2]=value
            with self.subTest(field=field),self.assertRaises(ValueError) as raised:replay(log,ctx,61108000)
            self.assertNotIsInstance(raised.exception,LandingPending)

    def test_fault_latch_cannot_be_cleared_or_replanned(self):
        log,ctx=fixture();m=LandingMonitor();m.begin(**ctx);bad=last(log);bad['fault']=1
        with self.assertRaises(ValueError):m.update(log,bad,61108000)
        with self.assertRaisesRegex(ValueError,'latched'):m.update(log,last(log),61108000)
        with self.assertRaises(ValueError):m.begin(**ctx)

    def test_no_plan_no_observation_or_failed_command_rejected(self):
        log,ctx=fixture();m=LandingMonitor()
        with self.assertRaisesRegex(ValueError,'Unplanned'):m.update(log,last(log),61108000)
        for field,value in [('hover_end_us',60999999),('command_lower_us',60999999),('cli_success',False)]:
            with self.subTest(field=field),self.assertRaises(ValueError):validate_context({**ctx,field:value})

    def test_gate_before_command_and_nonzero_output_or_disarmed_rejected(self):
        for field,value in [('excitation',.001),('armed',0),('excitation_fault',6)]:
            log,ctx=fixture();log.tables[('sta_velocity_ctrl_status',0)][field][-1]=value
            with self.subTest(field=field),self.assertRaises(ValueError):replay(log,ctx,61108000)
        log,ctx=fixture();log.tables[('vehicle_command',0)]['timestamp'][0]=61106000
        with self.assertRaisesRegex(ValueError,'before planned|before raw'):replay(log,ctx,61108000)

    def test_repeated_and_wrong_commands_rejected(self):
        for key,value in [('param3',5),('param2',3),('target_system',2),('target_component',0)]:
            log,ctx=fixture();log.tables[('vehicle_command',0)][key][0]=value
            with self.subTest(key=key),self.assertRaises(ValueError):replay(log,ctx,61108000)
        log,ctx=fixture();d=log.tables[('vehicle_command',0)]
        for k,v in list(d.items()):d[k]=np.append(v,v[-1]+1 if k=='timestamp' else v[-1])
        with self.assertRaisesRegex(ValueError,'Repeated'):replay(log,ctx,61108000)

    def test_command_missing_pending_then_final_reject(self):
        log,ctx=fixture();log.tables[('vehicle_command',0)]['command'][0]=22
        with self.assertRaises(LandingPending):replay(log,ctx,61108000)
        with self.assertRaises(ValueError):replay(log,ctx,61108000,final=True)

    def test_left_land_between_diagnostics_rejected(self):
        log,ctx=fixture();s=log.tables[('vehicle_status',0)]
        for key,v in list(s.items()):s[key]=np.append(v,61106000 if key in ('timestamp','nav_state_timestamp') else 4 if key=='nav_state' else 0)
        with self.assertRaisesRegex(ValueError,'Left'):replay(log,ctx,61108000)

    def test_status_failure_and_future_nav_timestamp_rejected(self):
        for key,value in [('failsafe',1),('failure_detector_status',1),('nav_state_timestamp',61109000)]:
            log,ctx=fixture();log.tables[('vehicle_status',0)][key][-1]=value
            with self.subTest(key=key),self.assertRaises(ValueError):replay(log,ctx,61108000)

    def test_duplicate_backwards_publications_not_relaxed(self):
        for topic in ('sta_velocity_ctrl_status','vehicle_status'):
            for delta in (0,-1):
                log,ctx=fixture();d=log.tables[(topic,0)];d['timestamp'][-1]=d['timestamp'][-2]+delta
                with self.subTest(topic=topic,delta=delta),self.assertRaises(ValueError):replay(log,ctx,61108000)

    def test_stale_future_cli_and_raw_clock_rejected(self):
        for offset in (-1,500001):
            log,ctx=fixture();m=LandingMonitor();m.begin(**ctx)
            with self.subTest(offset=offset),self.assertRaises(ValueError):m.update(log,last(log),61108000+offset)
        log,ctx=fixture();m=LandingMonitor();m.begin(**ctx);d=last(log);d['timestamp']=62000000
        with self.assertRaisesRegex(ValueError,'raw transport'):m.update(log,d,62000000)

    def test_nonfinite_missing_diagnostic_and_backward_clock(self):
        log,ctx=fixture()
        for key in ('timestamp','fault','excitation','armed'):
            d=last(log);d[key]=float('nan')
            with self.subTest(key=key),self.assertRaises(ValueError):healthy(d)
        for key in ('first_fail','first_input'):
            d=last(log);del d[key]
            with self.subTest(missing=key),self.assertRaises(ValueError):healthy(d)
        m=LandingMonitor();m.begin(**ctx);m.update(log,last(log),61108000)
        with self.assertRaisesRegex(ValueError,'Backward'):m.update(log,last(log),61107999)

    def test_completion_not_allowed_pending_or_before_plan(self):
        m=LandingMonitor()
        with self.assertRaises(ValueError):m.require_complete()
        log,ctx=fixture();m.begin(**ctx);log.tables[('vehicle_status',0)]={k:v[:1] for k,v in log.tables[('vehicle_status',0)].items()}
        m.update(log,last(log),61108000)
        with self.assertRaises(ValueError):m.require_complete()

    def test_offline_entry_cannot_spawn_or_write(self):
        import run_v04_flight11 as flight
        with patch.object(flight.subprocess,'Popen') as spawn,patch.object(flight.mavutil,'mavlink_connection') as connect:
            with self.assertRaisesRegex(RuntimeError,'Offline'):flight.main(checks=Mock(),scenario_path=Path('/tmp/no'))
            spawn.assert_not_called();connect.assert_not_called()

    def test_flight_changes_only_landing_hooks_poll_and_disabled_guard(self):
        scripts=Path(__file__).parent
        old=(scripts/'run_v04_flight10.py').read_text()
        expected=old.replace('"""Protocol09 authorized,','"""Offline landing10 integration, disabled before any side effects;')
        a=expected.index('    # This entry alone');b=expected.index('    parser = argparse.ArgumentParser()',a)
        expected=expected[:a]+'    raise RuntimeError("Offline landing repair only; new frozen batch and authorization required")\n'+expected[b:]
        expected=expected.replace('        cli("commander", "mode", "auto:land")',
            '        landing_lower = topic("vehicle_local_position")["timestamp"]\n        cli("commander", "mode", "auto:land")')
        expected=expected.replace('        checks.planned_landing = True',
            '        checks.planned_landing = True\n        checks.begin_landing(hover_start, state["position"]["timestamp"], landing_lower, output)')
        expected=expected.replace('            if state["land"].get("landed") and state["status"].get("arming_state") == 1:',
            '            if (state["land"].get("landed") and state["status"].get("arming_state") == 1\n                    and checks.landing_complete()):')
        expected=expected.replace('            time.sleep(0.5/speed)\n        else:\n            raise TimeoutError("Landing/automatic disarm timeout")',
            '            time.sleep(0.1/speed)\n        else:\n            raise TimeoutError("Landing/automatic disarm timeout")')
        self.assertEqual(expected,(scripts/'run_v04_flight11.py').read_text())

    def test_context_begin_is_once_and_requires_cli_success_flags(self):
        p=load_protocol();c=Checks(p,{},p['jobs'][0],Path('/tmp/unused'))
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            with self.assertRaises(ValueError):c.begin_landing(1000000,61000000,61000000,out)
            self.assertFalse((out/'landing_context.json').exists())
            c.planned_landing=c.observation_completed=True
            c.begin_landing(1000000,61000000,61000000,out)
            with self.assertRaises(ValueError):c.begin_landing(1000000,61000000,61000000,out)

    def test_monitor_wiring_ignores_old_cli_nav_for_landing_classification(self):
        import v04_monitor10 as module
        log,ctx=fixture();p=load_protocol();c=Checks(p,{},p['jobs'][0],Path('/tmp/unused'))
        c.reference={'position':{}};c.frozen_yaw={};c.landing_live=Mock();c.landing_live.read.return_value=log
        c.landing.begin(**ctx);d=last(log)
        d.update(requested_mode=0,requested_axes=0,effective_mode=0,effective_axes=0,pending=0,reject=0)
        state=dict(position={'timestamp':61100000},status={'nav_state':4,'arming_state':2})
        def topic(name):return d if name=='sta_velocity_ctrl_status' else {'timestamp':61108000}
        with tempfile.TemporaryDirectory() as tmp,patch.object(module.BaseChecks,'monitor') as base,\
                patch.object(module,'check_cli_reference'),patch.object(module,'replay',return_value={'through_us':61108000}):
            c.monitor('landing',None,topic,Path(tmp),state)
            base.assert_called_once();self.assertFalse(c.landing_complete())
            e=json.loads((Path(tmp)/'landing10_monitor.jsonl').read_text())
            self.assertEqual(e['cli_status']['nav_state'],4);self.assertFalse(e['evidence']['pending'])

    def test_disarm_cli_must_wait_for_raw_clear_and_controller_disarm(self):
        log,ctx=fixture();p=load_protocol();c=Checks(p,{},p['jobs'][0],Path('/tmp/unused'))
        c.landing.begin(**ctx);c.latest_diagnostic=last(log)
        c.landing.update(log,c.latest_diagnostic,61108000)
        self.assertFalse(c.landing_complete())
        d=last(log);d['armed']=0;d['excitation_fault']=0
        c.latest_diagnostic=d
        self.assertTrue(c.landing.update(log,d,61108000)['pending'])
        self.assertFalse(c.landing_complete())
        raw=log.tables[('sta_velocity_ctrl_status',0)]
        for key,v in list(raw.items()):raw[key]=np.append(v,61112000 if key=='timestamp' else d[key])
        d['timestamp']=61112000;c.latest_diagnostic=d
        self.assertFalse(c.landing.update(log,d,61112000)['pending'])
        self.assertTrue(c.landing_complete())


class RealLanding10Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record=json.loads((ROOT/'results09/run01.json').read_text())
        cls.entry=max(cls.record['logs'],key=lambda e:e['bytes']);cls.source=Path(cls.entry['archive']).parent
        if digest(cls.entry['archive'])!=cls.entry['sha256']:raise ValueError('Original input changed')
        cls.log=ULog(cls.entry['archive']);cls.events={e['name']:e['timestamp_us'] for e in cls.record['events']}
        cls.context=dict(hover_start_us=cls.events['hover_start'],hover_end_us=cls.events['hover_end'],
                         command_lower_us=cls.events['land_command'],cli_success=True)

    def test_series08_real_gate_is_component_pass_not_flight_pass(self):
        through=int(self.log.get_dataset('sta_velocity_ctrl_status').data['timestamp'][-1])
        r=replay(self.log,self.context,through,final=True)
        self.assertEqual(r['classification']['expected_planned_landing_gate'],12)
        self.assertFalse(self.record['success'])
        with self.assertRaises(KeyError):full.check_complete(self.log,self.events,self.context)

    def test_reader_matches_independent_command_and_status_arrays(self):
        from v04_landing_live10 import LandingLiveLog, TOPICS
        actual=LandingLiveLog(self.entry['archive']).read();count=0
        for ds in self.log.data_list:
            if ds.name in TOPICS:
                got=actual.get_dataset(ds.name,ds.multi_id).data
                for key,v in ds.data.items():np.testing.assert_array_equal(v,got[key]);count+=1
        self.assertGreater(count,1049)

    def test_extended_reader_is_warmed_by_existing_heading_polls(self):
        import v04_monitor10 as module
        p=load_protocol();c=Checks(p,{},p['jobs'][0],Path('/tmp/unused'))
        c.live=Mock(path=Path(self.entry['archive']))
        with patch.object(module.HistoricalChecks,'start_heading',return_value={'test':'ref'}):
            self.assertEqual(c.start_heading(None,None),{'test':'ref'})
        self.assertIs(c.live,c.landing_live)
        self.assertEqual(len(c.live.read().get_dataset('vehicle_command').data['timestamp']),
                         len(self.log.get_dataset('vehicle_command').data['timestamp']))

    def test_real_gate_incremental_status_lag_reproduced_and_resolved(self):
        log=copy.deepcopy(self.log);s=log.get_dataset('vehicle_status').data;full_status=copy.deepcopy(s)
        for k in s:s[k]=s[k][full_status['timestamp']<108244000]
        with self.assertRaises(LandingPending):replay(log,self.context,108244000)
        for k in s:s[k]=full_status[k]
        self.assertEqual(replay(log,self.context,108244000)['classification']['expected_planned_landing_gate'],1)

    def test_real_future_transition_and_hidden_fault_rejected(self):
        for kind in ('future','fault'):
            log=copy.deepcopy(self.log)
            if kind=='future':
                s=log.get_dataset('vehicle_status').data;i=np.flatnonzero(s['timestamp']==108244000)[0];s['timestamp'][i]+=1;s['nav_state_timestamp'][i]+=1
            else:
                d=log.get_dataset('sta_velocity_ctrl_status').data;i=np.flatnonzero(d['timestamp']==108244000)[0];d['fault'][i]=1
            with self.subTest(kind=kind),self.assertRaises(ValueError):replay(log,self.context,108356000)


class FullLanding10Test(unittest.TestCase):
    def run_chain(self, mutation=None):
        import analyze_v00
        import analyze_v04_core04 as core
        import analyze_v04_protocol09 as old
        record=json.loads((ROOT/'results06/run01.json').read_text())
        entry=max(record['logs'],key=lambda x:x['bytes']);self.assertEqual(digest(entry['archive']),entry['sha256'])
        u=ULog(entry['archive'])
        if mutation:mutation(u)
        with tempfile.TemporaryDirectory(prefix='landing10-SYNTHETIC-') as tmp:
            run=Path(tmp)/'run';copy_metadata(Path(entry['archive']).parent,run)
            p=load_protocol();job=p['jobs'][0];p['startup_overrides'].update(job['parameters'])
            r=copy.deepcopy(record);r.update(source_head='SYNTHETIC',scenario_path=str(CONFIG/'execution.json'),
                scenario_sha256=fingerprint(CONFIG/'execution.json'))
            (run/'result.json').write_text(json.dumps(r));(run/'job.json').write_text(json.dumps(job))
            (run/'authorization.json').write_text(json.dumps(dict(approved=True,source_head='SYNTHETIC',
                execution_sha256=r['scenario_sha256'],stage=p['stage'],maximum_attempts=6,user_approval='SYNTHETIC ONLY')))
            events={e['name']:e['timestamp_us'] for e in r['events']}
            (run/'landing_context.json').write_text(json.dumps(dict(hover_start_us=events['hover_start'],
                hover_end_us=events['hover_end'],command_lower_us=events['land_command'],cli_success=True)))
            reader=lambda path:u if str(path)==entry['archive'] else ULog(path)
            with patch.object(analyze_v00,'ULog',side_effect=reader),patch.object(core,'ULog',side_effect=reader),\
                    patch.object(old,'ULog',side_effect=reader),patch.object(full,'ULog',side_effect=reader):
                result=full.analyze_offline(run,p,job)
            self.assertFalse(result['accepted'])
        return result

    def test_full_chain_positive_synthetic_keeps_metrics(self):
        r=self.run_chain();self.assertTrue(r['full_chain_passed'],r)
        self.assertIn('local_output',r['historical_chain']);self.assertIn('height_task',r['historical_chain'])

    def test_full_chain_wrong_inner_mode_still_rejected(self):
        def change(u):
            d=u.get_dataset('sta_velocity_ctrl_status').data;i=np.searchsorted(d['timestamp'],60e6);d['inner_mode'][i]=1
        self.assertFalse(self.run_chain(change)['full_chain_passed'])

    def test_full_chain_reset_still_rejected(self):
        def change(u):
            d=u.get_dataset('vehicle_attitude').data;i=np.searchsorted(d['timestamp'],110e6);d['quat_reset_counter'][i]+=1
        self.assertFalse(self.run_chain(change)['full_chain_passed'])

    def test_full_chain_wrong_command_rejected_by_new_component(self):
        def change(u):
            d=u.get_dataset('vehicle_command').data;i=np.flatnonzero((d['command']==176)&(d['param3']==6))[0];d['target_component'][i]=0
        r=self.run_chain(change);self.assertFalse(r['full_chain_passed']);self.assertIn('target_component',r['error'])


if __name__=='__main__':unittest.main()
