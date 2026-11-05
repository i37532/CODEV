"""Bind only independently checked existing formal reservations, no blanket exemption."""
import json
import protocol as p

if __name__=='__main__':
    initial=p.DATA_ROOT/'seed_scan_initial.json'
    scan=p.read(initial);package=p.read(p.PACKAGE)
    allowed={str(p.PACKAGE):p.PACKAGE_SHA}
    old=p.read(p.HERE.parent/'ri06/seed_reservations.json')
    for name in ('execution.json','seed_audit_initial.json'):
        path=p.HERE.parent/'ri06'/name
        if p.fingerprint(path)!=old[str(path)]:raise ValueError('Original registry differs')
        allowed[str(path)]=old[str(path)]
    for gate in ('TH','TV','VH','VV'):
        root=p.PRIOR.DATA_ROOT/gate
        summary=root/'replay01/summary.json'
        if p.fingerprint(summary)!=package['input_sha256'][str(summary)]:raise ValueError('Old replay summary differs')
        f=root/'batch01/seed_audit_before_launch.json'
        expected=p.read(summary)['original_input_sha256_after']['files'][str(f)]
        if p.fingerprint(f)!=expected:raise ValueError('Unbound historical scan')
        allowed[str(f)]=expected
    if scan['invalid_json'] or {m['path'] for m in scan['matches']}!=set(allowed):
        raise ValueError('Unexpected seed occurrence or malformed JSON')
    for match in scan['matches']:
        field=match['field'];name=match['path']
        valid=(name==str(p.PACKAGE) and field.startswith('formal.jobs.')) or (
            name.endswith('/ri06/execution.json') and field.startswith('formal_jobs.')) or (
            name.endswith('/seed_audit_initial.json') and field=='seeds') or (
            name.endswith('/seed_audit_before_launch.json') and (field=='seeds' or field.startswith('registrations.')))
        if not valid:raise ValueError('Actual seed consumption outside registration field')
    allowed[str(initial)]=p.fingerprint(initial)
    with (p.HERE/'seed_reservations.json').open('x') as f:json.dump(allowed,f,indent=2);f.write('\n')
    print('Exact 8 prior reservation/audit files bound; 0 new flights')
