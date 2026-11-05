# RI04：R-ISTA Z 单轴九轮开发协议

日期：2026-10-24。仅 Gazebo Classic Iris SITL，gate B / task Z / TEST2 / 32s。入口分支 `research/ista-velocity-regularized`、HEAD `101d79701b09c764f14ba2290add4a524d44cf3f`；[授权记录](AUTHORIZATION_CN.md)只覆盖本轮。此为飞前协议，不预填任何测试、资格或飞行通过。

依据外部 `VELOCITY_RISTA_TODO_CN.md`、`VELOCITY_RISTA_STATUS_CN.md`、`VELOCITY_RISTA_PROMPTS_CN.md` 的共同规则和本轮明确授权，保留 [RI02](../../reports/RI02.md)、[RI03](../../reports/RI03.md)、[Z02](../../reports/Z02.md)、[Z03](../../reports/Z03.md)、[V06 起降修复](../../reports/V06_SOFT_LANDING.md)、[R02](../../reports/R02.md)、[R03 最终验收](../../reports/R03_ACCEPTANCE_CN.md)、[revision11](../../reports/R03_REVISION11.md) 和 [position11](../../reports/R03_POSITION11_OFFLINE.md) 的边界。旧文档的“尚未授权 RI04”描述属于当时状态，由本次请求新增本轮权限；旧阈值、历史结果和失败不重写。

## 范围、参数与预算

比较 PID MODE0、R-STA MODE3、补偿正则化隐式 R-ISTA MODE4。Z 为本地 NED 向下轴，不是姿态 pitch。生产保留 X/AXES1，只新增 Z/AXES4；MODE4 的 0/2/3/5/6/7 掩码及非 SITL 仍拒绝。本轮 PID 使用 AXES0，其余使用 AXES4。XY 速度 PID、原位置 P、姿态/rate PID、估计器/滤波/land detector、既有起降和默认 PID 不变；所有 PARAM_DEFINE 默认值不变。实际配置必须有 `MPC_VC_DIV=MC_RTC_DIV=1`、`MC_RTC_MODE=0`、`MC_STA_AXES=0`、`MC_RATT_TEST=0`、`MC_STA_TKO_MGT=0`。旧 ESTA 不产生新统计组。

共同 127 项实验配置来自 [RI00 interface.json](../ri00/results/interface.json) 的 `full_r03_parameters`，SHA-256 `37729b3d84309c899dce52803c234ef109f738ac0d1a4e1520a729dd18cbeb81`，经 RI02 配置工具核验。它源于 R03 revision11/run029，不能直接使用其旧 MODE/AXES/TEST，更不能把 frozen 中的原机参数备份当作实验配置。逐轮生成完整配置，只按已冻结任务覆盖 MODE/AXES/TEST 并按原规则保留日志位；不调参。

X/Y 的 lambda1/lambda2/epsilon/nu限/纠偏限为 `.5/.1/.01/.4/.8`，Z 为 **`2/1/.02/4/6`**，不使用源包 Z 高增益。epsilon 为 m/s，nu/纠偏为 m/s²。PID 水平 P/I/D `2.16/.48/.24`、Z `4/2/0`；`MPC_LAND_SPEED=.6`、`MPC_Z_VEL_MAX_DN=.55`、`MPC_USE_HTE=1`。R-STA/R-ISTA 共用增益、epsilon 和限制；差异包括补偿预测及候选状态进入当前输出，不能宣称仅 Euler 方式不同。

| 顺序 | 种子候选 | 算法 | MODE/AXES | TEST |
|---|---:|---|---|---:|
| run001 | 82001 | PID | 0/0 | 2 |
| run002 | 82001 | RSTA | 3/4 | 2 |
| run003 | 82001 | RISTA | 4/4 | 2 |
| run004 | 82002 | PID | 0/0 | 2 |
| run005 | 82002 | RISTA | 4/4 | 2 |
| run006 | 82002 | RSTA | 3/4 | 2 |
| run007 | 82003 | PID | 0/0 | 2 |
| run008 | 82003 | RSTA | 3/4 | 2 |
| run009 | 82003 | RISTA | 4/4 | 2 |

数据根为 `/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI04/B/batch01`。三组 PID 安全门均包含在最多九次内，三块交替顺序无法完全平衡，保留次序混杂限制。attempt 在参数准备/启动前落账即消费额度；未起飞仍计数，outcomes 初始全 unattempted，实际状态保留在账本和追加式 journal。

先对仓库 research、外部 experiments 和 plan 全历史 JSON 登记及源码/文档查重，排除全部已用、登记、弃用、预留和正式留出种子，包括 41001–41020、RI03 三组等。只有查重通过才登记上述候选；冻结/启动复查，只豁免精确 SHA 绑定的本次未尝试注册文件，不豁免目录。仅 IMU 显式播种，不声称其他噪声/宿主调度独立。

## 唯一 Z 任务与完整起降

