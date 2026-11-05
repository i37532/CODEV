# 速度环 R-ISTA 专项：分阶段提示词

2026-10-23，v1。配套：`VELOCITY_RISTA_TODO_CN.md`、`VELOCITY_RISTA_STATUS_CN.md`。本次只建立分支/计划，不运行下列任务；每个代码块可单独复制，阶段通过后才启动下一段。

仓库 `/home/yr/Desktop/Codev-autopilot`，新分支 `research/ista-velocity-regularized`，初始基线 `a286e40ec8bfbb0500b1c24add18c1a98b908778`。后续实际HEAD按每阶段现场核对，不反复强行回退到创建基线。

新矩阵只含PID、R-STA、R-ISTA；旧ESTA仅保留代码/历史/离线回归。原R04/R05暂停，其后续职责改由RI06/RI07承担新协议；不得直接启动旧含ESTA清单。以下候选预算不是本轮起飞授权，也不继承旧连续执行/push许可。

## RI00 — 先审计来源、公式、接口与参数

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md 的 RI00。
完整阅读本专项三文档、共同规则和阅读路线，核对 /home/yr/Desktop/Codev-autopilot 位于 research/ista-velocity-regularized，记录HEAD、工作区、递归子模块。保留本轮未提交的计划/入口文档及用户改动，不回退或清理；本阶段明确纳入新三文档plan/v1和暂停旧R04/R05的仓库入口改动，不覆盖旧冻结快照。
确认R03最终验收及源码/固件版本限制；阅读R00/R01/R02、R03_ACCEPTANCE_CN、revision11/position11与旧日志/保护经验。完整核对 /home/yr/Desktop/STA-ISTA-MATLAB-PX4 的补偿ISTA、通用隐式核、MATLAB包装、C++、参数、模型、来源与测试，保存原始指纹。
统一包内e=v_sp-v与PX4的s=v-v_sp、a/nu单位和NED方向；逐式核对补偿输入平移、p隐式关系、nu候选进入当前输出、边界/更新顺序。区分原ISTA、Proper-ISTA和本次R-ISTA，不继承未经核实的论文保证。用独立探针审计理想恒定/斜坡扰动、非零nu、实际8/12ms与滞后/约束限制，不能把保存CSV称本次MATLAB重跑。
审计候选MODE4/参数/日志冲突、HTE、Z/XYZ seed、保护与同sample重算，冻结最小接口和首个离线候选来源；不直接加载源包高增益，不调飞行参数。新实验仅PID/R-STA/R-ISTA，原位置P、姿态/rate PID及DIV1保持。
只做离线审计/独立探针，不修改生产控制律、参数、模型或准入，不飞行、不登记试飞。写research/sta-velocity-control/reports/RI00.md，记录真实命令/数量/退出码/未执行项；审查明确文件提交，更新外部进度完整SHA。不push、不执行RI01或旧R04/R05。
```

## RI01 — R-ISTA 独立内核，暂不接执行器

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md 的 RI01。
完整阅读本专项三文档/共同规则和RI00验收，核对 /home/yr/Desktop/Codev-autopilot 的 research/ista-velocity-regularized 分支、HEAD、工作区与子模块，确认前置通过，不清理已有改动。
按RI00固定的补偿正则化隐式关系实现独立C++14速度核，s=v-v_sp，输出只含m/s²纠偏；不套rate的g、不除质量、不重复FF。明确p与nu_candidate决定理想输出，再由独立commit改变状态；三轴隔离、reset、owner/轴/配置与reset代次/密封候选校验。
测试层内/层外、精确±分支边界及nextafter邻点、正负/零/非零nu、无效dt/参数/NaN/Inf、求根相减和中间上溢/下溢、跨实例/跨轴/重复/陈旧/篡改候选。用独立double单调隐式求根及残差，不复制同一解析式自证；再和来源MATLAB fixture核对，能实际运行MATLAB才称重跑通过。
独立对象覆盖正负/零恒定扰动、斜坡扰动、变化目标/非零FF、非零nu和实际sample周期；固定周期理论与变周期/限幅/噪声/姿态电机滞后结果分列。保护后输出不当严格隐式解，结论不符预期如实修订。
回归PID/R-STA及旧ESTA兼容、适用rate内核，构建SITL并证明新核无可生效执行器路径。仅Iris SITL工程的离线工作，不飞行、不改默认PID/上游/模型。
写reports/RI01.md，记录真实非零测试/命令/退出码/失败/未执行项；审查明确范围提交并更新进度完整SHA。不push、不执行RI02或旧R04/R05。
```

