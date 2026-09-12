# PX4 角速度控制器功能里程碑

编制日期：2026-09-12。本文是可逐项执行的详细计划，当前全部里程碑均未执行。

仓库：/home/yr/Desktop/Codev-autopilot  
核对的起点：main-v2_gps，9a3c4e3625474ce7fd2cd5c9687933ccf6a70bc7  
建议研究分支：research/sta-rate-control  
算法资料：[算法总结](</home/yr/Desktop/codev doc/algorithms/SUPER_TWISTING_FAMILY_CN.md>)  
执行入口：[每阶段可复制提示词](</home/yr/Desktop/codev doc/plan/STA_MILESTONE_PROMPTS_CN.md>)  
状态记录：[进度表](</home/yr/Desktop/codev doc/plan/STA_MILESTONE_STATUS_CN.md>)

## 1. 路线与执行范围

第一步执行 M00：从核实过的当前提交建立研究分支，记录原 PID 仿真基线。随后先实现 ESTA，再实现 ISTA。PID、ESTA、ISTA 最终保存在同一个分支、同一个固件中，由参数选择。分支用于隔离研究开发，参数用于公平切换算法。

连续 STA 是理论控制律；本文的 ESTA 是其显式欧拉实现，ISTA 是隐式实现。飞控实验比较 PID/ESTA/ISTA，连续 STA 留作离线参考。

| ID | 交付功能 | 进入前必须完成 | 完成标志 |
|---|---|---|---|
| M00 | 分支、环境快照、原 PID 基线 | 无 | 基线可运行、可追溯 |
| M01 | 控制器选择框架、PID 回归 | M00 | 默认 PID 等价 |
| M02 | ESTA 纯算法、输入增益映射、单元测试 | M01 | 公式和量纲测试通过 |
| M03 | 高频日志、运行状态与异常处理、实验脚本基础 | M02 | 接入前能观测并测试所有保护 |
| M04 | ESTA roll 单轴 | M03 | 单轴 SITL 验收 |
| M05 | ESTA roll/pitch | M04 | 双轴 SITL 验收 |
| M06 | ESTA 三轴 | M05 | yaw 单独校准、三轴完成任务 |
| M07 | ISTA 解析内核、数值测试 | M06 | 三分支和预测方程通过 |
| M08 | ISTA 接入及三控制器统一验证 | M07 | 逐轴验证后 PID/ESTA/ISTA 均可选 |
| M09 | 控制周期实验与计算成本测量 | M08 | 分频、保持和计时语义正确 |
| M10 | 正式论文对比、报告与复现实验包 | M09 | 参数冻结、重复试验、数据归档 |

你的七步路线是主干；这里把选择框架和日志提前，把纯算法、运行保护、逐轴验证拆开。所有飞行测试限定 Gazebo SITL；实机部署是单独任务。

## 2. 每个里程碑共同执行规则

1. 开始时核对分支、HEAD、工作区与上一个里程碑报告。已有改动属于用户，不能强行清理；只有真正重叠且无法隔离时才需要用户决定。
2. 一次只执行选定里程碑。实现 → 有针对性的测试 → 审查 diff → Git 提交 → 对该提交确认关键检查 → 更新记录 → 停止。
3. 在仓库内新增研究目录 /home/yr/Desktop/Codev-autopilot/research/sta-rate-control，保存小型配置、脚本、测试证据摘要和报告；飞控代码仍放在相应源码目录。
4. 文档所在 /home/yr/Desktop/codev doc/plan 在 CODEV Git 仓库外。M00 把三份计划复制到研究目录的 plan 子目录，使计划也可版本管理；以后外部文档作阅读入口，仓库内记录作实验依据。
5. 大型 ULog、编译产物和临时输出不提交。原始数据拟放在 /home/yr/Desktop/codev doc/experiments；每份报告记录绝对路径、SHA-256、运行配置、源码提交和是否有未提交补丁。
6. 每阶段报告放在 /home/yr/Desktop/Codev-autopilot/research/sta-rate-control/reports/Mxx.md，必须给出测试命令、退出码、实际执行结果、未完成检查和已知限制。
7. git add 使用明确文件列表，审查 git diff --cached。禁止 git add .、无关改动提交、自动 push、强推和修改旧基线提交。
8. 验收不通过时修复并重测受影响部分；外部依赖阻塞时记录 blocked。必要时可提交明确标注 WIP 的可审查进度，但不可称为验收通过，不得进入依赖阶段。
9. 提交时沿用仓库用户身份；若没有身份配置，报告原因，不编造身份。新提交 SHA 写入外部进度表；仓库内报告不要求预知自身提交的 SHA。
10. 提交后无源码变化通常只需核实提交内容和必要的快速检查，不必机械重复全部长耗时仿真。最终正式实验应在干净、确定的源码提交上运行。

