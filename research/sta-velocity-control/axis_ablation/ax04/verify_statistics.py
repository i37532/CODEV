"""Full frozen resampling counts on SYNTHETIC inputs and real empty manifest."""
import json
from design import build, empty_outcomes, BOOTSTRAPS, SIGN_DRAWS
from paired_stats import summarize
from common import CONFIG
from package import outcome_rows

rows=empty_outcomes(build())
for row in rows:
    row.update(status='accepted',rmse_m_s=[.01 if row['candidate']=='PID' else .008]*3)
    row.pop('reason')
s=summarize(rows)
assert len(s['primary_comparisons'])==14
assert all(abs(r['mean_difference_m_s']+.002)<1e-14 and r['n']==20 for r in s['primary_comparisons'].values())
empty=summarize(outcome_rows(json.loads((CONFIG/'outcomes_unattempted.json').read_text())))
assert empty['attempted']==empty['accepted']==0
print(json.dumps(dict(success=True,synthetic_comparisons=14,bootstrap_repetitions=BOOTSTRAPS,
    signflip_repetitions=SIGN_DRAWS,formal_attempted=0,formal_accepted=0,
    note='Synthetic statistics are not formal flight outcomes')))
