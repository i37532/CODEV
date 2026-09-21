# V00 接口审计与参考冻结（未通过飞行准入）

日期：2026-09-19。源码基线 `d00417ed1ccb779d6f7d3573328657f6ae9629a5`，
分支 `research/sta-velocity-control`。这不是 `main-v2_gps` 的旧基线。
全部源码位置以下均相对仓库根；此阶段不修改生产控制律。

## 1. 位置、速度、加速度接口

源文件：`src/modules/mc_pos_control/PositionControl/PositionControl.cpp/.hpp`。

```text
trajectory_setpoint（输入位置/速度/加速度前馈，NED）
  → setInputSetpoint / setState
  → _positionControl：位置 P + 速度前馈 → 最终速度目标 → 限速
  → _velocityControl：速度 PID + 加速度前馈 → 加速度需求
  → _accelerationControl：倾角约束、悬停推力比例、推力投影
  → 垂直优先推力限幅 + 水平剩余推力限制 + PID anti-windup
  → getLocalPositionSetpoint / getAttitudeSetpoint
  → 原姿态控制 → 原角速度 PID → quad_w mixer → 电机
```

- 坐标是本地 NED：X 北、Y 东、Z 向下；位置 m、速度 m/s、加速度 m/s²。
  yaw 改变不使这些速度轴旋转成机体系。姿态/电机端另有机体坐标转换。
- `setState()` 取位置、速度、yaw 和速度导数。这里 D 输入并不是直接使用
  `vehicle_local_position.ax/ay/az`：模块用 BlockDerivative 对有效速度求导和滤波。
- `_positionControl()`：`v_sp = Kpos*(p_sp-p) + v_ff`，经 `addIfNotNan` 合成；
  XY 矢量限幅优先位置纠偏分量，Z 限制在 `[-speed_up, speed_down]`。
  无位置设定但有速度设定时，位置分量不参与，而不是用零位置代替 NaN。
- `_velocityControl()`：`a_req = Kp*(v_sp-v) + I - Kd*v_dot + a_ff`。
  D 对测量求导；本步使用旧 I 输出，限幅/anti-windup 后更新一次 I。
  NaN 是可选设定分量未启用，不能统一视为无效传感器。
- `update()` 检查位置、速度、加速度各自的 X/Y 有限性成对，但即使配对检查失败，
  仍先调用位置/速度计算，再返回 `valid && _updateSuccessful()`。
  后者校验被控制状态以及全部最终加速度/推力有限性。不能认为失败调用没有改变积分。
- `_accelerationControl()`：body_z = normalize(-a_x,-a_y,g0)，限制倾角；
  collective = `(a_z*hover_thrust/g0-hover_thrust)/body_z.z`，限制最小推力，
  然后 `thrust = body_z*collective`。零加速度需求不等于零推力。
- 垂直推力先限制；XY 剩余量是 `sqrt(max_thrust²-thrust_z²)`，不是逐轴独立 clip。
  Z 积分在加深最小/最大推力饱和时冻结，最终限到 ±g0。
  XY tracking anti-windup 用 `2/Kp_x` 和 `thrust_xy*g0/hover_thrust` 代理；
  此代理不是实测加速度，也不能直接照搬给速度 ESTA 的 nu。
- 输出 `vehicle_local_position_setpoint.vx/vy/vz` 是合成和限速后的目标，不等于输入 FF。
  其中 acceleration 是限推力前加速度需求，thrust 是约束后的向量，两者不能混称实际输出加速度。
- `ControlMath::thrustToAttitude()` 以负推力方向生成 body_z，保留 yaw 方向，输出 q_d，
  body Z 推力为 `-norm(thrust)`；Euler 字段仅为日志，不参与该转换控制计算。

## 2. 模块 Run、HTE、参数与生命周期

源：`src/modules/mc_pos_control/MulticopterPositionControl.cpp/.hpp`、
`mc_pos_control_params.c`、`Takeoff/Takeoff.cpp/.hpp`。

- 调度由 vehicle_local_position 回调触发，另有 100ms 备用调度；只有取得新消息才推进此路径。
- `Run()` 每帧先处理参数/模式/land detector，HTE 新样本有效且 MPC_USE_HTE 开启时，
  `updateHoverThrust(new)` 使 Z 积分增加 `(new-old)*g0/new`，再更新悬停推力。
  V00 保留此策略；不能为新算法对照偷偷关闭 HTE。
- `SYS_VEHICLE_RESP>=0` 联动加速度、jerk、yaw、倾角等；
  `MPC_XY_VEL_ALL>=0` 联动水平速度，`MPC_Z_VEL_ALL>=0` 联动上下速度和起降速度。
  另有巡航/手动速度不超过最大速度、hover 在 min/max thrust 内的校验。
  PID 参数更新继续原实时语义，不是将全部参数套上 armed 暂存规则。
