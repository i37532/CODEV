# Research diagnostics. M08 permits PID or Iris SITL ESTA/ISTA AXES=1/3/7. NaN = not applicable.
uint64 timestamp
uint64 timestamp_sample
uint64 motor_timestamp
uint32 publish_seq # increments for every published diagnostic frame
uint32 update_seq # increments ONLY when the actual rate controller updates
uint32 motor_update_seq # publisher-side mixer sequence, not a polling count
uint32 config_seq # accepted experimental configuration revision, NOT effective mode
int32 requested_mode
int32 requested_axes
uint16 motor_saturation
uint16 reset_reason # StaProtection reset bitmask; applies ONLY to experiment state
uint8 effective_mode
uint8 effective_axes
uint8 request_status
uint8 timing_status # 0 good,1 first,2 duplicate,3 backward,4 gap,5 short
uint8 fault # first latched experiment fault; 6 measurement,7 config,8 numeric
uint8[3] limits # 1 mixer freeze,2 feedback invalid,4 nu limit,8 output limit
bool pending
bool config_pending
bool config_valid
bool motor_valid
bool measurement_valid
bool output_valid # true only when an emitted PID/mixed output is finite and valid
bool abort_requested
bool updated
bool held # retained previous command only; false for disabled/termination
bool armed
bool landed
bool maybe_landed
bool rate_enabled
bool pid_reset
bool pid_frozen
bool experiment_updated
bool experiment_frozen
bool termination
float32 raw_dt # signed sensor time delta before checks/clamp; NaN on first
float32 dt # actual legacy PID dt, unchanged by experiment guard
float32 battery_scale # applied after experimental output clipping; PID scales c_raw directly
float32[3] rate
float32[3] rate_sp
float32[3] angular_accel
float32[3] s # rate-rate_sp, rad/s
float32[3] nu # experiment state rad/s^2, not PID integral
float32[3] nu_before # selected algorithm state used to compute ideal a_raw
float32[3] lambda1
float32[3] lambda2
float32[3] g
float32 research_roll_addition # single mc_att_control publisher test input
float32 research_pitch_addition # single mc_att_control publisher M05 pitch test input
float32 research_yaw_addition # M06 world-z rate excitation, transformed to body before addition
bool pid_updated # actual PID update this cycle, false for all-axis ESTA/ISTA
uint32 pid_update_seq # counts real PID update calls, not experiment updates
float32 research_elapsed # seconds since pulse trigger, -1 when inactive
float32[3] a_raw # ideal selected algorithm virtual angular acceleration; NaN on PID axes
float32[3] c_raw # PID raw output, or ideal armed experiment a_raw/g BEFORE nu protection/clipping/battery scaling
float32[3] c_applied # actual emitted normalized command; NOT physical motor torque
float32[3] pid_integral_before
float32[3] pid_integral_after
float32[3] pid_p
float32[3] pid_d
float32[3] pid_ff
float32[3] nu_candidate # unconstrained candidate nu_next BEFORE freeze/limits
float32[3] a_protected # after protected nu substitution (ISTA), before command clip and battery scale
float32[3] xi # ideal ISTA only; NaN otherwise
float32[3] virtual_state # NaN unless ISTA
uint8[3] ista_branch # 255 not applicable; never label ESTA as sliding
uint8 ORB_QUEUE_LENGTH = 32
int32 div_req
uint8 div_eff
bool div_ok
bool div_wait
uint16 sat_bits
bool sat_valid
uint32 sat_n
float32[3] c_held # unscaled cached torque
float32 thrust
uint64 kern_ns # selected algorithm + protection/mixing, zero on hold
uint64 mod_ns # Run entry through output preparation, excludes this diagnostic publish
uint8 clock # 1 Linux host monotonic ns, 0 unsupported/zero
