# V04：发布时间与采样时间离线审计

2026-09-23。**审计完成，未修订验收器、未飞行，V04仍未通过。** 起点 `7cad95b02ead3362f8955da4ca78e78b017ddfae`，分支 `research/sta-velocity-control`，主仓库及递归子模块干净。完整读取速度计划/共同规则、实时进度表和protocol08结果；仅按用户“先离线审计”执行。

## 1. 结论：这两个时间回答不同问题

| 字段/证据 | 在本版姿态链的含义 | 不能据此推断 |
|---|---|---|
| `timestamp_sample` | 姿态所对应的IMU采样时刻，EKF输出预测使用的样本时间 | 消息已经发布或已被控制器消费 |
| `timestamp` | 发布者取当时的HRT时间；selector转发时重新填写 | 唯一消息ID、严格递增的采样编号 |
| uORB generation / 消费sample键 | 发布次数或明确消费关联（需要实际记录） | 仅由相同发布时间或ULog跨话题文件顺序还原 |

protocol08的两条消息发布时间都是60.128s，采样分别60.124s和60.128s，相差4ms。载荷不同、reset计数均3。**它违反现有“发布时间严格递增”的规则，但不证明采样倒退、数据重放或无人机失稳。** 历史失败判定保持，不能据此改成通过。

建议方向是：对经审计的姿态话题分别检查“采样递增”和“发布非递减”，同时保留全部消息、reset、缺样和新鲜度检查；但这不是简单把 `<=0` 改成 `<0`。同刻消息的匹配、窗口边界和指标权重必须一起定义、测试，并另行授权实现。

## 2. 实际源码证据

- [EKF2.cpp](../../../src/modules/ekf2/EKF2.cpp)：Run取`vehicle_imu.timestamp_sample`作为`now`传入PublishAttitude；后者写入`att.timestamp_sample`，正常非replay模式的`att.timestamp`取`hrt_absolute_time()`。因此同名`now`不必等于发布墙钟。
- [EKF2Selector.cpp](../../../src/modules/ekf2/EKF2Selector.cpp)：PublishVehicleAttitude检查sample是否陈旧，转发前把timestamp重写为当前HRT；没有用发布时间唯一性来标识样本。这里不把局部sample检查夸大为所有切换/异常路径的全局保证，日志仍应独立检查。
- [Simulator HIL入口](../../../src/modules/simulator/simulator_mavlink.cpp)：HIL_SENSOR的`time_usec`设置PX4模拟时钟。[drv_hrt.cpp](../../../platforms/posix/src/px4/common/drv_hrt.cpp)在本次已确认启用的`ENABLE_LOCKSTEP_SCHEDULER`配置下读取scheduler时间；[scheduler](../../../platforms/posix/src/px4/common/lockstep_scheduler/src/lockstep_scheduler.cpp)由set_absolute_time推进，不是每次读取就递增的序号。同一模拟时刻可以被读取多次。这说明同刻发布在时间源语义上可能，**不是复现了60.128s时完整的线程调度因果链**。
- [Subscription.hpp](../../../platforms/common/uORB/Subscription.hpp)及[DeviceNode](../../../platforms/common/uORB/uORBDeviceNode.cpp)：更新以generation/队列判定，不要求消息timestamp不同。队列和调度也可能让订阅者跳过部分发布。
- [logger.cpp](../../../src/modules/logger/logger.cpp)：按订阅列表读取已更新消息并拷贝原字段，不把记录写入时间替换成timestamp。跨话题ULog文件顺序是logger读取/写入顺序，不能自动当作飞控消费先后；没有dropout也不等于每条uORB发布都被记录。
- [姿态控制模块](../../../src/modules/mc_att_control/mc_att_control_main.cpp)：原dt使用`v_att.timestamp-_last_run`并夹至0.2–20ms。本版自动姿态反馈核心`AttitudeControl::update(q)`不接收dt，dt还用于手动姿态目标生成等路径。若实际连续消费同刻消息，dt可能触发下限；但本日志的rates_setpoint没有“消费哪条attitude”的sample/sequence键，**不能声称当时一定用了0.2ms，也不能证明没有影响**。本次不修改此上游语义。
- [位置/速度模块](../../../src/modules/mc_pos_control/MulticopterPositionControl.cpp)：原PID继续以local_position.timestamp得到input_dt/used_dt，新算法raw_dt取timestamp_sample。审计日志不授权把所有控制器dt改成sample时间，更不能修改clamp来掩盖异常。

上述19个源文件/消息/检查器指纹和实际HRT编译标志保存在[审计摘要](../v04/clock_semantics01/audit_summary.json)。完整提交固定全部其余源码。

## 3. 七批原始日志复核

复查series01–07七份主ULog及对应原结果记录，先后核验SHA；不同源码、种子和任务长度的数据仅用于开发审计，不能合并成新性能样本。

| 批次 | 起飞事件后已记录姿态条数 | 相邻发布时间相等 | 采样重复/倒退 |
|---|---:|---:|---:|
| series01 | 2613 | 0 | 0/0 |
| series02 | 1638 | 0 | 0/0 |
| series03 | 97 | 0 | 0/0 |
| series04 | 1826 | 0 | 0/0 |
| series05 | 19066 | 0 | 0/0 |
| series06 | 18568 | 0 | 0/0 |
| series07 | 6809 | 1 | 0/0 |

七份记录中的姿态sample间隔均为4–8ms。series07该区间最大`timestamp-timestamp_sample`为4ms，其余六份为0；这是观察结果，**不能据一次4ms现象制定通用年龄门槛**。8ms间隔也不能被解读成每个4ms发布都已无损记录。

