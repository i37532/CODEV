"""Create/check only the new formal transport freeze; old protocol immutable."""
import argparse
import json
import protocol as p

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    value=p.capture() if args.write else p.check()
    if args.write:
        path=p.HERE/'gates/FORMAL/frozen.json';path.parent.mkdir(parents=True,exist_ok=True)
        if p.git('ls-files','--',str(path.relative_to(p.REPO))):raise ValueError('Do not replace committed freeze')
        with path.open('w') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(dict(assets=len(value['assets']),external=len(value['external_assets']),jobs=len(value['jobs']),flights=0)))
