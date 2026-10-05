"""One-time accurate separate mass gate registration, no simulator access."""
import json
from pathlib import Path
import common
p=common.CONFIG/'execution.json'
if p.exists():raise RuntimeError('Do not overwrite a registration')
old=json.loads((common.REPO/'research/sta-velocity-control/v08/protocol04/execution.json').read_text())
d={k:old[k] for k in ('force_library','force_library_sha256','force_build_evidence','ground_probe_evidence','selection_sha256')}
d.update(stage='V08-protocol05-revised-mass-gate',pilot_seeds=[40401,40402,40403],seed_reservations={},
         first_failure_stops=True,formal_flights_permitted=False,maximum_attempts=6,
         transport_probe='/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V08/transport_probe03/evidence.json',
         inertia_rule='Q6(1.10 I), six significant decimal digits; mass exactly x1.10; no tolerance relaxation',
         preceding_qualified_gates='protocol04 heading6/force6; separate mass revision, not an eighteen-run homogeneous batch')
p.write_text(json.dumps(d,indent=2)+'\n');d['jobs']=common.jobs();p.write_text(json.dumps(d,indent=2)+'\n')
print('Registered six new mass attempts; no flights')
