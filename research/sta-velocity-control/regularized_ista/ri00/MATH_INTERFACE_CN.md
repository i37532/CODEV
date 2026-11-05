# RI00：补偿隐式核与最小接入接口冻结

日期：2026-10-23。范围仅离线审计。以下“后续要求”不是已实现功能，不开放 MODE4，不改变当前控制器。

## 1. 来源与命名

原包位于 /home/yr/Desktop/STA-ISTA-MATLAB-PX4。逐项证据见 results/source_fingerprints.json、models.json、source_limitations.json。29 个清单文件全部校验，再单独记录清单本身，共 30 个文件；SLX 中 8 份函数共 17 个嵌入匹配，工作区参数与 JSON 核对一致。只核实现有包，不声称找回原 Windows 工程或原 main-v2_gps ZIP。

本次 R-ISTA 指包内“输入补偿 + 边界层 + backward/implicit 离散核”。它不是旧 IstaRateControl，也不是 ProperIstaRateControl。来源文档不是论文定理的独立证明；本次只对实际代码、隐式关系和有限离线对象负责。

源模型的控制 Ts 均为 5ms，STA/ISTA 求解器固定步长分别为 1ms/0.5ms；不能把求解器步长当 PX4 控制周期。源模型质量 1.4kg、重力 9.8m/s²、电机时间常数 20ms、转动惯量等参数在 models.json 保留；没有加载到 Iris。源码包 C++ CTest 使用保存的 MATLAB CSV，不等于本次运行 MATLAB/Simulink。

## 2. 符号、量纲与更新顺序

包内 e=v_sp−v；PX4 统一 s=v−v_sp=−e。以下 p=−p_e，nu 的物理符号不翻转。

| 量 | 含义 / 单位 |
|---|---|
| s、p、epsilon | 本地 NED 速度误差 / m/s |
| a、nu、a_ff | 加速度纠偏、内部状态、原加速度前馈 / m/s² |
| lambda1 | sqrt(m)/s^(3/2) |
| lambda2 | m/s³ |
| h | 有效 sensor sample 时间差 / s |

X 北、Y 东、Z 向下。没有 rate 输入增益 g，没有重复除质量，没有在纯核加重力、PWM 或推力比例。正 s 应产生负纠偏；Z 正误差也是向上纠偏，并非直接增加某个电机输出。

定义 rho(p)=sat(p/epsilon)，Psi(p)=sqrt(max(|p|,epsilon))*rho(p)，epsilon>0。

源 MATLAB 补偿层先把 e+h*nu_old 传给通用核，通用核再构造 w=e_input−h*nu_old，故理想代数中 w=e。源 C++ 已消除此平移，直接用 e。PX4 应采用消元后的 s，不能真的先加再减大数。

冻结逐式约定：

~~~text
(RI-1) p = s + h*(a_ideal - nu_old)
(RI-2) nu_candidate = nu_old - h*lambda2*rho(p)
(RI-3) a_ideal = -lambda1*Psi(p) + nu_candidate
(RI-4) p + h*lambda1*Psi(p) + h²*lambda2*rho(p) = s
~~~

顺序：读取旧状态 → 求 p → 计算 nu_candidate → 用候选 nu 计算本步理想输出 → 独立保护裁决 → 最多提交一次。不是 R-STA 的“旧 nu 直接进入本步输出”。

令 A=h*lambda1、B=h²*lambda2、b=epsilon+A*sqrt(epsilon)+B：

- |s|≤b（含精确边界）：p=s/(1+A/sqrt(epsilon)+B/epsilon)。
- |s|>b：C=|s|−B，r=2*C/(sqrt(A²+4*C)+A)，p=sign(s)*r²。

RI-4 左端严格单调，根唯一。有理化式避免 sqrt(A²+4C)−A 的相减消失，但不自动解决平方/4C 中间量溢出、下溢或非法参数。独立探针使用 65 步单调二分及三式残差，不复制上述分支式作为参考。

