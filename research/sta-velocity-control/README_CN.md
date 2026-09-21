# 速度环 STA 研究

分支：research/sta-velocity-control；规划起点866bba6e0d200d7a5137146c2a67a1a751e01233。

V00已通过：保留原起飞逻辑，修订测试与world核验后，新授权批次3/3起降、60秒悬停和日志验收通过；37个C++及最终31个Python用例通过。历史失败保留。尚未执行V01、未实现新速度控制器。默认研究范围为XY速度PID/ESTA比较，Z速度PID、原位置P/姿态/rate PID保持；Z、Proper-ISTA与双层组合须单独授权。

- [初始TODO快照](plan/v1/VELOCITY_STA_TODO_CN.md)
- [初始阶段提示词](plan/v1/VELOCITY_STA_PROMPTS_CN.md)
- [初始状态快照](plan/v1/VELOCITY_STA_STATUS_CN.md)：只是2026-09-19编制状态，后续不可据此推断实际进度。
- [外部实时进度表](</home/yr/Desktop/codev doc/plan/VELOCITY_STA_STATUS_CN.md>)
- [V00报告（基线通过）](reports/V00.md)
- [V00恢复批次02：三轮指标、覆盖与勘误](reports/V00_RESUME02.md)
- [V00恢复批次：测试已修订，启动预检失败](reports/V00_RESUME01.md)
- [V00接口审计、Takeoff勘误与恢复条件](v00/INTERFACE_AUDIT_CN.md)

V00核对后将计划和基线工具纳入明确范围提交。后续reports/、scripts/、configs/、evidence/按阶段创建，不预填成功报告。plan/v1为初始快照，修订另存版本，已执行依据以对应提交协议/阶段报告为准。大型日志放仓库外VELOCITY-STA实验目录。

本阶段保留控制数学，只修订测试、增加高频日志话题及研究工具/文档/小型证据；不修改旧sim_scripts，不push。V00前置已满足，下一步V01仍须用户授权，不自动开始。
