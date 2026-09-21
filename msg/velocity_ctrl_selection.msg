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
