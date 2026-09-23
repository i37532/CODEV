# V04：起飞航向对齐离线审计及 protocol04 设计

2026-09-23。授权范围：先离线审计正常起飞航向对齐处理，再修订协议。本次新飞行 **0**、新种子 **0**；不是 V04 飞行验收。

## 1. 结论与边界

series02 首轮约 1.60m 的航向变化，与当前 ECL 首次空中磁航向对齐机制一致。七份已有 PID 日志均有一次类似起飞对齐，修正量约 0.066°–0.376°；它不是 ESTA 接入独有现象。但不能据此允许所有 reset，也不能把原失败改成通过。

目标补偿分布在 FlightTask、位置模块和姿态模块，不能由脚本统一再加一次 delta_heading。真实日志显示同时间戳新目标可能不作位置模块补偿，发布 yaw 也不一定跟随 reset 跳变；本审计不声称整条链严格无扰切换。

新版设计仅在任务前、证据齐全时分类一次正常对齐，然后一次性选取对齐后的任务 yaw。运行器/分析器尚未实现，无新飞行授权。V04 仍 `failed / needs_revision`，ESTA X 实际飞行仍为 0。

## 2. 基线与源码处理

开始 HEAD `bf98350bfdc50e5c4af5e01dbd48b06a167322a0`，分支 `research/sta-velocity-control`，工作区与递归子模块干净；未回退/清理。完整阅读外部速度计划/共同规则、进度表及 protocol03 设计/失败报告。旧计划/协议不覆盖。

ECL `b3fed06fe822d08d19ab1d2c2f8daf7b7d21951c`；Gazebo 子模块 `822050a7ab6fd87972e59f16312f451bce217a56`。逐源码指纹及递归版本见 [审计快照](../v04/heading_audit01/audit.json)。

| 位置 / 函数 | 实际行为与限制 |
|---|---|
| `src/lib/ecl/EKF/mag_control.cpp:127`，checkHaglYawResetReq / runInAirYawReset | 尚未空中磁对齐、内部延迟地形相对高度大于 1.5m 时提出请求，还须通过禁止/磁场等条件；成功后设置 mag_aligned_in_flight。不是任何 1.5m 飞行都必然成功。 |
| `src/lib/ecl/EKF/ekf_helper.cpp`，resetMagHeading / resetQuatStateYaw | 更新四元数/输出缓存、保存 delta、增加计数；并非把 NED 位置/速度整体旋转。 |
| `src/modules/ekf2/EKF2Selector.cpp`，PublishVehicleLocalPosition | 底层 reset 与主估计器切换都可能改变公共 heading 计数；单看计数不能区分原因。 |
| `src/modules/flight_mode_manager/tasks/FlightTask/FlightTask.cpp`，AutoLineSmoothVel/FlightTaskAutoLineSmoothVel.cpp:112 | 基类分发 reset，AutoLine 对 `_yaw_sp_prev` 加 delta；不代表所有分支的当前 `_yaw_setpoint` 都同步补偿。 |
| 同 tasks 目录 Auto/FlightTaskAuto.cpp / ManualAltitude/FlightTaskManualAltitude.cpp:334 | 起飞与一般 navigator yaw 处理不同，已锁定有限 yaw 可以保持；手动分支则对有限 yaw 加 delta。 |
| `src/modules/mc_pos_control/MulticopterPositionControl.cpp:326` | 仅目标时间戳早于 local_position 时，旧缓存随新计数补偿一次；同时间戳/较新目标不补偿。 |
| `src/modules/mc_att_control/mc_att_control_main.cpp:268` / AttitudeControl/AttitudeControl.hpp | 内部姿态目标乘以 reset 四元数；内部适配目标不等于公开原始 setpoint，不能用后者证明完全无瞬态。 |

series02 在 36.860s：local_position 与消费的目标时间戳同为 36.860s，发布 yaw 保持约 1.575771rad；reset_bits=16，无首次失败/重算。姿态 quat reset 晚约 4ms，附近采样 yaw 误差峰值约 0.006381rad。只是局部诊断，不是完整激励指标。

## 3. 已有日志复核

只读解析七份仓库清单指向的原始 ULog，逐文件校验 SHA-256。不同源码版本的开发资料，不是新配对七次实验；原验收结论不变。

| 历史记录 | 首次对齐时刻 s | delta ° | 相对原地面高度 m | estimator_status 对齐标志滞后 ms |
|---|---:|---:|---:|---:|
| V00-1 | 37.164 | 0.183739 | 1.573918 | 32 |
| V00-2 | 37.164 | 0.187007 | 1.567059 | 52 |
| V00-3 | 37.124 | 0.285263 | 1.569209 | 32 |
| V01 | 37.144 | 0.216900 | 1.567536 | 0 |
| V03 | 36.716 | 0.237373 | 1.588918 | 132 |
| V04 series01（失败） | 37.600 | 0.065805 | 1.589114 | 120 |
| V04 series02（失败） | 36.860 | 0.375859 | 1.599521 | 120 |

