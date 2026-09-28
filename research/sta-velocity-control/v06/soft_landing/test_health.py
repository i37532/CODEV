import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import numpy as np
from landing_health import check_health, window, verify_model, require_passive, REPO, sha
from contact_model import derive
import xml.etree.ElementTree as ET


class LandingHealth(unittest.TestCase):
    def test_actual_passive_admission_and_missing_cases(self):
        path=Path(__file__).resolve().parent/'offline03/evidence.json'
        self.assertEqual(require_passive(path)['candidate_cases'],10)
        e=json.loads(path.read_text()); e['cases'].pop()
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'bad.json'; f.write_text(json.dumps(e))
            with self.assertRaises(ValueError): require_passive(f)

    def log(self):
        tables={}; t=np.arange(100,dtype=np.int64)*4000+1000000
        for i in range(3):
            tables['sensor_accel',i]=dict(timestamp=t.copy(),timestamp_sample=t.copy(),
                x=np.zeros(100),y=np.zeros(100),z=np.full(100,-9.80665),
                **{f'clip_counter[{a}]':np.zeros(100) for a in range(3)})
            tables['vehicle_imu',i]=dict(timestamp=t.copy(),delta_velocity_clipping=np.zeros(100),delta_velocity_dt=np.full(100,4000))
        for i in range(6): tables['estimator_status',i]=dict(timestamp=t.copy(),filter_fault_flags=np.zeros(100))
        tables['estimator_selector_status',0]=dict(timestamp=t.copy(),primary_instance=np.zeros(100))
        log=SimpleNamespace(get_dataset=lambda n,i=0:SimpleNamespace(data=tables[n,i]))
        return log,tables

    def test_complete(self):
        r=check_health(self.log()[0],1010000,1300000)
        self.assertEqual(len(r['accel']),3); self.assertEqual(len(r['estimator']),6)

    def test_each_instance_fault_or_clipping_rejected(self):
        for name,key,instances,value in [('sensor_accel','clip_counter[2]',3,1),
                ('vehicle_imu','delta_velocity_clipping',3,4),('estimator_status','filter_fault_flags',6,131072),
                ('estimator_selector_status','primary_instance',1,2)]:
            for i in range(instances):
                log,tables=self.log(); tables[name,i][key][10]=value
                with self.assertRaises(ValueError): check_health(log,1010000,1300000)

    def test_missing_instance_not_zero_filled(self):
        log,tables=self.log(); del tables['vehicle_imu',2]
        with self.assertRaises(KeyError): check_health(log,1010000,1300000)

    def test_nonfinite_and_bad_time(self):
        for key,value in [('x',float('nan')),('z',float('inf')),('timestamp_sample',0)]:
            log,tables=self.log(); tables['sensor_accel',1][key][10]=value
            with self.assertRaises(ValueError): check_health(log,1010000,1300000)
        log,tables=self.log(); tables['vehicle_imu',0]['delta_velocity_dt'][10]=0
        with self.assertRaises(ValueError): check_health(log,1010000,1300000)

    def test_boundaries_gap_duplicate(self):
        for times in ([100,104,108],[100,104,104,108],[100,104,120,124]):
            with self.assertRaises(ValueError): window(dict(timestamp=np.array(times)),101,121,8)
        m=window(dict(timestamp=np.array([100,104,108,112])),101,110,4)
        self.assertEqual(m.tolist(),[True]*4)

    def test_real_failed_landing_clipping_is_still_rejected(self):
        from pyulog import ULog
        path=Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260928/V06/series02/run09')
        r=json.loads((path/'result.json').read_text())
        entry=max(r['logs'],key=lambda x:x['bytes'])
        self.assertEqual(sha(Path(entry['archive'])),entry['sha256'])
        u=ULog(entry['archive']); e={x['name']:x['timestamp_us'] for x in r['events']}
        end=int(u.get_dataset('sensor_accel',0).data['timestamp'][-1])-4000
        with self.assertRaisesRegex(ValueError,'clipping'): check_health(u,e['land_command'],end)

    def test_model_runtime_and_replay_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); directory=root/'models/iris'; directory.mkdir(parents=True)
            original=REPO/'Tools/sitl_gazebo/models/iris/iris.sdf'
            tree=derive(ET.parse(original).getroot())
            plugin=tree.find("model/plugin[@name='rotors_gazebo_imu_plugin']")
            plugin.set('filename','/frozen/libm10_imu.so')
            for name in ('iris.sdf','iris-gen.sdf'):
                ET.ElementTree(tree).write(directory/name)
            verify_model(root,Path('/frozen'))
            (root/'result.json').write_text(json.dumps(dict(logs=[dict(archive=str(root/'test.ulg'))])))
            manifest=dict(original=sha(original),derived=sha(directory/'iris.sdf'))
            (root/'model_manifest.json').write_text(json.dumps(manifest))
            verify_model(root,Path('/frozen'),replay=True)
            with self.assertRaises(ValueError): verify_model(root,Path('/wrong'))
            manifest['derived']='wrong'; (root/'model_manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): verify_model(root,Path('/frozen'),replay=True)
            with (directory/'iris-gen.sdf').open('a') as f: f.write(' ')
            with self.assertRaises(ValueError): verify_model(root,Path('/frozen'))


if __name__=='__main__': unittest.main()
