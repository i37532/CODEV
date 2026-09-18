# ISTA 后续研究：逐阶段复制提示词

配套：[TODO、验收规则及进度表](</home/yr/Desktop/codev doc/plan/ISTA_REDESIGN_TODO_CN.md>)。

使用方法：每次只复制一个代码块。全部阶段当前未开始；先 I00，验收后再发下一段。提示词是未来执行入口，本文件创建不代表已经运行测试或授权连续执行全部任务。

## I00 — 先审计原理，复现稳态偏差

```text
请仅执行 /home/yr/Desktop/codev doc/plan/ISTA_REDESIGN_TODO_CN.md 的 I00。
完整阅读该计划、原 STA_MILESTONES_CN.md 全文及共同规则、历史进度表，并读取仓库 M07/M08/M09/M10、ISTA_OPT01、ISTA_OPT02 报告。仓库为 /home/yr/Desktop/Codev-autopilot，核对 research/sta-rate-control 分支、HEAD、工作区和子模块，不回退或清理已有改动。
将新 TODO 和提示词纳入 research/sta-rate-control/ista_redesign 的新计划快照，不覆盖旧快照。核对原 MATLAB、原 ISTA C++、本地算法文档和 Proper Implicit 文献，固定文献版本、公式编号、量纲、状态下标、更新顺序与假设。审计算法总结 §5.6 的 h² 表述，必要时添加可追溯勘误，保留历史结果。
把恒定扰动下原 ISTA 可能存在 s=h*d 的线索变成推导与可运行回归：正负/零扰动、非零初始 nu、h=4/8/16ms、非单位 g，并加入斜坡扰动。用实际 C++ 内核、独立双精度参考和独立对象闭环核对，区分无约束理论与工程约束情形。旧日志的均值/方差/RMSE 分解仅作探索性诊断，不替换原主指标。
本阶段不修改生产控制律、保护或参数默认值，不飞行。结论不符预期时如实修订计划，不能硬推进。写 reports/I00.md，记录真实测试数量、命令、退出码和未执行项；审查 diff，明确范围提交，更新新 TODO 进度表与 SHA。不 push、不执行 I01。
```

## I01 — 新内核，暂不接执行器

```text
请仅执行 /home/yr/Desktop/codev doc/plan/ISTA_REDESIGN_TODO_CN.md 的 I01。
完整阅读新计划、原计划共同规则、进度表和 reports/I00.md，确认 I00 已通过，核对 /home/yr/Desktop/Codev-autopilot 的 research/sta-rate-control 分支、HEAD 和工作区。
按照 I00 固定的 Proper Implicit 文献版本实现独立命名的 C++14 内核。保留原 IstaRateControl、MODE=2 及旧参考数据，复用 s=rate-rate_sp、a/nu 的 rad/s² 单位和 c=a/g 接口，明确候选与提交状态、三轴隔离和 reset。
测试各分支、精确边界/邻点、正负对称、非零 nu、非单位 g、异常 dt/参数、相减损失、下溢/溢出；必要时使用经过推导的数值稳定等价式。用独立双精度隐式残差/求解参考及独立受扰对象闭环核对，固定周期理论与变步长健壮性分开。不得用复制同一解析式的参考自证。
回归 PID、ESTA、原 ISTA，构建 SITL 并确认新内核没有可生效的执行器路径。不开展飞行，未执行 MATLAB 要明确记录。写 reports/I01.md、审查并明确范围提交，记录实际测试数和退出码，更新新 TODO 进度表与 SHA。不 push、不执行 I02。
```

## I02 — 保护和起飞状态管理，先离线验证