复用 [R03 原协议](../../regularized_sta/r03/PROTOCOL_CN.md) 和 [原 targets.py](../../regularized_sta/r03/targets.py) 的 B 门，沿最终 revision11/position11 链。唯一目标来源为 Navigator→FlightTask→trajectory_setpoint 加既有模块任务开关；中性 RC/GCS 心跳不产生第二套控制目标。合法 NaN 拓扑、原位置 P 和一次有效 FF 保留。

每轮重启，首个完整自有日志可用后至少预热 30s，再冻结机载 xyz、heading、坐标参考和 reset 计数。原 commander takeoff 后仅一次 DO_REPOSITION，建立固定 XY、相对机载参考的 2.5m 高度和固定 yaw；不用 Gazebo 真值或当前位置 Hold 替换。高度 2–3m、`|vz|<.2m/s` 连续 3s，目标 Z 误差≤.05m、目标 `|vz|≤.05m/s`；gate 后 10s 内就绪、12s 后波形开始。保留一次命令 ACK、坐标及允许的起飞准备 heading 事件规则，不新增落地 reset 豁免。

`t` 是真实 sample 时间相对 gate 减 12s；在 `0<t<32s`：

```text
u(t) = .1 sin(2πt/8) sin²(πt/32) m/s
vz_target = 原位置P输出 + 原有效速度FF + u(t)
```

NED 正号向下，窗外附加量为零，四周期、光滑端点、附加速度完整积分为零；不承诺实际位移回零。记录字段是 `status.excitation` 标量，`excitation_y` 和 `excitation_z` 均为零，不误按字段名丢弃 Z 注入。TEST2 不改原 p_sp/v_ff/a_ff，也不把波形导数加入 FF。逐样本证明位置 P+FF+注入等于消费 v_sp；活动速度 clamp、reset 或缺少消费记录均不能伪装成等式成立。

主窗 32s，两个半窗各 16s；观察 90s，允许90–92s，完整保留任务后的稳定尾段。沿原 auto:land，等待自动上锁、双话题封口和完整尾窗，不截断落地日志。相对名义 2.5m 的高度偏离、对原位置目标的误差、对合成速度目标的跟踪分别解释；Z 波形是 P 之后的附加速度，不是另设一条 Z 位置轨迹，不能把名义高度偏离直接称为合成速度跟踪误差。

## 冻结数值、安全和风险门

数值阈值原样来自 R03 协议第4节、[AX04 execution](../../axis_ablation/ax04/execution.json)、最终 revision11/position11。V00/V01 PID 旧噪声尺度 `.010751/.008080/.005138m/s` 只是已有开发依据，不是新留出。

| 检查 | 规则 |
|---|---|
| 速度风险 | 主窗与两个半窗各轴候选 RMSE≤`1.25×同种子PID+[.02,.02,.01]m/s` |
| 位置/yaw风险 | 90s 每轴位置 RMSE≤`1.25×PID+.05m`；yaw RMSE≤`1.25×PID+.02rad` |
| 约束 | 占比≤.05，最长连续≤.5s |
| 安全 | 倾角≤15°，XY速≤1m/s，位置偏移≤2m，观察`|vz|≤.6m/s`，相对名义2.5m高度偏差≤1m，yaw偏差≤20° |
| 状态 | 故障/回退/首调用失败/同帧retry为0；模式、轴、DIV、内环及完整reset/健康规则正确 |
| sample/诊断 | raw_dt为真实sample差且在[.002,.04]s；最大间隙.04s；Z主窗≥3190样本、span≥31.96s |
| 日志/下游 | dropout=0、必要序号缺失=0；精确输出覆盖≥.8、含边界最大空洞≤.25s、匹配输出差0；不重建缺失 |
| 播种 | 前5000条IMU创新同种子最大差严格<1e−10、异种子严格>1e−6，沿实际runner边界 |

每对13项：主速度3、半窗速度6、位置3、yaw1。R-STA/R-ISTA 对同种子 PID 共6对、78项；主窗及非命令 XY 轴均不可省略。没有赢过 PID 不自动失效，风险越界必须停批。

RI02 数学检查原样继承：scaled隐式残差≤3e−6，理想输出/clip绝对容差2e−6，保护nu容差2e−7，上限容差1e−6，epsilon容差1e−7；核 h 逐值等于 raw_dt。核与旧诊断的实际输出逐值一致；XY 隐式字段 NaN、实际 PID 纠偏匹配。理想输出使用 nu_candidate，保护后的 nu_applied 不反向重算 a_ideal；strict 位只代表真实未保护更新。

Z 地面/ramp 使用原 PID，一次 prime 边界后以实际 h 的 `seed=PIDcorr+F_h(s)` 接入，不用 R-STA 的近似 seed。真实 h 有效、限制可行且下游无约束才允许接入；无可行解直接拒绝，不能以裁剪伪称平滑。HTE 只按已闭合、同配置的上一应用纠偏/FF缓存变换：`δ=(hover_old/hover_new−1)×(cached_corr_z+ff_z−g)`；不重算误差、无缓存/不闭合/保护则锁存拒绝，不承诺任意下一帧目标或h下连续。全向量先验后原子提交；same-sample故障回退不额外积分或递增控制序号。

