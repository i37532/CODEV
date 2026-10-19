# 正则化显式 STA 速度环研究

分支：research/sta-velocity-regularized；从AX05结果0a5796c3ed69d2e415696cf2450fbde74d56e6ea分出。
比较原PID、旧硬sign ESTA、新边界层R-STA；只做Iris SITL，位置P/姿态/rate PID及DIV1保持，不接ISTA。

- [连续执行及阶段push边界](AUTHORIZATION_CN.md)
- [创建时三文档](plan/v1/VELOCITY_STA_REGULARIZED_TODO_CN.md)
- [R00入口：最新授权与技术计划](plan/r00_entry/VELOCITY_STA_REGULARIZED_TODO_CN.md)
- [R00报告](../reports/R00.md)
- [数学与来源包审计](r00/math/MATH_AUDIT_CN.md)
- [PX4接口审计](r00/interface/README_CN.md)
- [最终基线、参数、资产及旧日志抽样](r00/evidence/baseline_audit02.json)
- [R01独立内核与离线验证入口](r01/README_CN.md)
- [R02保护、交接、HTE与日志离线验证入口](r02/README_CN.md)
- [R03 revision03：首败停批与部分结果](../reports/R03_REVISION03.md)
- [R03 prearm04：日志预热离线修复](../reports/R03_PREARM04_OFFLINE_REPAIR.md)
- [prearm04离线范围及下一批预算提案](r03_prearm04/OFFLINE_PROTOCOL_CN.md)
- [R03 revision04：X通过、Z数值验收首败与诊断](../reports/R03_REVISION04.md)
- [R03 revision05：Z/XY通过，XYZ日志依赖首败](../reports/R03_REVISION05.md)
- [handoff06：完整依赖隔离与离线回归](../reports/R03_HANDOFF06_OFFLINE_REPAIR.md)

实时进度在 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_REGULARIZED_STATUS_CN.md。
历史总路线为R00→R01→R02→R03四门→R04→R05；当前仅推进R03，验收/提交/push后停止，不自动启动R04/R05，不以性能必须获胜为目标。
当前R03仍needs_revision；保留revision04 A/X完整9轮，新revision05 B/Z、C/XY各完整9轮通过。D/XYZ首轮PID物理起降完成，但完整日志因内嵌handoff/task导入冲突拒绝，八轮未执行。
累计49尝试/48起飞/44接受/5失败。MODE3/AXES7已有源码准入但尚未飞行验收，不能称合格三轴配置。停止记录与隔离离线诊断见revision05报告；不把物理PASS或诊断重放accepted当原轮接受，不续旧批或自动扩预算。总57余8，完整新D9需总58，仅提案未激活。
旧AX05/V08/V09协议、日志和失败保留；新测试及统计只能用新冻结清单，不能把旧成功拼作新重复。