## 3. 与旧两种 ISTA 的实质差别

| 实现 | 隐式预测 / 输出关系 | 不可混淆之处 |
|---|---|---|
| 原 IstaRateControl | q=s+h*a；a=−lambda1*sqrt(|q|)*xi+nu_candidate | 消元右侧 s+h*nu_old；旧恒扰 s=h*d 线索来自此结构 |
| ProperIstaRateControl | z=s+h*(a−nu_candidate)；a=−lambda1*sqrt(|z|)*xi+2*nu_candidate−nu_old | 预测、输出与 nu 重构不同 |
| 本次 R-ISTA | RI-1…RI-4；epsilon>0 | 输入补偿消去 nu_old 对根的影响；不是 Proper 的正则化同义词 |

epsilon→0 时，R-ISTA 的某些根分支与 Proper 相似，仍不能交换控制律：中间分支 R-ISTA 为 a=nu_old−s/h，Proper 为 a=nu_old−2*s/h。旧 I01 固定文献的保证不自动适用。

## 4. 可推导的结论及其边界

仅对固定目标、无保护、理想 ZOH 对象 s_next=s+h*(a+d)：

恒定扰动的平衡为 p*=0、s*=0、nu*=−d。不是原 ISTA 的 s*=h*d。这是平衡分析；不等于全局有限时间、任意对象或实机鲁棒性证明。

边界层内令 alpha=lambda1/sqrt(epsilon)、beta=lambda2/epsilon、D=1+h*alpha+h²*beta，状态 (s,nu+d) 的固定周期矩阵为：

~~~text
[ 1/D       h ]
[ -h*beta/D 1 ]
~~~

trace=1+1/D，det=(1+h²*beta)/D。对正 h/增益，Jury 项 1−trace+det=h²*beta/D>0、1−det=h*alpha/D>0、1+trace+det=2+(2+h²*beta)/D>0；得到边界层局部 Schur 稳定，不证明外层全局或任意切换周期稳定。

线性扰动 d(t)=d0+r*t，使用每区间精确平均扰动；固定 h、稳态在边界层时：

~~~text
p* = epsilon*r/lambda2
s* = r*(epsilon + h*lambda1*sqrt(epsilon) + h²*lambda2)/lambda2
~~~

需 |r|≤lambda2，且对象/状态不受限。误差有 epsilon*r/lambda2 项，不是笼统 O(h²)，也不是任意斜坡零误差。本次实际8/12ms序列只做有限轨迹核对，未给变步长理论保证。

滞后、位置环产生的变化目标、实际内环/电机、FF 误差与推力耦合都破坏理想对象假设；超过可用纠偏的扰动不可能靠离散化消除。本次六条不可行限幅反例确实不收敛，保留且不称跟踪通过。

## 5. 来源数值与事务限制

实际源包测试复现：

1. 外对象但相同 nu、reset 到相同 nu 后的旧候选、篡改候选 nu_next，三者均可 commit。源包仅比较 nu 值不足以保护事务。
2. float 极小输入允许 subnormal 候选；大有限误差因中间量溢出返回 NumericalFailure。不能把源包验证成功推广成全部有限 float 输入都安全。
3. double 中 (1e−12+0.012*1e20)−0.012*1e20=0，直接 s 求根仍非零；平移消元必要，但此极端状态不在拟用飞行域。

后续 RI01 必须独立命名 RegularizedIstaVelocityControl，明确数值可用域和异常策略；owner/axis/config-generation/state-generation/reset/单次提交及候选载荷不可篡改。先全轴校验再原子提交，失败不能留下半组新状态。重复 sample 的失败重算不能再次积分。RI00 没有实现这些生产机制。

