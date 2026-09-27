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
from landing import LandingMonitor, LandingPending, replay, healthy, validate_context
from v04_monitor10 import Checks
from v04_protocol09 import load_protocol, CONFIG, fingerprint
from replay_v04_clock09 import ROOT, copy_metadata, digest
import analyze_v04_landing10 as full


def fixture():
    ts = np.array([1000000, 91000000, 91100000, 91104000, 91108000], dtype=np.uint64)
    d = dict(timestamp=ts, excitation_fault=np.array([0, 0, 0, 2, 2]), excitation=np.zeros(5),
             armed=np.ones(5), enabled=np.ones(5))
    for key in ('first_fail','first_input','retry_result','fault','sta_fault','failsafe','timing','inner_mode',
                'inner_axes','config_pending'):
        d[key] = np.zeros(5, dtype=int)
    for key in ('inner_divisor','inner_valid','pid_calls','valid'):
        d[key] = np.ones(5, dtype=int)
    status = dict(timestamp=np.array([1000000, 91104000], dtype=np.uint64),
                  nav_state_timestamp=np.array([900000, 91104000], dtype=np.uint64),
                  nav_state=np.array([4, 18]), failsafe=np.zeros(2), failure_detector_status=np.zeros(2))
    command = {k:np.array([v]) for k,v in dict(timestamp=91100000,command=176,
             param1=1,param2=4,param3=6,target_system=1,target_component=1).items()}
    log = Log({('sta_velocity_ctrl_status',0):d,('vehicle_status',0):status,('vehicle_command',0):command})
    ctx = dict(hover_start_us=1000000, hover_end_us=91000000, command_lower_us=91000000, cli_success=True)
    d['excitation_y']=np.zeros(5)
    return log, ctx


def last(log):
    return {k:v[-1].item() for k,v in log.get_dataset('sta_velocity_ctrl_status').data.items()}


