#!/usr/bin/env python3
import json
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch
import numpy as np
from calibrate_m04 import calculate
from run_m04 import Checks, arrays
from analyze_m04 import check_gyro_events
from compare_m04 import compare


class M04Scripts(unittest.TestCase):
    def test_v3_land_parameters_are_restored_together(self):
        with patch.dict('os.environ',{'M04_MODE':'0'}):
            c=Checks()
        self.assertEqual(c.config['MPC_LAND_SPEED'],0.3)
        self.assertEqual(c.config['LNDMC_Z_VEL_MAX'],0.3)
        c.original={'MPC_LAND_SPEED':0.7,'LNDMC_Z_VEL_MAX':0.5}
        calls=[]
        with tempfile.TemporaryDirectory() as tmp, patch('run_m04.M03Checks.get_param',side_effect=lambda cli,k:c.original[k]):
            c('cleanup',lambda *a:calls.append(a),None,Path(tmp))
        self.assertLess(calls.index(('param','set','MPC_LAND_SPEED',0.7)),calls.index(('param','set','LNDMC_Z_VEL_MAX',0.5)))

    def test_comparison_requires_matching_protocols_and_three_repeats(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs=[]
            for i in range(6):
                p=Path(tmp)/str(i);p.mkdir();runs.append(p)
                (p/'m04_analysis.json').write_text(json.dumps(dict(success=True,mode=int(i>=3),binary_sha256='one',ulog_sha256=str(i),
                    metrics={w:dict(rmse=[0.004,0.003,0.002]) for w in ['hover','tracking']})))
                (p/'m04_protocol.json').write_text(json.dumps(dict(limits=dict(rmse_ratio_max=1.25))))
                (p/'m04_config.json').write_text('{}')
                (p/'m04_source_hashes.json').write_text('{"calibration":"one"}')
            self.assertTrue(compare(runs[:3],runs[3:])['success'])
            with self.assertRaises(ValueError):
                compare(runs[:2],runs[3:])
            with self.assertRaises(ValueError):
                compare(runs[:3],[runs[3],runs[4],runs[4]])
            path=runs[5]/'m04_analysis.json'
            bad=json.loads(path.read_text()); bad['metrics']['tracking']['rmse'][0]=0.006
            path.write_text(json.dumps(bad))
            self.assertFalse(compare(runs[:3],runs[3:])['success'])
            (runs[5]/'m04_protocol.json').write_text('{}')
            with self.assertRaises(ValueError):
                compare(runs[:3],runs[3:])

    def test_switch_fifo_history_requires_suppression_and_complete_events(self):
        g={k:np.array(v) for k,v in dict(reason=[2,1],timestamp_sample=[8,12],
            previous_sample=[12,12],published=[0,0],event_seq=[3,4]).items()}
        check_gyro_events(g,np.array([4,8,12,16]))
        for key,value in [('published',[1,0]),('timestamp_sample',[7,12]),('event_seq',[3,5]),('reason',[3,1])]:
            bad=dict(g); bad[key]=np.array(value)
            with self.assertRaises(ValueError):
                check_gyro_events(bad,np.array([4,8,12,16]))

    def test_model_sign_and_local_working_point(self):
        result=calculate()
        self.assertAlmostEqual(result['g_R'],130.5752831836,places=7)
        self.assertLess(result['local_gain_variation'],.08)
        self.assertAlmostEqual(result['mass_kg'],1.55)
        for sample in result['samples']:
            self.assertGreater(sample['c']*sample['delta_alpha'],0)

    def test_model_record_matches_recomputation(self):
        recorded=json.loads((Path(__file__).resolve().parents[1]/'m04/calibration.json').read_text())
        self.assertEqual(recorded,calculate())

    def test_listener_vector_and_missing(self):
        self.assertEqual(arrays(' q: [1.0, 0, -0.2, 0]\n','q'),[1.,0.,-.2,0.])
        with self.assertRaises(RuntimeError):
            arrays('missing','q')

    def test_modes_are_explicit(self):
        with patch.dict('os.environ',{'M04_MODE':'2'}):
            with self.assertRaises(ValueError):
                Checks()

    def test_fault_is_abort_not_recovery(self):
        with patch.dict('os.environ',{'M04_MODE':'1'}):
            c=Checks()
        status=dict(effective_mode=1,effective_axes=1,fault=8,abort_requested=True,timestamp=1000000)
        with self.assertRaisesRegex(RuntimeError,'Latched'):
            c.monitor('hover',None,lambda _:status,None,{'position':{'timestamp':1000000}})

    def test_time_and_measurement_abort(self):
        with patch.dict('os.environ',{'M04_MODE':'0'}):
            c=Checks()
        d=dict(effective_mode=0,effective_axes=0,fault=0,abort_requested=False,timestamp=1000000,
               publish_seq=1,armed=True,output_valid=False,timing_status=0,measurement_valid=True)
        with self.assertRaisesRegex(RuntimeError,'Invalid active'):
            c.monitor('hover',None,lambda _:d,None,{'position':{'timestamp':1000000}})
        d['timestamp']=1
        with self.assertRaisesRegex(RuntimeError,'Stale'):
            c.monitor('hover',None,lambda _:d,None,{'position':{'timestamp':3000000}})


if __name__=='__main__':
    unittest.main()
