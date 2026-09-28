# V01 selection evidence, published once per consumed local position message.
# pid_calls counts actual PositionControl update calls (including failsafe retry).
# It is not a success counter or a complete velocity-controller diagnostic.
uint64 timestamp
uint64 timestamp_sample
uint64 input_timestamp
uint32 publish_seq
int32 requested_mode
int32 requested_axes
int32 effective_mode
int32 effective_axes
uint8 REJECT_NONE = 0
uint8 REJECT_MODE_RANGE = 1
uint8 REJECT_MODE_UNIMPLEMENTED = 2
uint8 REJECT_AXES_UNAVAILABLE = 4
uint8 reject
uint8 pid_calls
bool pending
bool armed
bool enabled
# V07: independent correction cadence; legacy sta_velocity update_seq counts calls.
# h is legacy PID dt for DIV1, true sensor delta at DIV>1 updates, NaN on holds.
int32 div_req
uint8 div_eff
bool div_pending
bool div_reject
uint32 control_seq
float32 h
bool control_updated
bool control_held
uint8 control_fault
uint8 interval_pos # conservative NED positive constraint directions since update
uint8 interval_neg
float32[3] correction # pre-acceleration-FF velocity feedback, not thrust or measured acceleration
float32[3] integral # actual PID state after invocation; HTE shifts can occur on holds
uint64 path_ns # velocity dispatch, mapping, protection and diagnostic path, incl held work
uint64 module_ns # Run entry to selection publication, excludes later diagnostics/scheduling
uint8 clock # 1 Linux host CLOCK_MONOTONIC; 0 unavailable, NOT lockstep HRT or board CPU
uint8 ORB_QUEUE_LENGTH = 8
