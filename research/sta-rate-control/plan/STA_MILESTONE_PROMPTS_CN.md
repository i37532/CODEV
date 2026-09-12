# 逐里程碑实现提示词

每次复制一个代码块到任务中即可。每个提示词都要求阅读详细计划和共同规则，完成测试、Git 提交和记录后停在本阶段，不自动执行下一阶段。

详细计划：[STA_MILESTONES_CN.md](</home/yr/Desktop/codev doc/plan/STA_MILESTONES_CN.md>)  
进度表：[STA_MILESTONE_STATUS_CN.md](</home/yr/Desktop/codev doc/plan/STA_MILESTONE_STATUS_CN.md>)

## M00：现在首先执行这一条

~~~text
请执行 /home/yr/Desktop/codev doc/plan/STA_MILESTONES_CN.md 的 M00，先完整阅读该计划及共同规则，并检查 STA_MILESTONE_STATUS_CN.md。
仓库为 /home/yr/Desktop/Codev-autopilot。请核对工作区、分支和 HEAD；以当前核实的 main-v2_gps 基线建立 research/sta-rate-control 分支。如果该分支已存在则检查并复用，不删除重建。
建立 research/sta-rate-control 研究目录，把外部三份里程碑文档纳入仓库计划快照。记录主仓库/子模块版本、实际 Gazebo 模型和 world、启动方法、参数、编译环境、日志及随机源；区分 Iris SITL 和 CODEV DP1000 实机配置。
完成原 PID 构建和现有 RateControl 单测，验证起飞、60 秒悬停和降落，重复 3 次，保存原始日志指纹与基线指标。沿用项目的 Gazebo 启动脚本，限定 SITL。
完成后写 reports/M00.md，审查实际改动，测试通过后按计划做明确范围的 Git 提交，记录 SHA 并更新外部进度表。不要 push。本阶段不接入 ESTA/ISTA。若必需验证被依赖阻塞，如实记 blocked，不能编造通过或继续 M01。
~~~

## M01：控制器选择框架

~~~text
请在 /home/yr/Desktop/Codev-autopilot 的 research/sta-rate-control 分支执行 M01。先读 /home/yr/Desktop/codev doc/plan/STA_MILESTONES_CN.md 全文、共同规则、进度表和仓库 M00 报告，核对前置验收。
实现控制器 dispatcher、MC_RTC_MODE、MC_STA_AXES、requested/effective 状态和未实现模式拒绝逻辑。默认 PID 与原 RateControl 的输出、状态时序和参数更新语义完全一致；此阶段只允许 PID 生效。
为原 PID 建立固定序列逐样本等价回归，覆盖饱和、落地、解锁状态和非零 FF；测试无效模式及切换行为。编译并完成 PID SITL 冒烟，确认实际运行了非零数量测试。
遵守计划的测试、diff 审查和 Git 提交流程，完成 reports/M01.md、记录提交 SHA 并更新进度表，不 push，不开始 M02。
~~~

## M02：ESTA 内核

~~~text
请执行 /home/yr/Desktop/codev doc/plan/STA_MILESTONES_CN.md 的 M02。完整阅读计划、共同规则及 M01 验收报告，确认 /home/yr/Desktop/Codev-autopilot 位于 research/sta-rate-control。
在 mc_rate_control 下新增 C++14 StaRateControl 算法及单元测试，参考 /home/yr/Desktop/codev doc/algorithms 的已核对公式。统一 s=rate-rate_sp、虚拟角加速度 a、nu 和归一化力矩 c=a/g 的单位。ESTA 用旧 nu 计算当步输出，再更新一次 nu；加入三轴独立状态、参数有效性和 reset 接口。
测试正负对称、零误差、异常 dt/参数/溢出、状态隔离、g 非 1 的映射，并用独立双精度参考及对象闭环核对结果。能运行 MATLAB 就逐样本对照，不能运行要明确记录，不能假称 MATLAB 通过。
此阶段算法不驱动执行器。回归 PID，测试通过后写 reports/M02.md、审查并提交本阶段改动，更新 SHA 和进度表，不 push，不开始 M03。
~~~