- 有效性：位置/速度需相应 valid 标志及有限值；XY 无效时成对置 NaN，速度导数滤波器 reset。
  Z 单独判定。`resetIntegral()` 在未起飞或飞行状态却地面接触时调用。
  退出位置控制只更新 Takeoff 状态，不可声称每次 disarm 都在任意路径立即清积分。
- 旧目标 timestamp 早于位置消息时，按 EKF position/velocity/heading reset counter
  将目标平移相同 delta，再保存 counter；未来 nu 策略不能无条件将每个 reset 都当误差突变。
- Z 纯速度任务（z_sp 非有限、vz_sp 有限非零）会将控制器实际速度设为
  `w*z_deriv+(1-w)*vz`，`w=min(abs(vz_sp)/MPC_LAND_SPEED,1)`，需估计有效。
  D 项仍由先前的 local_pos.vz 导数生成。只用原 vz 重算降落 PID 并不逐样本等价。
- 原机载任务/FlightModeManager 发布 trajectory_setpoint，mc_pos_control 发布姿态目标，
  mc_att_control 发布角速度目标；后续 V00 运行器只能发 commander 高层模式命令及中性 RC/GCS
  保活，不再并行发布 offboard/attitude/rate 目标。该发布者链尚未用本阶段运行日志确认。

## 3. Takeoff 的重要勘误与失败

`generateInitialRampValue()` 第45行虽计算 `-g0/max(Kp_z,0.01)`，**第46行随后覆盖为0**。
因此当前有效初值恒0，不能照计划预读概括写成“当前 ramp 初值依赖 Z Kp”。
保留 plan/v1 原文字，本文件是可追溯勘误，不覆盖历史快照。

`git blame` / `git show` 确认覆盖行来自
`317ee4c9cca25c33bc4ef81fc48056fb1d82800d`（2021-11-08，Takeoff: optimise the takeoff action）。
该历史提交只加这一行；不能仅凭标题推断完整设计理由。

现有 `TakeoffTest.RegularTakeoffRamp` 设 Kp=g0/0.5、ramp=2s、目标1.5m/s、dt=.5s：

| 第几次 updateRamp | 旧测试期望 m/s | 当前实际 m/s |
|---|---:|---:|
| 1 | 0 | 0.375 |
| 2 | 0.5 | 0.75 |
| 3 | 1 | 1.125 |
| 4、5 | 1.5 | 1.5 |

这是1个用例、3个断言失败，不是3个独立测试失败。测试假定初值 -0.5，源码实际为0。
源码与测试契约不同已复现；这不单独证明无法飞行，也不能被旧起降成功抵消。

原 Takeoff 状态顺序：disarmed → spoolup → ready_for_takeoff → rampup → flight；
landed 可回 ready，disarm 回 disarmed，非位置控制路径可 skip 到 flight。
飞行前屏蔽 Z 加速度 FF；未起飞或飞行中地面接触时清设定，置加速度(0,0,100)并 reset 积分。
倾角限值有 slew，起飞阶段最小推力可从0起（PositionControl 内仍有极小正下界）。
这些原语义保持，不修改全局 land detector。

## 4. 失效与同帧二次 update

首次 `_control.update(dt)` 失败后，原模块调用 failsafe、重设约束和输入，再调用一次
`_control.update(dt)`，第二次返回值未用于发布门禁，然后仍发布输出。
首次失败也可能改变积分；未来新算法 evaluate/commit 必须显式防止同一采样提交两次。

failsafe 有迟滞。迟滞达成后 XY 速度有效则设 vx/vy=0；XY 无效则设水平加速度0并要求降落。
Z 速度有效时设零速度或保留下降目标；无效时改为加速度 Z=.3。
迟滞尚未达成时函数不重置调用者的零初始化临时 setpoint，不能笼统称为“始终沿用上帧目标”。
V00 只记录，不改上游失效策略，不以零推力/切 PID 代替安全策略。

## 5. 时间与日志证据边界

- 原控制 dt = clamp((local_pos.timestamp-last)*1e-6, .002, .04)。
  时间戳是无符号类型，异常倒退不是带符号检测；V00 不静默修正旧语义。
- `EKF2::PublishLocalPosition()` 将 timestamp_sample 设为传入 IMU 样本时间，
  timestamp 通常取 hrt_absolute_time（replay 分支例外）。
  多实例 EKF2Selector 保留 sample、丢弃陈旧/倒退 sample，并以当前 hrt 重盖发布 timestamp。
- 输出 local_position_setpoint / attitude_setpoint 的 timestamp 取发布时 hrt，没有输入 sample 标识；
  下游“最近一条”配对只是带时差的匹配，不可冒充精确逐样本被消费状态。
- 当前没有启动 V00 模拟器，**实际速度环频率、dt 分布、时差分布均未测得**。
  world 4ms、角速度250Hz不等于速度环250Hz。