固定 h 理想模型与实际约100Hz、典型8/12ms、噪声/约束/内环电机滞后对象分列。保留极小float数值域拒绝，不静默冲零或临时PID接管；18条旧提前停止和6条不可行限制反例不能写成全部收敛。MATLAB未重跑则明确标注，旧3990参考fixture不能冒充新执行。

## 源码、模型、完整日志与资格

新冻结以 RI03 `gates/A/frozen.json` 为已提交输入，合法重绑定入口源码；不能要求 RI04 生产改动仍等于旧 RI03 字节，也不能改写旧冻结。完整 mc_pos_control、RI00–RI03输入、旧 RI03 gates/results/报告、历史入口和新 RI04源/入口均入清单；新结果与本轮 gates 排除自指。只允许本轮明确八条生产/测试路径，全部 PARAM_DEFINE 保持；79外部资产原SHA、33清洁递归子模块、模型/world/插件原身份不变。归档校验检查声称 source_head 的 Git blob/gitlink，不要求当前HEAD或当前生产源码退回历史版本。

启动器 `./sitl/run.sh --headless --backend gazebo --model iris`，1×仿真；world `sitl/worlds/empty_grey.world` SHA `09d9a334728b35a5ca0392e8751e3df5b8aea8b1d5019f8e850a4b0b8bc57b96`。AX02软接触 Iris（kp2500、kd50、max_vel.2、max_contacts4）SHA `fe9900329b47f3afb3f2aafac164af047a6feb0e676ea74e658ada5e887b5150`，质量/惯量/几何/摩擦不改。沿用 `VELOCITY-STA-20260923/V04/plugins01`；保留未使用插件指纹不表示增加扰动。

先真实非零离线验证，再冻结并提交，干净源码重新构建并取得本阶段资格，才能执行准确九轮。资格包括正负方向、真实周期、滞后对象、参数保存/重启、armed修改取消、disarm/reset、HTE、故障/termination和模块接线，及旧 RI03 X 和 R03 B 的独立兼容回放。旧 ESTA 仅旧日志离线覆盖。旧通过收据不能授权新固件；启动器可能重构建，startup后、takeoff前仍核实际二进制SHA。默认dry-run，真实启动需显式执行和当前阶段完整资格绑定。

日志链为 prearm04 增量准备→warmup10相对预热→position11双时钟。publication不倒退、sample严格增、publish/log序号连续，同publication完整组和严格前驱不丢弃，载荷/reset/reference/health逐条核验；raw/排队镜像重叠逐位一致，不全话题去重。结束等待位置和姿态更晚publication；保持500ms运输新鲜度、40ms位置间隙、20ms目标配对及原落地pending/尾窗规则。

逐轮完整BSON备份、完整写入与实际读回；SDLOG_PROFILE保留原位并OR16/1024/2048，原冻结值3089。沿原批前12GiB、逐轮10GiB磁盘和512MiB tmpfs余量规则；只管理本轮自有进程，停止后精确恢复原参数。原始ULog、启动/命令/目标/失败证据持久归档并核SHA后才释放本轮tmpfs，不删除历史换空间。

## 首败停、指标与结案

首个安全、必需有效性、日志、配对风险、归档或清理/恢复失败立即停批；不重试、补飞、换种子、调参、扩预算、改门槛或用旧样本补齐。记录全部attempt、airborne、accepted、failed、unattempted。只有9接受、9独立完整回放、6对风险及恢复/清理全部真实通过，才可验收；否则如实 failed/needs_revision/blocked，不以“未发生飞行”抹去已消费尝试。

报告真实消费 v/v_sp 的逐轴时间加权RMSE、均值/方差、`J=三轴RMSE算术平均`，主窗/半窗、位置/高度/yaw、非命令XY、p/理想nu/应用nu、约束/HTE/交接、真实模式/周期和完整时钟证据。共同外部轨迹不等于相同合成v_sp；加速度请求/推力代理不是真实加速度。

TV按真实更新序列，分纠偏、加速度请求、推力，不能称能耗。原生谱和分析专用100Hz ZOH→513tap/8Hz Blackman FIR→25Hz、裁边2.56s、0–7Hz共同带宽分列，不用于填补原始缺测。核/模块median/p95/p99/max为宿主耗时，不是板级CPU/WCET。n=3仅开发描述，保留顺序/宿主调度限制；不预设R-ISTA胜出、不宣称正式显著性或实机泛化。

报告实际命令、非零数量、退出码、全部失败与未执行项、原始指纹、源码/固件完整SHA、独立结果提交SHA和历史状态差异。独立回放用新进程完整解码，比较数值/类型/顺序/谱，原始证据前后不变；摘要中的nonfinite标签只能描述原指标，不能修改原日志或把无穷限制写成有限通过。RI03和R03结果只作继承/兼容证据，不并入本轮样本。不push、不进入RI05或原R04/R05。
