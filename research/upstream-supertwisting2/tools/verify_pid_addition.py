#!/usr/bin/env python3
"""Verify the single PID extension and immutable prior three-flight evidence."""
import json
from pathlib import Path

import numpy as np
from pyulog import ULog

from prepare_compare import DATA, REPO, sha, git, save
from run_hover import active_simulators


def verify():
    out = Path('/home/yr/Documents/UPSTREAM_STA2_PID_RSTA_RISTA_HOVER_20261102')
    old_out = Path('/home/yr/Documents/UPSTREAM_STA2_RSTA_RISTA_HOVER_20261102')
    entry = json.loads((DATA/'entry.json').read_text())
    manifest = json.loads((DATA/'manifest04_pid.json').read_text())
    analysis = json.loads((out/'metrics.json').read_text())
    replay = json.loads((DATA/'analysis_replay_pid01/metrics.json').read_text())
    old_analysis = json.loads((old_out/'metrics.json').read_text())
    old_receipt = json.loads((DATA/'verification.json').read_text())
    assert analysis['summary'] == replay['summary']
    assert analysis['summary']['complete_comparison'] and analysis['summary']['planned'] == 4
    assert [r['metrics'] for r in analysis['runs']] == [r['metrics'] for r in replay['runs']]
    assert [r['metrics'] for r in analysis['runs'][:3]] == [r['metrics'] for r in old_analysis['runs']]
    assert all(sha(REPO/n) == h for n, h in entry['dirty_files'].items())
    assert git(REPO, 'rev-parse', 'HEAD') == entry['head']
    assert git(REPO, 'branch', '--show-current') == entry['branch']
    assert git(REPO, 'submodule', 'status', '--recursive') == entry['submodules']
    assert sha(REPO/'build/px4_sitl_default/bin/px4') == entry['firmware_sha256']
    assert sha(REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016') == '06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc'
    for record in old_receipt['records']:
        assert sha(record['result_path']) == record['result_sha256']
        for log in record['ulog']:
            assert sha(log['archive']) == log['sha256']
    records = []
    for job, row in zip(manifest['jobs'], analysis['runs']):
        result = json.loads(Path(job['result_path']).read_text())
        assert result['success'] and result['parameter_restore_exact'] and not result['remaining_simulators']
        assert sha(Path(job['bin'])/'px4') == job['firmware_sha256']
        for p, h in job['source_assets'].items():
            assert sha(Path(job['repo'])/p) == h
        for log in result['logs']:
            assert sha(log['archive']) == log['sha256']
            assert Path(log['archive']).stat().st_size == log['bytes']
        records.append(dict(id=job['id'], label=job['label'], result_path=job['result_path'],
            result_sha256=sha(job['result_path']), logs=result['logs']))
    row = analysis['runs'][-1]
    log = ULog(row['ulog']['archive'], message_name_filter_list=['sta_velocity_ctrl_status','sta_rate_ctrl_status'])
    diagnostics = {}
    expected = {
        'sta_velocity_ctrl_status':dict(effective_mode=0, effective_axes=0, active_axes=0,
            committed_axes=0, pid_axes=7, inner_mode=0, inner_axes=0, inner_divisor=1,
            inner_valid=1, fault=0),
        'sta_rate_ctrl_status':dict(effective_mode=0, effective_axes=0, div_eff=1,
            pid_updated=1, experiment_updated=0, fault=0)}
    for name, fields in expected.items():
        data = log.get_dataset(name).data
        t = data['timestamp']
        mask = (t >= row['events']['hover_start']) & (t <= row['events']['hover_end'])
        assert mask.sum() >= 20
        for field, value in fields.items():
            assert field in data and np.all(data[field][mask] == value), (name, field)
        diagnostics[name] = dict(samples=int(mask.sum()), verified_fields=fields)
    assert not active_simulators()
    receipt = dict(verified=True, new_attempts=1, new_takeoffs=1, new_accepted=1,
        total_launches=6, total_takeoffs=4, total_accepted=4, historical_prearm_failures=2,
        historical_records_unchanged=True, historical_metrics_unchanged=True,
        redecoded_metrics_equal=True, protected_user_files=len(entry['dirty_files']),
        parameter_restore_exact=True, branch=entry['branch'], head=entry['head'],
        firmware_sha256=entry['firmware_sha256'], runner_tests=57, diagnostics=diagnostics,
        manifest_sha256=sha(DATA/'manifest04_pid.json'), metrics_sha256=sha(out/'metrics.json'),
        old_receipt_sha256=sha(DATA/'verification.json'), records=records,
        figures=[dict(path=p.name,sha256=sha(p)) for p in sorted(out.glob('*.png'))])
    save(DATA/'verification_pid.json', receipt)
    save(out/'verification.json', receipt)
    print(json.dumps({k:receipt[k] for k in ('verified','new_attempts','total_accepted',
        'historical_records_unchanged','historical_metrics_unchanged','protected_user_files')}, ensure_ascii=False))


if __name__ == '__main__':
    verify()
