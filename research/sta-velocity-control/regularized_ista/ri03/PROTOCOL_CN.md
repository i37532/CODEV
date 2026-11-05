# RI03：R-ISTA X 单轴九轮开发协议

日期：2026-10-24。仅 Gazebo Classic Iris SITL。入口为 `research/ista-velocity-regularized` / `e7fb67112e4cf605f5ddf362f120c320a64d2cf5`；[授权记录](AUTHORIZATION_CN.md)只覆盖本阶段。此为飞前协议，不表示任何新测试、资格或飞行已通过。实际源码、固件和参数/模型/分析器身份由本阶段冻结文件及干净资格收据绑定，结果提交不冒充飞行源码。

## 范围、来源与九次清单

比较 PID MODE0、R-STA MODE3 和补偿正则化隐式 R-ISTA MODE4；只选择本地 NED 北向 X，不能将其解释为 roll。MODE4 只开放 AXES1，其他掩码拒绝；PID 使用 AXES0。Y/Z 速度 PID、原位置 P、姿态/rate PID、传感器/滤波/估计器/land detector、既有起降和默认 PID 保持。真实配置必须满足 `MPC_VC_DIV=MC_RTC_DIV=1`、`MC_RTC_MODE=0`、`MC_STA_AXES=0`、`MC_RATT_TEST=0`、`MC_STA_TKO_MGT=0`。旧 ESTA 不产生新统计组。

固定参数来自 [RI00 完整参数来源](../ri00/results/interface.json) 的 `full_r03_parameters`，文件 SHA-256 为 `37729b3d84309c899dce52803c234ef109f738ac0d1a4e1520a729dd18cbeb81`，经 [RI02 配置工具](../ri02/tools/configuration.py)核对。原来源为 R03 revision11/run029 的 127 项实验配置，不是旧 frozen 文件中的原始参数备份。逐轮生成完整参数，只改变 MODE/AXES/TEST，并按原规则保留日志位；不调参。

X/Y 的 lambda1/lambda2/epsilon/nu限/纠偏限为 `.5/.1/.01/.4/.8`，Z 为 `2/1/.02/4/6`；epsilon 单位 m/s，nu/纠偏单位 m/s²。PID 水平 P/I/D 为 `2.16/.48/.24`，Z 为 `4/2/0`；`MPC_LAND_SPEED=.6`、`MPC_USE_HTE=1`。R-STA 与 R-ISTA 使用共同增益、epsilon 和限制；差异包含补偿预测及候选状态进入当前输出，不能称只改变 Euler 离散方式。

| 顺序 | 种子 | 算法 | MODE/AXES | TEST |
|---|---:|---|---|---:|
| run001 | 81001 | PID | 0/0 | 1 |
| run002 | 81001 | RSTA | 3/1 | 1 |
| run003 | 81001 | RISTA | 4/1 | 1 |
| run004 | 81002 | PID | 0/0 | 1 |
| run005 | 81002 | RISTA | 4/1 | 1 |
| run006 | 81002 | RSTA | 3/1 | 1 |
| run007 | 81003 | PID | 0/0 | 1 |
| run008 | 81003 | RSTA | 3/1 | 1 |
| run009 | 81003 | RISTA | 4/1 | 1 |

三组 PID 均是预算内安全门。其余顺序按表交替，三块无法完全平衡，保留次序混杂限制。新预算最多 9 次，旧 R03 的 97 次历史不纳入本轮样本，也不提供追加额度。参数准备/启动一个已登记 attempt 即消费额度，未起飞仍记账。注册时 outcomes 保持全 unattempted，实际状态另记账本及追加式 journal。

种子在仓库 research、外部 experiments 和 plan 全历史 JSON 登记及源码/文档查重；41001–41020 等正式留出、AX 和 R03 已用/弃用/预留种子均不可复用。冻结及启动前复查，只允许精确 SHA 绑定且未尝试的本次注册文件豁免，不豁免整个目录。仅 IMU 显式播种；其他噪声和宿主调度不保证独立。

## 固定 X 任务与起降

