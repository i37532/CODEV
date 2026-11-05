# I03 default-off takeoff nu-manager diagnostics. No simulator truth is accepted.
uint64 timestamp
uint64 timestamp_sample
uint32 publish_seq
uint32 config_seq
int32 requested_enable # raw MC_STA_TKO_MGT request
uint8 state # 0 disabled,1 idle,2 waiting,3 confirm takeoff,4 released,5 confirm landing,6 landed hold,7 fault
uint8 event # 0 none,1 arm,2 takeoff candidate,3 cancelled,4 released,5 landing candidate,6 cancelled,7 landed,8 estimator jump,9 timeout,10 disarm
bool effective_enable
bool config_pending
bool freeze
bool reset
bool abort
bool estimate_valid
bool armed
bool landed
bool maybe_landed
float32 local_z # onboard local-position NED, m
float32 local_vz # onboard local vertical velocity NED, m/s
uint8 ORB_QUEUE_LENGTH = 32
