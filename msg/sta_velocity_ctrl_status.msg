# V03: exact final controller invocation per local-position input, no interpolation.
# mode1/axes1..7 selects local NED ESTA axes (SITL only, see z_phase).
# mode2 unavailable. Unselected velocity axes and all rate axes remain PID.
# nu/a_sta are NaN on PID axes, NOT estimated STA states.
# a_proxy is thrust * g / hover_thrust + gravity: model proxy, not measured acceleration.
# constraint_bits: 1 tilt, 2 minimum thrust, 4 maximum Z, 8 XY remainder.
# reset_bits: 1 vxy,2 vz,4 xy,8 z,16 heading,32 ground suppression.
# timing: 0 valid,1 first,2 repeated/reversed,3 out of 2..40ms domain.
# timing faults here are observational; PID retains legacy clamped input timestamp dt.
uint64 timestamp
uint64 timestamp_sample
uint64 input_timestamp
uint64 setpoint_timestamp
uint64 output_timestamp
uint64 attitude_timestamp
uint64 inner_timestamp
uint64 inner_check_timestamp
uint32 publish_seq
uint32 update_seq
uint32 inner_seq
uint32 config_generation
int32 requested_mode
int32 requested_axes
int32 effective_mode
int32 effective_axes
float32 raw_dt
float32 input_dt
float32 used_dt
float32 excitation
float32 excitation_y
float32 excitation_z # E01-XYZ TEST4 additional Down velocity; TEST2 uses excitation
float32 excitation_time
float32 hover_thrust
float32 tilt_limit
float32 thrust_min
float32 thrust_max
float32[3] p_sp
float32[3] v_ff
float32[3] v_sp
float32[3] v
float32[3] v_dot
float32[3] a_ff
float32[3] s
float32[3] nu_before
float32[3] nu_ideal
float32[3] nu_applied
float32[3] a_sta
float32[3] a_req
float32[3] a_proxy
float32[3] thrust
float32[4] q_sp
uint32 controller_time_us
uint32 module_time_us
uint8 clock # 0=HRT (simulation time in lockstep), not board CPU cost
uint8 pid_calls
uint8 pid_axes
uint8 active_axes
uint8 committed_axes
uint16 sta_flags
uint16 sta_fault
bool config_pending
uint8 reset_bits
uint8 constraint_bits
uint8 timing
uint8 takeoff_state
uint8 reject
int8 inner_mode # -1 means unavailable
uint8 inner_axes
uint8 inner_divisor
uint8 inner_reads
bool inner_valid
bool updated
bool valid
bool pending
bool armed
bool enabled
bool landed
bool contact
bool failsafe
bool fault # PID observer unchanged; X ESTA invalid transactions latch until disarm
# First invocation, preserved even when the final retry is valid.
# first_fail: 1 XY pairing,2 position estimate,4 velocity/derivative,8 acceleration,16 thrust,32 STA latch
# first_input: bits0..2 p_sp,3..5 v_ff,6..8 a_ff,9..11 v,12..14 v_dot finite
uint16 first_fail
uint16 first_input
uint8 retry_result # 0 not attempted,1 valid,2 invalid
uint8 excitation_fault # latched: 1 sensor clock,2 gate lost after start,4 controller failure
uint8 z_phase # 0 not Z,1 ground/ramp PID,2 PID handover,3 Z ESTA,4 Z acceleration-only; active_axes authoritative
float32 z_hte_shift # Z nu rebase due to HTE since previous invocation, m/s^2
uint8 ORB_QUEUE_LENGTH = 8
