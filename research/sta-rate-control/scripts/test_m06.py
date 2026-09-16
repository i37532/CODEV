#!/usr/bin/env python3
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from unittest.mock import patch
from calibrate_m06 import calculate
from run_m06 import Checks
from compare_m06 import compare
from analyze_m04 import outer_yaw_feedforward_max


class M06Scripts(unittest.TestCase):
    def test_fixed_heading_accepts_complete_zero_feedforward(self):
        d=dict(timestamp=np.arange(200),yaw_sp_move_rate=np.zeros(200))
        self.assertEqual(outer_yaw_feedforward_max(d,0,199,.0001),0)

    def test_fixed_heading_rejects_spikes_nan_and_incomplete_data(self):
        for bad in (.785398,-.785398,float('nan'),float('inf')):
            d=dict(timestamp=np.arange(200),yaw_sp_move_rate=np.zeros(200))
            d['yaw_sp_move_rate'][50]=bad
            with self.assertRaises(ValueError):outer_yaw_feedforward_max(d,0,199,.0001)
        with self.assertRaises(ValueError):outer_yaw_feedforward_max(d,0,10,.0001)

    def test_yaw_calibration_sign_coupling_and_record(self):
        c=calculate()
        self.assertEqual(c,json.loads((Path(__file__).resolve().parents[1]/'m06/calibration.json').read_text()))
        self.assertAlmostEqual(c['g_Y'],34.5823263568,places=7)
        self.assertGreater(c['acceleration_jacobian'][0][2],19)
        self.assertLess(c['local_gain_variation'],.08)
        for sample in c['samples']: self.assertGreater(sample['delta_alpha'][2]*sample['delta_c_yaw'],0)

    def test_independent_yaw_config_and_precursor(self):
        for mode in (0,1):
            for yaw in (0,1):
                with patch.dict('os.environ',{'M06_MODE':str(mode),'M06_YAW_ONLY':str(yaw)}): c=Checks()
                self.assertEqual(c.axes,7*mode);self.assertEqual(c.protocol['trigger'],3 if yaw else 4)
                self.assertNotEqual(c.config['MC_STA_L1_Y'],c.config['MC_STA_L1_R'])
        with patch.dict('os.environ',{'M06_MODE':'2'}):
            with self.assertRaises(ValueError): Checks()

    def test_gate_rejects_cross_axis_degradation_idle_pid_and_precursor(self):
        protocol={'milestone':'M06','version':2,'trigger':4,'limits':{'rmse_ratio_max':1.25},'windows':{'yaw_only':[0,12]},
                  'scenario_parameters':{'MPC_YAW_MODE':3},'heading_contract':{'max_outer_yaw_feedforward_rad_s':.0001}}
        with tempfile.TemporaryDirectory() as tmp:
            runs=[]
            for i in range(6):
                p=Path(tmp)/str(i);p.mkdir();runs.append(p)
                s=dict(success=True,mode=int(i>=3),axes=7*int(i>=3),milestone='M06',pid_updates_armed=0 if i>=3 else 100,
                       binary_sha256='same',ulog_sha256=str(i),max_outer_yaw_feedforward_rad_s=0,
                       metrics={w:dict(rmse=[.004,.003,.002]) for w in ['hover','tracking','yaw_only']})
                for name,value in [('m04_analysis.json',s),('m04_protocol.json',protocol),('m04_config.json',{'MPC_YAW_MODE':3}),('m04_source_hashes.json',{'scene':'same'})]:
                    (p/name).write_text(json.dumps(value))
            self.assertTrue(compare(runs[:3],runs[3:])['success'])
            path=runs[5]/'m04_analysis.json';bad=json.loads(path.read_text())
            bad['metrics']['yaw_only']['rmse'][0]*=1.3;path.write_text(json.dumps(bad))
            self.assertFalse(compare(runs[:3],runs[3:])['success'])
            bad['pid_updates_armed']=1;path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):compare(runs[:3],runs[3:])
            bad['pid_updates_armed']=0;path.write_text(json.dumps(bad))
            protocol['trigger']=3
            for run in runs:(run/'m04_protocol.json').write_text(json.dumps(protocol))
            with self.assertRaises(ValueError):compare(runs[:3],runs[3:])


    def test_disarmed_transitions_require_reset_and_never_arm(self):
        with patch.dict('os.environ',{'M06_MODE':'1'}): checks=Checks()
        values={'MC_RTC_MODE':1,'MC_STA_AXES':7}; calls=[]
        def cli(*args):
            calls.append(args)
            if args[:2]==('param','set'): values[args[2]]=args[3]
            return 'nu: [0.0000, 0.0000, 0.0000]'
        def topic(name):
            if name=='vehicle_status':return {'arming_state':1}
            return dict(armed=False,effective_mode=values['MC_RTC_MODE'],effective_axes=values['MC_STA_AXES'],pending=False,config_pending=False,config_valid=True,fault=0)
        with tempfile.TemporaryDirectory() as tmp:
            checks('disarmed',cli,topic,Path(tmp))
            self.assertEqual([e['mask'] for e in json.loads((Path(tmp)/'postflight_transitions.json').read_text())],[1,3,7,0])
            self.assertEqual(calls[0],('logger','stop'))
            self.assertTrue(checks.flight_logger_stopped)
            with self.assertRaises(RuntimeError):checks('disarmed',cli,lambda n:{'arming_state':2},Path(tmp))
        self.assertFalse(any(call[0]=='commander' for call in calls))


if __name__=='__main__':unittest.main()
