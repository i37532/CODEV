"""Read-only revision06 scope and provenance summary; never grants qualification."""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit():
    p = load('_revision06_readonly_protocol', HERE/'protocol.py')
    f = load('_revision06_readonly_freeze', HERE/'freeze.py')
    p.validate_manifest()
    changes = f.check_scope()
    history = p.retained_history()
    retained = p.retained_abc()
    return dict(revision=p.REVISION, entry_head=f.ENTRY,
                actual_head=p.git('rev-parse', 'HEAD'),
                stage='offline_scope_audit_not_qualification',
                historical_attempts=history['attempts'],
                historical_takeoffs=history['takeoffs'],
                historical_accepted=history['accepted'],
                historical_failed=history['failed'],
                retained_design_runs=retained['accepted_design_runs'],
                new_planned=len(p.design()['jobs']), total_budget=p.TOTAL_MAXIMUM_ATTEMPTS,
                production_changes_from_r02=changes,
                production_changes_from_revision_entry=[],
                actual_masks=f.gate_masks('D'),
                retained_abc=retained, new_flights=0,
                execution_authority_granted=False,
                limitation='Compact hashes only here; qualification separately performs all three original complete raw replays')


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2))
