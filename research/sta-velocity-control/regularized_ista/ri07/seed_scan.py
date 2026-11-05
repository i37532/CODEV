"""Strict all-history formal-seed scan; exact file reservations, never root exemptions."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('_ri07_seed_protocol',HERE/'protocol.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

def raw_scan():
    scanner=p.load_file('_ri07_history_scanner',p.REPO/'research/sta-velocity-control/scripts/check_v04_protocol02.py')
    scanner.CONFIG=Path('/__RI07_no_directory_exemption__')
    return scanner.seed_audit(sorted({j['seed'] for j in p.formal()['jobs']}))

def audit():
    result=raw_scan()
    allowed=p.read(HERE/'seed_reservations.json')
    for name,sha in allowed.items():
        if p.fingerprint(name)!=sha:raise ValueError('Changed exact seed registration '+name)
    # Execution metadata is a new explicit registration, pinned by source freeze.
    allowed[str(HERE/'execution.json')]=p.fingerprint(HERE/'execution.json')
    # The new immutable freeze repeats the exact planned manifest, not flights.
    # Check every frozen source/parameter first; no directory-wide exemption.
    frozen_path=HERE/'gates/FORMAL/frozen.json'
    p.check()
    allowed[str(frozen_path)]=p.fingerprint(frozen_path)
    result['registrations']=[m for m in result['matches'] if m['path'] in allowed]
    result['matches']=[m for m in result['matches'] if m['path'] not in allowed]
    result['accepted']=not result['matches'] and not result['invalid_json']
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--raw',action='store_true')
    args=parser.parse_args()
    result=raw_scan() if args.raw else audit()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(files=result['files_parsed'],invalid=result['invalid_json'],
        matched_files=sorted({m['path'] for m in result['matches']}),accepted=result['accepted']),indent=2))
