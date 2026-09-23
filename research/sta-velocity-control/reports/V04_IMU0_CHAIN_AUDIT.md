# V04：IMU0 真实转换链离线验证

2026-09-23。用户授权仅为“先离线验证 IMU0 转换链”。**离线诊断完成，缺陷复现；生产实现未修复，V04 仍 failed / needs_revision。新飞行、种子消耗、飞行预算均为 0。**

## 1. 结论与边界

已不再只是复制转换表达式：本轮实际编译并调用原 `Simulator::update_sensors`、`PX4Accelerometer` 和 `VehicleIMU::Run()`，通过真实 uORB 检查 `sensor_accel_fifo → sensor_accel → vehicle_imu`。

**确认：IMU0 的无检查 float→int16 转换可以将超量程冲击变成反方向加速度，且丢失 clipping 提示；错误能够传到 EKF 使用的 `vehicle_imu.delta_velocity` 输入话题。** IMU1/2 走浮点路径，同样合成输入保持方向并标记超量程。后级积分不会自动修复已失真的样本。

这不是“缺陷已经修好”，也不是“原飞行根因已经最终证明”。旧 series06/run01 缺少冲击时刻原始 HIL 加速度和完整高频各 IMU 数据；合成 −250 m/s² **不是实测峰值**。本轮没有执行 EKF 融合/selector、接触物理或完整飞行任务，不能把脉冲面积直接当成融合后 NED 垂向速度变化。

## 2. 实际测试链与版本

```text
合成 mavlink_hil_sensor_t（机体系比力，m/s²；4 ms 间隔）
  → 原 Simulator::update_sensors
      ├─ IMU0：除 scale → int16 FIFO → 原 updateFIFO → sensor_accel[0]
      └─ IMU1/2：原浮点 update → sensor_accel[1/2]
  → 三个原 VehicleIMU::Run（实际 uORB、校准、积分、clipping、发布）
  → vehicle_imu[0/1/2]：delta_velocity、dt、clipping
  → EKF2 读取边界（本轮只审计源码，未执行融合）
```

- 起点：`research/sta-velocity-control`，HEAD `ef12d22419dfb0ab91dea21cd976f86da113b7fa`，初始主仓库/递归子模块干净；未回退或清理。
- 三个被测实现、EKF2 消费端及三个消息文件，与原飞行源码 `658e57e8ff549cdb89780c61c53ca8b3ec4faa0d` 逐字节一致。Gazebo `822050a7ab6fd87972e59f16312f451bce217a56`；ECL `b3fed06fe822d08d19ab1d2c2f8daf7b7d21951c`。完整 SHA 和子模块清单见 [integrity.json](../v04/imu0_chain01/integrity.json)。
- 编译器 GCC 11.4.0，C++14。从现有测试编译数据库和链接命令取得依赖；三个实现与 SITL 默认构建的数值选项一致：`-O2 -fno-signed-zeros -fno-trapping-math -freciprocal-math -fno-math-errno -std=gnu++14`。
- 这是同步功能夹具，不是整机调度复现：测试构建没有生产配置的 `ENABLE_LOCKSTEP_SCHEDULER`；仅夹具用 `-fno-access-control` 访问入口，HRT 异步调度替身不执行，逐采样同步调用 `Run()`；没有改生产头文件或 CMake。没有调用 Simulator 网络/start/run 或 VehicleIMU::Start，没有连接 Gazebo。
- 测试进程关闭参数自动保存、使用默认校准及无旋转，设置测试内 `IMU_INTEG_RATE=250`，预热150帧后检查实际输出 `delta_velocity_dt=4000µs`、sample 时间与三轴隔离。4ms是本诊断输入周期，亦与原记录的IMU流相符，不是声称位置控制环250Hz。

关键源码：`simulator_mavlink.cpp:230–234` 转换及驱动调用；`PX4Accelerometer.cpp:115/140` 浮点/FIFO路径；`VehicleIMU.cpp:224/410` 消费、积分与发布；`EKF2.cpp:315` 多实例读取 delta_velocity/dt/clipping。

## 3. 范围内行为与边界

scale=`9.80665/2048 ≈ 0.0047884034 m/s²/count`。范围内测三轴各8个输入（−150、−100、−9.80665、−1、0、+1、+100、+150），稳态 IMU0 量化误差不超过约1 LSB；IMU1/2保留浮点输入。检查其他轴不串扰，积分 dt/sample 正确。

FIFO每次只有1个整数样本，驱动报告实际是 `0.5×(上次整数+本次整数)×scale`；它不是本次整数直接乘scale。VehicleIMU再做梯形积分。因此单个范围内 −100 m/s² 脉冲会在驱动成为两帧约 −50，再在积分成为约1/4、1/2、1/4面积分布；总面积约−0.4 m/s，与浮点路径一致（允许量化误差）。这说明瞬时曲线存在路径差异，不能要求各IMU逐帧完全相同。

边界测试覆盖实际整数±32735附近及−32768/+32767。clipping按**实际已发布整数**判定，不把浮点除法/倒数优化的舍入猜测当参考。FIFO约32735计数开始标记接近量程；IMU1/2浮点路径的默认阈值与它不完全相同。

- `−16g ≈ −156.906403 m/s²` 对应−32768：本机安全边界测试通过，clipping置位。
- `+16g ≈ +156.906403 m/s²` 对应+32768：已经超出int16正端。sanitizer在原 `simulator_mavlink.cpp:232` 报错退出1。
- −156.911194、±157、±250、NaN、±Inf、1e20也分别检出越界/非法转换，共10次独立诊断退出1。
- `fields_updated=0` 时包含NaN的加速度不应发布，本测试通过；这**不等于**有效加速度字段中NaN已获安全处理。

