"""Generate derived source/seed snapshots; no flight or parameter writes."""
import json
from common import CONFIG, REPO, digest, fresh_seeds
from capture_v04_protocol10 import capture


def main():
    for name in ('frozen.json', 'seed_audit.json'):
        if (CONFIG / name).exists(): raise RuntimeError('Freeze already exists; do not overwrite it')
    seeds = fresh_seeds()
    if not seeds['accepted']: raise RuntimeError('Seed reuse or invalid registry')
    frozen = capture()
    names = set(frozen['assets'])
    names.update(str(p.relative_to(REPO)) for p in CONFIG.glob('*') if p.suffix in ('.py', '.json', '.md'))
    names.update(['src/modules/logger/logged_topics.cpp', 'src/modules/logger/logged_topics.h',
                  'src/modules/logger/params.c', 'src/modules/logger/EstimatorDiagnosticTopicsTest.cpp'])
    frozen['assets'] = {name: digest(REPO / name) for name in sorted(names)}
    frozen['kind'] = 'One PID diagnostic with unchanged flight gates and opt-in additional logging'
    (CONFIG / 'seed_audit.json').write_text(json.dumps(seeds, indent=2) + '\n')
    (CONFIG / 'frozen.json').write_text(json.dumps(frozen, indent=2) + '\n')
    print(json.dumps(dict(assets=len(names), parsed=seeds['files_parsed'], accepted=seeds['accepted'])))


if __name__ == '__main__': main()
