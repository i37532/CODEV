"""Require 30s after the first complete owned-log warmup read, not boot time.

No safety exception is swallowed. Existing 180s host deadline, 500ms freshness
and complete attitude boundary/reset checks remain unchanged.
"""
import json
import math
from pathlib import Path

MINIMUM_US=30_000_000
RECEIPT='r03_warmup10.jsonl'


class Readiness:
    def __init__(self):
        self.first=None;self.previous=None;self.failed=False;self.ready=False

    def observe(self,timestamp,prepared):
        try:
            if self.failed or self.ready:raise ValueError('Warmup finished or failure latched')
            if (type(timestamp) not in (int,float) or not math.isfinite(timestamp)
                    or not 0<timestamp<2**53 or int(timestamp)!=timestamp):
                raise ValueError('Invalid warmup sample clock')
            if type(prepared) is not bool:raise ValueError('Invalid prepared flag')
            now=int(timestamp)
            if self.previous is not None and now<=self.previous:raise ValueError('Non-increasing warmup clock')
            self.previous=now
            if self.first is not None and not prepared:raise ValueError('Prepared owned log lost')
            if prepared and self.first is None:self.first=now
            elapsed=None if self.first is None else now-self.first
            self.ready=elapsed is not None and elapsed>=MINIMUM_US
            return dict(timestamp_us=now,first_prepared_sample_us=self.first,elapsed_us=elapsed,
                        minimum_us=MINIMUM_US,ready=self.ready,prepared=prepared,execution_authority_granted=False)
        except BaseException:
            self.failed=True
            raise


def warmup_ready(checks,state,output):
    if not hasattr(checks,'_warmup10'):checks._warmup10=Readiness()
    prepared=checks._prearm_state();reader=prepared.get('reader')
    usable=(not prepared['failed'] and prepared['warmup_reads']>=1
            and reader is not None and reader.last_timing.get('completed') is True)
    try:
        if prepared['failed']:raise ValueError('Existing prearm preparation failure latched')
        row=checks._warmup10.observe(state['position']['timestamp'],usable)
        row.update(warmup_reads=prepared['warmup_reads'],reader_path=str(reader.path) if reader else None)
    except BaseException as exc:
        checks._warmup10.failed=True
        row=dict(error=repr(exc),ready=False,execution_authority_granted=False)
        raise
    finally:
        with (Path(output)/RECEIPT).open('a') as f:f.write(json.dumps(row,allow_nan=False)+'\n')
    return row['ready']


def require_ready(checks):
    state=getattr(checks,'_warmup10',None)
    if state is None or not state.ready or state.failed:raise ValueError('No completed post-logger 30s warmup')
