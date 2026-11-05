"""Require the completed separate landing qualification before V06 tasks."""
import json
from pathlib import Path
from contact_model import SETTINGS
from landing_health import sha, REPO


def require_qualification(path):
    path=Path(path); q=json.loads(path.read_text())
    if not q['qualified'] or (q['planned'],q['accepted'],q['pairs'])!=(6,6,3):
        raise ValueError('Incomplete soft-landing qualification')
    if q['contact_settings']!=SETTINGS or q['contact_source_sha256']!=sha(path.parent/'contact_model.py'):
        raise ValueError('Contact candidate differs from qualified configuration')
    if q['original_iris_sha256']!=sha(REPO/'Tools/sitl_gazebo/models/iris/iris.sdf'):
        raise ValueError('Original Iris differs')
    if len(q['rows'])!=6 or {r['mode'] for r in q['rows']}!={0,1}:
        raise ValueError('Qualification lacks both algorithms')
    for name,digest in q['evidence_sha256'].items():
        if sha(Path(name))!=digest: raise ValueError('Qualification evidence changed '+name)
    return dict(source_head=q['source_head'],accepted=6,pairs=3,qualified_contact_sha256=sha(path))
