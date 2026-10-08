"""Generate new immutable AX04 artifacts; refuses overwrite. Never flies."""
import json
from pathlib import Path
import sys
from design import HERE, REPO, OLD, build, expanded, empty_outcomes, SEEDS
from common import fingerprint
from paired_stats import precision, summarize


def write(name, value):
    path = HERE/name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def main():
    import check_v04_protocol02 as audit
    audit.CONFIG = Path('/__AX04_no_directory_exemption__')
    initial = audit.seed_audit(list(SEEDS))
    if not initial['accepted']:
        raise RuntimeError('Seed collision/invalid history: '+str(initial))
    development = json.loads((HERE.parent/'ax03/results/summary.json').read_text())
    if not development['success'] or any(development['counts'][t]['accepted'] != 24 for t in ('H','V')):
        raise RuntimeError('AX03 incomplete')
    d = build()
    write('seed_audit_initial.json', initial)
    write('execution.json', d)
    write('manifest.json', expanded(d))
    outcomes = empty_outcomes(d)
    write('outcomes_unattempted.json', outcomes)
    write('precision.json', precision(development))
    for sub in ('pid', 'esta'):
        write(sub+'/frozen.json', json.loads((OLD/sub/'frozen.json').read_text()))
    for path in (OLD/'parameters').glob('*.json'):
        write('parameters/'+path.name, json.loads(path.read_text()))
    # Registration whitelist is exact files, never a directory exemption.
    registrations = ('seed_audit_initial.json','execution.json','manifest.json','outcomes_unattempted.json')
    write('seed_reservations.json', {str(HERE/p):fingerprint(HERE/p) for p in registrations})
    print('Generated 320 unattempted jobs; no formal outcome or flight produced')


if __name__ == '__main__':
    main()