## 4. 冲击缺陷如何传播

在零输入基线、无旋转与默认校准条件下，每轴分别施加±250 m/s²一个4ms样本，随后4帧零输入。以下是本机原源码未加sanitizer的观测，不是可移植的越界取模定义：

| 合成脉冲 | IMU0 总 delta_velocity / m/s | IMU1/2 总 delta_velocity / m/s | IMU0−IMU1 / m/s | 冲击首帧 clipping |
|---:|---:|---:|---:|---|
| −250 m/s² × 4ms | +0.255260229 | −1.000000000 | +1.255260229 | IMU0=0，IMU1/2=1 |
| +250 m/s² × 4ms | −0.255260229 | +1.000000000 | −1.255260229 | IMU0=0，IMU1/2=1 |

X/Y/Z三轴结果一致。−250输入在本机变成FIFO整数+13327，按scale重建约+63.815052 m/s²；因驱动半样本平均，实际 `sensor_accel[0]` 两帧各约+31.907526，后级delta_velocity三帧约+0.063815、+0.127630、+0.063815。不要把+63.815直接称为该单脉冲的公开加速度峰值。

clipping在已经缩窄的整数上计算，+13327远未到阈值，故没有提示；VehicleIMU忠实地继承了这个缺失。浮点IMU1/2虽然标记超量程，原路径并没有把±250幅值裁掉。本测试不主张浮点路径就是完整真实传感器模型，只用它作同输入对照。

越界浮点转整数属于未定义行为，其他编译器/优化不保证得到同样符号或数值。sanitizer检出原实现的问题，是更稳健的诊断依据。即使上述面积差与旧日志速度分歧量级接近，也不能由此反推出原始峰值或证明唯一因果。

## 5. 实际验证、失败与未执行项

最终 `imu0_chain_verify07` 总退出0：

- 4个范围有效/接口C++用例通过；同4个加sanitizer重跑通过，不重复计数。
- 1个独立缺陷复现用例通过其“错误方向且无clipping”的断言，含三轴正负6个脉冲；**不是生产安全测试通过**。
- 10个非法输入各单独进程运行，预期退出1，并核对错误确实来自原Simulator转换行；不计成10个通过的普通gtest。
- `imu0_chain_regression01`：原109个不同C++、211个Python用例通过；SITL、测试构建与 `DONT_RUN=1 make px4_sitl_default gazebo_iris -j4` 均退出0。原PID两组各2048步等价和已有生命周期回归保留。旧复制表达式探针也随旧回归器重跑，其sanitizer退出1为另一项预期诊断，不混进本轮10个真实链案例。

保留全部开发失败：verify01夹具编译遇到严格double-promotion警告；verify02链接漏conversion库；verify03/04四用例中首项过、后三项失败，原因是uORB跨夹具保留旧队列、合成时间重新起算；verify05清理消费者队列后2过2失败，观察订阅仍残留一帧。最终同时清理测试消费者和观察订阅、增加逐样本时间戳断言，未改变生产函数或放松误差标准。verify06通过4+1用例及8个非法输入；verify07增加正16g和负端邻点，共10个。原目录、日志、对象和命令全保留，见 [attempts.json](../v04/imu0_chain01/attempts.json)。不存在因此增加飞行或预算。

未执行：Gazebo启动/飞行、真实HIL抓包、EKF端到端切换、非默认旋转/校准、非均匀时钟/异步调度、陀螺越界修复、MATLAB、实机。没有新增ULog，不修改旧批次接受数或旧日志主指标。

完整命令/退出码：[真实链验证](../v04/imu0_chain01/verification.json)、[原回归](../v04/imu0_chain01/regression.json)、[回归汇总](../v04/imu0_chain01/regression_summary.json)。样本与面积见 [samples.json](../v04/imu0_chain01/samples.json)。`passed=true`仅表示相应离线验证器按预期完成。

## 6. 复现与指纹

先确保已有SITL测试构建及依赖，再在仓库根目录执行；输出目录须为不存在的新目录：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/research/sta-velocity-control/scripts:$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/scripts/verify_v04_landing_ekf_audit.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/imu0_chain_regression02'
python3 research/sta-velocity-control/scripts/verify_v04_imu0_chain.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/imu0_chain_verify08'
```

本轮实际是regression01、verify01–07；上述02/08仅为未来复现占位，未执行。新链测试不纳入飞行CMake，不能直接运行未过滤的全部gtest并把专用InvalidConversionProbe的预期中止当成意外失败。

199项protocol07冻结资产、42份原始批次文件、59份前次审计工件全量SHA-256复核通过；本轮175份外部工件保留，含所有失败，索引 [artifacts.sha256](../v04/imu0_chain01/artifacts.sha256) 的SHA-256为 `abf8762040c9067a3cfc4274073695074dacaff0f0eea9798cd782bc717e653f`。EEPROM仍 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，无残留PX4/Gazebo进程。生产源码、模型、参数、运行器、冻结协议和验收门槛均未修改。

## 7. 下一步与停止点

建议另行授权一个**上游仿真加速度转换修复**，先明确有限输入的转换前限幅、边界及clipping保真、非有限输入的拒绝/状态策略，并回归范围内原行为及三IMU差异。不能未经设计就声称“取零”或简单裁幅等同安全；不能关闭多EKF、强制IMU1、放宽reset条件来代替修复。非FIFO物理模型一致性、陀螺路径或更多上游修改若需要，应单列范围。

本轮到离线诊断报告为止；未实施上述修复，未修改降落准入。原series06仍1尝试/0完整起降/0接受，ESTA0、余5停止；六批累计6尝试/0接受。只提交研究夹具、验证器、证据及文档入口，完整提交SHA更新外部进度表；**不push、不补飞、不继续余5、不进入V05。**
