# R00：当前 PX4 接口与 R-STA 接线审计

日期：2026-10-16。入口源码 `0a5796c3ed69d2e415696cf2450fbde74d56e6ea`，分支 `research/sta-velocity-regularized`。
本项只读源码、参数声明、现有生成消息和历史协议；没有修改生产控制、参数、模型、旧协议或日志，没有飞行、MATLAB、固件构建或运行控制单测。
当前结果为“接口审计通过，可实施独立内核”，不是新算法已接线/已准入。

## 1. 模式、参数与隔离

| 项目 | 当前证据 | 新路径约定 |
|---|---|---|
| `MPC_VC_MODE=0` | 原 PID，AXES=0 | 保持默认及算术/状态时序 |
| MODE=1 | 旧硬 sign ESTA，SITL AXES=1…7 | 全部旧掩码、旧配置保留 |
| MODE=2 | selector 明确 `ModeUnimplemented`，元数据 Reserved | 保留拒绝，不改成 R-STA |
| MODE=3 | 当前 selector `mode > 2` 拒绝，未分配 | 可用独立标识；R02 仍拒绝生产准入，R03 逐门开放1→4→3→7 |
| epsilon 参数 | `src`/`boards` 的 PARAM_DEFINE 声明无同名 | 建议 `MPC_VC_EPS_X/Y/Z`，各12字符，m/s；新算法有限且严格正 |
| 新掩码2/5/6 | 旧 MODE1 已有实现 | 本专项 MODE3 明确拒绝；不能误撤旧 MODE1 能力 |
| 分频 | 旧 PID/X/XY 支持 DIV2/4，含Z及新增混合仅DIV1 | 本专项所有算法固定 DIV1，不自动扩分频 |

参数名无冲突只证明当前声明，R02 仍须检验生成元数据、`param_find`、实际保存/重载。epsilon 数值域和候选由 R00 数学审计及 R01 固定，不在此设新飞行默认。
应复用原 lambda/nu/纠偏限值以支持“同增益只改正则化”比较；epsilon 仅在 MODE3 有效，不能因 MODE1 的 epsilon 为0而拒绝旧配置。

## 2. 当前数据流和真实混合轴

`PositionControl::_positionControl`：位置P＋原速度FF → XY矢量/上下速度约束 → 实际 `_vel_sp`。
速度纠偏使用 `s=_vel-_vel_sp`；这里 `_vel` 的Z可能已由 `vz/z_deriv` 混合，不直接拿未混合 local_position.vz 代替。
新核只给加速度纠偏：纠偏限幅 → 原有效加速度FF一次 → 原倾角/HTE/推力映射 → Z优先、XY余量 → 保护整体裁决 → 状态提交。
`a_sta` 为理想纠偏；`a_req` 为最终加速度需求；`a_proxy=thrust*g/hover_thrust+gravity` 是约束代理，不是实测加速度。

正常空中、三轴速度目标有效且交接结束时：

| AXES | 旧 ESTA 正常轴 | 正常 PID 轴 | 专用函数 |
|---:|---|---|---|
| 0 | 无 | XYZ | `_velocityControlPid` |
| 1 | X | YZ | `_velocityControlEstaX` |
| 2 | Y | XZ | `_velocityControlEstaMixed` |
| 3 | XY | Z | `_velocityControlEstaXY` |
| 4 | Z | XY | `_velocityControlEstaZ` |
| 5 | XZ | Y | `_velocityControlEstaMixed` |
| 6 | YZ | X | `_velocityControlEstaMixed` |
| 7 | XYZ | 无 | `_velocityControlEstaXYZ` |

含Z路径在地面/ramp/contact完整PID、priming一帧有界PID交接，不能称所有时刻均纯STA。X/XY priming仅FF/零纠偏且不补闲置所选轴PID。XYZ正常期不计算闲置PID；不活动所选轴保持加速度-only，不偷偷恢复速度PID。`pid_axes`、`active_axes`、`committed_axes` 和 `z_phase` 必须共同核验。

## 3. 必须同步的四处非线性重构

