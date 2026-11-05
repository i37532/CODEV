#!/usr/bin/env python3
"""External, disclosed orchestration exception for attempt 214 ONLY.

Do not mutate the frozen repository or old results. Preserve all frozen batch
checks and job order; add one explicit, fingerprint-bound review to its resume
decision. This is NOT a pre-arm-gap adjudication or a successful analysis.
"""
import hashlib
import inspect
import json
from pathlib import Path
import sys

REPO = Path('/home/yr/Desktop/Codev-autopilot')
ROOT = Path('/home/yr/Desktop/codev doc/experiments/M10-20260917/formal01')
LABEL = '0213_A_m1_inertia_s3103'
AUTHORIZATION = '允许第 214 轮也保持无效、不补飞，记录新的协议偏离后继续剩余 386 次'
BATCH_SHA = '742917618019f09419c86a62221b9be48157339df5c1411dda21bc1b7a5be119'
EXECUTION_SHA = '920d145bf4b1e169a2dd83dc736ef1de280f1b3850dbb1fa9850b712cf317b62'
ANALYSIS_SHA = '0413dd63db4a2527cd3aeaeac544a66f32470fff21b6f47c69d37b292d180489'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def authorized_214(root, label, reviewed):
    if root.resolve() != ROOT or label != LABEL:
        return False
    assert reviewed['user_authorization'] == AUTHORIZATION
    assert reviewed['disposition'] == 'retain_failed_attempt_and_continue'
    assert reviewed['user_authorized_inflight_data_loss'] is True
    for key in ('accepted', 'retained_prearm_gap', 'analysis_resolved_without_reflight', 'flight_repeated'):
        assert reviewed[key] is False, key
    assert sha(ROOT / (LABEL + '.execution.json')) == EXECUTION_SHA == reviewed['original_execution_sha256']
    assert sha(ROOT / LABEL / 'm10_analysis.json') == ANALYSIS_SHA == reviewed['new_analysis_sha256']
    assert sha(ROOT / LABEL / 'result.json') == reviewed['result_sha256']
    for path, fingerprint in reviewed['ulogs'].items():
        assert sha(path) == fingerprint
    row = json.loads((ROOT / LABEL / 'm10_analysis.json').read_text())
    assert row['success'] is False and row['failure_class'] == 'analysis_or_data_quality'
    return True


def main():
    source = REPO / 'research/sta-rate-control/scripts/batch_m10.py'
    assert sha(source) == BATCH_SHA, 'Frozen orchestration source changed'
    sys.path.insert(0, str(source.parent))
    import batch_m10
    code = inspect.getsource(batch_m10.execute)
    original = "if previous.get('halt') and not (reviewed.get('analysis_resolved_without_reflight') or retained_gap):"
    replacement = "if previous.get('halt') and not (reviewed.get('analysis_resolved_without_reflight') or retained_gap or authorized_214(root, label, reviewed)):"
    assert code.count(original) == 1
    batch_m10.authorized_214 = authorized_214
    exec(compile(code.replace(original, replacement), str(Path(__file__).resolve()) + ':disclosed_resume_extension', 'exec'), batch_m10.__dict__)
    reviewed = json.loads((ROOT / (LABEL + '.adjudication.json')).read_text())
    assert authorized_214(ROOT, LABEL, reviewed)
    assert not authorized_214(ROOT, '0214_B_m2_inertia_s3103', reviewed)
    assert not authorized_214(ROOT.parent, LABEL, reviewed)
    print('Authorized attempt 214 remains INVALID; only its resume halt is waived. No reflight.', flush=True)
    sys.argv = [str(source), 'formal', '--output', str(ROOT), '--plugins', str(ROOT.parent / 'plugins03'),
                '--frozen', str(REPO / 'research/sta-rate-control/m10/FROZEN.json'), '--speed', '5']
    batch_m10.main()


if __name__ == '__main__':
    main()