class Landing10Test(unittest.TestCase):
    def test_same_time_transition_and_old_status_regression(self):
        log,ctx=fixture();r=replay(log,ctx,91108000,final=True)
        self.assertEqual(r['classification']['expected_planned_landing_gate'],2)
        self.assertFalse(r['consumed_status_proven'])

    def test_future_status_not_borrowed_for_earlier_gate(self):
        log,ctx=fixture();s=log.tables[('vehicle_status',0)];s['timestamp'][-1]=91104001;s['nav_state_timestamp'][-1]=91104001
        with self.assertRaisesRegex(ValueError,'past/equal'):replay(log,ctx,91108000)

    def test_missing_transition_pending_live_not_final(self):
        log,ctx=fixture();log.tables[('vehicle_status',0)]={k:v[:1] for k,v in log.tables[('vehicle_status',0)].items()}
        with self.assertRaises(LandingPending):replay(log,ctx,91108000)
        with self.assertRaises(ValueError):replay(log,ctx,91108000,final=True)

    def test_delayed_transition_resolves_without_changing_raw(self):
        log,ctx=fixture();original=copy.deepcopy(log);status=log.tables[('vehicle_status',0)]
        log.tables[('vehicle_status',0)]={k:v[:1] for k,v in status.items()}
        clock=[0.];m=LandingMonitor(lambda:clock[0]);m.begin(**ctx)
        self.assertTrue(m.update(log,last(log),91108000)['pending'])
        log.tables[('vehicle_status',0)]=status;clock[0]=.1
        self.assertFalse(m.update(log,last(log),91208000)['pending'])
        for key,values in original.tables[('sta_velocity_ctrl_status',0)].items():
            np.testing.assert_array_equal(log.tables[('sta_velocity_ctrl_status',0)][key],values)

    def test_timeout_exact_boundary_and_one_us_beyond(self):
        for elapsed,ok in [(500000,True),(500001,False)]:
            log,ctx=fixture();status=log.tables[('vehicle_status',0)];log.tables[('vehicle_status',0)]={k:v[:1] for k,v in status.items()}
            m=LandingMonitor(lambda:0);m.begin(**ctx);m.update(log,last(log),91108000)
            # Keep stream current: the first unresolved gate must not get a new deadline.
            d=log.tables[('sta_velocity_ctrl_status',0)]
            for key,v in list(d.items()):d[key]=np.append(v,91108000+elapsed if key=='timestamp' else v[-1])
            if ok:self.assertTrue(m.update(log,last(log),91108000+elapsed)['pending'])
            else:
                with self.assertRaisesRegex(ValueError,'timeout'):m.update(log,last(log),91108000+elapsed)
                self.assertTrue(m.failed)

    def test_wall_timeout_even_with_paused_simulator(self):
        log,ctx=fixture();log.tables[('vehicle_status',0)]={k:v[:1] for k,v in log.tables[('vehicle_status',0)].items()}
        wall=[0.];m=LandingMonitor(lambda:wall[0]);m.begin(**ctx);m.update(log,last(log),91108000)
        wall[0]=.500001
        with self.assertRaisesRegex(ValueError,'timeout'):m.update(log,last(log),91108000)

    def test_real_fault_never_hidden_by_pending(self):
        for field,value in [('excitation_fault',3),('first_fail',1),('retry_result',1),('fault',1),
                            ('sta_fault',1),('failsafe',1),('timing',1),('inner_mode',1),('valid',0)]:
            log,ctx=fixture();log.tables[('vehicle_status',0)]={k:v[:1] for k,v in log.tables[('vehicle_status',0)].items()}
            log.tables[('sta_velocity_ctrl_status',0)][field][2]=value
            with self.subTest(field=field),self.assertRaises(ValueError) as raised:replay(log,ctx,91108000)
            self.assertNotIsInstance(raised.exception,LandingPending)

    def test_fault_latch_cannot_be_cleared_or_replanned(self):
        log,ctx=fixture();m=LandingMonitor();m.begin(**ctx);bad=last(log);bad['fault']=1
        with self.assertRaises(ValueError):m.update(log,bad,91108000)
        with self.assertRaisesRegex(ValueError,'latched'):m.update(log,last(log),91108000)
        with self.assertRaises(ValueError):m.begin(**ctx)

    def test_no_plan_no_observation_or_failed_command_rejected(self):
        log,ctx=fixture();m=LandingMonitor()
        with self.assertRaisesRegex(ValueError,'Unplanned'):m.update(log,last(log),91108000)
        for field,value in [('hover_end_us',90999999),('command_lower_us',90999999),('cli_success',False)]:
            with self.subTest(field=field),self.assertRaises(ValueError):validate_context({**ctx,field:value})

    def test_gate_before_command_and_nonzero_output_or_disarmed_rejected(self):
        for field,value in [('excitation',.001),('armed',0),('excitation_fault',6)]:
            log,ctx=fixture();log.tables[('sta_velocity_ctrl_status',0)][field][-1]=value
            with self.subTest(field=field),self.assertRaises(ValueError):replay(log,ctx,91108000)
        log,ctx=fixture();log.tables[('vehicle_command',0)]['timestamp'][0]=91106000
        with self.assertRaisesRegex(ValueError,'before planned|before raw'):replay(log,ctx,91108000)

    def test_repeated_and_wrong_commands_rejected(self):
        for key,value in [('param3',5),('param2',3),('target_system',2),('target_component',0)]:
            log,ctx=fixture();log.tables[('vehicle_command',0)][key][0]=value
            with self.subTest(key=key),self.assertRaises(ValueError):replay(log,ctx,91108000)
        log,ctx=fixture();d=log.tables[('vehicle_command',0)]
        for k,v in list(d.items()):d[k]=np.append(v,v[-1]+1 if k=='timestamp' else v[-1])
        with self.assertRaisesRegex(ValueError,'Repeated'):replay(log,ctx,91108000)

    def test_command_missing_pending_then_final_reject(self):
        log,ctx=fixture();log.tables[('vehicle_command',0)]['command'][0]=22
        with self.assertRaises(LandingPending):replay(log,ctx,91108000)
        with self.assertRaises(ValueError):replay(log,ctx,91108000,final=True)

    def test_left_land_between_diagnostics_rejected(self):
        log,ctx=fixture();s=log.tables[('vehicle_status',0)]
        for key,v in list(s.items()):s[key]=np.append(v,91106000 if key in ('timestamp','nav_state_timestamp') else 4 if key=='nav_state' else 0)
        with self.assertRaisesRegex(ValueError,'Left'):replay(log,ctx,91108000)

    def test_status_failure_and_future_nav_timestamp_rejected(self):
        for key,value in [('failsafe',1),('failure_detector_status',1),('nav_state_timestamp',91109000)]:
            log,ctx=fixture();log.tables[('vehicle_status',0)][key][-1]=value
            with self.subTest(key=key),self.assertRaises(ValueError):replay(log,ctx,91108000)

    def test_duplicate_backwards_publications_not_relaxed(self):
        for topic in ('sta_velocity_ctrl_status','vehicle_status'):
            for delta in (0,-1):
                log,ctx=fixture();d=log.tables[(topic,0)];d['timestamp'][-1]=d['timestamp'][-2]+delta
                with self.subTest(topic=topic,delta=delta),self.assertRaises(ValueError):replay(log,ctx,91108000)

    def test_stale_future_cli_and_raw_clock_rejected(self):
        for offset in (-1,500001):
            log,ctx=fixture();m=LandingMonitor();m.begin(**ctx)
            with self.subTest(offset=offset),self.assertRaises(ValueError):m.update(log,last(log),91108000+offset)
        log,ctx=fixture();m=LandingMonitor();m.begin(**ctx);d=last(log);d['timestamp']=92000000
        with self.assertRaisesRegex(ValueError,'raw transport'):m.update(log,d,92000000)

    def test_nonfinite_missing_diagnostic_and_backward_clock(self):
        log,ctx=fixture()
        for key in ('timestamp','fault','excitation','armed'):
            d=last(log);d[key]=float('nan')
            with self.subTest(key=key),self.assertRaises(ValueError):healthy(d)
        for key in ('first_fail','first_input'):
            d=last(log);del d[key]
            with self.subTest(missing=key),self.assertRaises(ValueError):healthy(d)
        m=LandingMonitor();m.begin(**ctx);m.update(log,last(log),91108000)
        with self.assertRaisesRegex(ValueError,'Backward'):m.update(log,last(log),91107999)

    def test_completion_not_allowed_pending_or_before_plan(self):
        m=LandingMonitor()
        with self.assertRaises(ValueError):m.require_complete()
        log,ctx=fixture();m.begin(**ctx);log.tables[('vehicle_status',0)]={k:v[:1] for k,v in log.tables[('vehicle_status',0)].items()}
        m.update(log,last(log),91108000)
        with self.assertRaises(ValueError):m.require_complete()


    def test_only_observation_contract_changed_in_context(self):
        import inspect
        import landing
        import v04_landing10 as old
        expected=inspect.getsource(old.validate_context).replace('60e6 <= b-a <= 62e6','90e6 <= b-a <= 92e6')
        self.assertEqual(expected,inspect.getsource(landing.validate_context))
        for span,ok in [(60000000,False),(89999999,False),(90000000,True),(92000000,True),(92000001,False)]:
            ctx=dict(hover_start_us=1000000,hover_end_us=1000000+span,command_lower_us=1000000+span,cli_success=True)
            if ok: validate_context(ctx)
            else:
                with self.assertRaises(ValueError): validate_context(ctx)

    def test_runner_landing_and_full_analyzer_binding(self):
        import common,run,analyze,landing,landing_complete
        p=common.load_protocol(); c=run.Checks(p,{},p['jobs'][0],Path('/tmp/unused'))
        self.assertIs(type(c.landing),landing.LandingMonitor)
        self.assertIs(analyze.check_complete,landing_complete.check_complete)
        self.assertIs(landing_complete.replay,landing.replay)
        with tempfile.TemporaryDirectory() as tmp:
            c.planned_landing=c.observation_completed=True
            c.begin_landing(1000000,91000000,91000000,Path(tmp))
            self.assertEqual(c.landing.context['hover_end_us'],91000000)

    def test_y_gate_and_missing_output_rejected(self):
        for value in (.001,float('nan')):
            log,ctx=fixture(); log.tables[('sta_velocity_ctrl_status',0)]['excitation_y'][-1]=value
            with self.assertRaises(ValueError): replay(log,ctx,91108000,final=True)
            with self.assertRaises(ValueError): healthy(last(log))

if __name__=='__main__': unittest.main()