以下行号属于入口源码 `src/modules/mc_pos_control/PositionControl/PositionControl.cpp`：

| 位置 | 现有用途 | R-STA 必须使用的关系 |
|---|---|---|
| 156，`updateHoverThrust` | 用当前s及nu恢复Z纠偏 | `correction=-lambda1*Psi(s,eps)+nu` |
| 656，Z priming | PID→Z STA状态播种 | `nu=PID_correction+lambda1*Psi(s,eps)` |
| 713，XYZ priming | 全部活动轴有界原子播种 | 同一Psi，先全部验证再播种 |
| 785，XZ/YZ priming | 混合含Z路径播种 | 当前MODE3不开放5/6，但新公共接口不能引入与数学核不一致的重构 |

`Psi(s,eps)` 层内 `s/sqrt(eps)`、层外 `sqrt(abs(s))*sign(s)`。建议新核提供统一可测试非线性接口，四处按显式算法分支调用；旧路径保留原浮点运算顺序，避免无必要的“等价重排”破坏逐位基线。
HTE补偿已经是 `shift=(hover_old/hover_new-1)*(correction+ff-g)`，并检查饱和及nu/纠偏范围。不能退回源包旧ZIP文档中的简化PID积分式，也不能两次补偿。非零s/nu/FF、非零倾角和HTE变化均须验证连续性；裁剪seed不等于连续交接。

## 4. 公共保护、配置和生命周期

- `StaVelocityControl::current` 已检查 owner/axis/sealed_axis/revision/密封payload，`setParameters/reset/commit` 均使旧候选失效。新核不得采用包内“nu数值相等”替代；reset回同值、跨对象/轴、重复提交、epsilon-only修改后旧候选要拒绝。
- `StaVelocityProtection::same` 当前显式比较axes、lambda1/2、nu及纠偏限制；新增variant和epsilon必须进入比较及`validConfig`。`PositionControl::configureVelocityEsta` 还维护 requested/effective/changed/pending/generation，不能只改底层same。失效模式请求不能污染有效增益。
- armed修改仅暂存，恢复有效请求取消pending；disarm后合法整体配置才生效。MODE1↔MODE3、退出/重入、重新解锁需清旧状态及失效未提交候选，不能共享陈旧nu。
- `begin/evaluate/finish` 根据全部活动轴校验候选及proxy后原子提交；每sample最多一次，保留同帧failsafe第二次update拒绝重复积分。保持状态限幅/纠偏限幅/约束方向冻结，允许恢复方向nu增量；不借用机体mixer位或PID `2/Kp` ARW。
- XY目标成对；NaN表示未启用，不替换为零反馈。保持位置/速度/加速度输入原配对规则，含Z混合轴在原输入非法时不能先播种再报错。
- 保留地面抑制、起飞取消/接触/弹跳/超时、测量无效/恢复、EKF reset保守拒绝、mode退出/重入、fault latch及disarm清除。缺真实inner PID/测量/有效输出或termination时不发布失效输出；“不发布/零推力”不等于安全悬停。
- 原位置P、姿态、角速度PID、传感器/滤波、上游估计器、land detector、HTE本身、默认模型禁止改动。

## 5. 时间语义不可照抄源包旧接口

`MulticopterPositionControl::Run` 当前同时记录 local_position.timestamp（发布）和 timestamp_sample（采样）。原 PID/微分器使用发布差clamp到2…40ms；STA保护用采样差，原始差不合格就latch，不能通过clamp掩盖。
DIV1时 `velocity_ctrl_selection.h` 仍是旧PID used_dt；真正STA积分h应按 `sta_velocity_ctrl_status.raw_dt` 核验。DIV>1另有真实sample更新差，本专项不启用。新核不写死5ms，不把旧ZIP的“全部用传入dt”当当前代码约定。
同时保留 publish_seq、update_seq（调用次数含failsafe）、control_seq（真实更新）三者含义。成本为Linux宿主CLOCK_MONOTONIC，不是lockstep HRT、板级CPU或WCET。

## 6. 日志容量和分析链

本次读取现有实际生成C++，按 `Logger::write_format` 的 `topic_name:fields` **连padding及NUL** 核算：