## RI02 — 保护、起降交接、日志与工具，先离线

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md 的 RI02。
完整阅读三文档/共同规则和RI00/RI01、R02、R03最终日志链报告；核对 /home/yr/Desktop/Codev-autopilot 的 research/ista-velocity-regularized、HEAD、工作区、子模块，确认前置通过。
把经审计的新模式/配置/requested/effective/pending/reject、参数代次/armed暂存取消/disarm生效/重启保存接线，但生产准入仍关闭。MODE0/1/2/3语义不变，默认PID；新实验不含旧ESTA统计组。
专门定义R-ISTA理想p/a/nu_candidate与保护后的输出/nu关系，不照搬R-STA旧nu输出及冻结后重构。测试饱和方向/反馈有效性/脱离限幅、水平矢量与Z优先、一次FF、HTE和Z/XYZ seed，保护后不声称满足原隐式方程；三轴整体有效才原子提交。
覆盖地面/ramp/假离地/取消/弹跳/超时、EKF各reset、半组NaN/纯加速度、无效恢复/退出重入、故障/termination、同sample二次update、跨起飞reset、末轴失败不部分提交。保持原位置P、姿态/rate PID、DIV1和现有起降/模型/估计器，不额外引入起飞管理。
新增所需诊断并验证ULog实际格式长度/生成/注册/队列，区分双时钟、真实更新、候选/应用/发布输出。实现独立regularized_ista工具默认dry-run，完整参数备份恢复，复用R03最终相对预热/增量读取/白名单/同刻组/完整边界reset/落地尾窗链；错模式/轴/内环/时间/缺样/未接管负例，历史日志全链回放不改判，不放宽数值规则。
PID和R-STA各至少两组2048步逐样本回归，旧ESTA只离线防退化；实际非零PositionControl/ControlMath/Takeoff/RateControl、模块/参数/分析测试和SITL构建。证明新模式仍不可接管；本阶段零飞行。
写reports/RI02.md、记录实际数量/命令/退出码/失败/未执行项，审查明确提交并更新完整SHA。不push、不执行RI03或旧R04/R05。
```

## RI03 — R-ISTA X 单轴开发验证

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md 的 RI03。
完整读三文档/共同规则、RI00–RI02验收和R03最终任务/阈值证据，核对 /home/yr/Desktop/Codev-autopilot 的 research/ista-velocity-regularized 分支、HEAD、工作区、子模块。只在Iris SITL执行，本阶段候选上限9次，不继承旧自动扩预算或push授权。
仅开放经审计新模式AXES1；X是本地NED北向，不是roll。Y/Z速度PID、原位置P/姿态/rate PID、MPC_VC_DIV=MC_RTC_DIV=1、旧起飞管理关闭，其他新掩码拒绝。合法XY目标、唯一发布者、一次FF不变。
先合成方向、真实sample周期与内环电机滞后独立模型、模式/重启/armed修改/disarm/reset/故障/termination和完整接线回归。冻结一组共同来源参数、小幅零净位移X激励、定高约2.5m/固定yaw/起降/主半窗、原安全/非命令轴/日志数值阈值及来源。
全历史查重新种子并登记：PID/R-STA/R-ISTA各3个配对开发轮，共9，PID先行，准确顺序和停止/缺失规则先固定。先提交协议/源码/模型/分析器/参数指纹，在同门干净源码取得真实资格后沿用项目启动器执行。不要飞旧ESTA，不拿历史R03成功补样本。
首个安全或必需有效性失败立即停批，不补飞/换种子/调参/扩预算/改门槛。解码真实模式、X误差、Y/Z非命令轴、位置/高度/yaw、p/理想与应用nu、输出/限制/HTE/接管/时间；9接受、9独立回放、6对PID开发风险检查全部通过才验收，性能不必赢。
写reports/RI03.md，保留所有失败/未执行/指纹与参数恢复，记录真实非零测试、命令及退出码；审查单独结果提交，更新协议/源码与结果完整SHA。不push、不执行RI04或原R04/R05。
```

