#!/usr/bin/env python3
"""Read-only experiment checks, then a new receipt; no simulation capability."""
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from pyulog import ULog

from prepare_compare import DATA, REPO, ORIGINAL, sha, git, save

entry = json.loads((DATA/'entry.json').read_text())
manifest = json.loads((DATA/'manifest03.json').read_text())
figures = Path('/home/yr/Documents/UPSTREAM_STA2_RSTA_RISTA_HOVER_20261102')
analysis = json.loads((figures/'metrics.json').read_text())
replay = json.loads((DATA/'analysis_replay01/metrics.json').read_text())
assert analysis['summary'] == replay['summary']
assert [r['metrics'] for r in analysis['runs']] == [r['metrics'] for r in replay['runs']]
assert analysis['summary']['complete_three_system_comparison']
assert all(sha(REPO/name)==value for name,value in entry['dirty_files'].items())
assert git(REPO,'rev-parse','HEAD') == entry['head']
assert git(REPO,'branch','--show-current') == 'research/upstream-supertwisting2'
assert git(REPO,'submodule','status','--recursive') == entry['submodules']
assert sha(REPO/'build/px4_sitl_default/bin/px4') == entry['firmware_sha256']
assert sha(REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016') == '06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc'
assert not git(ORIGINAL,'diff','--ignore-submodules=dirty','--name-only','HEAD')
records = []
for id in ('S001','S101','S102','S202','S203'):
    path = DATA/'runs'/id/'result.json'
    result = json.loads(path.read_text())
    assert result['parameter_restore_exact'] and not result['remaining_simulators']
    takeoff = any(e['name']=='takeoff_command' for e in result['events'])
    for log in result['logs']:
        assert sha(log['archive']) == log['sha256']
        assert Path(log['archive']).stat().st_size == log['bytes']
        if not takeoff:
            decoded = ULog(log['archive'],message_name_filter_list=['vehicle_status'])
            data = decoded.get_dataset('vehicle_status').data
            assert len(data['timestamp']) and np.all(data['arming_state'] != 2)
    records.append(dict(id=id,success=result['success'],takeoff=takeoff,
        result_path=str(path),result_sha256=sha(path),ulog=result['logs'],
        failure=result.get('error') or result.get('analysis_error')))
assert sum(r['takeoff'] for r in records) == 3
assert sum(r['success'] for r in records) == 3
for job in manifest['jobs']:
    assert sha(Path(job['bin'])/'px4') == job['firmware_sha256']
    for p,v in job['source_assets'].items(): assert sha(Path(job['repo'])/p) == v
receipt = dict(verified=True,process_launches=5,prearm_tooling_failures=2,takeoffs=3,completed_flights=3,
    retries_of_airborne_tasks=0,parameter_restore_exact=True,protected_user_files=len(entry['dirty_files']),
    branch=git(REPO,'branch','--show-current'),head=entry['head'],
    author_head=git(ORIGINAL,'rev-parse','HEAD'),original_tracked_control_changes=0,
    independent_analysis_equal=True,offline_script_tests=49,records=records,
    analysis_metrics_sha256=sha(figures/'metrics.json'),
    native_position_logging_hz={'Upstream STA2':125,'RSTA':10,'RISTA':10},
    limitations=['one flight per complete system','different PX4/controller/model systems',
        'native logging rates differ; not a high-frequency jitter comparison',
        'queued vehicle_local_position_log was not present; no invented dense data',
        'two startup-only harness failures retained; numerical/flight thresholds unchanged'],
    build_logs=[dict(path=str(p),sha256=sha(p)) for p in sorted(DATA.glob('*log'))],
    figures=[dict(name=p.name,sha256=sha(p)) for p in sorted(figures.glob('*.png'))])
save(DATA/'verification.json',receipt)
save(figures/'verification.json',receipt)
print(json.dumps({k:receipt[k] for k in ['verified','process_launches','prearm_tooling_failures',
    'takeoffs','completed_flights','independent_analysis_equal','protected_user_files']},ensure_ascii=False))
