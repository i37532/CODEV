# PX4 速度环研究进度表

更新时间：2026-09-19。规划版本：v1。
仓库：/home/yr/Desktop/Codev-autopilot
分支：research/sta-velocity-control
规划时HEAD：866bba6e0d200d7a5137146c2a67a1a751e01233

[TODO及共同规则](</home/yr/Desktop/codev doc/plan/VELOCITY_STA_TODO_CN.md>)｜[阶段提示词](</home/yr/Desktop/codev doc/plan/VELOCITY_STA_PROMPTS_CN.md>)。

## 当前状态

- 分支已建立并切换，原角速度研究分支保留。
- 本次仅创建计划/提示词/进度表及仓库初始快照；未修改控制代码、参数或旧研究记录。
- 速度研究构建/单测/飞行均未执行，V00不算通过；没有新的验收报告或提交SHA，不push。
- 主线：位置P保留、速度先X再XY ESTA、Z速度PID、姿态和角速度PID；未批准Z/Proper-ISTA/双层组合执行。
- 旧I05剩余17轮继续保持未执行，不属于新速度研究任务；旧数据只作经验，不能算新速度样本。

## 里程碑

| ID | 功能 | 状态 | 协议/源码SHA | 结果SHA | 实际尝试/接受 | 报告 |
|---|---|---|---|---|---|---|
| V00 | 审计与原速度PID基线 | pending | — | — | 0/0 | 未生成 |
| V01 | 选择框架/PID等价 | pending | — | — | 0/0 | 未生成 |
| V02 | ESTA速度内核 | pending | — | — | 0/0（计划离线） | 未生成 |
| V03 | 保护/日志/分析器 | pending | — | — | 0/0 | 未生成 |
| V04 | ESTA X | pending | — | — | 0/0 | 未生成 |
| V05 | ESTA XY | pending | — | — | 0/0 | 未生成 |
| V06 | 名义任务/脚本 | pending | — | — | 0/0 | 未生成 |
| V07 | 速度分频/耗时 | optional_pending | — | — | 0/0 | 未生成 |
| V08 | 等预算训练/正式冻结 | pending | — | — | 0/0 | 未生成 |
| V09 | 正式留出 | pending | — | — | 0/0 | 未生成 |
| E01 | Z/XYZ | awaiting_scope_approval | — | — | 0/0 | 未生成 |
| E02 | Proper-ISTA速度版本 | awaiting_scope_approval | — | — | 0/0 | 未生成 |
| E03 | 内外环2×2组合 | awaiting_scope_approval | — | — | 0/0 | 未生成 |

状态：pending、in_progress、passed、failed、needs_revision、blocked；可选阶段另用optional_pending/awaiting_scope_approval/skipped_by_scope。blocked必须说明缺失依赖；未满足必需验收不能写passed。

## 阶段记录模板

每完成一阶段追加，不覆盖历史失败：

- 阶段/日期/状态：
- 开始分支/HEAD/工作区：
- 实际修改范围：
- 预注册协议/参数/种子/任务预算：
- 构建/单测命令、退出码、实际用例数：
- 实际计划数/尝试数/完成数/接受数/未运行数：
- 失败、缺失及协议偏离：
- 外部数据路径、ULog及汇总SHA-256：
- 对照参数与实际速度/角速度模式：
- 协议/源码提交完整SHA：
- 结果提交完整SHA及提交后检查：
- 报告链接与未执行项：
- 下一阶段是否准入：通过不表示自动授权。

## 规划检查记录

2026-09-19：核实新分支和HEAD，阅读原里程碑及ISTA后续经验，检查PositionControl、模块Run/HTE/Takeoff/failsafe及测试注册。计划文档与链接/快照一致性校验不属于飞控单测。
新目录尚无执行脚本；所有拟议参数和日志仅是设计草案，不可直接当已实现命令使用。