| 话题 | 格式所需字节 | 队列 |
|---|---:|---:|
| sta_velocity_ctrl_status | 1475 / 1500 | 8 |
| velocity_ctrl_selection | 584 / 1500 | 8 |

主诊断余量仅25字节。**优先扩现有selection话题**保存新算法版本、有效epsilon及必要配置代次，用 publish_seq/sample/input_timestamp 与主诊断精确一对一关联；不要将数值字段塞进主诊断触发格式截断，也不要另加话题后忽略当前SITL logger256槽的已用容量。扩selection仍须重新生成、长度检查、排队/缺样负例；不是现有二进制已支持新字段。
既有主诊断已分列nu_before/nu_ideal/nu_applied/a_sta/a_req/a_proxy/thrust，无需新名隐藏旧语义。默认logger100ms与HIGH_RATE全速必须区分，保留SDLOG_PROFILE已有位。

现可复用链条但不能直接运行旧资格：

1. `axis_ablation/ax04/run.py` 的启动/参数备份恢复/唯一logger会话/私有tmpfs归档及软接触资产检查。
2. `ax04/common.py` → `ax02`及`v08/protocol02`共享工具 → V04最终时钟/航向/目标交接 → V06合格接触/降落 → V07位置队列、IMU双时钟和归档规则。
3. `ax04/core.py` + **`ax02/cadence.py`** 重建实际速度、FF、保护、nu、PID剩余轴；此cadence仍硬编码硬sign公式，`if mode`不能自动代表R-STA。新版本必须显式区分0/1/3并验证epsilon/variant，不改旧版本判定。
4. 新运行器/分析器置于regularized_sta，绑定新branch/source-head、参数/协议/固件/分析器指纹及新有限清单；默认dry-run。旧AX04 manifest固定320、旧授权receipt、资格SHA及输出目录不能借来跑R03。

保留 `vehicle_local_position_log` 独立32队列和log_seq、原队列与全部重叠字段逐位检查；不改控制输入。姿态/IMU双时钟仅白名单，sample严格递增、发布非递减、同刻候选歧义及完整前驱/闭边界/reset逐条验证；其他话题不普遍去重/放宽。下游partial coverage如实声明，dropout=0不证明全话题无损。

## 7. R01/R02准确实现与回归范围

R01：独立 `RegularizedStaVelocityControl` C++14（命名可在实现时固定），三轴evaluate/commitProtected/reset、有限参数域/稳定分段Psi/rho与强候选；独立双精度与对象回归。仅核＋测试＋CMake，不向生产dispatcher注册。保留旧内核源码及其回归。

R02：新增新模式元数据但生产准入关闭；配置/保护容纳显式variant和epsilon；统一四处新Psi重构；Module参数读取和requested/effective日志；selection扩字段、实际生成检查；新dry-run工具和显式模式分析器。若采用新公共helper，必须保留旧路径操作顺序和限值规则。

必需离线用例包括：

- PID/旧ESTA 0/1/2/3/4/5/6/7配置，其中MODE0仅AXES0、MODE1为1…7；原路径至少两序列各2048步、XYZ/非零FF/ARW/HTE/NaN/限幅/reset/ramp/failsafe。
- 新0/1/3模式及2拒绝、signed越界、未准入轴、非法epsilon、armed暂存/取消/disarm、BSON保存重载、新对象、epsilon-only代次与跨模式陈旧候选。
- X/XY地面/priming、Z/XYZ地面/ramp/一次有界PID seed/正常纯选中算法、同sample二次update、状态隔离、HTE连续、约束方向与末轴失败原子性。
- PositionControl/ControlMath/Takeoff/RateControl及适用rate内核实际非零执行，SITL构建；实际模块Run/uORB轨迹检查，不把夹具当飞行。
- 新分析器错模式/错误epsilon、错轴/错rate/DIV、错误时间/重复/歧义/reset/缺样/未接管、公式重建错误、日志长度/队列/参数备份恢复/软着陆负例。旧真实日志只读回放，旧判不变。

