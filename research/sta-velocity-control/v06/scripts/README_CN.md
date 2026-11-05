# V06 速度研究脚本

软着陆专项与V06完整任务均已通过：专项6轮/3对；独立protocol03三任务18轮/9对及完整回放通过，无IMU截幅或降落EKF切换，参数完整恢复。ESTA三任务平均速度误差和请求TV高于PID，不能称性能全面胜出。旧失败不改判、不拼接数据。详见 ../../reports/V06_SOFT_LANDING.md 和 ../../reports/V06.md。当前18轮预算已耗尽，fly默认仍可查看清单，但拒绝再次执行；新实验需另冻源码/新种子/有限预算。
仅 Gazebo Classic Iris SITL。这里 ESTA 是 **XYZ速度环**，角速度仍是 PID；不是旧 sim_scripts 的角速度 ESTA。

## 打开 Gazebo，落地切换
在仓库根目录运行（不加 --execute 只显示计划）：
```bash
./research/sta-velocity-control/v06/scripts/start.sh --execute
# 另一个终端：必须已经落地、上锁
./research/sta-velocity-control/v06/scripts/switch.sh esta --execute
./research/sta-velocity-control/v06/scripts/switch.sh pid --execute
```
start 默认 PID，不起飞；使用项目 sitl/run.sh 原启动器。switch 加载已验收 E01-XYZ 参数并检查实际速度模式和角速度 PID，不连接实机/其他仓库，不修改旧 sim_scripts。手动会话 TEST=0，不自动施加任务。退出时在 PX4 控制台执行 shutdown，启动脚本恢复原始完整 EEPROM；恢复前不强制关闭终端。备份在外部 V06/manual。

## 自动起飞、任务、降落及对比
本目录 start 和 protocol03 fly 使用合格弹性接触派生 Iris：kp=2500、kd=50、max_vel=.2、max_contacts=4。只改变机体与地面的接触参数，不改变控制律、增益、惯量、传感器信号或默认仓库模型。手动 start 保留原IMU插件，正式 fly 使用冻结的配对噪声插件；二者不能当成同一重复实验。旧 sim_scripts 默认行为不变。该接触模型没有实机起落架标定，不代表实机软着陆通过。

先退出手动 PX4/Gazebo/QGC。fly 自行重启后端、预热、起飞至约2.5m、进入任务、降落上锁并完整恢复参数；不需要先 start。
```bash
./research/sta-velocity-control/v06/scripts/fly.sh all
# 正式执行需绑定冻结源码和预算；授权文件记录本次已有持续授权
./research/sta-velocity-control/v06/scripts/fly.sh all --execute --source-head <协议源码完整SHA> --authorization <外部授权JSON绝对路径>
```
也可把 all 换成 hover、figure8、heading，按此顺序分任务执行；每个任务自动PID/XYZ ESTA各3轮。只有上一任务完整通过且恢复参数才允许继续；失败不续跑。总计18轮，消耗后拒绝重复；重新实验需新版本清单/种子/有限预算，不能把旧正式结果覆盖或当作新重复。源码HEAD发生变化也要重新冻结，不 checkout 回旧提交强行重跑。switch 用于手动查看会话，正式 fly 由清单自动切换，不受手动选择污染。

- hover：90秒观察，其中64秒主指标窗口。
- figure8：固定yaw，小幅低速8字，64秒、两圈、平滑起止。
- heading：相同8字，同时平滑改变机头方向；不是强机动。
- 目标：Navigator/FlightTask 基础目标 + 默认关闭的 SITL 每帧轨迹适配；原位置P仍工作。速度/加速度前馈各加一次。不同算法的最终 v_sp 含实际位置误差纠偏，不保证逐样本相同。
- 默认自动运行无界面。不要另开第二套Gazebo/PX4抢占端口；本轮验收针对无界面冻结启动命令。手动 start 可看模型，但不等同正式任务完成。

## 日志与 PlotJuggler
每轮外部目录保存 result.json、xyz_metrics.json、startup/runtime参数、commands、samples、ULog和SHA-256；ledger.json包含逐轮与配对结论。原始数据与失败不进Git，大型路径及指纹进结果包。
PlotJuggler 使用其 ULog 插件打开 result.json 指向的 .ulg；不要把 CSV 插值结果代替验收证据。

优先看 sta_velocity_ctrl_status：
- v[0..2] 对 v_sp[0..2]：实际与控制器真正消费的速度目标，误差s单位m/s。
- p_sp 与 vehicle_local_position.x/y/z：移动位置目标与实际位置，NED的Z向下，高度=-z。
- v_ff、a_ff：目标前馈；a_req 为加速度请求，a_proxy仅推力映射代理，均不是加速度真值。
- nu_before/nu_ideal/nu_applied、a_sta、constraint_bits：积分状态与保护；thrust/q_sp 为输出。
- requested/effective_mode/axes、active_axes/pid_axes、z_phase、fault、timing、reset_bits：真实配置与生命周期。
- excitation_time：任务时钟；老excitation/excitation_y/excitation_z应全0。MPC_VCT_TEST=5/6/7区分三任务。
- timestamp_sample/input_timestamp/raw_dt/used_dt/publish_seq/update_seq：采样与发布时序。
vehicle_attitude_setpoint 的 yaw_body/yaw_sp_move_rate 对实际姿态yaw；sta_rate_ctrl_status 必须 MODE0/AXES0/DIV1。
raw trajectory_setpoint 是未加研究轨迹的基础目标，不能把它单独当成已消费的移动目标。

降落专项另外看所有实例的 sensor_accel.clip_counter、vehicle_imu.delta_velocity_clipping、estimator_status.filter_fault_flags 和 estimator_selector_status.primary_instance；必须有覆盖 landed_disarmed 的实际日志边界，不能靠外推补齐。并检查落地后 postland_tail.json 与最终日志检查一致。

这是三种名义任务的开发回归，不是正式留出实验，也不承诺ESTA每轴胜出。E01显示Z误差和输出变化负担可能比PID大，V06如实报告。
