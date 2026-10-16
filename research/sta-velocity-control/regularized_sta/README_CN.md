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

实时进度在 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_REGULARIZED_STATUS_CN.md。
阶段按R00→R01→R02→R03四门→R04→R05；每阶段验收/提交/push后继续，不以性能必须获胜为目标。
旧AX05/V08/V09协议、日志和失败保留；新测试及统计只能用新冻结清单，不能把旧成功拼作新重复。