冻结的最小候选域：epsilon 沿用元数据 [0.001,1]m/s；增益/限制为有限正 normal，零值仍表示未配置，不引入 epsilon=0 回退。适配采样窗沿用现保护 [0.002,0.04]s，核自身异常 dt 要拒绝而非 clamp。本次数值证据只覆盖指定候选、源包增益及列明输入网格，不证明整个有限 float 域；RI01 需定义并测试非零中间量的 subnormal/消失、溢出拒绝和零误差例外，不能默默冲零通过。未设置新的飞行参数上限或安全阈值。

## 6. 保护映射：候选与应用值不可混写

原包 MATLAB/C++：先形成理想候选和输出（包装加 FF），裁剪输出，按饱和方向冻结外推 nu 增量，再限 nu；外部禁止积分同样保持旧状态；不按冻结后的 nu 重算本步输出。源包装含位置任务自己的 −lambda*v 前馈，不能复制进 PX4。

冻结后续最小 PX4 适配策略：纯核只输出纠偏；原 a_ff 在适配层一次加入；保持原限速、倾角、推力转换、Z 优先/XY 余量流程。先各轴理想候选，经过纠偏限幅和共同下游裁决，再原子提交 applied nu。状态被冻结/裁剪时不凭空把当前输出重算成另一个算法。源包裁剪“含 FF 总输出”与 PX4“纠偏限制+下游总约束”不同，必须在 RI02 分开测试。

日志保留 p、nu_old、nu_ideal、nu_applied、a_ideal、限幅后纠偏、原 FF、实际推力和 thrust-equivalent proxy；代理不是实际加速度。保护介入时 strict_implicit=false。直接把 a 改为 a+delta_nu 并保持同 p，会使 RI-1 残差成为 −h*delta_nu；更不能照搬 Proper 的 2*delta_nu。

NED 加速度保护不能直接解释机体 mixer 正负饱和位；不采用原 PID 的 2/Kp tracking ARW 更新 nu。反馈无效/过期、NaN 使能、XY 成对、故障 latch、退出/重入和同 sample 二次 update 继承已审计生命周期，但新增算法各分支必须另测。零力矩/零纠偏不是安全策略；不新增未经验证的 PID 接管。

## 7. HTE 与 Z/XYZ 交接：不能照搬 R-STA

现 PositionControl 的 R-STA seed 近似采用 PID纠偏+lambda1*Psi(s)，HTE 用 −lambda1*Psi(s)+当前nu 还原纠偏。这对本次隐式候选关系不成立。

定义 F_h(s)=lambda1*Psi(p)+h*lambda2*rho(p)=(s−p)/h，则 a_ideal=nu_old−F_h(s)。对同一冻结 s、h、配置且未受保护的目标 PID 纠偏 c：

~~~text
nu_seed = c + F_h(s)
~~~

这只保证该冻结输入的代数连续。seed 必须记录 h；交接边界仍使用 PID 的 priming 帧，不偷偷提交新算法积分。若以先前有效 sample h 预置，下一帧真实 h/s 变动需另做8↔12ms及变化目标的有界过渡测试，不能假称预测了下一帧。超 nu 限制或保护使逆映射不可达时不得伪称无扰切换。

HTE 应使用带 sample/配置身份的上一实际 applied 纠偏缓存，不能用已提交 nu 再 evaluate（会多推进一次），也不能还原为 R-STA 式。原保持推力关系的竖直平移为：

~~~text
delta_nu = (hover_old/hover_new−1)*(cached_correction_z + original_ff_z − gravity)
~~~

仅在身份一致、有限且相应约束未破坏关系时可作为待验证适配。状态、缓存和 generation 必须一起处理；无有效缓存/重叠限幅时不猜测补偿，而按明确保护规则拒绝或暂停接管。RI02 需覆盖 HTE 同帧、sample 重算、落地抑制、接触弹跳、估计 reset、参数切换/重启、故障/termination。此处只做等式与反例探针，未实现 HTE/seed 新路径。

## 8. MODE / 参数 / 日志最小契约

