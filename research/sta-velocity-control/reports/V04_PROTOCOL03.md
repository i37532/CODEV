# V04 protocol03：执行协议与实现

日期：2026-09-23。起点：a367c7afa561e5f3829f39ad6092b51e63afd2bf，research/sta-velocity-control，主仓库/递归子模块干净。

用户批准 protocol02 新高度任务后，又明确批准正常计划降落 Gate=2 分类修订。本版保留旧计划/失败结论，候选、门槛、种子9201–9203、六次预算不变；不修改生产控制算法或起飞逻辑。

## 实现及审查范围

- 新增隔离运行器、明确高度/命令/入口纯函数、独立分析器及冻结资产工具；旧运行器/分析器不改。
- 原项目launcher、原起飞、唯一导航目标源；一次本地MAVLink高度请求，单独记录ACK及导航读回，三秒稳定后才记hover_start。无外部轨迹/角速度发布者。
- 控制参数和EEPROM全量备份/精确恢复；最大六次、首个必需失败停、配对失败停、禁止自动恢复目录。
- 新分析器继承旧数值和精确下游匹配阈值，额外检查首次失败、输入有效位、真实日志入口、完整激励、真实模式与计划降落退出。原始fault保存不改写。
- logger高频配置只补position_setpoint_triplet、vehicle_command_ack；不改变传感器/控制周期或profile其他位。消息格式仍为1403字节、queue8。
- 有意保留原PID dt夹限、HTE、Takeoff/默认参数与位置/速度/推力数学；verify_v04_repair逐项比较原冻结参考。

## 实际离线验证

第一轮完整验证目录：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/protocol03_verify01`。
`verify_v04_repair.py --output <该目录>`：104个不同C++用例（含两组2048步PID等价）、84项Python、SITL构建和DONT_RUN=1 Gazebo构建，全部退出0。

后续新增运行器故障注入、实际生产激励头文件轨迹和完整离线高度链测试；新protocol03专属测试最终19项退出0（早期dry-run因尚未生成frozen.json失败一次，生成冻结文件后通过；不是飞行失败）。最终全量及提交后重建记录由结果报告补充，不将之前84项冒充最终计数。

提交前最终验证：外部 `protocol03_verify02`，104个不同C++、89项Python（其中19项新协议测试），两项构建、格式检查和diff检查全部退出0。独立生产头文件轨迹由其中1项Python测试实际编译执行，不重复计算为新增gtest。冻结142项资产；递归子模块版本未改变。

测试覆盖：命令单位/ACK来源和时效、坐标及reset、稳定窗口/重复倒退/间断/截止、真Gate/Clock/Controller位、模式退出/重入、disarm清零、首次失败/重算/缺字段、NaN通道、完整窗口/高度目标/日志缺项、六次上限与首失败停及全参数恢复。模拟批次不计实际飞行次数。

MATLAB未运行，本阶段无新内核。实际飞行和最终参数/ULog指纹在独立结果提交记录；本文件不预判V04通过，不进入V05、不push。

入口：[protocol03](../v04/protocol03/README_CN.md)。历史：[protocol02冲突审计](V04_PROTOCOL02_PREFLIGHT.md)、[REPAIR01](V04_REPAIR01.md)、[原V04失败](V04.md)。
