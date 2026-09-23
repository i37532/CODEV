# V04：降落期 EKF 切换与目标补偿离线审计

2026-09-23。范围：只读分析 series06/run01、核对固定源码、离线回归和数值风险探针。**新飞行 0；没有修改控制器、估计器、仿真传感器、参数、运行器、验收规范或门槛。V04 仍 failed / needs_revision。**

## 1. 结论

这次不是打印精度误报。降落中 EKF0 与其他估计器出现明显的垂向速度分歧，selector 的相对误差评分满足切换条件，111.656s 从实例0切到1。切换后参考及多类 reset 确实改变，宿主按冻结协议中止。

**本次实际消费的旧缓存目标没有漏补偿或重复补偿**：位置模块当帧给位置、速度和 yaw 各加一次 delta；下一帧消费 FlightTask 重新生成的目标，不再加 delta。Z 跟踪误差在切换当帧保持连续，但这不等于整个自动任务、姿态控制和实际飞行严格无扰。

有两项不能忽略：

1. 离线仿真真值在切换前已出现下降转回升，符合近地接触/弹起的线索；没有接触力日志，不能断言具体碰撞机理。
2. 源码存在 **IMU0 加速度无检查转 int16 的超范围风险**。独立探针已复现风险，但原始 HIL 峰值没有记录，尚不能确定它就是本次估计器分歧的根因。

因此本轮**不修订协议、不增加降落 reset 豁免、不申请/执行新批次**。建议先离线验证 IMU0 真实转换链，再决定是否另行授权上游修复或有限的降落切换准入规则。

## 2. 核对范围与原始依据