- 默认日志 local_position/local_position_setpoint 间隔100ms、trajectory_setpoint 200ms，
  高频profile额外覆盖 rate/attitude/actuator，但不会自动将前述速度话题改为全速。
  perf 计数差只能估计模块调用率，不能提供每步dt或证明所有调用均完成控制更新。
- 旧 I05/M09 日志经验：dropout=0≠话题无损；不能要求每条诊断都恰好匹配单队列 actuator。
  后续需单列状态完整性、实际匹配分母/比例/最长缺口，不插值制造合格样本。

## 6. 冻结资源、环境、参数和随机源

外部根 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260919/V00`。
`verification03/references/` 保存25份源码/模型/启动器参考，包含 PositionControl、ControlMath、
Takeoff 全部实现/头文件/原测试；`audit03/snapshot/` 补充参数、EKF selector、原内环及插件源码。
来源HEAD和每文件SHA见 verification03/evidence.json、audit03/manifest.json；
仓库 v00/evidence 内存小型副本和外部全量SHA索引。

- recursive submodule 状态均与记录提交一致，内部工作区均干净；Gazebo 子模块
  `822050a7ab6fd87972e59f16312f451bce217a56`。
- 预定启动 `./sitl/run.sh --headless --backend gazebo --model iris`；
  原 Tools/sitl_run.sh 仍有按进程名清理逻辑，运行前必须拒绝已有模拟器，避免影响他人进程。
- 静态解析资产是 `Tools/sitl_gazebo/models/iris/iris.sdf`，包含 gps/gps.sdf；
  world=`sitl/worlds/empty_grey.world`，ODE、4ms、250 update/s、请求实时因子1、原噪声。
  尚无本阶段运行控制台，故不能把这些静态选择写成“运行时已确认模型”。
- Iris 预期 airframe10016 / quad_w；DP1000 是4065 / quad_x，其配置只存审计指纹，未运行。
- Ubuntu22.04.5、g++11.4.0、Python3.10.12、Gazebo Classic11.10.2；其余完整版本见日志。
  记录26个现存 libgazebo*.so 指纹，不称这26个都被载入或本阶段重编译。
- 构建固件SHA256 `db49db4d7ff1f92a3738c8259de845ac77971a1d0feee552e2a050cff35c0c20`。
- 参数声明默认 MODE0/AXES0/DIV1/MC_RATT_TEST0/MC_STA_TKO_MGT0；
  默认 MPC_XY_P=.95、MPC_Z_P=1，XY速度PID=(1.8,.4,.2)，Z=(4,2,0)，HTE=1。
  SYS_VEHICLE_RESP=-.4、MPC_XY_VEL_ALL=-10、MPC_Z_VEL_ALL=-3。
  **这些不是本阶段实测生效值**，airframe和持久化配置还可能覆盖。
- 只读备份 parameters_10016 全部1129字节；有效首份BSON长度575，后有554字节残留。
  PX4解码到EOO停止，离线解码也只读有效首份，全部原字节保留。29个持久化条目含
  SYS_AUTOSTART10016、IMU_INTEG_RATE250；未存的控制参数不能凭文件缺项判定实际运行值。
  此次未设置/保存任何飞行参数，无需恢复；全参数运行前后备份/恢复仍是未完成验收项。
- IMU/GPS/mag/baro 源码使用默认构造 std::default_random_engine，未发现显式 seed 覆盖。
  不复用 M10 特制播种插件、不沿用3101等正式种子。未来3轮原模型重复应记 seed=null，
  不能伪称3个独立随机种子或逐位可复现；Gazebo/调度/EKF选择还有其他不确定性。

## 7. 未执行的飞行协议与恢复条件

单测门禁失败，**未冻结可执行飞行协议、未完成 V00 飞行运行器，也未开始任何基线尝试**。
不能直接拿 run_m00.py 运行来补交：该旧脚本没有本次速度环指标/参数冻结的完整门禁。

下一次继续V00前需先决定 Takeoff 契约：保留当前CODEV零初值并补充/修订相应测试，
或有明确依据地恢复负初值（会改变飞行行为）。两者都不是本报告已批准的修复。
建议先保留现行为、审查历史意图并补齐测试，不直接删生产代码的一行来迎合旧断言。

修复通过后须另行冻结准确协议及干净源码提交，再执行最多3轮，无自动补飞：
每轮重启、预热、起飞约2.5m、60s悬停、降落上锁；唯一目标来源按第2节。
倾角15°、悬停高度误差1m、水平速度1m/s、XY偏离2m、垂直速度.6m/s只是计划初值，
起降独立窗口、时限、日志规则、参数全集及安全中止策略必须在新协议中具体实现并测试。
当前没有伪造已冻结参数或飞行成功数据；V01禁止准入。
