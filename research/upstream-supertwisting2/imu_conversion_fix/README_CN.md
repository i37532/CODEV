# 原版 STA2 仿真 IMU 转换修复与离线回归

后续进展：用户授权的[最小起降验证和四系统对比](../quick_results/README_CN.md)已完成，5 次全部接受。原 PositionControl 失败通过只补测试初始化解决，STA 控制律未改；下文保留本轮离线修复时的历史结论。

2026-11-02。已保留原版快照，并在独立工作树修复仿真加速度的整数转换。**IMU 专项 14 项通过、正常量程 2048 帧与原转换逐帧一致、SITL 构建成功；没有修改 STA 控制律，没有飞行。** 原 PositionControl 单测仍有 12 项失败，在未修改原源码上复现相同失败，不能称全部控制回归通过。

本轮只完成离线修复，不赋予新飞行资格，不续跑已停批的 B04，不改判历史失败，未提交、未 push。

## 原版和修复版分开保留

| 用途 | 位置或版本 |
| --- | --- |
| 原版工作树，保持原状 | `/home/yr/Desktop/Codev-SuperTwisting2-original` |
| 原版 HEAD | `fc3720f67767c78cfab668777de13f68562fe2fd` |
| 独立修复工作树 | `/home/yr/Desktop/Codev-SuperTwisting2-imu-fix` |
| 修复分支 | `research/sta2-sim-imu-fix`，同一 HEAD 加本轮未提交补丁 |
| 主研究仓库 | `/home/yr/Desktop/Codev-autopilot`，仍为 `research/upstream-supertwisting2` |
| 主仓库 HEAD | `1f6fe1c7a46c22ea41a6a6a51c51498142ca6d62` |

外部证据根目录为 `/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-IMU-FIX-20261102`。其中 `original_snapshot/` 保存原 HEAD 的完整主仓库 tar、原固件、编译配置、转换源码及原工作区/子模块差异；`snapshot.json` 记录递归子模块版本和原主仓库及已初始化子模块的 15,336 个文件指纹。子模块没有再各自打完整 tar，原目录原地保留，修复工作树使用相同提交的本地对象。不要删除作为共享对象来源的原目录。

原固件 SHA-256：`4416c1dc1b93c9a7c96dd0d252b100d1a209cbe5dc0d8baff808c96609983716`。

修复固件 SHA-256：`71a3e620864fa1f00c9b3d43230146cda88237e2a6f7c7c56e2cbf09a39cbed4`。由修复工作树新建 `build/px4_sitl_default` 构建，未启动此固件。HEAD 不包含未提交补丁，复现必须同时使用补丁及其指纹，不能仅使用 HEAD。

## 修复范围

原问题与接地证据见[原版接地审计](../offboard/STA2_CONTACT_AUDIT_CN.md)。生产改动只有仿真适配模块的两个文件：

- `SimulatorMavlink.cpp`：IMU0 FIFO 加速度先按可表示范围饱和，再转换为 `int16_t`。在除以比例系数之前判断端点，避免极大有限输入在缩放时溢出。保留原比例、量程、截断及驱动 clipping 标记。
- `SimulatorMavlink.hpp`：新增每个加速度计独立的无效输入计数器。NaN/Inf 拒绝整个加速度向量，不发布假零值、不推进最后有效采样时间；不阻断同报文中的独立陀螺字段。计数饱和、不回绕。

该上游每个报文只更新其 `id` 指定的传感器，未改为广播三路。IMU1/2 有限输入的浮点路径未加限幅；原 blocked/stuck 故障注入语义保留。新增 `ImuConversionTest.cpp` 和仅在 `BUILD_TESTING` 下注册的 CMake 测试目标，不修改生产调度。

**未改内容：** rate/position/velocity 控制律、增益、默认参数、控制器 dt、驱动积分实现、EKF、land detector、模型、接触资产、原起降逻辑及实验数值阈值。主研究仓库原有未提交源码也未改动。

原 STA2 实际是角速度 STA、XY 速度误差归一化 PID，Z 速度的 STA 输出被注释，实际仍为 PID。因此修复版应标为“原 STA2 控制律＋仿真 IMU 适配修复”，不能冒称完全未修改原仓库，也不能当作仅替换速度控制律的试验。

## 离线验证结果

| 验证 | 实际数量及结果 | 退出码 |
| --- | --- | --- |
| 实际 SimulatorMavlink → 加速度驱动 → uORB → VehicleIMU 链 | 14 项全部通过，无跳过 | 0 |
| 正常量程原/新转换对照 | 2048 帧，整数、加速度、积分、采样时间检查与 clipping 一致 | 0 |
| 原版超量程负对照 | 1 项按新正确性要求失败，证明确实能检出原缺陷 | 1，预期 |
| 实际转换源码 float-cast-overflow 检查 | 同 14 项再次通过，不重复计为新增用例 | 0 |
| RateControl | 1 项通过 | 0 |
| AttitudeControl | 3 项通过 | 0 |
| ControlMath | 9 项通过 | 0 |
| Takeoff | 2 项通过 | 0 |
| PositionControl | 16 项中 4 通过、12 失败 | 1 |
| 未修改原 PositionControl 源码独立编译对照 | 同 16 项、同 12 个失败名称 | 1 |
| SITL 固件构建 | `make px4_sitl_default -j4`，1069 个构建步骤 | 0 |

测试采用真实转换、校准、驱动、积分及发布实现；测试夹具关闭异步调用，手动推进 VehicleIMU，不启动模拟器网络或飞行。不能把这种同步链测试称完整异步系统或 EKF 闭环验证。

