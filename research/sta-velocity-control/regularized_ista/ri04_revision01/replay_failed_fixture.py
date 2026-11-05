"""Re-audit original failed boundary into this revision's fresh evidence root.

Historical extraction/math are untouched; no old output or verdict is rewritten.
"""
import argparse
import hashlib
import json
from pathlib import Path
import protocol as p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if p.DATA_ROOT not in output.parents or output.exists():
        raise ValueError('Fresh current revision evidence directory required')
    old = p.load_file('_ri04_revision01_recorded_boundary', p.HERE.parent/'ri04_hte_fix/fixture.py')
    result = old.extract()
    header = old.render_header(result['values'])
    old.require((old.HERE/'recorded_hte_fixture.hpp').read_text() == header,
                'Committed historical fixture differs from raw log')
    result['header_sha256'] = hashlib.sha256(header.encode()).hexdigest()
    output.mkdir(parents=True)
    (output/'recorded_hte_fixture.hpp').write_text(header)
    (output/'summary.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(success=result['success'], candidates=len(result['candidates']),
        original_failure_preserved=result['original_failure_preserved'], new_flights=0)))


if __name__ == '__main__':
    main()
