# 速度环 STA 研究

分支：research/sta-velocity-control；规划起点866bba6e0d200d7a5137146c2a67a1a751e01233。

V00、V01已通过；V02前置缺口已在用户授权继续后修复，历史失败保留。V03 **in_progress**：离线保护、PID诊断日志及验证已完成，唯一一次PID小速度飞行待执行；不能先写最终通过。默认研究范围为XY速度PID/ESTA比较；Z、Proper-ISTA与双层组合须单独授权。

- [初始TODO快照](plan/v1/VELOCITY_STA_TODO_CN.md)
- [初始阶段提示词](plan/v1/VELOCITY_STA_PROMPTS_CN.md)
- [初始状态快照](plan/v1/VELOCITY_STA_STATUS_CN.md)：只是2026-09-19编制状态，后续不可据此推断实际进度。
- [外部实时进度表](</home/yr/Desktop/codev doc/plan/VELOCITY_STA_STATUS_CN.md>)
- [V00报告（基线通过）](reports/V00.md)
- [V01报告：选择框架、逐样本等价及一次冒烟](reports/V01.md)
- [V02报告：离线 ESTA 速度内核](reports/V02.md)
- [V03：公共保护、日志与一次PID验证](reports/V03.md)
- [V03历史前置审计：失败复现与V02勘误](reports/V03_PREFLIGHT.md)
- [V03冻结协议与日志说明](v03/protocol01/README_CN.md)
- [V00恢复批次02：三轮指标、覆盖与勘误](reports/V00_RESUME02.md)
- [V00恢复批次：测试已修订，启动预检失败](reports/V00_RESUME01.md)
- [V00接口审计、Takeoff勘误与恢复条件](v00/INTERFACE_AUDIT_CN.md)

V00核对后将计划和基线工具纳入明确范围提交。后续reports/、scripts/、configs/、evidence/按阶段创建，不预填成功报告。plan/v1为初始快照，修订另存版本，已执行依据以对应提交协议/阶段报告为准。大型日志放仓库外VELOCITY-STA实验目录。

当前有效速度配置仅MPC_VC_MODE=0/MPC_VC_AXES=0；其他请求显式拒绝，原PID数学和参数更新语义保持。V02历史提交已push；本次V03不push。