- 审计起点：`research/sta-velocity-control`，HEAD `1032dcf56cb62a713c8ae00ce402d4c3160ca71f`；开始工作区及递归子模块干净，未回退/清理。
- 完整阅读外部速度 TODO/共同规则、实时进度和 protocol07 结果；参考旧起飞 heading 审计。首次定位时不存在的 `src/lib/FlightTasks` 已更正为实际 `src/modules/flight_mode_manager/tasks`，不是缺失依赖。
- 飞行源码：`658e57e8ff549cdb89780c61c53ca8b3ec4faa0d`；Gazebo `822050a7ab6fd87972e59f16312f451bce217a56`；ECL `b3fed06fe822d08d19ab1d2c2f8daf7b7d21951c`。
- 原数据：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series06/run01`。主 ULog `11_01_38.ulg`，SHA-256 `46a50a2c0678ead8efd093ee7ad193144a46a0f5c116e202fc1ed6f26b0c523b`；启动 ULog `11_01_37.ulg`，SHA-256 `b68cb8e04397f4426758ef2d399605db4408c35c8343fc8f5a194a8712f88499`。两份日志 dropout=0、corruption=false，但这不代表每个话题都是全速记录。
- 实际速度/角速度均 PID：速度 MODE/AXES=0/0，rate MODE/AXES/DIV=0/0/1；旧起飞管理关闭。未运行 ESTA、ISTA 或实机。
- 原判定保留：本批 1 尝试、1 完整观察、0 完整起降、0 接受；ESTA0、余5停止。六批累计6尝试/0接受，不能把本审计的通过当作飞行通过。

## 3. 事件顺序：先出现估计分歧，再切换，再宿主中止

以下都是日志原始仿真时间，不把 CLI 读取时刻当作事件发生时刻。

| 时间 s | 证据 |
|---:|---|
| 107.544 / 107.680 | 宿主发送降落 / 实际 AUTO_LAND |
| 111.436 | 10Hz 仿真真值 `vz≈+0.66m/s`（NED 向下） |
| 111.480–111.488 | 所选 `sensor_combined` Z 比力出现正向尖峰，最大 `+64.19574m/s²`；该流 clipping=0 |
| 111.536 / 111.636 | 真值 `vz≈−0.10/−0.51m/s`，已转为上升；此时尚未主实例切换 |
| 111.596 | selector 中 EKF0 combined ratio≈0.239534，EKF1≈0.016113，开始快速降低相对评分 |
| 111.644 | EKF1 relative ratio≈−0.340526，主实例仍0 |
| 111.656 | 主实例0→1，公共位置/速度/heading/姿态 reset 同时改变 |
| 111.668 | FlightTask 第一个新目标被位置模块消费 |
| 112.028 | 宿主检查报 `CLI reference representation changed: ref_timestamp` 并中止 |

选择器依据：`EKF2Selector.cpp:283`起将速度/位置比值平均后与高度比值取最大。EKF0 在111.636s的已记录比值是 vel=0.473488、pos=0.005579、hgt=0.000347，故 combined≈0.239534；EKF1 对应 combined≈0.016113。配置 `EKF2_SEL_ERR_RED≈0.2`，两者差≈−0.223421，下一次累计相对评分预测为−0.563947，跨过源码−0.5门槛；距上次选择也已超过10s。

切换时两个实例 healthy=1，gyro/accel fault均0，记录的 filter_fault_flags=0；证据与 `Run()` 的“当前健康但替代实例误差更低”分支一致，**不是只有主实例坏掉才会切换**。分支原因本身没有遥测字段，不能据此反推未记录的每个调度过程。备选实例短暂 healthy 变化也不能仅凭低频状态断言硬件故障。

111.836s 的低频日志进一步显示：EKF0 `vz≈+0.655m/s`、GPS垂向速度 innovation≈+1.106m/s；EKF1 `vz≈−0.545m/s`、innovation≈−0.00156m/s。它支持垂向估计分歧，不证明分歧的唯一物理原因。

## 4. 参考变化不等于无人机瞬间跳动

111.644→111.656s：`ref_timestamp` 1196000→1192000，lat/lon不变，`ref_alt` 488.481506→488.481262m（仅−0.000244m）；但公共估计 `z` 0.587583→0.423413m、`vz` +0.757946→−0.513145m/s。

`EKF2Selector.cpp:412` 的公共输出在实例切换时重新计算差值并递增计数；本次六个位置/速度 delta 与新旧公共值之差逐字段核对一致：Z delta=−0.164170m、Vz delta=−1.271091m/s；heading delta≈−0.001595rad。位置模块 reset_bits=31。

这些差值包含不同滤波器估计的差异及相邻采样的运动，**不是都能视为同一坐标系的刚性平移**，也不是机体瞬间跳了16cm。不能仅更新 ref_timestamp，或者给脚本所有目标统一再加一遍 delta 来“解决”。

## 5. 目标如何处理：确切区分三层

`selector 公共 reset → FlightTask 重新生成目标 / MPC 旧缓存补偿 → 姿态模块内部适配 → rate PID`

### 5.1 MPC 旧缓存：本次确实只补一次

`MulticopterPositionControl.cpp:326`：仅 `_setpoint.timestamp < local_pos.timestamp` 时，对计数变化的相应目标加 delta。111.656s 消费的仍是111.644s目标，因此执行补偿；111.668s输入和新目标时间戳相同，且 reset 计数已记账，不再补偿。

下面 `v_ff` 是上游平滑速度前馈；`v_sp` 是叠加位置P后的实际速度环目标；`v` 是速度环测量。不能把它们混作一种目标。

| 时间 s | p_sp Z / m | v_ff Z / m/s | v_sp Z / m/s | v Z / m/s | a_req Z / m/s² | 归一化推力 Z |
|---:|---:|---:|---:|---:|---:|---:|
| 111.644 | 0.571470 | +0.700000 | +0.683887 | +0.757946 | −0.542891 | −0.749627 |
| 111.656 | 0.407300 | −0.571091 | −0.587204 | −0.513145 | −0.544118 | −0.749712 |
| 111.668 | 0.404285 | −0.536139 | −0.549006 | −0.536139 | −0.301161 | −0.732112 |

切换当帧 `v_sp−v` 前后均约−0.074059m/s；请求加速度只变约−0.001227m/s²，不是因目标漏补偿而突然增加约1.27m/s误差。XYZ位置与速度目标共6字段逐项 float32 精确匹配，yaw输出也匹配原目标加 delta。

### 5.2 FlightTask 新目标：重置平滑器，不是把所有目标永久平移

自动任务实际走 `FlightModeManager.cpp:223` 的 AutoLineSmoothVel。`FlightTask.cpp:48` 分派 reset；`FlightTaskAutoLineSmoothVel.cpp:90`起把平滑器的位置/速度状态设为新测量，再继续生成轨迹。新目标 `vz=−0.536139m/s` 与当时新估计一致，不等于旧目标加一次/两次 delta。这是原任务逻辑，不是 ESTA 的改动。

`AutoMapper::_prepareLandSetpoints()` 内部先提出下降速度和 NaN Z位置，但 AutoLine 平滑后公开 `trajectory_setpoint.z` **仍是有限值**；因此本次切换附近未启用 MPC 的 `z_deriv/vz` 混合分支，实际 `v[2]` 使用 `local_position.vz`。不能因为处于 LAND 就假定只控垂向速度、关闭位置P。

本次 LAND triplet 的 lat/lon 是 NaN、yaw有限。`FlightTaskAuto.cpp:169`起保留本地 `_lock_position_xy`；reset handler 重置平滑器，但未给这个锁定终点统一加 delta。参考更新、锁定终点、平滑器状态不是同一件事，不能据本轮几毫米XY reset就保证大幅reset也无扰。

### 5.3 yaw / 姿态与导数：仍有明确边界

旧目标 yaw=1.592893rad，MPC当帧输出约1.591299rad；下一份 navigator固定yaw又是1.592893rad。AutoLine补偿 `_yaw_sp_prev`，并不保证每份公开yaw永远跟着累计delta。

`mc_att_control_main.cpp:258`起**先读取新姿态目标，再检查四元数reset并适配内部目标**；`AttitudeControl.hpp:85`为 `q_delta*q_sp`。随后再来的外部目标可替换内部目标。内部消费顺序/适配后的目标没有独立日志，不能由公开姿态目标推导全链严格无扰，亦不能仅看到两个模块都“补偿”就认定本次发生双补偿。

`set_vehicle_states()` 仅在速度无效时重置导数，并未因有效测量的reset计数直接清零导数。因此 Z导数在切换时从−3.484跳至−31.530m/s²。当前 `MPC_Z_VEL_D_ACC=0`，本轮它不直接形成Z轴D输出；不能声称不同D增益也安全。没有改这段既有语义。

当前 ESTA X 保护对“新目标时间戳不早于本次 vxy reset”的情形会设置 `unmatched_reset_axes` 并可能锁存 `ResetMismatch`。本次PID日志只证明其实际旧缓存路径，不能代替未来ESTA reset准入验证。

## 6. 新发现的上游数值风险：证据分级

`src/modules/simulator/simulator_mavlink.cpp:212`起：IMU0走FIFO，scale=`9.80665/2048`，量程16g；将 `sensors.zacc/scale` 直接赋给 `sensor_accel_fifo.int16 z[0]`，没有转换前边界检查。IMU1/2走浮点 `update()`。`PX4Accelerometer::updateFIFO()` 的clipping检测在缩窄转换之后；若之前已失真，clipping=0不能排除该风险。

本机 C++14/O2 **合成**输入−250m/s²时，未检查转换打印重建值+63.815m/s²；加入 `-fsanitize=float-cast-overflow -fno-sanitize-recover=float-cast-overflow` 后，明确报超出short范围，退出1（预期诊断）。范围内−9.81m/s²正常退出0。

**已经证实的是源码风险与合成复现；未证实的是这次旧飞行的精确HIL峰值和完整因果链。** 越界浮点转整数不能当作可移植的取模规律；本机数值不保证其他编译器/优化相同。不能把合成−250写成实测峰值。

当前日志：`sensor_combined`约250Hz；各 `sensor_accel`约1Hz、`vehicle_imu`约2Hz、各 `estimator_local_position/innovations`约2Hz。没有冲击瞬间的所有原始IMU通道或HIL加速度；插件 innovations 文件只存噪声增量而非含真实加速度的完整输入。10Hz真值也不足以反算毫秒级冲击峰值。无日志dropout不弥补这些采样/字段缺口。

## 7. 实际离线验证与归档

- 新只读审计18项检查全部通过，**不是18次实验或新增C++用例**；两次审计输出保留，最终为 `landing_ekf_audit02`。
- 109个不同C++用例、211个Python用例通过，退出0；其中新增7个审计工具测试。PID两组各2048步、旧速度/角速度、实际Run/uORB缓存reset和原姿态测试均保留。未新增完整EKF/FlightTask/姿态异步端到端测试。
- SITL构建、测试构建、`DONT_RUN=1 make px4_sitl_default gazebo_iris -j4`均退出0，**未启动Gazebo**。
- 合成转换探针范围内退出0；越界sanitizer退出1是预期风险检出，不计作“生产实现测试通过”。探索时曾尝试在稀疏IMU窗口计算采样间隔，因仅一条记录报空数组错误；已确认是日志频率限制，未伪造全频率IMU数据。
- 199项protocol07冻结资产、42份原始批次文件、59份本轮外部审计/回归工件指纹核验通过。EEPROM未变：`06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`；无残留模拟器。

逐命令/退出码及小型证据见 [verification.json](../v04/landing_ekf_audit01/verification.json)、[完整审计摘要](../v04/landing_ekf_audit01/audit.json)、[原始文件指纹](../v04/landing_ekf_audit01/original_artifacts.sha256)、[本轮工件指纹](../v04/landing_ekf_audit01/artifacts.sha256)。后者SHA-256：`24b008298e814080960cf985e80cea6a902c8f82e547c1e08405efe3076a0622`。

所有原始日志及2.48MB逐样本timeline仍在仓库外；仓库不复制大日志。复现命令如下，输出目录必须换成尚不存在的新目录：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/research/sta-velocity-control/scripts:$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/scripts/audit_v04_landing_ekf.py \
  '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series06/run01' \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/landing_ekf_audit03'
python3 research/sta-velocity-control/scripts/verify_v04_landing_ekf_audit.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/landing_ekf_verification02'
```

本次实际审计目录为audit01/02、验证目录verification01；上面的03/02只作未来复现占位，尚未执行。复用旧回归器的 `base=640a...` 和 `failsafe_semantics_intentionally_changed=true` 描述历史差异，**不是本轮修改了failsafe**。

## 8. 下一步决策与停止点

建议先做“真实 Simulator→FIFO→加速度→估计器输入链”的离线边界/冲击注入对照，验证量程溢出、clipping和多IMU差异；保留范围内旧行为。不为凑基线而关闭多EKF、强制指定主实例、统一接受reset或调低着陆速度。

如果需要上游修复，另行说明范围并取得授权；如果最终只修订降落准入，需先定义有界reset、目标补偿可观测性、接触/弹跳、ESTA锁存及完整降落上锁条件，再冻结新协议并另申请预算。本轮没有实施这些后续工作。

仅新增研究审计脚本/测试/探针、报告和证据入口，按明确文件列表提交；完整提交SHA记外部进度表。**不push、不补飞、不续跑余5、不进入V05。**