## RI04 — R-ISTA Z 单轴开发验证

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md 的 RI04。
完整读三文档/共同规则、RI03验收、RI02保护与既有Z/起降报告；核对 /home/yr/Desktop/Codev-autopilot 的 research/ista-velocity-regularized、HEAD、工作区、递归子模块，确认X门通过。
新开放AXES4，保留已验收X，其他新掩码拒绝；XY速度PID、原位置P/姿态/rate PID、两个DIV1、旧实验起飞管理关闭。先离线复跑X，重点验证NED Z方向、独立nu、地面/ramp到Z有界接管、HTE、垂直推力优先、落地尾窗和跨起飞reset；不改land detector/模型/上游。
冻结R03式XY保持、小幅平滑升降回原高度、唯一目标/一次FF、主半窗及全部安全/非命令轴/日志门槛。沿用固定参数来源，不抄源包高增益。PID/R-STA/R-ISTA各3新配对种子，共9次，全历史查重，PID先行准确顺序/预算先提交。
同门干净源码/资格后用项目Gazebo Iris启动器执行；首个安全或必需有效性失败停批，不补飞/调参/放宽阈值。任务Z目标跟踪与相对2.5m高度偏离分别报告，分析XY/yaw、p/候选和应用状态、限制/HTE/输出/时序。每轮参数精确恢复；9接受/9独立回放/6对PID风险检查通过才验收。
写reports/RI04.md，实际非零测试/命令/退出码/失败/缺失如实记录，审查单独结果提交并更新两个完整SHA。不push、不执行RI05或旧R04/R05，不实机。
```

## RI05 — R-ISTA XY、XYZ 顺序验收

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md 的 RI05。
完整读三文档/共同规则、RI03/RI04验收及R03最终XYZ/日志链，核对 /home/yr/Desktop/Codev-autopilot 的 research/ista-velocity-regularized、HEAD、工作区、子模块。严格A→B，前门不合格不得扩大。
A：开放新AXES3，复跑X/Y正负及固定yaw低速水平8字；Z速度PID。B仅A通过后开放AXES7，水平8字叠加既有小幅平滑升降，检查Z限幅对XY、三轴nu隔离/原子提交、HTE/起降有界接管。XYZ正常运行只算所选算法，不用闲置PID做正常输出。
保持原位置P/姿态/rate PID、DIV1、旧起飞管理关闭、一次FF和合法XY；回归新1/4/3/7、PID/R-STA、保存重启、armed修改与disarm切换、故障/termination、重新解锁reset。2/5/6仍不开放。
每门PID/R-STA/R-ISTA各3个新配对种子=9，合计18；参数跨门固定，不飞旧ESTA。每门先离线模型/接线和实际非零测试，再准确冻结任务/阈值/种子/顺序/有限预算/资产并提交，干净源码取得资格后沿用项目Iris启动器执行。
首个安全/必需有效性失败停批，不补飞/换种子/调参/扩预算或放宽规则。每门9接受、9独立回放、6对PID风险检查；逐轴/位置/高度/yaw、p/nu/限制、输出/接管/真实模式/覆盖/时序与TV如实报告，版本不同分别披露，不拼旧成功数据。
写reports/RI05.md分列A/B，冻结合格XYZ完整配置及局限；保留原始ULog/指纹/失败/缺失、参数恢复，审查明确结果提交并更新完整SHA。不push、不执行RI06或旧R04/R05，不分频、不实机。
```