直接按原始ULog消息边界解析的姿态timestamp/sample数组与pyulog完全一致；series07连续读器与独立解码1049个字段数组一致。两条异常消息位于字节偏移18470941与18472270，未排序/去重/修改。当前严格accessor仍拒绝series07。

七批的其余十类话题一起检查并保留描述结果；起飞后的所选话题中，同刻还出现在已有专用语义处理的command/ACK事件。不能因这类事件允许同刻，就把事件规则推广到全部连续状态、输出或主指标话题。

series07在附近只记录到60.120/60.128/60.136s的rate目标。这不足以确定两个姿态sample哪个被消费、消费几次或因果顺序。禁止拿“最后一条时间不大于目标”的离线匹配冒称实际消费证明。

## 4. 现有验收链的风险及最小修订边界（仅建议，未生效）

| 环节 | 审计结果 | 后续实现必须满足 |
|---|---|---|
| `v04_heading_stream.data`与`analyze_v00`话题频率检查 | 两处都拒绝timestamp相等，只改在线入口仍可能离线失败 | 仅对明确白名单的姿态流统一语义；采样重复/倒退、发布倒退仍拒绝，缺字段不能填补 |
| `index/previous_indices`使用searchsorted-right | 同刻取最后一条，不提供唯一消费证据 | 保留全部同刻候选；描述性“最后已发布”必须标明口径；需要因果时用实际消费键，无法确定就报歧义 |
| `span`的窗口起点 | 同刻组从最后一条开始，可能遗漏前一条及reset边沿 | 包含完整边界组和前驱，逐条检查reset/delta；不能去重后再检查 |
| `exact_output_match`使用intersect1d | 重复输出键会保留第一次匹配，可能漏掉不同的第二条输出 | 输出关联保持原唯一键要求；有重复不能静默选择第一条，需拒绝或使用可证明的复合键 |
| 指标、缺样、频率 | 发布时间差可能为0，采样差却为4ms；两者不可互换 | 采样频率与发布间隔分别报告；物理时间积分不能靠0权重丢消息。速度主指标仍用原实际更新/sample口径，yaw旧描述口径不得暗改 |
| 安全/阶段门禁 | 同刻组内也可能出现reset、切换或越界 | 所有记录都检查；同刻不豁免primary/reference/reset、非有限值、真实大间断、无效测量或fault |

12个新离线用例验证了这些事实：同刻不同sample、重复/倒退sample、倒退发布、间断/年龄/未来样本、无效输入、旧严格拒绝仍有效、原序列不变、匹配歧义、边界隐藏reset、交集隐藏第二输出、两种时间权重差异、只有发布时间的话题不能伪造sample。

其中“交集隐藏第二输出”测试故意给旧助手两条同键而值不同的输出，复现其覆盖率100%且匹配误差0的结果；**这是助手在重复键输入上的局限，不证明旧完整验收链曾放过这种飞行，也不是新的准入逻辑。** 新文件只做描述/反例，无运行器导入或替换。

后续还需另定并冻结姿态发布延迟/同刻组年龄条件，保持原位置40ms、下游覆盖/间隔、yaw匹配新鲜度等既有门槛；不能用当前失败数据临时放宽。若需要新增真实消费关联日志或改变上游时间处理，属于额外范围，先说明再授权。

## 5. 实际验证与完整性

输出根：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04`。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/research/sta-velocity-control/scripts:$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/scripts/audit_v04_clock_semantics.py --output <全新审计目录>
python3 -m unittest test_v04_clock_semantics -v
python3 research/sta-velocity-control/scripts/verify_v04_protocol04.py --output <全新回归目录>
```

本次对应`clock_semantics_audit01`、`clock_semantics_verify01`；均退出0。新增12项Python独立运行通过，完整回归 **109个不同C++、234个Python（222+12）通过**，SITL/测试及DONT_RUN Gazebo构建退出0，两组各2048步原PID回归保持。重复执行不累计；未新增或运行完整EKF/selector异步调度测试，也未重跑11项IMU转换链专项或MATLAB/Octave。本次没有新开发测试失败。

原series02不完整飞行重分析按预期退出1；series07原严格时间检查在审计中仍拒绝，不改变历史accepted。当前构建基于起点7cad95b02e加未提交研究工具，不是新飞行固件授权；原8df90c62a1的日志/固件指纹不改。

收尾完整性检查首次因未带旧M00依赖目录而在导入时出现`ModuleNotFoundError: pymavlink`，退出1，尚未执行指纹检查。补齐上列PYTHONPATH后重跑退出0：14份原输入、19个源码、65份外部工件、完整审计JSON及EEPROM指纹一致，无活动模拟器。这是检查命令的环境错误，不计入功能测试数或飞行次数。

新65份外部工件已指纹归档，索引SHA `9c1c12b559c928bf64e53c437ed269ace4461f27ef58d98de891794815bb6e8c`。series07的41份原始及263份前次验证工件、series06的42份原始工件复核不变；protocol08的253执行资产全部一致。参数未设置/保存，EEPROM仍为`06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`。

## 6. 停止点

仅新增独立只读审计、12项反例测试、报告/证据和入口，未改src/msg/模型、既有验收脚本或冻结协议。按明确范围审查提交，完整SHA写外部实时进度表；不push。

**新飞行0、新种子0、新预算0；原1尝试/0通过/余5停止及累计7尝试/0通过、ESTA0不变。** 建议下一步获准后仅实现离线的姿态双时间语义与歧义处理，做七批回放及负例回归；其后另冻新批次并申请飞行。不能直接续跑或先删检查换通过，不进入V05。