## M03：日志、保护和实验脚本

~~~text
请执行 /home/yr/Desktop/codev doc/plan/STA_MILESTONES_CN.md 的 M03，完整读取计划、共同规则和前置报告，在 /home/yr/Desktop/Codev-autopilot 的研究分支操作。
实现公共保护适配器、模式/参数生效规则、落地冻结与重置、raw_dt 检查、mixer 饱和有效性和方向处理、故障 latch 与 SITL 中止策略。不要把输出零力矩等同安全；PID 接管必须满足计划的有效测量、状态初始化及过渡测试条件。
新增并注册 sta_rate_ctrl_status 消息，记录真实更新序号、sample 时间、requested/effective mode、轴掩码、dt、s、nu、raw/applied 输出、限制、reset/fault。加入高频日志及最小解析/场景脚本，保留已有日志配置位，核实 motor_limits 采样率和丢样。
用自动测试覆盖生命周期、armed 参数修改、时间异常和饱和方向；运行原 PID SITL 并实际解码 ULog，核对输出等价。保持 ESTA 未启用。
测试通过后提交，完成 reports/M03.md，更新提交 SHA 与进度表，不 push，不开始 M04。
~~~

## M04：ESTA roll

~~~text
请执行 /home/yr/Desktop/codev doc/plan/STA_MILESTONES_CN.md 的 M04，完整读取计划、共同规则、M00 基线和 M03 验收，核对 /home/yr/Desktop/Codev-autopilot 的研究分支。
先基于实际 Gazebo 模型或原 PID 下受控小扰动标定 roll 输入增益 g_R，写明归一化力矩到角加速度的比例、工作点及误差。冻结试验限值后，开放 ESTA MODE=1、AXES=1，pitch/yaw 保持原 PID。
先验证合成输入的输出方向，再做低幅、零净转角角速度脉冲或小姿态激励。明确有效 setpoint 发布者、其余轴和推力来源，禁止多个发布者争抢。运行 PID/ESTA 相同场景各 3 次，检查日志中的模式、nu、饱和、RMSE、姿态/高度边界和失败事件。
达到预设开发门槛后保存独立实验参数和 reports/M04.md，审查并提交，更新 SHA/进度表。不 push、不实机测试、不扩大到 pitch；若失败就修复或标 blocked，不删除失败数据。
~~~

## M05：ESTA roll/pitch

~~~text
请执行 /home/yr/Desktop/codev doc/plan/STA_MILESTONES_CN.md 的 M05，读完整计划、共同规则与 M04 报告，确认研究分支和前置验收。
在 /home/yr/Desktop/Codev-autopilot 中标定 pitch 的 g_P 和独立增益，验证 ESTA AXES=3；yaw 保持 PID。优先复用已有三轴接口，避免复制 roll 代码或共享内部 nu。
完成 roll 回归、pitch 正负激励和 R/P 小幅组合激励，PID/ESTA 同场景各 3 次，检查交叉轴响应、yaw/高度、状态隔离和 mixer 饱和。沿用预先固定的门槛，记录全部失败。
测试通过后保存参数、reports/M05.md，审查并提交本阶段改动，更新 SHA 与进度表，不 push，不开始三轴接入。
~~~

## M06：ESTA 三轴

~~~text
请执行 /home/yr/Desktop/codev doc/plan/STA_MILESTONES_CN.md 的 M06。完整读取计划和共同规则、M05 报告，确认 /home/yr/Desktop/Codev-autopilot 研究分支。
独立标定 yaw 输入增益和控制参数，先 yaw 小激励再全轴 ESTA AXES=7。检查 yaw 饱和对 R/P 的影响。全轴正常控制只计算所选算法，保留已测试的异常处理。
回归 1/3/7 掩码、PID、参数重载、disarm 后模式切换与状态重置；完成相同悬停、姿态任务和起降场景。三轴 ESTA 通过后冻结参数作为后续回归基准。
写 reports/M06.md，测试通过后提交明确范围的改动，更新 SHA/进度表，不 push，不开始 ISTA。
~~~

## M07：ISTA 内核

