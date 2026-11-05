#!/usr/bin/env python3
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from calibrate_m05 import calculate
from run_m05 import Checks
from compare_m05 import compare


class M05Scripts(unittest.TestCase):
    def test_pitch_calibration_matches_record_and_sign(self):
        value=calculate()
        recorded=json.loads((Path(__file__).resolve().parents[1]/'m05/calibration.json').read_text())
        self.assertEqual(value,recorded)
        self.assertAlmostEqual(value['g_P'],112.7635334435,places=7)
        self.assertLess(value['local_gain_variation'],.08)
        self.assertNotEqual(value['g_P'],value['g_R_retained'])
        for row in value['samples']:
            self.assertGreater(row['delta_c_pitch']*row['delta_alpha'][1],0)

    def test_mode_axes_and_independent_gains(self):
        for mode in (0,1):
            with patch.dict('os.environ',{'M05_MODE':str(mode)}):
                c=Checks()
            self.assertEqual(c.axes,3*mode)
            self.assertEqual(c.protocol['trigger'],2)
            self.assertNotEqual(c.config['MC_STA_G_R'],c.config['MC_STA_G_P'])
            self.assertEqual(c.config['MC_STA_L1_R'],2.5)
        with patch.dict('os.environ',{'M05_MODE':'2'}):
            with self.assertRaises(ValueError): Checks()

    def test_noncommanded_axis_degradation_fails_frozen_phase_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs=[]
            protocol={'milestone':'M05','limits':{'rmse_ratio_max':1.25},
                      'windows':{'roll_only':[0,12],'pitch_only':[12,24],'synchronous':[24,36]}}
            for i in range(6):
                p=Path(tmp)/str(i);p.mkdir();runs.append(p)
                summary=dict(success=True,mode=int(i>=3),axes=3*int(i>=3),milestone='M05',
                             binary_sha256='same',ulog_sha256=str(i),
                             metrics={w:dict(rmse=[.004,.003,.002]) for w in ['hover','tracking',*protocol['windows']]})
                (p/'m04_analysis.json').write_text(json.dumps(summary))
                (p/'m04_protocol.json').write_text(json.dumps(protocol))
                (p/'m04_config.json').write_text('{}')
                (p/'m04_source_hashes.json').write_text('{"scenario":"same"}')
            self.assertTrue(compare(runs[:3],runs[3:])['success'])
            path=runs[5]/'m04_analysis.json'
            bad=json.loads(path.read_text())
            for axis,window in [(1,'roll_only'),(0,'pitch_only'),(2,'synchronous')]:
                bad['metrics'][window]['rmse'][axis]*=1.3
            path.write_text(json.dumps(bad))
            failed=compare(runs[:3],runs[3:])
            self.assertFalse(failed['success']); self.assertEqual(len(failed['violations']),3)
            bad['axes']=1;path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError): compare(runs[:3],runs[3:])

    def test_cleanup_preserves_pitch_and_roll_parameter_values(self):
        with patch.dict('os.environ',{'M05_MODE':'1'}): c=Checks()
        c.original={'MC_STA_L1_R':0.,'MC_STA_L1_P':0.,'MC_STA_G_P':0.,'MC_RTC_MODE':0,'MC_STA_AXES':0}
        calls=[]
        with tempfile.TemporaryDirectory() as tmp, patch('run_m04.M03Checks.get_param',side_effect=lambda cli,k:c.original[k]):
            c('cleanup',lambda *a:calls.append(a),None,Path(tmp))
            self.assertEqual(json.loads((Path(tmp)/'restored_parameters.json').read_text()),c.original)
        self.assertIn(('param','set','MC_STA_G_P',0.),calls)


if __name__=='__main__': unittest.main()
