"""Independent formal bindings; no inherited AX03 permission or seed exemption."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from design import HERE as CONFIG, REPO, OLD, validate, expanded

LEGACY = REPO / 'research/sta-velocity-control/v08/protocol02'
QUALIFICATION = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-AXIS-ABLATION-20261008/AX04/qualified_source.json')
for path in (OLD, LEGACY, REPO/'research/sta-velocity-control/scripts',
             REPO/'research/sta-velocity-control/v06/soft_landing'):
    if str(path) not in sys.path:
        sys.path.append(str(path))
from v04_protocol10 import load_protocol as inherited


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def design():
    return json.loads((CONFIG/'execution.json').read_text())


def jobs():
    return expanded(design())


def validate_manifest(d=None):
    return validate(design() if d is None else d)


def load_protocol():
    d = design()
    p = inherited()
    p.update(d['protocol_overrides'])
    p.update(stage=d['stage'], jobs=expanded(d), seeds=d['seeds'], maximum_attempts=320,
             flight_authorized=False, execution_ready=True)
    p['startup_overrides'] = {**p['startup_overrides'], **d['fixed_parameters']}
    p['candidate'] = {k: v for k, v in d['fixed_parameters'].items() if k.startswith(('MPC_VC_L','MPC_VC_NU','MPC_VC_A_'))}
    p['artifacts'] = {**p['artifacts'], 'new_run_root': d['output_root']}
    return p


def fresh_seeds():
    import check_v04_protocol02 as audit
    old = audit.CONFIG
    try:
        audit.CONFIG = Path('/__AX04_no_directory_exemption__')
        result = audit.seed_audit(design()['seeds'])
    finally:
        audit.CONFIG = old
    allowed = json.loads((CONFIG/'seed_reservations.json').read_text())
    for path, sha in allowed.items():
        if fingerprint(path) != sha:
            raise RuntimeError('Changed seed design reservation ' + path)
    result['design_registrations'] = [x for x in result['matches'] if x['path'] in allowed]
    result['matches'] = [x for x in result['matches'] if x['path'] not in allowed]
    result['accepted'] = not result['matches'] and not result['invalid_json']
    result['excluded'] = 'none; exact fingerprinted unattempted/design registrations only'
    return result


def require_authorization(path, protocol):
    f = Path(path) if path else None
    if f is None or not f.is_absolute() or not f.is_file():
        raise RuntimeError('AX04 cannot fly; separate explicit AX05 authority receipt required')
    r = json.loads(f.read_text())
    if (r.get('approved') is not True or r.get('stage') != protocol['stage']
        or r.get('maximum_attempts') != 320
        or r.get('basis') != 'User explicitly requested AX05, limited to this frozen 320-attempt batch'):
        raise RuntimeError('No valid stage-specific AX05 permission')
    head = subprocess.check_output(['git','rev-parse','HEAD'], cwd=REPO, text=True).strip()
    qualified = qualification()
    if (r.get('approved') is not True or r.get('source_head') != head
        or r.get('stage') != protocol['stage'] or r.get('maximum_attempts') != 320
        or r.get('execution_sha256') != fingerprint(CONFIG/'execution.json')
        or r.get('frozen_sha256') != fingerprint(CONFIG/'frozen.json')
        or r.get('firmware_sha256') != qualified['firmware_sha256']
        or r.get('qualification_sha256') != fingerprint(QUALIFICATION)
        or head != qualified['source_head']
        or r.get('basis') != 'User explicitly requested AX05, limited to this frozen 320-attempt batch'):
        raise RuntimeError('Wrong AX05 source/protocol/budget/authority binding')
    validate_manifest()
    return r


def qualification():
    """Post-commit offline receipt breaks Git SHA/binary hash circularity.

    It cannot be minted by the flight runner. AX04 creates it only after the
    final source commit is clean, rebuilt, and offline checks succeed.
    """
    q = json.loads(QUALIFICATION.read_text())
    if (q.get('success') is not True or q.get('new_flights') != 0
        or q.get('frozen_sha256') != fingerprint(CONFIG/'frozen.json')
        or q.get('execution_sha256') != fingerprint(CONFIG/'execution.json')):
        raise RuntimeError('Missing or inconsistent AX04 clean-source qualification')
    return q


class Admission:
    """Balance includes PID; numerical paired risk gates are deferred, not relaxed."""
    def __init__(self):
        self.jobs = jobs()
        self.accepted = []
        self.metrics = {}
        self.checked = set()
        self.failed = False
        self.last_pairs = []

    def before(self, job):
        self.last_pairs = []
        n = len(self.accepted)
        if self.failed or n >= 320 or self.jobs[n] != job:
            raise RuntimeError('Failed/exhausted/out-of-order formal batch')
        if n % 8 == 0 and len(self.checked) != (n // 8) * 7:
            raise RuntimeError('Previous seed block has unresolved paired gates')
        if job['task'] == 'V' and (n < 160 or len(self.checked) < 140):
            raise RuntimeError('H160/140paired gates incomplete')

    def accept(self, job, metrics):
        self.before(job)
        if metrics.get('accepted') is not True or metrics.get('job') != job:
            self.failed = True
            raise RuntimeError('Required flight/log validity failed')
        key = job['task'], job['seed']
        block = self.metrics.setdefault(key, {})
        block[job['candidate']] = metrics
        pairs = []
        if 'PID' in block:
            from core import compare
            for name, item in block.items():
                pair_key = (*key, name)
                if name == 'PID' or pair_key in self.checked:
                    continue
                pair = compare(block['PID'], item)
                pair.update(candidate=name, axes=item['job']['axes'])
                self.last_pairs.append(pair)
                if not pair['accepted']:
                    self.failed = True
                    raise RuntimeError('Frozen paired development risk gate failed: ' + str(pair_key))
                self.checked.add(pair_key)
                pairs.append(pair)
        self.accepted.append(job)
        return pairs

    def abort(self):
        self.failed = True