历史资格检查必须区分：`v08/protocol02.test_tuning.TuningTest.test_original_production_and_launcher_unchanged` 要求自V07源码不变，AX01已明确不适用新授权实现；AX04的500资产/固件资格检查只对旧正式包有效。**不删除旧测试、不把它们伪改为通过，也不据其失败否定新功能；** 新验证器显式标provenance_not_applicable，另建本专项冻结和逐样本基线。控制数学/生命周期/日志负例仍适用，不能一并跳过。

## 8. 本项真实检查、偏差和未执行

命令（cwd为仓库）：

```bash
python3 research/sta-velocity-control/regularized_sta/r00/interface/audit.py
```

最终 **15项源码/生成物断言通过，退出0**；其中参数定义在src/boards全域搜索，四处重构精确定位156/656/713/785，9份源码SHA随stdout输出。不是15个C++控制单测。脚本只输出stdout、不写文件、不启动仿真；后续源码合法改变后这些R00历史断言预期不再全部成立，不能作为R02资格套件。

审计纠正：初稿消息检查曾错误删去padding后计算1453/562字节，检查返回0但口径错误；核对logger.cpp:1480实际snprintf后修为包括全部fields/NUL，最终1475/584。没有据初稿声称已扩字段可用。一次检索不存在的`msg/sta_velocity_aux_status.msg`显示文件不存在，实际没有该话题；新规划改为扩selection而非假定辅助话题已存在。

源码阅读和检索退出0；`git diff --check`另由阶段总验证记录。新增仅本目录audit.py/本说明；未执行生产编译/控制单测/日志完整回放/MATLAB/飞行/调参/实机，未改任何历史日志及资格。数学稳定域与实测周期由R00其他审计项记录，本文件不替代那部分证据。

## 9. 本项阅读清单及最终记录链约定

本项完整读取外部正则化三文档，随后补读其新增2026-10-16连续授权顶部；完整读取旧 `VELOCITY_STA_TODO_CN.md` 396行（含历史更新，不把旧“未通过/不push”误当当前授权）。完整读取以下接口/日志专项资料：

- `reports/AX01.md`，全掩码、真实PID轴、HTE/接管、资格不适用说明。
- `reports/V04_CLOCK_SEMANTICS_AUDIT.md`，93行；同发布时间不能证明同样本/同消费。
- `reports/V04_CLOCK09_REPAIR.md`，80行；姿态白名单、同刻歧义、边界/reset和输出唯一键。
- `reports/V04_IMU0_CHAIN_REPAIR.md`，87行；转换范围/非有限拒绝/裁幅及clipping，保留现有修复、不重新修改上游。
- `v07/imu_clock01/AUDIT_CN.md`；三个IMU实例双时钟与12ms年龄/缺口、完整同刻边界组，不扩白名单。
- `v07/logchain03/PLAN_CN.md`，36行；最终位置独立32队列、log_seq与256槽。
- `v07/logger_file04/AUDIT_CN.md`；无-t既有递增session、唯一文件/归属/不覆盖。
- `v07/pending05/PLAN_CN.md`；pending期间最多8次立即完整监视，宿主和仿真两个500ms界均不放宽。
- `v07/ram_log06/PLAN_CN.md`；显式私有0700 tmpfs、停机后独占归档/fsync/源前后及副本SHA，不删除RAM源或冒称持久黑匣子。
- `v07/target07/PLAN_CN.md`及`v07/protocol07/execution.json`；实际消费setpoint_timestamp精确匹配唯一trajectory源，原40ms年龄与2e-6数值核对，不以最近位置输入时间猜目标。

另检查V07报告最新通过段（1–68行）、AX00/AX05相关日志/版本摘要与当前AX02/AX04实际运行/分析链；并未把这项分工声明为重跑了这些历史阶段或完整读取所有历史结果附录。阶段总报告的其他阅读由主任务分别记录。
只读检索曾猜测 `v07/protocol07/README_CN.md` 不存在（wc命令退出1），随后通过rg定位上述真实规范；一次文件名过滤末尾模式漏`.md`返回1后纠正。均未构成控制或飞行测试失败，不隐瞒为“所有探索命令均0”。
