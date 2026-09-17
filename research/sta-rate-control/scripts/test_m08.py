import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from m08_ista_reference import ideal
from run_m08 import Checks, RESEARCH
from compare_m08 import ratios, compare


class M08Tests(unittest.TestCase):
    def test_independent_reference_equations_boundaries_and_neighbours(self):
        s=np.array([-.0625, np.nextafter(np.float32(-.0625),np.float32(-1)),0,.0625,
                    np.nextafter(np.float32(.0625),np.float32(1))],dtype=float)
        r=ideal(s,0.,.125,2.,4.,3.)
        np.testing.assert_array_equal(r['branch'],[2,3,2,2,1])
        np.testing.assert_allclose(r['virtual'],s+.125*r['a'],atol=1e-16)
        np.testing.assert_allclose(r['nu'],-.125*4*r['xi'],atol=1e-16)
        np.testing.assert_allclose(r['a'],-2*np.sqrt(np.abs(r['virtual']))*r['xi']+r['nu'],atol=1e-16)

    def test_staged_configuration_and_unchanged_scenes(self):
        for scene,suffix,axes in [('roll','roll',1),('rp','rp',3),('rpy','rpy',7)]:
            with patch.dict('os.environ',{'M08_MODE':'2','M08_SCENE':scene,'M08_CONFIG':str(RESEARCH/'m08'/('iris_ista_'+suffix+'.json'))}):
                c=Checks();self.assertEqual(c.axes,axes);self.assertEqual(c.mode,2)
                self.assertEqual(c.protocol['limits']['rmse_ratio_max'],1.25)
                self.assertEqual(c.protocol['hover_seconds'],60)
                self.assertEqual(c.config['MC_STA_L1_Y'],1.5)
                self.assertEqual('MPC_YAW_MODE' in c.config,scene=='rpy')

    def test_mode_and_scene_mismatch_rejected(self):
        for env in ({'M08_MODE':'3'},{'M08_MODE':'2','M08_SCENE':'roll'}):
            with patch.dict('os.environ',env):
                with self.assertRaises(ValueError):Checks()

    def test_cross_axis_gate_rejects_single_failed_window(self):
        ref=[{'metrics':{'hover':{'rmse':[1,1,1]},'yaw_only':{'rmse':[1,1,1]}}}]*3
        candidate=json.loads(json.dumps(ref[0]));candidate['metrics']['yaw_only']['rmse'][0]=1.26
        self.assertFalse(ratios(ref,[candidate],['hover','yaw_only'],1.25)['success'])
        with self.assertRaises(ValueError): compare([],[],[])

    def test_ground_transitions_clear_state_never_arm(self):
        with patch.dict('os.environ',{'M08_MODE':'2'}):c=Checks()
        values={'MC_RTC_MODE':2,'MC_STA_AXES':7};commands=[]
        def cli(*args):
            commands.append(args)
            if args[:2]==('param','set'):values[args[2]]=args[3]
            return 'nu: [0, 0, 0]'
        def topic(name):
            if name=='vehicle_status':return dict(arming_state=1)
            return dict(armed=False,effective_mode=values['MC_RTC_MODE'],effective_axes=values['MC_STA_AXES'],
                        pending=False,config_pending=False,config_valid=True,fault=0)
        with tempfile.TemporaryDirectory() as tmp:
            c('disarmed',cli,topic,Path(tmp))
            events=json.loads((Path(tmp)/'postflight_transitions.json').read_text());self.assertEqual(len(events),8)
            self.assertEqual(events[-1]['mode'],0)
        self.assertFalse(any(cmd[0]=='commander' for cmd in commands))

    def test_nine_run_comparison_rejects_parameter_drift_and_idle_pid(self):
        protocol=json.loads((RESEARCH/'m08/protocol.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            runs=[]
            for i in range(9):
                path=Path(tmp)/str(i);path.mkdir();runs.append(path);mode=i//3
                config=json.loads((RESEARCH/'m08/iris_pid.json').read_text())
                config.update(protocol['scenario_parameters'],MC_RTC_MODE=mode,MC_STA_AXES=7 if mode else 0)
                if mode==2:config['MC_STA_L1_P']=2.0
                summary=dict(success=True,mode=mode,axes=7 if mode else 0,pid_updates_armed=0 if mode else 100,
                             binary_sha256='same',ulog_sha256=str(i),
                             metrics={w:dict(rmse=[.004,.003,.002]) for w in ['hover','tracking',*protocol['windows']]})
                for name,obj in [('m04_analysis.json',summary),('m04_protocol.json',protocol),
                                 ('m04_config.json',config),('m04_source_hashes.json',{'same':'source'})]:
                    (path/name).write_text(json.dumps(obj))
            self.assertTrue(compare(runs[:3],runs[3:6],runs[6:])['success'])
            path=runs[8]/'m04_config.json';bad=json.loads(path.read_text());bad['MC_STA_L1_P']=2.4
            path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):compare(runs[:3],runs[3:6],runs[6:])
            bad['MC_STA_L1_P']=2.;path.write_text(json.dumps(bad))
            path=runs[8]/'m04_analysis.json';bad=json.loads(path.read_text());bad['pid_updates_armed']=1
            path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):compare(runs[:3],runs[3:6],runs[6:])
