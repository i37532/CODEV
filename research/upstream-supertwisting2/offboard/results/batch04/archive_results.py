#!/usr/bin/env python3
"""Archive B04 small evidence after stop/completion; never retry or change outcomes."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
from prepare import sha256
from run import active_simulators

ROOT = Path('/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102-B04')
DEST = Path(__file__).resolve().parent


def copy_exact(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256(target) != sha256(source):
            raise ValueError('Existing archive differs: ' + str(target))
    else:
        shutil.copy2(source, target)


def main():
    if active_simulators():
        raise ValueError('Refuse final archive while a simulator is running')
    manifest_path = ROOT / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest_sha = sha256(manifest_path)
    for path, expected in manifest['assets'].items():
        if sha256(path) != expected:
            raise ValueError('Frozen asset changed: ' + path)
    for job in manifest['jobs']:
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=job['repo'], text=True).strip()
        if head != job['source_head'] or sha256(Path(job['bin']) / 'px4') != job['firmware_sha256']:
            raise ValueError('Frozen source/firmware changed')
        for relative, expected in job['source_assets'].items():
            if sha256(Path(job['repo']) / relative) != expected:
                raise ValueError('Frozen source file changed: ' + relative)
    for label, repo in (('main', '/home/yr/Desktop/Codev-autopilot'),
                       ('original', '/home/yr/Desktop/Codev-SuperTwisting2-original')):
        actual = subprocess.check_output(['git', 'submodule', 'status', '--recursive'], cwd=repo, text=True)
        if actual != (ROOT / ('submodules_' + label + '.txt')).read_text():
            raise ValueError('Submodule versions changed')
    rows = []
    saw_stop = False
    for job in manifest['jobs']:
        directory = ROOT / 'runs' / job['id']
        if not directory.exists():
            saw_stop = True
            rows.append(dict(id=job['id'], task=job['task'], system=job['system'], attempted=False,
                             status='unattempted_batch_stopped'))
            continue
        if saw_stop:
            raise ValueError('Attempt after failure or skipped job')
        receipt = directory / 'result.json'
        result = json.loads(receipt.read_text())
        if not result.get('finished_utc') or result.get('remaining_simulators') != []:
            raise ValueError('Attempt is not closed')
        if result['manifest_sha256'] != manifest_sha or any(result[key] != job[key] for key in ('id', 'task', 'system')):
            raise ValueError('Attempt identity changed')
        accepted = result['success'] is True
        if accepted and not (result['independent_replay_passed'] and result['parameter_restore_exact']):
            raise ValueError('Incomplete successful acceptance')
        saw_stop = not accepted
        for log in result['logs']:
            if sha256(log['archive']) != log['sha256'] or Path(log['archive']).stat().st_size != log['bytes']:
                raise ValueError('Archived ULog changed')
        if accepted and (directory / 'metrics.json').read_bytes() != (directory / 'independent_replay.json').read_bytes():
            raise ValueError('Independent metrics replay differs')
        took_off = False
        if (directory / 'origin.json').exists():
            origin = json.loads((directory / 'origin.json').read_text())
            for line in (directory / 'samples.jsonl').read_text().splitlines():
                sample = json.loads(line)
                if not sample['land']['landed'] and origin['z'] - sample['position']['z'] > .3:
                    took_off = True
                    break
        for path in [*directory.glob('*.json'), *directory.glob('parameters_*.txt')]:
            copy_exact(path, DEST / job['id'] / path.name)
        rows.append(dict(id=job['id'], task=job['task'], system=job['system'], attempted=True,
                         status='accepted' if accepted else 'rejected', success=accepted, took_off=took_off,
                         task_completed=result.get('task_completed', False),
                         independent_replay_passed=result['independent_replay_passed'],
                         parameter_restore_exact=result['parameter_restore_exact'],
                         result_path=str(receipt), result_sha256=sha256(receipt), logs=result['logs'],
                         terminal_event=next((e for e in result['events'] if e['name'] == 'landed_disarmed'), None),
                         errors={key: value for key, value in result.items() if key.endswith('error')},
                         evidence_sha256={str(p): sha256(p) for p in directory.rglob('*') if p.is_file()}))
    attempted = sum(row['attempted'] for row in rows)
    accepted = sum(row.get('success', False) for row in rows)
    report = dict(status='completed_all_eight' if accepted == 8 else 'stopped_first_required_failure',
                  manifest_sha256=manifest_sha, planned=8, attempted=attempted, accepted=accepted,
                  took_off=sum(row.get('took_off', False) for row in rows),
                  task_completed=sum(row.get('task_completed', False) for row in rows),
                  rejected=attempted - accepted, unattempted=8 - attempted,
                  historical_attempts_before=5, historical_attempts_after=5 + attempted,
                  cumulative_maximum=13, no_retry=True, no_retuning=True, no_threshold_change=True,
                  frozen_asset_count=len(manifest['assets']), source_assets_unchanged=True,
                  recursive_submodules_unchanged=True, remaining_simulators=[],
                  tests=manifest['combined_offline_qualification'], no_push=True, rows=rows)
    for path in [*ROOT.glob('*.json'), *ROOT.glob('*.log'), *ROOT.glob('*.txt')]:
        copy_exact(path, DEST / path.name)
    for path in (ROOT / 'live_bridge02').rglob('*'):
        if path.is_file(): copy_exact(path, DEST / path.relative_to(ROOT))
    with (DEST / 'batch_result.json').open('x') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({key: report[key] for key in ('status', 'planned', 'attempted', 'accepted', 'rejected', 'unattempted', 'frozen_asset_count')}))


if __name__ == '__main__': main()
