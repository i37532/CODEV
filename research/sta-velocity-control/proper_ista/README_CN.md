# Proper-ISTA 速度环研究

2026-10-28：**PV00离线审计完成，尚无Proper速度飞行资格；PV01未启动**。新分支 `research/proper-ista-velocity` 从 RI07 结果提交 `8079e17177e3edb597d8da1597081a82cbd6747a` 创建；原 `research/ista-velocity-regularized` 基线分支保持不变。

## 计划入口

实时文件在外部计划目录；本目录 `plan/v1` 保存创建时快照，以后不覆盖。

| 文件 | 实时版本 | 仓库初始快照 |
|---|---|---|
| TODO 与共同规则 | [TODO](</home/yr/Desktop/codev doc/plan/VELOCITY_PROPER_ISTA_TODO_CN.md>) | [v1 TODO](plan/v1/VELOCITY_PROPER_ISTA_TODO_CN.md) |
| 进度表 | [STATUS](</home/yr/Desktop/codev doc/plan/VELOCITY_PROPER_ISTA_STATUS_CN.md>) | [v1 STATUS](plan/v1/VELOCITY_PROPER_ISTA_STATUS_CN.md) |
| 分阶段提示词 | [PROMPTS](</home/yr/Desktop/codev doc/plan/VELOCITY_PROPER_ISTA_PROMPTS_CN.md>) | [v1 PROMPTS](plan/v1/VELOCITY_PROPER_ISTA_PROMPTS_CN.md) |

路线：PV00 审计滞后/噪声/极小数 → PV01 独立速度核 → PV02 保护/HTE/起降与工具 → PV03 X → PV04 Z → PV05 XY/XYZ → PV06 等预算调参与正式协议 → PV07 正式比较。

候选四算法：PID、R-STA、R-ISTA、Proper-ISTA。候选预算280=48开发+72调参验证+160正式，只是待冻结设计，不是本轮飞行授权。Proper新模式编号尚待PV00审计，MODE5只是候选；现有MODE4仍是R-ISTA。原位置P、姿态/rate PID、DIV1和默认PID保留，仅Iris SITL，不实机。

## 已有依据与边界

- [Proper 旧离线探针报告](../reports/PROPER_ISTA_PROBE.md)：理想对象优势不等于带滞后/噪声时优势；没有速度飞行资格。
- [旧探针工具](../proper_ista_probe/README_CN.md)：保持原样，不用新工作覆盖旧结果。
- [RI07 三算法正式报告](../reports/RI07.md)：已完成200次，不含Proper；其数据已见，不是新留出。
- [当前 PID 与 R 系列使用手册](../regularized_ista/USAGE_CN.md)：这是已有工作区文档，未自动纳入本专项提交；不是Proper飞行入口。

PV00交付：[报告](../reports/PV00.md) · [数学/数值契约](pv00/CONTRACT_CN.md) · [离线复现](pv00/README_CN.md)。原144轨迹复现，新69诊断完成；12个极小数拒绝和不可行限幅反例保留。551个C++、46个Python实际检查通过；数值拒绝根因与滞后/噪声适用性分开，尚未修复生产控制律。

本阶段明确范围提交计划快照、专项入口和PV00成果；完整SHA见实时进度表，未push。没有修改生产控制/参数/模型，没有飞行。入口原有两个README、使用手册和图表的未提交状态及指纹保留。下一步须另行启动PV01，不能直接切MODE5起飞。
