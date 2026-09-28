"""Opt-in Iris contact variant; never edits source or controls/sensor signals."""
import copy
import math
import xml.etree.ElementTree as ET

COLLISION = "model/link[@name='base_link']/collision[@name='base_link_inertia_collision']"
SETTINGS = {'surface/contact/ode/kp': '2500', 'surface/contact/ode/kd': '50',
            'surface/contact/ode/max_vel': '0.2', 'max_contacts': '4'}


def shape(element):
    return (element.tag, tuple(sorted(element.attrib.items())), (element.text or '').strip(),
            tuple(shape(child) for child in element))


def checked_collision(root):
    matches = root.findall(COLLISION)
    if len(matches) != 1:
        raise ValueError('Exactly one original Iris base collision required')
    collision = matches[0]
    if collision.findtext('geometry/box/size') != '0.47 0.47 0.11':
        raise ValueError('Unexpected Iris collision geometry')
    if collision.findtext('surface/contact/ode/min_depth') != '0.001':
        raise ValueError('Unexpected contact depth')
    return collision


def derive(root):
    """New XML tree; source tree remains untouched. Reject already modified input."""
    collision = checked_collision(root)
    if (collision.find('max_contacts') is not None or
            collision.find('surface/contact/ode/kp') is not None or
            collision.find('surface/contact/ode/kd') is not None or
            collision.findtext('surface/contact/ode/max_vel') != '0'):
        raise ValueError('Not the pinned original contact')
    result = copy.deepcopy(root)
    target = checked_collision(result)
    for path, value in SETTINGS.items():
        parent_path, _, tag = path.rpartition('/')
        parent = target.find(parent_path) if parent_path else target
        node = target.find(path)
        if node is None:
            node = ET.SubElement(parent, tag)
        node.text = value
    validate(root, result)
    return result


def validate(original, derived):
    """Whitelist all structural differences, not just values in modified fields."""
    candidate = copy.deepcopy(derived)
    collision = checked_collision(candidate)
    for path, expected in SETTINGS.items():
        nodes = collision.findall(path)
        if len(nodes) != 1 or not math.isfinite(float(nodes[0].text)) or float(nodes[0].text) != float(expected):
            raise ValueError('Wrong/duplicate contact field '+path)
        if path == 'surface/contact/ode/max_vel':
            nodes[0].text = '0'
        else:
            parent_path, _, _ = path.rpartition('/')
            parent = collision.find(parent_path) if parent_path else collision
            parent.remove(nodes[0])
    if shape(original) != shape(candidate):
        raise ValueError('Changes outside contact whitelist')


def effective_contact(step=.004, ground_kp=1e12, ground_kd=1.):
    if not all(math.isfinite(x) and x > 0 for x in (step, ground_kp, ground_kd)):
        raise ValueError('Invalid physical input')
    kp = 1. / (1. / 2500. + 1. / ground_kp)
    kd = 50. + ground_kd
    return {'kp': kp, 'kd': kd, 'erp': step*kp/(step*kp+kd), 'cfm': 1./(step*kp+kd)}
