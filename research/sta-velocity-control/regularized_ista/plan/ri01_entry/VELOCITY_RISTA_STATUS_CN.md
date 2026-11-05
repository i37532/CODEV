# 速度环 R-ISTA 专项：实时进度

## RI01 执行中（2026-10-24，最新）

仅授权RI01。入口 research/ista-velocity-regularized / e8e38752499c12b9c39bb7dc95da58f27ff029d4，工作区干净，33递归子模块一致；RI00已按用户随后请求push到codev同名分支。正在实现测试目标独立内核并离线验证；MODE4仍拒绝、不改生产准入/参数/模型，0飞行。不push、不进入RI02/旧R04/R05。下方RI00“未push”为当时阶段收尾记录。

更新：2026-10-23。当前状态：**RI00 离线审计通过并提交；工作区干净，未push；RI01 未启动**。

## RI00 完成记录

- 入口 HEAD：a286e40ec8bfbb0500b1c24add18c1a98b908778；33递归子模块匹配且内部干净；原五份计划/入口保留纳入，v1未覆盖，另存ri00_entry。
- 最终证据audit02：2项原包CTest、12项新增Python测试、4896单步核对、90条独立对象轨迹，probe退出0；7980行是已有MATLAB CSV，不是本次MATLAB重跑。六条预定不可行限幅反例明确不收敛，不称跟踪成功。
- 数学：理想恒扰平衡s=0，不再是旧h*d；斜坡仍有epsilon及h相关偏差。HTE/seed/保护不能照搬R-STA，候选事务需加强；未继承Proper论文保证。
- 原包30文件指纹、865仓库与79外部冻结资产重新匹配；MODE4真实selector仍拒绝，生产控制/参数/模型/准入未变。
- 外部证据：/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261023/RI00/audit01、audit02，两者完整保留。
- 报告：/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/RI00.md；公式/接口与小证据在regularized_ista/ri00。
- 实际新尝试/起飞/接受=0/0/0，新种子0；未运行MATLAB、新PX4构建、生产整套回归或Gazebo。未push，未启动RI01/原R04/R05。
- RI00 完整提交 SHA：e8e38752499c12b9c39bb7dc95da58f27ff029d4（49个明确文件，父提交a286e40ec8bfbb0500b1c24add18c1a98b908778）。提交后工作区干净、生产路径差异为空、33子模块内部干净；50个Markdown目标及JSON/脚本语法/证据指纹检查通过。未push。

## RI00 执行入口（2026-10-23）

用户已明确仅授权 RI00。入口 HEAD a286e40ec8bfbb0500b1c24add18c1a98b908778，分支 research/ista-velocity-regularized；工作区原有五份计划/入口 Markdown 保留并纳入本阶段。33 递归子模块版本一致。已完成离线审计；新飞行/种子均0，不修改生产、不push、不启动后续阶段。下方创建时记录仅保留历史。

## 建分支时仓库与范围（历史，非最新状态）

- 仓库：`/home/yr/Desktop/Codev-autopilot`。
- 分支：`research/ista-velocity-regularized`。
- 创建基线/当前HEAD：`a286e40ec8bfbb0500b1c24add18c1a98b908778`，已验收R03结果；不是新R-ISTA实现或飞行提交。
- 原分支：`research/sta-velocity-regularized`，保持该提交和历史结果；没有删除重建/回退。
- 分支创建前工作区干净，33个递归子模块无增减/版本偏离；当前新增计划/入口文档尚未提交或push，不称“当前工作区干净”。
- 本专项仅PID、R-STA、R-ISTA参与新实验；旧ESTA只保留代码/历史与离线回归。原R04/R05暂停，后续由RI06/RI07另冻三算法协议，旧冻结包只读。
- 本轮仅规划，控制代码/参数/模型/日志实现未变；未构建、未运行算法单测/Matlab/仿真、未登记新种子、未创建实验批。

## 建分支时实际核对（历史）

1. Git现场核对并从指定完整SHA新建分支；HEAD未改变。没有提交、推送或启动RI00。
2. 阅读当前R03验收、R02保护/日志、旧计划共同规则与R04/R05内容，并核对源包补偿ISTA/通用隐式核/C++接口、参数和验证说明。
3. 在源包运行 `sha256sum --check SHA256SUMS.txt`：**29/29 OK，exit0**。这仅证明包内列出文件完整，不是算法回归/Matlab重跑/PX4适配通过。
4. 当前selector/元数据只到MODE3，MODE2仍拒绝；候选MODE4留RI00全链冲突审计，不在本轮开放。R-STA接口s=v−v_sp；包内e=v_sp−v，转换已列TODO待RI00正式审计。
5. 初次组合只读命令因工作目录下相对报告路径不存在exit2，已改真实路径重新读取；分支创建命令后的名称检索无匹配使组合exit1，随后独立核实新分支创建成功。不把这些检索当算法测试。
6. 收尾文档一致性校验实际exit0：三文档与plan/v1逐字节一致；8个阶段/8段完整提示词；36+54+200=290候选预算；旧三文档暂停入口、33子模块、基线与旧分支HEAD、Markdown链接全部核对；仓库仅5个Markdown文件改动，无控制代码变更。此为文档检查，不是算法测试或任何RI阶段通过。`git diff --check`亦exit0。

## 阶段状态

| 阶段 | 状态 | 新飞行候选 | 实际尝试/起飞/接受 | 源码/结果提交 |
|---|---|---:|---|---|
| 建分支与计划 | 纳入RI00明确范围提交 | 0 | 0/0/0 | 完整SHA见顶部RI00记录 |
| RI00 来源/接口审计 | passed（仅离线） | 0 | 0/0/0 | 完整SHA见顶部RI00记录 |
| RI01 独立内核 | in_progress，仅离线 | 0 | 0/0/0 | 入口e8e38752499c12b9c39bb7dc95da58f27ff029d4 |
| RI02 保护与日志离线 | not_started | 0 | 0/0/0 | — |
| RI03 X | not_started | 9 | 0/0/0 | — |
| RI04 Z | not_started | 9 | 0/0/0 | — |
| RI05 A/XY→B/XYZ | not_started/not_started | 9+9 | 0/0/0 | — |
| RI06 公平调参/正式协议 | deferred，待接入合格 | 36+18 | 0/0/0 | — |
| RI07 正式比较 | deferred，待RI06合格 | 80+120 | 0/0/0 | — |
| 原R04/原R05 | paused，旧含ESTA清单不执行 | 不激活 | 本轮0/0/0 | 旧记录不改 |

当前实际飞行授权为0。36+54+200=290只是未来候选总量，不包含也不替代R03历史97次；没有新增批次或重复样本。新种子未分配，所有旧使用/弃用/正式预留必须后续全历史查重。

## 下一步

下一步仅建议另行明确启动 **RI01** 独立内核，读取RI00公式/接口冻结与报告。生产保护/HTE/seed及新准入尚未实现，不能直接飞行。本轮完成RI00即停止。

后续每阶段记录完整源码与结果SHA、实际非零测试/退出码、计划/尝试/起飞/接受/缺失、原始ULog指纹、失败和参数恢复；不能在此预填通过。既有R-STA R03通过不代表R-ISTA已接入。

## 文件入口

- TODO：`/home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md`
- 提示词：`/home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_PROMPTS_CN.md`
- 仓库快照：`/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/regularized_ista/plan/v1/`
- 源包：`/home/yr/Desktop/STA-ISTA-MATLAB-PX4/`
- R03结论：`/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/R03_ACCEPTANCE_CN.md`