```text
请仅执行 /home/yr/Desktop/codev doc/plan/ISTA_REDESIGN_TODO_CN.md 的 I02。
完整阅读新计划、原共同规则、进度表、I00/I01 和 ISTA_OPT02 报告，核对 /home/yr/Desktop/Codev-autopilot 的研究分支和工作区，确认前置验收。
审计新内核与公共保护的映射，不能照搬旧算法的 nu 修改/输出重算关系。独立记录理想候选与限幅/冻结后的 applied 输出和状态，测试饱和方向、反馈有效性、状态限制、时间异常和故障 latch，不把受保护输出称为严格隐式解。
实现默认关闭、可单独消融的实验起飞 nu 管理，仅使用机载可用估计/状态信号，不使用 Gazebo 真值，不修改全局 land detector，不改变 PID 原有语义。离线覆盖解锁未起飞、离地、估计跳变、假离地、起飞取消、落地弹跳、空中误判、超时、重新解锁、armed 参数修改和 disarm 生效，说明迟滞、释放条件及避免永久冻结的方法。
新保护关闭时回归旧行为，新内核仍不得驱动执行器。必要日志变更须检查 ULog 格式长度和消息生成。若需上游修改或另一种 conditioned 算法，停止并说明新增范围，不自行夹带实现。
本阶段不飞行。写 reports/I02.md，记录非零实际测试数量、退出码和 I03 消融因素；审查并提交明确范围改动，更新新 TODO 进度表与 SHA。不 push、不执行 I03。
```

## I03 — 单独验证起飞保护的作用

```text
请仅执行 /home/yr/Desktop/codev doc/plan/ISTA_REDESIGN_TODO_CN.md 的 I03。
完整阅读新计划、原共同规则、进度表及 I02、ISTA_OPT02 报告，确认前置测试通过，核对 /home/yr/Desktop/Codev-autopilot 研究分支和工作区。
先冻结并提交隔离消融协议：ESTA/原 ISTA 分别比较旧保护与新增起飞 nu 管理，其他参数、场景、阈值不变。每个安全配置计划至少 3 个配对开发种子，运行前确定准确清单、顺序、预算和时间窗。核查种子使用历史；已知危险高增益配置只离线分析，不为凑矩阵强行飞行。
在干净协议/源码提交上沿用项目 Gazebo Iris 启动器执行，Proper-ISTA 不得驱动执行器。记录地面阶段 nu、离地时 nu、倾角、高度、振荡、起降及误冻结；实际解码 ULog，检查模式、时序和丢样，Gazebo 真值仅用于离线诊断。
不要求新保护必然改善；依据预设门槛选择后续共同保护基准，可保留原保护，若均不安全则停止。保留所有失败，不自动补飞、扩大预算或放宽门槛。
写 reports/I03.md，区分协议/源码与结果提交，审查后提交结果，更新新 TODO 进度表及两个 SHA。缺失依赖标 blocked，不伪称通过。不 push、不执行 I04。
```

## I04 — 新算法只接 roll

```text
请仅执行 /home/yr/Desktop/codev doc/plan/ISTA_REDESIGN_TODO_CN.md 的 I04。
完整阅读新计划、原共同规则、进度表、I01–I03 报告，确认保护基准已固定，核对 /home/yr/Desktop/Codev-autopilot 研究分支和工作区。
为 Proper-ISTA 分配经核对的独立模式标识，保留 MODE=0/1/2 含义，同步参数、dispatcher、requested/effective、日志、解析器及脚本。本阶段新算法只开放 AXES=1，3/7 明确拒绝；pitch/yaw 保持 PID，默认 PID 不变。
核验实际模型和已标定 g；先合成输入测试方向、nu 提交和保护后输出，回归模式切换、重启保存、armed 修改、disarm/reset、故障及 termination，不继承陈旧状态。
明确 setpoint 唯一发布者、推力及其余轴来源。冻结小幅零净转角激励、起降悬停任务、阈值和种子，先提交协议/源码，再在干净提交上沿用项目启动器运行 Iris SITL：新算法与固定 ESTA 同场景各 3 次，并做 PID 冒烟和原 ISTA 回归。解码 ULog，核对真实模式、更新序列、理想/应用输出、nu、饱和、误差及非命令轴。
保留失败，达到预设门槛才验收。写 reports/I04.md、审查并提交结果，更新新 TODO 进度表及 SHA。不 push、不扩展 pitch、不执行 I05、不实机测试。
```

## I05 — 双轴、三轴和分频，按子门依次验证