## RI06 — 三算法公平调参、冻结新正式协议

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md 的 RI06（修订后R04的职责，不运行旧R04清单）。
完整读本专项三文档/共同规则、RI05、原R03、V08/AX05相关参数与统计经验；核对 /home/yr/Desktop/Codev-autopilot 的 research/ista-velocity-regularized、HEAD、工作区、子模块，确认XYZ已通过。所有旧数据均已见开发知识，不是新留出。
只比较PID/R-STA/R-ISTA，XYZ速度环；原位置P、姿态/rate PID、DIV1、保护/限制/合格模型/软着陆链固定。旧ESTA不进入新矩阵，仅保持离线兼容。
先提交等额训练协议：每算法3候选×H/V两场景×2新训练种子=12，共36；训练选定各1候选，再每算法H/V×3独立验证种子=6，共18，总54。候选范围/生成/epsilon自由度、目标权重、失败惩罚、并列/无合格候选/早停、准确顺序与种子登记先固定。验证不反复换候选，不单给落后算法追加机会，披露历史额外开发预算。
A组保留共同安全有效域内同lambda/epsilon/限制/保护的R-STA与R-ISTA，说明两者差异还含补偿预测，不称单纯Euler离散化效应；B组各自等预算选参。A固定配置与B优化配置分离，不把调优参数冒充只改形式。
正式候选A=2算法×H/V×20新配对块=80，B=3算法×H/V×20新配对块=120，总200。训练/验证/正式A/正式B种子隔离，同组跨任务保留块相关；H为固定yaw水平8字，V叠加平滑小升降。用开发方差说明n与精度限制，正式前冻准确清单，不新增扰动/质量/分频。
冻结逐轴时间加权RMSE、J、Z/非命令轴、位置/高度/yaw、接受率/限制、TV/频谱/成本口径、主半窗、失败与日志/缺失处理、8个主比较的配对CI/多重比较及重采样种子次数、最小实用差。不得要求R-ISTA必胜或看正式数据追加样本。
仅执行已冻结54预算内训练/独立验证，首个安全或必需有效性失败停批并保存，不补飞。通过后冻结正式源码/固件/参数/模型/world/插件/分析器/manifest，outcomes全unattempted。本阶段不运行正式留出。
写reports/RI06.md，记录真实测试/命令/退出码/实际次数/失败/缺失和下一阶段准确预算；审查明确提交、更新进度完整SHA。不push、不执行RI07或旧R05，不实机。
```

## RI07 — 新正式实验与报告

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md 的 RI07（修订后R05的职责，不运行旧含ESTA清单）。
完整阅读三文档/共同规则、RI06验收和最终正式协议，核对 /home/yr/Desktop/Codev-autopilot 的 research/ista-velocity-regularized、干净冻结源码/固件/工作区/子模块/模型/参数/分析器指纹。本次只执行RI06准确清单，候选200；不扩大V09、旧320消融、分频、ISTA其他变体或实机。
A为R-STA/R-ISTA同参数结构比较，B为PID/R-STA/R-ISTA公平调参后比较，分别按冻结任务门/种子块/顺序执行，不混参数和源码。原位置P/姿态/rate PID、DIV1、保护/模型保持；每轮重启、相对日志预热、备份恢复，核实真实模式/轴/接管/目标/更新序列。
首个安全或必需有效性失败停批，保留所有尝试/无效/未起飞/未执行，不自动补飞、改参数/门槛、换种子或扩样。科学指标不要求新算法胜出，失败不填0，不挑有利配对子集。
真实解码全部ULog、独立回放/指纹与统计复算；按预注册时间窗、逐轴/J、配对块/CI/多重比较和缺失规则分析。报告位置/高度/yaw、候选与应用nu/输出、限制/接受率、真实更新TV、共同带宽及原生谱、宿主成本和实际n，说明接受条件化偏差与随机源限制。
大日志外置，仓库存参数/路径/SHA-256索引、metrics/图表摘要与复现入口。写reports/RI07.md和简明中文总结，明确预算偏离/未完成项，不足清单不能称完整正式矩阵通过；不把保护后结果当严格隐式理论，也不宣称实机结论。
记录真实命令/非零测试/退出码、审查明确范围结果提交、更新完整SHA后停止。不push、不自动其他阶段、不硬件部署。
```
