# 速度环 STA 研究

分支：research/sta-velocity-control；规划起点866bba6e0d200d7a5137146c2a67a1a751e01233。

V00已执行审计、构建及离线测试，但必需Takeoff测试失败，状态为failed/needs_revision；飞行0次，V01未准入。未实现新速度控制器。默认研究范围为XY速度PID/ESTA比较，Z速度PID、原位置P/姿态/rate PID保持；Z、Proper-ISTA与双层组合须单独授权。

- [初始TODO快照](plan/v1/VELOCITY_STA_TODO_CN.md)
- [初始阶段提示词](plan/v1/VELOCITY_STA_PROMPTS_CN.md)
- [初始状态快照](plan/v1/VELOCITY_STA_STATUS_CN.md)：只是2026-09-19编制状态，后续不可据此推断实际进度。
- [外部实时进度表](</home/yr/Desktop/codev doc/plan/VELOCITY_STA_STATUS_CN.md>)
- [V00报告（未通过）](reports/V00.md)
- [V00接口审计、Takeoff勘误与恢复条件](v00/INTERFACE_AUDIT_CN.md)

V00核对后将计划和基线工具纳入明确范围提交。后续reports/、scripts/、configs/、evidence/按阶段创建，不预填成功报告。plan/v1为初始快照，修订另存版本，已执行依据以对应提交协议/阶段报告为准。大型日志放仓库外VELOCITY-STA实验目录。

本阶段只提交审计工具/文档/小型证据；不修改research/sta-rate-control及旧sim_scripts，不push。先解决Takeoff源码与测试契约不一致，再继续V00；不能直接开始V01。