## 3. 实现前必须统一的技术约定

### 3.1 作用范围与模型

主替换点是 [RateControl::update](</home/yr/Desktop/Codev-autopilot/src/modules/mc_rate_control/RateControl/RateControl.cpp:60>) 附近的角速度算法；包装入口是 [MulticopterRateControl::Run](</home/yr/Desktop/Codev-autopilot/src/modules/mc_rate_control/MulticopterRateControl.cpp:100>)。原 RateControl 保留作 PID 基准，新算法可使用 StaRateControl 独立类及单独 CMake 子目录。

M00 必须辨认实际 Gazebo 模型。现有脚本的 Gazebo iris 模型不等于 CODEV DP1000 实机，不能把 DP1000 的质量、参数或 airframe ID 写成 Iris 仿真的配置。先固定已运行的模型，扩展 DP1000 模型属于后续工作。

### 3.2 输入增益不能只靠“调 lambda”含糊处理

采用近悬停单轴设计模型：

$$
\dot s_i=g_i c_i+d_i-\dot\omega_{sp,i},\qquad s_i=\omega_i-\omega_{sp,i},\quad g_i>0.
$$

c 是归一化力矩指令，g 的单位是每单位归一化指令对应的 rad/s²。算法内核输出虚拟角加速度 a，内部状态 nu 也使用 rad/s²：

$$
c_{raw,i}=a_i/g_i.
$$

ESTA：

$$
a_k=-\lambda_1\sqrt{|s_k|}\operatorname{sgn}(s_k)+\nu_k,\qquad
\nu_{k+1}=\nu_k-h\lambda_2\operatorname{sgn}(s_k).
$$

因此 lambda1 单位为 (rad/s²)/sqrt(rad/s)，lambda2 为 rad/s³。输出是旧 nu 计算的 a_k，再提交 nu_next；交换顺序就不再是本文的 ESTA。

ISTA 在同一虚拟通道上满足：

$$
\tilde s_{k+1}=s_k+h a_k=s_k+h g_i c_{raw,k}.
$$

这是设计模型预测，不是含饱和、电机动态和扰动的实际下一状态。g 必须通过 Gazebo 模型计算或原 PID 下的小扰动识别确定，记录工作点、误差和适用范围；先在 M02 定义映射，在 M04 启用前校准。仅把归一化 c 代入 s+h*c 再调整 lambda，不能声称得到物理一致的论文 ISTA。

保持两种滑模实现相同的 g、反馈信号和公共映射。第一版不暗加 PID 的 D 项或重复 I 项，也不新增参考加速度前馈。原 PID 的现有 FF 保留并记录实际值；若之后研究额外前馈，另做消融。

### 3.3 参数、状态和保护边界

拟议参数名均需再次检查冲突并定义元数据：

- MC_RTC_MODE：0=PID，1=ESTA，2=ISTA；M01 仅 PID 可执行，M04 才开放 ESTA，M08 才开放 ISTA。
- MC_STA_AXES：位掩码，1=roll，2=pitch，4=yaw；3=R/P，7=三轴。默认 0。
- MC_STA_L1_R/P/Y、MC_STA_L2_R/P/Y、MC_STA_NU_R/P/Y：每轴增益、内部状态上限。
- MC_STA_G_R/P/Y：输入增益。无效或尚未校准的配置不能被当作可飞配置。
- MC_RTC_DIV：M09 才实现；默认 1。在此之前固定原更新周期。