覆盖三轴/三设备及 id 隔离、整数端点与相邻浮点数、正负超量程与 `FLT_MAX`、NaN/Inf 各轴、无效首包、无效连续序列/恢复、缺字段、blocked/stuck、独立 gyro 继续处理及计数饱和。恢复保留真实 8 ms 或 84 ms 间隔，不伪造 4 ms；84 ms 测试使用零加速度，仅证明本版 uint32 时间链行为，不证明长缺测后的动力学正确性。极大有限值的 IMU1/2 仅检查转换/发布，未宣称其极端值积分安全。

原转换对照使用快照中未经修改的 `SimulatorMavlink.cpp`，与相同测试夹具编译；头文件使用新增计数存储的版本以保持对象布局一致，原转换代码不访问新增存储。这是实际原转换源码对照，不是重新运行原固件飞行。

### 超量程方向验证

每轴输入一个 4 ms 的 ±250 m/s² 合成脉冲，统计完整驱动滤波及积分尾部：

| 输入 | 原 IMU0 积分 | 修复 IMU0 积分 | IMU1/2 浮点路径积分 |
| --- | ---: | ---: | ---: |
| −250 m/s² | +0.255260 m/s，错误方向 | −0.627626 m/s，有 clipping | −1.000000 m/s |
| +250 m/s² | −0.255260 m/s，错误方向 | +0.627606 m/s，有 clipping | +1.000000 m/s |

这些是**机体系比力积分**，不是 NED 估计速度，也不是新接地实测。饱和恢复了符号和截断标志，但丢失真实冲击面积，不能由此认定高度估计或接地反弹已解决。旧日志缺少转换前原始 HIL 波形，本轮合成试验也不能证明它是历史失败的唯一原因。

### 原 PositionControl 失败单列

未修改的原 `PositionControl.cpp`、`ControlMath.cpp`、`PositionStaControl.cpp` 独立编译后，12 个失败名称与修复树一致。该单测不链接 SimulatorMavlink，相关控制源码哈希一致，因此这批失败不是 IMU 补丁引入的。

静态线索是旧测试夹具只初始化经典 PID 配置，而真实上游模块还调用新增 STA/归一化参数初始化；测试出现 NaN/Inf。尚未把这一线索确认为全部失败的唯一原因。本轮保留测试失败，不改控制律、不删断言、不把测试期望改成接受异常输出。失败名和原始输出见 `evidence01/verification.json` 与外部 `verify01/unit-PositionControl.log`、`original_PositionControl.log`。

开发过程也保留：首次测试构建因 include/API 差异失败；第一次链测试受夹具异步回调竞争影响，第二次残留一个从旧 Codev 误带来的 uint16 时间断言。修正测试夹具及本版 uint32 时间断言后第三次 14/14 通过；未更改生产积分器以迁就测试。`build_test01.log`、`chain01/02/03.log/xml` 均保留。初次控制 `ctest` 返回 8，最终按各套件直接执行记录真实退出码，不把预期失败变成通过。

## 复核入口及证据

[完整补丁](evidence01/sta2_sim_imu_fix.patch)、[机器可读结果和实际命令](evidence01/verification.json)、[范围与指纹审计](evidence01/scope_audit.json)已归档。补丁包含两个生产文件、CMake 和新增测试，`git apply --check` 在原目录、`--reverse --check` 在修复目录均返回 0，仅检查没有实际应用/撤销。

本轮实际执行的最终验证入口：

```bash
cd /home/yr/Desktop/Codev-autopilot
python3 -B research/upstream-supertwisting2/imu_conversion_fix/verify.py \
  --output '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-IMU-FIX-20261102/verify01'
# exit 0：IMU 修复检查通过且原 PositionControl 失败与原版一致；不是所有套件通过。
python3 -B research/upstream-supertwisting2/imu_conversion_fix/archive.py
# exit 0：保存补丁、小型证据和外部日志 SHA-256；不覆盖已有归档。
```

重复验证必须为 `--output` 指定新的不存在目录，脚本拒绝覆盖证据。`prepare.py` 是本轮一次性快照/分支建立记录，不要对已有目录重复执行。`verification.json` 保存每条真实编译、链接、测试命令和退出码；`scope_audit.json` 保存外部构建日志、初期失败日志与最终 XML 的 SHA-256。

以下命令只重建/离线测试，不启动 Gazebo：

```bash
cd /home/yr/Desktop/Codev-SuperTwisting2-imu-fix
export PYTHONPATH='/home/yr/Desktop/Codev-autopilot/.px4-python'
export PATH="/home/yr/Desktop/Codev-autopilot/.px4-python/bin:$PATH"
cmake -S . -B build/px4_sitl_test -G Ninja -DCONFIG=px4_sitl_test
cmake --build build/px4_sitl_test --parallel 4 --target \
  functional-ImuConversion unit-rate_control_test unit-AttitudeControl \
  unit-ControlMath unit-Takeoff unit-PositionControl
./build/px4_sitl_test/functional-ImuConversion
make px4_sitl_default -j4
```

最终范围审计确认：原版 15,336 个文件、原固件、原子模块状态及 B04 的 314 项冻结资产未变；主仓库原有 tracked diff 原样保留。两个仓库 `git diff --check` 返回 0；没有 PX4/Gazebo 进程。

## 新批次前仍需完成

1. 审查并明确记录原 PositionControl 测试债务及其对新资格的影响；当前不是“全测试通过”的版本。
2. 为修复工作树建立独立启动/资格路径，冻结修复源码补丁、固件、工具和资产指纹，保留原版作为对照；不能覆盖旧原版标签或沿用旧固件资格。
3. 另行冻结有限 SITL 清单后，实际核对接地前后 raw IMU/clipping、估计与真值、模式、参数恢复和完整落地尾窗。原数值安全阈值保持，不续跑 B04 剩余六轮。

本轮到离线验证结束，没有新飞行、飞行预算、性能结论或实机验证。
