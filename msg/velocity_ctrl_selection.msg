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
# R02 configuration evidence. Join sta_velocity_ctrl_status by exact
# (publish_seq, timestamp_sample), never by approximate publication time.
# variant: 0 PID, 1 original ESTA, 3 regularized explicit STA,
# 4 compensated regularized implicit STA, 255 unknown. MODE4 metadata is NOT
# production admission: RI02 keeps it unavailable outside offline test friends.
uint8 variant_req
uint8 variant_eff
# Requested raw parameter values (m/s), including rejected invalid values.
float32[3] eps_req
# Actual effective regularized width on selected axes; otherwise NaN (unused).
float32[3] eps_eff
# Last accepted STA configuration generation, not a control-update counter.
uint32 sta_gen
bool sta_pending
# Invalid requested STA configuration, independent of mode rejection/fault.
# May be true for unused/unconfigured STA gains while effective mode is PID.
bool sta_reject
# RI02 compensated-implicit diagnostics. Join the unchanged sta_velocity status
# by (publish_seq,timestamp_sample); that topic supplies s,nu_before,FF,limits.
# Version identifies equations/field semantics, not flight qualification.
uint8 ri_version
# valid means a complete ideal candidate AND a successful atomic transaction
# in the final invocation (not proof that the protected pair is implicit).
# Rejected transactions, ground, seed-only, disabled, other mode => false/NaN for
# nu_candidate/a_ideal. Seed-only p is identified by ri_seed_h>0, not ri_valid.
# Applied state/output may still describe the handover.
bool ri_valid
float32[3] ri_p # compensated nominal prediction, m/s, NOT measured next error
float32[3] ri_nu_candidate # ideal next nu used in current ideal a, m/s^2
float32[3] ri_nu_applied # protected committed state, not generally implicit
float32[3] ri_a_ideal # ideal correction before one acceleration FF, m/s^2
float32[3] ri_a_applied # protected correction before FF, m/s^2
float32[3] ri_acc_published # actual published acceleration setpoint, not measured a
float32[3] ri_thrust_published # actual published normalized thrust setpoint
float32 ri_h # implicit candidate sample interval, not legacy PID publication dt
float32 ri_seed_h # only seed inversion interval; not a normal integral update
uint64 ri_cache_sample # sample identity of the applied correction cache
bool ri_cache_valid
uint8 ri_strict_axes # unaltered ideal pair only; never claim protected implicit solve
uint8 ri_commit_axes # actual committed axes in the final invocation
uint8 ORB_QUEUE_LENGTH = 8