默认 MODE=0、AXES=0。实验配置单独存储，不能改 airframe 默认值让新固件自动启用实验控制器。记录 requested mode 与 effective mode，未实现值必须显式报告 unsupported。

飞行中对实验模式、轴掩码、增益、映射和分频的改动暂存，disarm 后校验并生效；不能先清状态再发现不允许切换。纯 PID 模式保持原有参数更新语义。

重置逻辑明确为：首次启动、disarm、退出实验 rate 控制、有效配置切换时清零；进入 landed 时清零一次并冻结；maybe_landed 冻结。触发源、时刻和原因可记录。不能只因 EKF 姿态四元数 reset 就盲目清角速度内部状态，应核对角速度/设定值是否真的发生重置。

使用 sensor timestamp_sample 求真实时间差，同时保存 raw_dt 与算法使用的 dt。先检测时间倒退、重复和长间断，再处理限幅；仅看被夹到 20 ms 的 dt 会漏报原始停顿。

饱和保护按候选 delta_nu/g 的输出方向判断，读取 mixer 有效位和正负饱和标志，限幅和冻结必须可见。ISTA 的受约束实现与理想解析解分开记录，不能修改 nu 后继续声称三个隐式方程严格成立。

异常不等于“零力矩即可安全”。参数不合法应在启用前拒绝；飞行中数值错误在 SITL 由明确的试验中止状态机处理并计为失败。仅在测量有效且已测试 PID 状态初始化与输出过渡时才允许应急 PID 接管；传感器无效不能靠切 PID 修复。保留现有 commander/termination 语义；仿真中止可重启该次实例，不能把事故段从统计中消失。

### 3.4 测试入口与结果有效性

已核对的本版本入口如下，实际执行前仍需检查生成目标：

~~~bash
cd /home/yr/Desktop/Codev-autopilot
git diff --check
make px4_sitl_default
make tests TESTFILTER=RateControl
./sitl/run.sh --headless --backend gazebo --model iris
~~~

新增 StaRateControlTest.cpp 按现有 px4_add_unit_gtest 注册，预期目标名 unit-StaRateControl。make tests TESTFILTER=StaRateControl 只是待实现后的示例，必须检查确实执行了非零测试。编译环境沿用本仓库 sitl 脚本中的 Python 设置。不要用“进程退出为 0 但未匹配到测试”当通过。

已知板级配置包括 /home/yr/Desktop/Codev-autopilot/boards/codev/dp1000-v2/default.cmake；交叉编译需核对工具链。只有 SITL 通过时标记 SITL-ready，不能标记实机验证通过。没有 MATLAB/Octave 时，独立双精度参考可补充校验，但必须明确没有执行 MATLAB 对照，不能伪称已通过。

所有正弦和脉冲先在独立角速度模型中验证。自由飞行 roll rate 非零会累积倾角，采用短、零净转角脉冲或姿态小幅激励；直接 rate 模式需给出推力和其余轴控制策略。不能一边由姿态环发布 rates setpoint，一边另一发布者争抢同一话题。

## 4. 功能里程碑规格

### M00 — 建分支并冻结 PID 基线

交付：研究分支、计划快照、environment.md、baseline 参数与模型指纹、报告 M00.md、数据归档约定。

执行：先核对起点和未提交改动；分支不存在则从核实的起点创建，已存在则检查历史并复用，不能删除重建。记录主仓库/子模块 SHA、Gazebo/PX4/编译器版本、模型和 world、启动命令、实际参数、日志路径、实际频率、随机源与 lockstep 设置。

测试：构建原固件，执行现有 RateControl 单测；PID 起飞、60 s 悬停、降落，重复 3 次。选定运行实例，确认日志确为该进程产生。量化原始噪声、姿态漂移和输出范围供后续门槛使用。

