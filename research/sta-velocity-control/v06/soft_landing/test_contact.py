"""Model integrity only; passing is not flight or Gazebo physical acceptance."""
import copy
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from contact_model import COLLISION, derive, validate, shape, effective_contact

REPO = Path(__file__).resolve().parents[4]


class ContactModel(unittest.TestCase):
    def setUp(self):
        self.original = ET.parse(REPO/'Tools/sitl_gazebo/models/iris/iris.sdf').getroot()

    def test_source_is_unchanged(self):
        before = shape(self.original)
        new = derive(self.original)
        self.assertEqual(shape(self.original), before)
        self.assertNotEqual(shape(new), before)
        validate(self.original, new)

    def test_no_inertia_geometry_motor_or_sensor_change(self):
        for path in ('model/link/inertial/mass', 'model/link/inertial/inertia/ixx',
                     COLLISION+'/geometry/box/size', 'model/plugin/rotorVelocitySlowdownSim'):
            new = derive(self.original)
            node = new.find(path)
            self.assertIsNotNone(node, path)
            node.text = '99'
            with self.assertRaises(ValueError):
                validate(self.original, new)

    def test_unknown_attribute_and_plugin_rejected(self):
        for path in ('model', 'model/plugin', COLLISION):
            new = derive(self.original)
            new.find(path).set('unexpected', 'true')
            with self.assertRaises(ValueError):
                validate(self.original, new)

    def test_duplicate_field_rejected(self):
        new = derive(self.original)
        ET.SubElement(new.find(COLLISION+'/surface/contact/ode'), 'kp').text = '2500'
        with self.assertRaises(ValueError): validate(self.original, new)

    def test_missing_and_invalid_fields(self):
        for value in ('nan', 'inf', '-1', '2501'):
            new = derive(self.original)
            new.find(COLLISION+'/surface/contact/ode/kp').text = value
            with self.assertRaises(ValueError): validate(self.original, new)
        new = derive(self.original)
        new.find(COLLISION).remove(new.find(COLLISION+'/max_contacts'))
        with self.assertRaises(ValueError): validate(self.original, new)

    def test_wrong_input_and_second_application_rejected(self):
        with self.assertRaises(ValueError): derive(derive(self.original))
        self.original.find(COLLISION+'/surface/contact/ode/max_vel').text = '.1'
        with self.assertRaises(ValueError): derive(self.original)

    def test_missing_and_duplicate_collision_rejected(self):
        root = copy.deepcopy(self.original)
        root.find("model/link[@name='base_link']").append(copy.deepcopy(root.find(COLLISION)))
        with self.assertRaises(ValueError): derive(root)
        self.original.find("model/link[@name='base_link']").remove(self.original.find(COLLISION))
        with self.assertRaises(ValueError): derive(self.original)

    def test_ode_mapping(self):
        c = effective_contact()
        self.assertAlmostEqual(c['kp'], 2499.99999375)
        self.assertEqual(c['kd'], 51)
        self.assertAlmostEqual(c['erp'], 10/61, places=8)
        self.assertAlmostEqual(c['cfm'], 1/61, places=8)
        for bad in (0, -1, float('inf'), float('nan')):
            with self.assertRaises(ValueError): effective_contact(step=bad)


if __name__ == '__main__': unittest.main()
