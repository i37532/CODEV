# V00 恢复批次01：原PID三轮基线（飞行前冻结）

2026-09-21。用户明确授权保留现有起飞逻辑，修订并补齐对应测试，然后继续三轮基线。
旧失败见8462f8139e的V00报告与原始证据，不删除、不改成通过。

## 修改与不变项

只改TakeoffTest：保留原全部状态断言，修正零初值斜坡的三个预期值，新增6个生命周期/时间/增益用例。
Takeoff.cpp、PositionControl、ControlMath、HTE、failsafe、位置/速度/姿态/rate控制数学均无修改。
只在既有logger HIGH_RATE配置增加local_position、local_position_setpoint、trajectory_setpoint三个全发布率请求。
不新增消息、不改变控制调度，其他profile位全部保留。

源起点8462f8139e88b8976dcd89424c3c04525489b72b，分支research/sta-velocity-control。
实际飞行必须在本协议/源码提交的干净工作区，--source-head填写现场完整SHA；不将dirty构建称为飞行版本。
提交后重建固件并记录实际SHA，三轮由同一启动前指纹约束，若启动器重编译导致变化即停止。
静态冻结来源与26个现存插件指纹见frozen.json；模型/插件/控制参数变化拒绝。

## 任务、参数与三轮预算

准确清单run01→run02→run03，每轮新PX4/Gazebo进程；最多3次，失败立即停止，无补飞和自动续跑。
原默认随机引擎；seed=null，不冒称三个独立种子。不加载M10或旧ISTA插件/扰动。
沿用sitl/run.sh --headless --backend gazebo --model iris，empty_grey.world，1倍lockstep。
Iris10016/quad_w，不是DP1000；拒绝现有PX4/Gazebo/QGC、占用端口、自定义logger_topics和生成模型覆盖。

固定原位置P、XYZ速度PID、姿态和rate PID。MC_RTC_MODE/MC_STA_AXES/MC_RATT_TEST/MC_STA_TKO_MGT=0，MC_RTC_DIV=1。
所有MC_和MPC_及SYS_VEHICLE_RESP值见frozen.json，从当前生成参数定义冻结；若持久化值与此不同，停止，不能偷偷调参。
本版起飞参数实际叫MIS_TAKEOFF_ALT，设为2.5m（不是NAV_TAKEOFF_ALT）。HTE、滤波、估计器原配置保持。
SDLOG_MODE=1，SDLOG_PROFILE保留原位并OR16，logger在预热前重启为256KiB、1000Hz轮询、全程记录。
SDLOG_DIRS_MAX临时1000，避免当前7个历史目录被第8天启动清理；预检磁盘留余量，不删除旧日志。

启动前完整备份EEPROM原字节；只重编码受控启动覆盖（原持久化其他条目保持），每次关闭自有实例后恢复原字节。
完整运行参数在起飞前/落地后归档和验证；机内飞行计数可变化，不混入控制参数比较。
还原原BSON包括尾随字节，不将修改后的启动参数冒充用户原参数。

机载flight_mode_manager是轨迹目标来源，mc_pos_control提供姿态/推力，mc_att_control提供角速度目标。
运行器只发本地commander起飞/模式命令、GCS保活和中性RC；没有第二个offboard/姿态/角速度目标发布者。
预热至少30秒模拟时间且估计就绪；起飞后本版CODEV自动切POSCTL，明确请求Hold；稳定3秒进入悬停。
悬停60秒，再AUTO_LAND直到landed且disarmed。墙钟超时、包络、日志门槛准确值均在protocol.json，代码同步冻结。

## 预注册门槛与指标

- 全飞行：无failsafe/failure_detector/研究fault/termination，实际内环模式0/掩码0/DIV1，旧激励为0；有效测量与输出。
- 倾角≤15°、XY距起点≤2m、水平速度≤1m/s；高度在[-.5,4]m；起降|vz|≤3.5m/s。
- 悬停：60–62s；高度距2.5m≤1m，进入悬停时≤.5m，|vz|≤.6m/s，yaw跟踪误差≤20°。
- 有限归一化命令绝对值≤1.001；没有把M10的0.15试验限幅强加给原PID。饱和比例照实报告，不以“从未饱和”为门槛。
- 全飞行rate诊断publish_seq不得缺样；ULog dropout=0；8个连续话题悬停至少600点、最大相邻间隔≤.25s。
- 原速度模块未有样本级诊断。最终输出目标与最近先于它的实测状态匹配，匹配年龄≤20ms，指标时间覆盖≥59.75s；
  无插值，不声称精确复原被消费状态。输出发布/位置timestamp与timestamp_sample间隔及perf调用数分别报告。
- 本版ULog只保存已使用参数；18项核心位置/速度/rate增益与HTE、全部启动覆盖必须存在并符合冻结值。
  其余冻结参数逐项校验完整CLI参数表，ULog中存在的也必须相符，缺项列表公开，不把未使用参数缺项误报为日志故障。
- actuator仅按真实timestamp_sample交集比对c_applied，实际匹配必须逐位一致、覆盖≥80%、最大间隔≤.25s。
  这是V00预注册的有限覆盖检查，不继承I05不可能的100%要求；缺失不能据此断言每条实际输出都无误。
- 60秒悬停逐轴时间权重速度/位置RMSE、mean/std/max，另记姿态、yaw、高度、加速度需求/推力与rate误差。
  日志状态与输出匹配限制公开；V00不作完整频谱/电机能耗/独立样本统计或性能胜出结论。

失败关闭自有SITL并保留原始ULog/console/CLI/参数/ledger，不以零力矩或PID接管声称安全。
前一步检查失败不启动下一轮，不自动调阈值；脚本异常也消耗已启动尝试，不可另换目录自动补飞。

## 命令

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
python3 research/sta-velocity-control/scripts/run_v00.py \
  --source-head '<本协议实际完整提交SHA>' \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V00/series01'
# 上面只dry-run；核对后同一命令加 --execute 才执行三轮。
```

飞行前离线验证verification02：37个C++用例（Takeoff8、Position15、ControlMath9、Rate1、Dispatcher4），
16个Python工具测试；构建及所有命令退出0。另外DONT_RUN=1构建Gazebo目标，没有启动仿真。
正式三轮完成或首次失败后写独立结果提交并更新实时进度；不push、不执行V01。
