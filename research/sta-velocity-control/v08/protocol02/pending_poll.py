"""Do not return to the slow task loop with unresolved raw landing evidence.

The unchanged LandingMonitor enforces BOTH original 500ms deadlines on every
poll, including time spent decoding/checking. Never reset its pending_since.
Every poll reruns the full inherited safety, history and raw-evidence checks.
No simulator/controller command, no flight retry, and no timeout enlargement.
"""


def drain(landing, poll, record):
    for index in range(8):
        before=landing.clock()
        item=dict(poll=index+1,host_start=before,pending_since=landing.pending_since)
        try:
            poll(index)
            item.update(host_end=landing.clock(),now_us=landing.last_now,
                        evidence=landing.last_evidence,pending_since_after=landing.pending_since)
            record(item)
        except Exception as exc:
            item.update(host_end=landing.clock(),now_us=landing.last_now,error=repr(exc))
            record(item)
            raise
        if not landing.last_evidence or not landing.last_evidence['pending']:
            return
    landing.failed=True
    raise ValueError('Bounded landing poll count exhausted')