门槛：三次完成、无控制失效；随机源不能保证可重复时如实注明。缺失 Gazebo/工具链时记 blocked。记录源码基线完整 SHA。

提交建议：docs(research): establish PID baseline and STA milestone plan

### M01 — 选择框架和 PID 等价回归

交付：dispatcher/选择接口、MODE 与 AXES 参数、requested/effective 状态、未实现模式拒绝逻辑。

位置：/home/yr/Desktop/Codev-autopilot/src/modules/mc_rate_control/MulticopterRateControl.cpp 及对应头文件、参数文件；测试可单独放 ControllerSelectionTest.cpp。

测试：原 PID 对固定输入序列逐样本比较；涵盖饱和、落地、disarm、非零 FF、参数更新。新旧使用相同初始状态及浮点顺序，目标是精确等价；任何偏差必须解释。未实现模式显式拒绝，默认模式不额外限幅、不提前改变积分时序。

门槛：PID 回归与模式测试通过；SITL PID 冒烟通过；MODE=1/2 仍不能输出新算法。

提交建议：feat(control): add selector with unchanged PID default

### M02 — ESTA 内核和带单位的适配接口

交付：StaRateControl.cpp/.hpp、子目录 CMakeLists.txt、StaRateControlTest.cpp、独立期望值/双精度参考测试数据；此阶段不驱动执行器。

测试：输出用旧 nu、状态每步只更新一次；正负对称、s=0、nu 非零、三轴状态隔离；非正/NaN/Inf 参数及异常 h；有限输入造成中间溢出；g=1 与 g 非 1 的 a→c 映射；reset。单元闭环使用独立对象模拟、不同扰动和采样周期，不能只重复实现公式做自证。

门槛：有效域定义明确，C++14 通过，本机非零数量单测通过；原 PID 回归通过。内核 nu 单位、输出单位、状态更新顺序有注释。

提交建议：feat(control): add tested ESTA kernel and input-gain mapping

### M03 — 日志、生命周期、保护和实验脚本

交付：公共保护适配器、研究状态机、sta_rate_ctrl_status.msg、消息注册、高频日志设置、日志解析和场景脚本基础。新功能保持未启用。

日志字段至少包括 sample timestamp、publish timestamp、update_seq、requested/effective mode、axis mask、raw_dt/dt、s/nu、a_raw/c_raw/c_applied、updated/held、限制标志、饱和有效性、故障/reset 原因。ISTA 的 xi/branch/virtual_state 预留，但 ESTA 下标记不适用，不能显示“sliding”。

测试：disarm/land/maybe_landed/模式退出及重新进入；armed 参数更新不立即生效；时间倒退/停顿；饱和方向、无效/过期 mixer 反馈；数值故障 latch 和试验中止；消息能出现在 ULog。检查原 PID 输出不因 logger 开启而改变。

日志要求：HIGH_RATE bit 4 加到已有 SDLOG_PROFILE 中，而不是无条件覆盖为 17；例如原值 131 按位加入 16 后为 147。确认新状态和 motor_limits 记录率足够；仅启用现有 high-rate profile 不保证 motor_limits 全速。根据序列号统计丢样，不能假设 uORB 无损。

门槛：自动化保护测试通过；至少一份真实 PID ULog 可解码，原生频率和丢样统计可计算；短试验若有更新缺失必须重采或标记不适合 TV/频谱分析。

提交建议：feat(research): add controller lifecycle diagnostics and SITL harness

### M04 — ESTA roll 单轴接入

交付：MODE=1 的可用路径，AXES=1 配置、roll 输入增益标定记录、试验限值、对比报告。

启用前：用 Gazebo 模型与 PID 下受控的小扰动估计 g_R，核对正负、幅值和工作点；对象增益只存在于模型中时可先标记该模型专用。固定其余外环及电机模型。混合轴验证需保证 pitch/yaw PID 的状态更新正常；可以在此阶段计算完整 PID 再选轴，但记录额外计算成本。

