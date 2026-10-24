# R-ISTA 速度环专项

## 当前状态（2026-10-24）

RI03 X 与修复后的 **RI04 Z 开发门已通过，仅 Iris SITL**。RI04 revision01 新9轮全部接受，9独立回放、6对78项风险检查通过；旧3轮（含1失败）原样保留，总历史12次，无补飞或调参。MODE4仍仅允许AXES1/4，默认PID；未push、未执行RI05或旧R04/R05、不实机。

- [RI04 revision01 验收报告](../reports/RI04_REVISION01.md)
- [新九轮协议与复现入口](ri04_revision01/README_CN.md)
- [旧失败报告（保留原判）](../reports/RI04.md)
- [HTE离线修复](../reports/RI04_HTE_FIX.md)
- [RI03 X 验收](../reports/RI03.md)

以下RI02及创建时“关闭准入/0飞行”等为历史时点说明，不覆盖本条当前结论。

**RI02 保护/模块/日志/工具离线验收通过，MODE4生产准入仍关闭**。609项C++、354项Python（348工具＋6独立参考）、SITL构建和36份历史完整日志回放通过。本轮不飞行、不push、不自动RI03。

- [RI02 报告（保护、交接与日志限制）](../reports/RI02.md)
- [RI02 工具、证据及复现](ri02/README_CN.md)
- [RI02 执行入口三文档快照](plan/ri02_entry/VELOCITY_RISTA_TODO_CN.md)

- [RI01 报告（含数值域停止及不可行反例）](../reports/RI01.md)
- [RI01 工具、证据及复现](ri01/README_CN.md)
- [RI01 执行入口三文档快照](plan/ri01_entry/VELOCITY_RISTA_TODO_CN.md)

- [RI00 报告](../reports/RI00.md)
- [公式与最小接口冻结](ri00/MATH_INTERFACE_CN.md)
- [离线探针、证据及复现](ri00/README_CN.md)
- [RI00 执行入口三文档快照](plan/ri00_entry/VELOCITY_RISTA_TODO_CN.md)

- 分支：`research/ista-velocity-regularized`。
- 创建基线：`a286e40ec8bfbb0500b1c24add18c1a98b908778`（已验收R03的结果提交，不是新R-ISTA飞行源码）。
- 来源：`/home/yr/Desktop/STA-ISTA-MATLAB-PX4/` 的补偿预测＋边界层隐式ISTA；不是原硬sign ISTA或旧Proper-ISTA的同名替代。
- 新比较组只有 **PID、R-STA、R-ISTA**。旧ESTA代码/历史只读保留并做必要离线回归，不加入新实验矩阵。
- 原R04/R05暂停；后续由RI06/RI07重新冻结三算法调参/正式协议，不直接运行旧含ESTA清单。只限Iris SITL，原位置P/姿态/rate PID、DIV1保持，不实机。

## 计划入口

仓库创建时快照（后续不覆盖）：

- [TODO与共同规则](plan/v1/VELOCITY_RISTA_TODO_CN.md)
- [创建时进度表](plan/v1/VELOCITY_RISTA_STATUS_CN.md)
- [可逐段复制的提示词](plan/v1/VELOCITY_RISTA_PROMPTS_CN.md)

外部实时版本：

- [TODO](</home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md>)
- [进度表](</home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_STATUS_CN.md>)
- [提示词](</home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_PROMPTS_CN.md>)

路线：RI00审计→RI01内核→RI02保护/日志离线→RI03 X→RI04 Z→RI05 XY/XYZ→RI06公平调参→RI07正式比较。

候选新预算：36开发＋54训练验证＋200正式＝290；本轮实际起飞授权与新飞行为0。阶段门/清单/种子/源码需事先冻结；原R03失败/日志和接受数据不填补本专项样本。下一步仅建议另行启动RI03，先只开放X并冻结准确协议/源码与新固件身份；本轮不自动执行、登记种子或push。

创建时三文档/入口改动按用户明确授权一并纳入RI00提交，plan/v1保持原样。原[R03最终报告](../reports/R03_ACCEPTANCE_CN.md)及[结果包](../regularized_sta/r03_results11/README_CN.md)保留，不改判、不删除。完整提交SHA见外部进度表，或以Git查询相应阶段报告的提交。
