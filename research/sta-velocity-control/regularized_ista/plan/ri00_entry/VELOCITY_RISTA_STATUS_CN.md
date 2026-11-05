# 速度环 R-ISTA 专项：实时进度

更新：2026-10-23。当前状态：**分支与计划已建立，RI00 尚未启动**。

## RI00 执行入口（2026-10-23）

用户已明确仅授权 RI00。入口 HEAD a286e40ec8bfbb0500b1c24add18c1a98b908778，分支 research/ista-velocity-regularized；工作区原有五份计划/入口 Markdown 待提交，保留并纳入本阶段。33 递归子模块版本一致。正在离线审计；新飞行/种子均 0，不修改生产、不 push、不启动后续阶段。下方尚未启动为创建时记录。

## 当前仓库与范围

- 仓库：`/home/yr/Desktop/Codev-autopilot`。
- 分支：`research/ista-velocity-regularized`。
- 创建基线/当前HEAD：`a286e40ec8bfbb0500b1c24add18c1a98b908778`，已验收R03结果；不是新R-ISTA实现或飞行提交。
- 原分支：`research/sta-velocity-regularized`，保持该提交和历史结果；没有删除重建/回退。
- 分支创建前工作区干净，33个递归子模块无增减/版本偏离；当前新增计划/入口文档尚未提交或push，不称“当前工作区干净”。
- 本专项仅PID、R-STA、R-ISTA参与新实验；旧ESTA只保留代码/历史与离线回归。原R04/R05暂停，后续由RI06/RI07另冻三算法协议，旧冻结包只读。
- 本轮仅规划，控制代码/参数/模型/日志实现未变；未构建、未运行算法单测/Matlab/仿真、未登记新种子、未创建实验批。

## 本轮实际核对

1. Git现场核对并从指定完整SHA新建分支；HEAD未改变。没有提交、推送或启动RI00。
2. 阅读当前R03验收、R02保护/日志、旧计划共同规则与R04/R05内容，并核对源包补偿ISTA/通用隐式核/C++接口、参数和验证说明。
3. 在源包运行 `sha256sum --check SHA256SUMS.txt`：**29/29 OK，exit0**。这仅证明包内列出文件完整，不是算法回归/Matlab重跑/PX4适配通过。
4. 当前selector/元数据只到MODE3，MODE2仍拒绝；候选MODE4留RI00全链冲突审计，不在本轮开放。R-STA接口s=v−v_sp；包内e=v_sp−v，转换已列TODO待RI00正式审计。
5. 初次组合只读命令因工作目录下相对报告路径不存在exit2，已改真实路径重新读取；分支创建命令后的名称检索无匹配使组合exit1，随后独立核实新分支创建成功。不把这些检索当算法测试。
6. 收尾文档一致性校验实际exit0：三文档与plan/v1逐字节一致；8个阶段/8段完整提示词；36+54+200=290候选预算；旧三文档暂停入口、33子模块、基线与旧分支HEAD、Markdown链接全部核对；仓库仅5个Markdown文件改动，无控制代码变更。此为文档检查，不是算法测试或任何RI阶段通过。`git diff --check`亦exit0。

## 阶段状态

| 阶段 | 状态 | 新飞行候选 | 实际尝试/起飞/接受 | 源码/结果提交 |
|---|---|---:|---|---|
| 建分支与计划 | 已建立，未提交 | 0 | 0/0/0 | 基线a286e40ec8…，无新提交 |
| RI00 来源/接口审计 | not_started | 0 | 0/0/0 | — |
| RI01 独立内核 | not_started | 0 | 0/0/0 | — |
| RI02 保护与日志离线 | not_started | 0 | 0/0/0 | — |
| RI03 X | not_started | 9 | 0/0/0 | — |
| RI04 Z | not_started | 9 | 0/0/0 | — |
| RI05 A/XY→B/XYZ | not_started/not_started | 9+9 | 0/0/0 | — |
| RI06 公平调参/正式协议 | deferred，待接入合格 | 36+18 | 0/0/0 | — |
| RI07 正式比较 | deferred，待RI06合格 | 80+120 | 0/0/0 | — |
| 原R04/原R05 | paused，旧含ESTA清单不执行 | 不激活 | 本轮0/0/0 | 旧记录不改 |

当前实际飞行授权为0。36+54+200=290只是未来候选总量，不包含也不替代R03历史97次；没有新增批次或重复样本。新种子未分配，所有旧使用/弃用/正式预留必须后续全历史查重。

## 下一步

仅建议明确启动 **RI00**：复制 `VELOCITY_RISTA_PROMPTS_CN.md` 的RI00完整提示词执行；首阶段可明确纳入本轮未提交计划快照和入口文档，保留无关用户改动。本轮到规划停止。

后续每阶段记录完整源码与结果SHA、实际非零测试/退出码、计划/尝试/起飞/接受/缺失、原始ULog指纹、失败和参数恢复；不能在此预填通过。既有R-STA R03通过不代表R-ISTA已接入。

## 文件入口

- TODO：`/home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md`
- 提示词：`/home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_PROMPTS_CN.md`
- 仓库快照：`/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/regularized_ista/plan/v1/`
- 源包：`/home/yr/Desktop/STA-ISTA-MATLAB-PX4/`
- R03结论：`/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/R03_ACCEPTANCE_CN.md`