测试：合成输入 s>0/nu=0 得到负 c，s<0 得到正 c；在 SITL 逐渐增加小幅零净转角 pulse 或姿态激励；先悬停，再跟踪，再小扰动；ESTA 与 PID 同一场景各 3 次。保护触发记录为失败。

初始开发门槛（M00 基线核对后、看 ESTA 结果前固定）：完成 60 s 悬停和降落；无 NaN、回退或中止；测试额外倾角上限先设 15°、高度误差上限先设 1 m；跟踪 RMSE 不超过同场景 PID 的 1.25 倍。以上只是该小幅 SITL 场景的开发门槛，若原 PID 都不满足，先修改场景并记录新预设；不能看新算法结果后放宽阈值。

提交建议：feat(control): enable and validate roll-axis ESTA

### M05 — ESTA roll/pitch

交付：AXES=3 配置、g_P 标定、pitch 独立增益、组合激励报告。

测试：复跑 roll；pitch 正负激励；R/P 同步小幅正弦；yaw 继续 PID。三轴 nu 不得共享或串扰；记录高度、yaw 误差、饱和和交叉轴响应。同场景 PID/ESTA 各 3 次。

门槛：沿用预先固定的开发阈值，无回退/中止；非命令轴退化超过门槛时检查耦合、限幅和状态，不能仅“画面看起来稳定”就通过。

提交建议：feat(control): validate roll-pitch ESTA configuration

### M06 — ESTA 三轴完成

交付：AXES=7 配置、g_Y 标定、yaw 独立增益、完整 ESTA 参数文件、起降回归。

测试：yaw 单独激励后再三轴；yaw 变化时保留姿态环的坐标变换；记录 yaw 饱和对 roll/pitch 的影响。验证重启参数保存、切回 PID、三种 axes 配置、不同起飞运行的内部状态一致性。

门槛：PID 与 ESTA 都完成预设悬停、姿态任务、降落；全轴 ESTA 模式不计算闲置 PID 用作正常输出，但异常接管的状态策略有测试；将合格 ESTA 参数冻结为下一阶段回归基准。

提交建议：feat(control): complete three-axis ESTA integration

### M07 — ISTA 解析内核

交付：共享相同单位接口的 ISTA，三分支解析解、数值稳健实现和独立参考测试；暂不开放 MODE=2。

测试：三分支、两条精确边界与边界两侧浮点邻点；xi 位于 [-1,1]；理想域中验证 virtual_s=s+h*a、nu_next=nu-h*lambda2*xi 和隐式控制方程。验证 g 非 1 时 virtual_s=s+h*g*c_raw；接近边界根号相减消减、q 下溢、异常判别式与中间溢出。

不得机械复制参考头文件：现有直接根号相减在 float 下接近边界可能损失精度，可采用等价有理化求根，必须与双精度独立解比较。端到端对象闭环检查理想无扰动行为；扰动、噪声、饱和场景独立报告，不把理论保证扩展到受约束实现。

门槛：内核测试通过、ESTA/PID 回归通过、输入增益映射与 M02 一致；不需要实时迭代求解。

提交建议：feat(control): add numerically validated analytic ISTA kernel

### M08 — ISTA 接入及统一模式验证

交付：MODE=2 可用；ISTA片段诊断；raw/受保护输出区别；三个控制器的参数配置和统一回归报告。

执行顺序仍是 ISTA roll → R/P → R/P/Y，每一步通过才扩大轴数。共用映射、日志、保护和场景；nu 不可在不同算法间隐式继承。

测试：初次启动、参数重载、armed 切换拒绝、disarm 切换、无效模式、所有掩码；ISTA 抗饱和修改后的状态必须与日志一致。正式对比时全轴选择只正常计算当前控制器。回归 M04–M06 的任务。

门槛：三种控制器可按文档独立启动，启用参数与日志 effective mode 一致；开发基线都完成。ISTA 可能比 ESTA 某项指标差，应如实记录，不能以“必须更好”作为通过条件。

提交建议：feat(control): integrate ISTA with staged three-axis validation

### M09 — 采样周期、保持输出和成本

