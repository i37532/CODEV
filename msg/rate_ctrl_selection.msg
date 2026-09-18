# Multicopter controller selection. Published at startup and on state changes.
uint64 timestamp
int32 requested_mode             # Unmodified MC_RTC_MODE value
int32 requested_axes             # Unmodified MC_STA_AXES value
uint8 effective_mode             # Applied mode: PID=0, ESTA=1, ISTA=2, Proper-ISTA=3
uint8 effective_axes             # Applied experimental-axis bit mask; PID uses 0
uint8 request_status
bool pending                     # Latest request awaits disarmed evaluation

uint8 MODE_PID = 0
uint8 MODE_ESTA = 1
uint8 MODE_ISTA = 2
uint8 MODE_PROPER_ISTA = 3
uint8 REQUEST_ACCEPTED = 0
uint8 REQUEST_UNSUPPORTED = 1
uint8 REQUEST_INVALID_MODE = 2
uint8 REQUEST_INVALID_AXES = 3
