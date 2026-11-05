# Event-only diagnostic; no invented timestamps or silent switch filtering.
uint64 timestamp
uint64 timestamp_sample # candidate sample
uint64 previous_sample # last actual output sample BEFORE this decision
uint32 device_id
uint32 event_seq
uint32 duplicate_count
uint32 backward_count
uint32 zero_count
uint32 switch_count
uint8 reason # 0 accepted,1 duplicate,2 backward,3 zero,4 cadence not due
bool published
bool switched
uint8 ORB_QUEUE_LENGTH = 8