交付：MC_RTC_DIV=1/2/4、调度器测试、原始时间差统计、内核和模块耗时。

基频由日志实测；只有实测接近 400 Hz，才把三组标成约 400/200/100 Hz。保持传感器滤波配置相同，算法每 N 次有效回调计算一次，h 使用自上次真正更新以来的 sensor 时间差。

未更新周期保持力矩候选，不更新 nu/PID 积分、不重复缩放历史输出；推力、模式、故障和终止检查仍每回调执行。记录最新饱和反馈及其有效性；定义分频间隔内的保守饱和汇总策略并对三控制器一致应用，避免漏掉短饱和。

测试：不规则时间戳、N=1 等价回归、N=2/4 更新次数、模式变化和终止在保持期间即时处理、电池缩放不累计、推力不随力矩降频冻结。分频先标量闭环，再 PID，再 ESTA/ISTA 的小幅 SITL 场景。

门槛：采样频率、真实更新次数和积分步长正确。统计 TV 时只取真正更新序列或统一时间网格，给出相同时间窗及 TV/秒；原生抖振量和抗混叠后共同带宽频谱分别报告。计算成本从实际计时得出，SITL 宿主机结果不等价于板载实时性能。

提交建议：feat(research): add verified control decimation and timing metrics

### M10 — 论文正式对比与可复现结果

交付：场景驱动、参数搜索/选择记录、训练和测试集清单、失败分类、原始数据索引、绘图及指标程序、最终报告。

分两组问题：A 组 ESTA/ISTA 使用同样的 lambda 和 g，隔离离散化效应；B 组三控制器在相同调参预算、约束和训练集下各自调优，评价实际性能。不能用 PID 参数数目不同当作减少它调参机会的理由。

先以 M09 标称频率完成名义任务；再逐项增加有限变化率力矩扰动、惯量失配、噪声、采样变化。理想力矩阶跃/白噪声另列压力测试，不声称满足连续扰动导数有界假设。修改惯量须保持物理可实现且记录是否同步改质量。

冻结代码和参数后，每个随机场景计划 20 次配对种子运行；先做少量试运行估计方差，再说明最终样本数依据。记录每个插件是否实际接受 seed，不能把一个全局 seed 当作全部噪声可控。相同条件纯确定性重复不形成独立随机统计样本。

指标：跟踪 RMSE/IAE、带预定保持规则的恢复时间、控制 RMS/峰值、TV、频谱、饱和比例、成功率、CPU、日志丢样。参数调优和测试时间窗均预先记录。统计对配对差值检查假设；非正态也不自动满足 Wilcoxon 的对称性假设，可采用配对 bootstrap/置换方法并声明条件，多场景检验处理多重比较。

门槛：一条命令能复现一个场景并生成对应指标；另一人按记录能定位源码/配置/日志。失败运行进入成功率统计，无法计算的收敛时间标为未收敛/删失，不能写成仿真结束时间冒充收敛。

该阶段建议两次提交：先提交脚本、冻结参数与测试规范；在这个干净提交上正式运行；再提交报告与数据指纹。这样 ULog 的源码版本与正式结果能准确对应。

提交建议：feat(research): freeze reproducible controller comparison protocol  
结果提交：docs(research): record PID ESTA ISTA comparison results

## 5. 对前一版计划的补充与修正

本文作为执行细则，以下内容优先于早期概览：

- 先做分支与基线，再做 ESTA；选择开关和高频日志前置。
- 输入增益在第一次 ESTA 飞行前校准，ISTA 使用相同虚拟角加速度映射。
- 异常输出零控制量不作为“安全策略”；使用已测试的故障状态机和仿真中止规则。
- landed 进入时清零、随后冻结；armed 参数改动不立刻清零或生效。
- 实际 Hz 从日志得出；分频不能冻结推力、安全检查或重复放大电池补偿。
- 外部计划需要仓库内快照；本次生成计划不等于已创建分支或已完成实现。
- 保留单个研究分支和可切换三算法，主实验只改变角速度内环。
