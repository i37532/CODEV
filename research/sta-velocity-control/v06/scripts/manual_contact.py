"""Qualified contact for the separate V06 viewer; no seeded IMU or control edits."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

V06=Path(__file__).resolve().parents[1]
REPO=V06.parents[2]
sys.path.insert(0,str(V06/'soft_landing'))
from contact_model import derive, validate, SETTINGS
from qualification import require_qualification


def prepare(output, env):
    require_qualification(V06/'soft_landing/qualified_contact.json')
    source=REPO/'Tools/sitl_gazebo/models/iris'
    model=Path(output)/'models/iris'; model.mkdir(parents=True,exist_ok=False)
    original=ET.parse(source/'iris.sdf').getroot()
    derived=derive(original); validate(original,derived)
    ET.ElementTree(derived).write(model/'iris.sdf',encoding='utf-8',xml_declaration=True)
    shutil.copyfile(model/'iris.sdf',model/'iris-gen.sdf')
    shutil.copyfile(source/'model.config',model/'model.config')
    (model/'meshes').symlink_to(source/'meshes',target_is_directory=True)
    env['GAZEBO_MODEL_PATH']=str(model.parent)+':'+str(source.parent)
    record=dict(settings=SETTINGS,model_path=str(model),original_sha256=hashlib.sha256((source/'iris.sdf').read_bytes()).hexdigest(),
                derived_sha256=hashlib.sha256((model/'iris.sdf').read_bytes()).hexdigest(),imu='original plugin; manual viewer is not a paired seeded experiment')
    (Path(output)/'model_manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    return record
