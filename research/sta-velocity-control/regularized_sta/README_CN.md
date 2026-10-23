# 正则化显式 STA 速度环研究

分支：research/sta-velocity-regularized；从AX05结果0a5796c3ed69d2e415696cf2450fbde74d56e6ea分出。
比较原PID、旧硬sign ESTA、新边界层R-STA；只做Iris SITL，位置P/姿态/rate PID及DIV1保持，不接ISTA。

## 最新入口：R03 四门已验收

见 [最终中文报告](../reports/R03_ACCEPTANCE_CN.md)、[阶段入口](../reports/R03.md)和[只读结果复现包](r03_results11/README_CN.md)。X/Z/XY/XYZ 四门各9接受、9独立回放、6配对通过；前三门 revision09、新 XYZ revision11 分别披露源码/固件，不混池。新 D 完整九轮0失败，原始输入未变、参数恢复、无残留仿真。

历史累计97尝试/95起飞指令/87接受/8失败或无效/2诊断，所有旧失败保留；实际设计为四门36接受。R-STA 的 XYZ 跟踪误差较小，但 TV/宿主耗时并非优于 PID。仅开发验收，不是正式统计或实机结论。结果提交后按授权 push；到 R03 停止，不自动 R04/R05。

## 历史入口与检查点（保留原判）

当前入口：[revision11有限XYZ九轮](../reports/R03_REVISION11.md)。原revision09 A/X、B/Z、C/XY各9接受/9独立回放/6配对已通过；revision10 D在第6轮停止，5接受/1失败/3未执行，累计88尝试/86起飞指令/78接受/8失败/2诊断。新D9（总上限97）必须在新的干净源码资格后执行，当前尚未飞行、R03未验收。见[停批原始证据](../reports/R03_REVISION10_STOP.md)、[双时钟检查审计与回归](../reports/R03_POSITION11_OFFLINE.md)和[准确协议](r03_revision11/PROTOCOL_CN.md)。下方旧“当前”段落保留为历史，不再是运行入口。

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
- [revision06：保留前三门，只重做XYZ九轮](../reports/R03_REVISION06.md)
- [revision06预算与持续修订授权](AUTHORIZATION_R03_REVISION06_CN.md)
- [revision06实际3轮停批与原始指纹](../reports/R03_REVISION06_STOP.md)
- [EKF超时的真实时序、证据缺口与范围边界](../reports/R03_EKF_TIMEOUT_AUDIT.md)

实时进度在 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_REGULARIZED_STATUS_CN.md。
历史总路线为R00→R01→R02→R03四门→R04→R05；当前仅推进R03，验收/提交/push后停止，不自动启动R04/R05，不以性能必须获胜为目标。
当前R03仍needs_revision；保留revision04 A/X完整9轮，新revision05 B/Z、C/XY各完整9轮通过。revision06 D/XYZ前2轮PID/RSTA接受，第3轮ESTA在降落期真实EKF切换/参考变化，在线拒绝后停批，剩6未执行，见[停批报告](../reports/R03_REVISION06_STOP.md)。
累计52尝试/51起飞指令/46接受/6失败。MODE3/AXES7已有源码准入但尚未完整飞行验收，不能称合格三轴配置。2026-10-20用户明确授权必要预算调整至R03验收；当前有限总预算58已用52，候选新D9需总61，但尚未激活、未登记新种子。先离线确定真实故障及范围内修复；不调参、放宽规则、直接续旧清单或无界补飞，不把部分接受拼成完整门。
旧AX05/V08/V09协议、日志和失败保留；新测试及统计只能用新冻结清单，不能把旧成功拼作新重复。