复用 [R03 原 X 定义](../../regularized_sta/r03/PROTOCOL_CN.md)及最终 revision11/position11 检查链。唯一目标链为 Navigator→FlightTask→trajectory_setpoint 加既有默认关闭的模块任务适配；中性 RC/GCS 心跳不发布第二套控制目标。保持合法 XY NaN 拓扑和一次有效 FF。

每轮重启，日志首次完整可用后至少预热 30s，再冻结原机载 xyz、heading、参考坐标和 reset 计数。原 commander takeoff 后，仅一次 DO_REPOSITION 建立原目标链的固定 XY、2.5m 高度和固定 yaw；不得用当前位置 Hold 或 Gazebo 真值替换。进入条件是高度 2–3m、`|vz|<.2m/s` 连续 3s、Z 目标误差≤.05m、目标 `|vz|≤.05m/s`；gate 后 10s 内就绪，12s 后开始波形。保留原一次命令 ACK、坐标与允许的起飞准备 heading 事件检查，不给落地 reset 例外。

令 `t` 为真实 sample 时间相对激励 gate 减 12s。在 `0<t<32s`：

```text
u(t) = .2 sin(2πt/8) sin²(πt/32) m/s
vx_target += u(t)
```

窗外附加量为 0；四周期、端点光滑、完整附加速度积分为零。这不承诺实际位置精确回零；原位置 P 仍回拉。不得把波形导数再加到 FF。主窗 32s、前后半窗各 16s；观察 90s，接受区间 90–92s，任务结束后的稳定段仍完整保留。原 auto:land 后等待自动上锁、完整落地封口与尾窗，不截断日志。

## 数值安全、有效性与开发风险

阈值来源为 [R03 协议第4节](../../regularized_sta/r03/PROTOCOL_CN.md)、[AX04 冻结覆盖项](../../axis_ablation/ax04/execution.json)及最终 [position11 审计](../../reports/R03_POSITION11_OFFLINE.md)。V00/V01 已见 PID 噪声尺度 X/Y/Z 为 `.010751/.008080/.005138m/s`，是旧开发依据，不能称新留出。下列规则不根据 RI03 新结果调整。

| 检查 | 冻结规则 |
|---|---|
| 每轴速度风险 | 每个候选≤`1.25×同种子PID+[.02,.02,.01]m/s`，主窗及两个半窗逐轴检查 |
| 位置/yaw 风险 | 90s 每轴位置RMSE≤`1.25×PID+.05m`；yaw RMSE≤`1.25×PID+.02rad` |
| 约束 | 占比≤.05，最长连续≤.5s |
| 物理安全 | 倾角≤15°，XY速≤1m/s，位置偏移≤2m，观察`|vz|≤.6m/s`，名义2.5m高度偏差≤1m，yaw偏差≤20° |
| 状态 | 故障/回退/首调用失败/同帧retry为0；实际模式/轴/DIV/内环正确，完整reset与健康规则通过 |
| sample/诊断 | raw_dt为实际sample差且在[.002,.04]s；诊断最大间隙.04s；X主窗≥3190样本且span≥31.96s |
| 日志/下游 | dropout=0，必要序号缺失=0；精确输出覆盖≥.8、最大空洞≤.25s、已匹配输出差0；不补造缺测 |
| 配对播种 | 前5000条IMU创新，同种子最大差严格<1e−10，异种子严格>1e−6，沿用实际runner边界 |

每对包括主速度3、半窗速度6、位置3、yaw1共13项不等式。R-STA/R-ISTA 各与同种子 PID 比较，共6对；性能未赢不自动无效。Y/Z 非命令轴仍逐轴检查，不能只报 X 或 J。

R-ISTA 数学与状态检查原样继承 [RI02 分析器](../ri02/tools/analyzer.py)：scaled隐式残差≤3e−6，理想输出/纠偏clip绝对容差2e−6，保护nu容差2e−7，状态上限容差1e−6，epsilon容差1e−7；核 h 必须逐值等于 raw_dt。实际纠偏及新旧诊断对应载荷逐值一致；Y/Z 隐式字段保持 NaN、实际 PID 纠偏一致。理想输出使用 nu_candidate，冻结/限幅后的状态不重新伪装成严格隐式解；strict位按真实未保护条件核验。

## 完整日志链、资产与资格