~~~text
请执行 /home/yr/Desktop/codev doc/plan/STA_MILESTONES_CN.md 的 M07，完整阅读技术约定、共同规则和 M06 报告，在 /home/yr/Desktop/Codev-autopilot 研究分支操作。
基于 /home/yr/Desktop/codev doc/algorithms 的解析公式实现 ISTA，复用 s、虚拟角加速度 a、nu 和 c=a/g 接口，此阶段保持 MODE=2 不可启用。
测试三分支和精确边界/邻点、xi 范围、三个隐式方程、非单位 g 映射，以及 float 求根相减损失、下溢、溢出和无效输入。必要时用等价有理化求根，并与独立双精度参考比较；测试理想和受约束情形时区分结论。
执行独立对象闭环和 ESTA/PID 回归。通过后写 reports/M07.md、审查并提交，更新 SHA/进度表，不 push，不执行 M08。
~~~

## M08：ISTA 接入

~~~text
请执行 /home/yr/Desktop/codev doc/plan/STA_MILESTONES_CN.md 的 M08，完整阅读计划、共同规则和 M07 验收，在 /home/yr/Desktop/Codev-autopilot 研究分支操作。
开放 ISTA MODE=2，复用公共映射、保护和日志。依次验证 ISTA roll、R/P、R/P/Y，前一步通过才扩大掩码。记录理想解析候选与饱和/冻结后的 applied 输出和 nu，不能把受保护输出当作严格隐式解。
完成三种模式及掩码、重启、armed 修改拒绝、disarm 切换、故障和起降回归；测试场景与 ESTA 一致。有效模式必须与日志一致，算法间不继承陈旧状态。
结果不要求 ISTA 所有指标胜出，但必须满足开发验收并如实报告。通过后写 reports/M08.md、保存配置、提交并更新 SHA/进度表，不 push，不开始分频实验。
~~~

## M09：分频与耗时

~~~text
请执行 /home/yr/Desktop/codev doc/plan/STA_MILESTONES_CN.md 的 M09，完整阅读共同规则、采样约定和 M08 报告，确认 /home/yr/Desktop/Codev-autopilot 研究分支。
新增 MC_RTC_DIV=1/2/4；保持传感器和滤波配置一致，真实更新时间使用 sensor 时间差，未更新周期保持力矩且不积分。模式、故障、termination 和推力仍每回调处理，电池缩放不可累乘。按计划定义饱和汇总策略。
测试非均匀时间戳、N=1 等价、N=2/4 状态更新次数、长停顿、保持期间安全事件和新推力；先标量模型，再三个控制器的低幅 SITL。频率名称以实际日志为准。
加入核函数/模块耗时统计，按真正更新序列计算 TV，区分共同带宽频谱与原生抖振。通过后写 reports/M09.md、审查并提交、更新 SHA/进度表，不 push，不自动运行 M10 大批实验。
~~~

## M10：论文实验

~~~text
请执行 /home/yr/Desktop/codev doc/plan/STA_MILESTONES_CN.md 的 M10。完整阅读计划、共同规则和 M09 验收，在 /home/yr/Desktop/Codev-autopilot 的研究分支完成可复现实验包。
构建两类对比：同 lambda/g 的 ESTA 对 ISTA 离散化实验；相同调参预算下分别优化的 PID/ESTA/ISTA 工程实验。分离训练测试集，预定指标、时间窗、失败标准和参数范围。
先提交场景脚本、冻结参数和分析规范，在该干净源码提交上运行正式试验，再单独提交结果报告。按计划逐项测试扰动、惯量、噪声和控制周期，随机场景计划 20 个配对种子，实际独立性/种子支持和样本数依据必须记录。
保留失败、回退和未收敛记录，检查日志丢样及时间同步；输出误差、控制负担、饱和、成功率、成本及合适的统计结果。大型日志留在外部 experiments 目录，仓库提交路径、SHA-256、配置、图表/摘要与复现方法。
完成 reports/M10.md、结果提交和外部进度表，报告两次提交 SHA、实际完成场景和缺失项，不 push，不做实机部署。
~~~