起飞事件均在 AUTO_TAKEOFF、armed、已离地且主实例对齐标志先为 0。V00-2、V00-3 在降落 106.056s 另有 heading reset，同时主估计器 0→2、位置/速度计数及参考高度变化；这不属于首次对齐例外，新规则仍拒绝。旧 V00 原规则验收不追改，新规则是否能完成整轮必须将来验证。

固定版本 estimator_status 的 logger 间隔 200ms；selector/status_flags 约 1Hz 或变化即发布；event_flags 仅事件发布。series02 在 reset 时 selector 最近消息年龄 0.58s，event_flags 最近消息年龄 31.26s，不能仅据此说丢样。新规范分别限定周期话题年龄；事件流检查原始快照、连续可观测性和计数，不要求不存在的心跳。对齐证据未到时保持 pending，不提前通过。

## 4. 修订内容及停止点

详见 [protocol04 简明规范](../v04/protocol04/README_CN.md) 和 [完整设计](../v04/protocol04/protocol.json)。保留旧候选、性能/安全门槛、准备总超时 150s、观察/激励窗口及正常计划降落分类；仅修订起飞 heading 分类和任务 yaw 冻结。

新增 5°修正上限、1–3m 准备高度、0.5s 确认等待、1s 安静段及不超过 1°的任务 yaw 变更，是明确披露的开发工程条件，不是独立测试结果或理论界。对齐后 yaw 只冻结一次，保留原 pre-arm yaw；不重冻位置/高度参考，不再叠加 delta，不不断追随测量。

纯函数检查已组装证据包，不等于实际运行器能采齐证据，也不表示七份旧日志满足新版完整验收。在线 primary 绑定、异步 pending、缺失流/序号和完整 ULog 分类尚未接线。旧脚本仍是旧规则，不得直接用于新批。

拟议最多六次、三组全新 PID→ESTA 配对，准确种子/目录/逐轮清单未分配。先补齐独立接线/离线测试并冻结干净执行提交，再申请新飞行；旧失败和停止预算不复用。

## 5. 实际测试与复现

新增两项真实 Run/uORB 测试：旧缓存正负/跨角度边界 delta 只补偿一次；同时间戳/较新目标不重复补偿。新增 10 项 Python 测试覆盖边界、计数回绕/跳变、阶段/重复事件、缺字段/非有限值/超时、四元数一致、一次 yaw 冻结及继承指纹。

最终实际 **106 个不同控制相关 C++ + 3 个既有 AttitudeControl = 109 个 C++，99 个 Python** 均通过，退出码 0；重复运行不重复累计。既有姿态三项不是新增 EKF reset 端到端测试。PID 两组各 2048 步位级回归保留；SITL 与 DONT_RUN Gazebo 构建通过，未启动 Gazebo。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
# 以下是本次真实命令；复跑必须改用新的未存在输出目录，不能覆盖。
python3 research/sta-velocity-control/scripts/audit_v04_heading.py --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/heading_audit02'
python3 research/sta-velocity-control/scripts/verify_v04_repair.py --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/heading_verification02'
build/px4_sitl_test/unit-AttitudeControl --gtest_output=xml:'/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/heading_attitude01.xml'
```

三命令均退出 0。最终逐命令/计数见 [evidence.json](../v04/heading_audit01/evidence.json)，Python 原输出/姿态 XML 同目录。复用验证器中 `base=640a...`、`failsafe_semantics_intentionally_changed=true` 是相对更早修复前版本的字段，不代表本轮改了 failsafe；本轮以起点 git diff 为准。

未执行：新飞行、完整 EKF/FlightTask 闭环仿真、MATLAB、实机、ISTA、V05、push。测试未失败；文档首次 apply_patch 因末尾匹配失败未落盘，已更正，不是测试失败。早期与最终离线输出均保留。

## 6. 归档与提交

外部 heading_audit01/02、heading_verification01/02、heading_attitude01.xml 保留；[指纹索引](../v04/heading_audit01/artifacts.sha256)保存外部实际路径。原日志只读并核验；不重新生成原实验结果。

81份本轮外部工件指纹全量核对通过。protocol04设计SHA-256为 `c071d1648ee260fcfde411514d11feef6926cf165113739c61bbfd63b4d1db8d`；仍为离线设计，不是可飞源码冻结。

EEPROM parameters_10016 未变，SHA-256 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`。生产控制/估计器/Takeoff、参数、消息/日志配置和模型均未改，src 仅测试差异。本轮按明确文件列表提交，完整 SHA 记录外部进度表，不 push；V04 不验收。