复用并冻结 revision11 的 prearm04 增量准备→warmup10 相对预热→position11 双时钟链及完整科学分析。publication 不倒退、sample 严格递增、publish/log 序号连续；同 publication 完整组和严格前驱全部保留，逐条检查载荷、reset、reference、健康及故障。位置 raw/排队镜像重叠载荷逐位相同，不全话题去重。在线结束封口等待位置和姿态的更晚 publication；保持500ms运输新鲜度、40ms位置间隙、20ms目标配对新鲜度及原落地 pending/尾窗规则。

启动器为 `./sitl/run.sh --headless --backend gazebo --model iris`，1×仿真、`sitl/worlds/empty_grey.world`。沿用 AX02/AX04 合格软接触 Iris（kp2500、kd50、max_vel.2、max_contacts4），派生模型 SHA-256 为 `fe9900329b47f3afb3f2aafac164af047a6feb0e676ea74e658ada5e887b5150`，world 为 `09d9a334728b35a5ca0392e8751e3df5b8aea8b1d5019f8e850a4b0b8bc57b96`。既有 `VELOCITY-STA-20260923/V04/plugins01` 的插件/manifest、原模型、全部依赖和33子模块由冻结清单逐项绑定；保留未使用插件的指纹不表示新增扰动。

执行顺序是实际非零离线验证→冻结并提交→同门干净源码重新构建/资格→准确九次清单→独立完整解码与配对→单独结果提交。旧R03资格及RI02离线PASS不授权当前固件。项目启动器可能重构建，因此 startup 后、takeoff 前仍核对实际二进制 SHA。默认dry-run，执行必须显式参数及本阶段准确资格绑定，不能自行制造通过收据。

先验证正负方向、真实sample周期和内环/电机滞后的独立对象，以及参数保存重启、armed修改/取消、disarm/reset、故障/termination和完整接线。固定 h 理想关系与实际约100Hz、典型8/12ms及噪声/限幅/滞后对象分列；不套源包5ms或高增益。RI01/RI02极小float数值域拒绝仍保留，不静默冲零或临时PID接管；18条旧提前停止和6条不可行限幅反例不能写成全部收敛。MATLAB未重跑则明确记载。

逐轮完整BSON备份、完整参数写入与实际读回；原SDLOG_PROFILE位按位保留并OR16/1024/2048，原冻结值3089。启动前容量检查及逐轮磁盘/tmpfs余量规则保留。只管理自有进程，停止后才精确恢复原参数；原始ULog、启动/命令/目标/失败证据持久归档并核验SHA后，才释放本轮tmpfs。不得删除历史换空间。

## 判决、指标与收口

首个安全、必需有效性、配对风险、日志、归档或清理/恢复失败立即停批。保存所有尝试、未起飞、失败和未执行项；不补飞、不换种子、不重试、不调参、不扩预算、不改门槛、不以旧飞行补样本。只有9接受、9独立完整回放、6对全部风险检查以及参数恢复全部真实完成，才可验收；否则如实记 failed/needs_revision/blocked 及缺口。

报告实际消费 v/v_sp 的逐轴时间加权RMSE、均值/方差，`J=三轴RMSE算术平均`；完整主窗及半窗，位置/高度/yaw、接受率、非命令轴、p/理想nu/应用nu、限制/HTE/交接、实际模式、双时钟和真实更新均保留。共同外部轨迹不等于相同合成v_sp；加速度目标/推力代理不是实测加速度。

TV按真实更新序列，分别报告纠偏、加速度请求和推力，不能称能耗。原生谱与分析专用100Hz ZOH、513tap/8Hz Blackman FIR后25Hz、裁边2.56s、0–7Hz共同带宽口径分列，不用于填补日志。核/模块median/p95/p99/max是宿主耗时，不是板级CPU/WCET。每算法n=3，仅作开发描述；R-ISTA对R-STA可描述，不预设获胜或宣称正式显著性/实机泛化。

报告记录实际命令、非零数量、退出码、全部失败、未执行项、原始指纹、源码/固件及独立结果提交完整SHA。独立回放必须新进程完整解码并比较数值/类型/顺序及谱，保持原始输入首尾不变；旧失败仅作诊断，不改判。不push，不进入RI04或原R04/R05。