```text
请仅执行 /home/yr/Desktop/codev doc/plan/ISTA_REDESIGN_TODO_CN.md 的 I05。
完整阅读新计划、原共同规则、进度表、I04 与 M09 报告，确认 roll 已通过，核对 /home/yr/Desktop/Codev-autopilot 研究分支和工作区。
严格按 A→B→C 子门推进，前一步不通过不得扩大范围。A：AXES=3，pitch 正负和 R/P 同步小幅激励，复跑 roll，yaw 继续 PID。B：先 yaw 小激励，再 AXES=7，保留姿态环坐标变换，检查 yaw 饱和对 R/P 的影响。每个新掩码与固定 ESTA 同场景各 3 次。
回归三轴状态隔离、MODE、AXES=1/3/7、参数保存、disarm 切换、重启及跨起飞 reset。全轴正常运行只计算所选算法。
C：固定传感器/滤波，按 DIV=1→2→4，先独立模型/自动测试，再每个 DIV 与固定 ESTA 各 3 次低幅 SITL。检查 sensor 时间差、保持不积分、推力/安全每回调处理、饱和区间汇总及电池缩放不累乘；按实际日志报告频率。保持 PID、ESTA、原 ISTA 回归。
每个子门飞行前冻结并提交场景、阈值、参数和种子，在干净源码提交运行；保持项目启动器和 Iris SITL 限定。失败全保留，不补飞或放宽阈值换通过。写 reports/I05.md，分列 A/B/C 结论，审查并提交，更新新 TODO 进度表及 SHA。不 push、不执行 I06。
```

## I06 — 公平调参与新正式实验协议

```text
请仅执行 /home/yr/Desktop/codev doc/plan/ISTA_REDESIGN_TODO_CN.md 的 I06。
完整阅读新计划、原共同规则、进度表、I05、M10、ISTA_OPT01/OPT02 报告，核对 /home/yr/Desktop/Codev-autopilot 研究分支和工作区。旧 M10 及已有优化数据只能作为开发知识，不是新留出集。
设计 A 组：ESTA/原 ISTA/Proper-ISTA 同 g/λ、同保护比较离散化，明确共同有效域与理论限制。设计 B 组：PID/ESTA/原 ISTA/Proper-ISTA 各自调参，给相同新候选评估预算和筛选规则，披露历史额外开发预算。
先提交训练协议，固定参数范围、次数、失败惩罚、早停、场景和种子登记；再执行该预算内训练/选参验证，不允许单独给落后算法追加机会。分离训练、选参验证和正式测试，正式留出不能提前用于调参。
正式协议明确任务/扰动/惯量/噪声/分频的准确矩阵、总次数、指标权重、时间窗、失败与日志标准、缺失处理、配对统计/置信区间、多重比较及 TV/频谱/成本口径。随机场景以 20 个配对测试种子为候选设计，记录独立性及样本数依据。预定义大部分改善的含义，但不得要求数据一定支持。
本阶段不运行正式留出试验。写 reports/I06.md，冻结参数、源码、模型、插件、分析规范和逐轮清单；审查提交，更新新 TODO 进度表及 SHA，报告下一阶段准确预算后停止。不 push、不执行 I07。
```

## I07 — 新正式实验和报告

```text
请仅执行 /home/yr/Desktop/codev doc/plan/ISTA_REDESIGN_TODO_CN.md 的 I07。
完整阅读新计划、原共同规则、进度表、reports/I06.md 和全部冻结协议，确认前置通过，核对 /home/yr/Desktop/Codev-autopilot 研究分支、干净正式源码提交、固件/参数/模型/插件指纹。
严格按冻结清单在 Gazebo Iris SITL 运行正式留出试验，配对 scene/seed，遵守随机顺序和预算；不调参、补飞、加种子或改变主指标。协议偏离先记录，需要新授权的暂停请求用户决定。保留全部失败、中止、回退、未收敛和日志无效，不能只统计成功轮次。
检查真实随机源、时间同步、更新序列和日志丢样。输出预定误差/偏差、控制负担、饱和、成功率、成本与配对统计；以独立运行/种子为统计单位，不把日志采样点当独立样本。TV 用真实更新序列，共同带宽频谱与原生抖振分开。
区分离散化 A 组、有限预算工程 B 组和起飞保护消融的结论；Proper-ISTA 不能冒充原 M10 ISTA。大型原始日志留外部，仓库保存路径/指纹、配置、图表摘要和复现分析，保留阴性结果。
完成 reports/I07.md，审查并提交明确范围结果，更新新 TODO 进度表，报告正式源码 SHA、结果 SHA、实际完成数、失败与缺失。未完成则如实标明，不制造验收通过。不 push、不实机部署、不自动开始新搜索。
```
