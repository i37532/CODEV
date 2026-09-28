import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import manual_contact as m


class ManualContact(unittest.TestCase):
    def test_qualified_model_and_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            env={'UNCHANGED':'yes','GAZEBO_MODEL_PATH':'untrusted'}
            result=m.prepare(Path(tmp)/'session',env)
            model=Path(result['model_path'])
            source=m.REPO/'Tools/sitl_gazebo/models/iris'
            m.validate(ET.parse(source/'iris.sdf').getroot(),ET.parse(model/'iris.sdf').getroot())
            self.assertEqual((model/'iris.sdf').read_bytes(),(model/'iris-gen.sdf').read_bytes())
            self.assertEqual(env['UNCHANGED'],'yes')
            self.assertEqual(env['GAZEBO_MODEL_PATH'],str(model.parent)+':'+str(source.parent))
            self.assertTrue((model/'meshes').is_symlink())

    def test_qualification_failure_has_no_model_side_effect(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'require_qualification',side_effect=ValueError('unqualified')):
            path=Path(tmp)/'session'; env={}
            with self.assertRaises(ValueError): m.prepare(path,env)
            self.assertFalse(path.exists()); self.assertEqual(env,{})

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'session'; m.prepare(path,{})
            before=(path/'models/iris/iris.sdf').read_bytes()
            with self.assertRaises(FileExistsError): m.prepare(path,{})
            self.assertEqual(before,(path/'models/iris/iris.sdf').read_bytes())

if __name__=='__main__': unittest.main()