- 候选 MODE4 当前空闲；真实 selector C++ 探针仍明确拒绝为 ModeRange，生效 PID。MODE0/1/2/3 含义保留，MODE2 不放开；新实验只有0/3/4。
- 当前准入、PositionControl::_staEffective、公共保护 variant 检查、模块 variant 日志/epsilon 选择均只识别1/3；MODE4 不能只改 selector，否则存在静默走旧分支的风险。后续显式全链扩展，不把未知值转换为 X 或 STA。
- 最小参数策略：复用现有15个 MPC_VC_{L1,L2,EPS,NU,A}_{X,Y,Z}，各名称唯一且≤16字符；三算法使用独立完整配置文件，disarm 后整组原子加载，armed 暂存/取消并更新配置代次。只切 MODE 不加载整组参数不算有效切换。此次不增加参数、不改默认值。
- 首个离线 R-ISTA 候选来自 R03 revision11/run029 的完整127项配置：XY=.5/.1/.01/.4/.8，Z=2/1/.02/4/6（依次lambda1/lambda2/epsilon/nu限/纠偏限）。是低增益工程来源，不是 R-ISTA 已验收参数；高增益源包仅用于离线公式核对。
- MODE/AXES/DIV/log parser 和脚本需共同修改。未来按 X→Z→XY→XYZ 门控；不自动放开2/5/6，DIV1，rate MODE0/AXES0/DIV1，MC_RATT_TEST=0、旧起飞管理0。
- 当前生成 ULog format 含 topic名、分隔符和末尾NUL：sta_velocity_ctrl_status=1475字节、velocity_ctrl_selection=708字节；队列均8。前者接近1500字节，优先在后者补 p/h/候选来源/strict 标志，并按 publish_seq/sample 精确关联；RI02 必须重生成、核实完整长度/注册/高频日志/覆盖，不能仅推算。
- 不新占 logger topic 槽来规避历史上限；不修改旧 R03 冻结解析器以认识 MODE4。新解析器单独版本、实际模式拒绝、时钟规则和覆盖测试不可省略。

## 9. 历史限制继续有效

revision11/position11 的完整同刻消息组、reset边界、发布与采样时间白名单、尾部刷新及增量解析规则保留；不能去重后假称没有缺样。IMU 修复的真实调度变化、R03 分组源码/固件差异、有限下游覆盖仍需披露。

RI00 不提供新的全固件构建、起降验收、参数持久化或保护闭环结果。来源成立、公式可复现只是进入独立内核实现的前提，不是飞行准入或 R-ISTA 优于 R-STA/PID 的证据。

## 10. 后续回归继承与版本化要求

继续适用：PositionControl/ControlMath/Takeoff、VelocityControlTest、VelocityDecimationTest 的默认 PID 和原顺序；RegularizedVelocityRegressionTest、StaVelocityControlTest、RegularizedStaVelocityControlTest 的旧算法；VelocityAxes/VelocityZIntegration/VelocityXYZIntegration/RegularizedVelocityIntegration 的轴隔离、保护、HTE、交接和同帧重算；模块/参数测试和 rate 各核回归。RI00 只核实代码未变，不冒充已执行这些整套测试。

需要新增或显式版本化：MODE上限3、只识别variant1/3、MODE4未实现、核未链接/源码逐字节完全不变、固定模块格式长度/参数表等旧断言。保留旧冻结报告和参考原样，建立新阶段基线；不得全局替换旧期望让测试“自然通过”。新核只进入单测目标的 RI01 与生产仍拒绝 MODE4 的 RI02，要分别有无执行器路径检查。

R03 revision11/numeric_adapter.py 的候选复核明确 MODE3 only，不能原地改成4；新 R-ISTA 需要按 RI-1…4 的独立解析器。原 sim_scripts 的 MODE 是角速度模式，不能把它当速度切换入口；后续单独 regularized_ista 工具，不改旧默认目标。
