# PX4 速度环研究：可复制执行提示词

日期：2026-09-19。配套：[TODO与共同规则](</home/yr/Desktop/codev doc/plan/VELOCITY_STA_TODO_CN.md>)｜[进度](</home/yr/Desktop/codev doc/plan/VELOCITY_STA_STATUS_CN.md>)。

一次只复制一个阶段。创建本文件不代表执行；当前应从V00开始。V07可选，不做时V08/V09只按基频比较。E01/E02/E03先批准范围与独立子计划，不能以“继续”默认为扩大范围。

| 阶段 | 提示词用途 | 飞行预算/边界 |
|---|---|---|
| V00 | 基线与接口审计 | 详见下方及TODO，失败停止，不自动补飞 |
| V01 | 选择框架 | 详见下方及TODO，失败停止，不自动补飞 |
| V02 | ESTA速度内核 | 详见下方及TODO，失败停止，不自动补飞 |
| V03 | 公共保护与日志 | 详见下方及TODO，失败停止，不自动补飞 |
| V04 | ESTA X单轴 | 详见下方及TODO，失败停止，不自动补飞 |
| V05 | ESTA XY双轴 | 详见下方及TODO，失败停止，不自动补飞 |
| V06 | 脚本与任务回归 | 详见下方及TODO，失败停止，不自动补飞 |
| V07 | 速度分频与耗时（可选） | 详见下方及TODO，失败停止，不自动补飞 |
| V08 | 公平调参与正式协议 | 详见下方及TODO，失败停止，不自动补飞 |
| V09 | 正式留出实验 | 详见下方及TODO，失败停止，不自动补飞 |

## V00 — 基线与接口审计

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_TODO_CN.md 的 V00。
完整阅读该计划及共同规则、VELOCITY_STA_STATUS_CN.md 和本阶段前置报告；首次执行还读取计划指定的旧研究经验与日志审计。核对 /home/yr/Desktop/Codev-autopilot 位于 research/sta-velocity-control，并记录 HEAD、工作区、递归子模块；不回退、不清理已有改动。
主线固定原位置 P、姿态控制、Z 速度 PID（除非本阶段明确获准）和角速度 PID；实际核实 MC_RTC_MODE=0、MC_STA_AXES=0、MC_RTC_DIV=1、MC_RATT_TEST=0，关闭旧实验起飞管理。仅 Iris Gazebo SITL，沿用项目启动器，不继续旧 ISTA 实验、不部署实机。
该分支已创建，从现场核实的当前HEAD建立速度PID基线，不删除重建，不回退main。核对外部三份计划与仓库plan/v1初始快照；将本阶段计划/工具纳入明确提交。
完整审计 PositionControl::_positionControl/_velocityControl/_accelerationControl、模块Run/HTE/Takeoff/failsafe。记录NED坐标、目标与加速度FF、XY成对NaN、Z混合速度、参数联动、reset和同帧二次update；记录实际timestamp与timestamp_sample及周期，不能假定250Hz。
冻结当前原PositionControl/ControlMath/Takeoff参考、模型/world、参数、环境和随机源。构建SITL并执行实际非零PositionControl、ControlMath、Takeoff与RateControl测试。
先提交PID-only协议/运行器；计划最多3次新基线尝试，每轮重启、预热、起飞约2.5m、悬停60s、降落上锁，任何必需检查失败立即停止。冻结唯一目标源、安全阈值及起降窗口；核对实际内环PID并备份恢复参数，保存状态/输出/ULog指纹与基线指标。没有完成3轮不能验收V00。
记录实际非零测试数量、命令、退出码、未执行项与失败；依赖缺失标 blocked，未达标标 failed/needs_revision，不能伪造通过。
需要飞行时先冻结并提交准确场景/参数/阈值/种子/顺序/预算，在干净源码提交运行，再提交结果；失败停止，不自动重试、补飞、扩预算或改阈值。使用新外部数据目录并保留原始指纹。
完成 research/sta-velocity-control/reports/V00.md，审查 diff，明确文件列表提交，提交后核对并更新外部进度表完整 SHA；不 push、不自动进入下一阶段。
```

## V01 — 选择框架

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_TODO_CN.md 的 V01。
完整阅读该计划及共同规则、VELOCITY_STA_STATUS_CN.md 和本阶段前置报告；首次执行还读取计划指定的旧研究经验与日志审计。核对 /home/yr/Desktop/Codev-autopilot 位于 research/sta-velocity-control，并记录 HEAD、工作区、递归子模块；不回退、不清理已有改动。
主线固定原位置 P、姿态控制、Z 速度 PID（除非本阶段明确获准）和角速度 PID；实际核实 MC_RTC_MODE=0、MC_STA_AXES=0、MC_RTC_DIV=1、MC_RATT_TEST=0，关闭旧实验起飞管理。仅 Iris Gazebo SITL，沿用项目启动器，不继续旧 ISTA 实验、不部署实机。
确认V00通过。实现速度controller selector/dispatcher、独立MPC_VC_MODE/MPC_VC_AXES元数据和requested/effective/pending/reject，名称先查冲突。只允许原速度PID生效，MODE1/2及未开放轴显式拒绝。
默认PID数学、状态更新顺序、NaN/前馈、速度/倾角/推力约束、HTE和原PID参数更新语义完全保留。对照V00冻结参考至少两组各2048步逐样本回归，覆盖XYZ、非零速度/加速度FF、ARW、HTE、起飞ramp、reset及failsafe同帧二次update；非法模式/armed暂存取消/disarm生效/重启单测。
编译并确认实际非零测试；先提交协议/源码，执行1次PID起降冒烟，实际解码选择与rate模式，不能以构建成功代替飞行。
记录实际非零测试数量、命令、退出码、未执行项与失败；依赖缺失标 blocked，未达标标 failed/needs_revision，不能伪造通过。
需要飞行时先冻结并提交准确场景/参数/阈值/种子/顺序/预算，在干净源码提交运行，再提交结果；失败停止，不自动重试、补飞、扩预算或改阈值。使用新外部数据目录并保留原始指纹。
完成 research/sta-velocity-control/reports/V01.md，审查 diff，明确文件列表提交，提交后核对并更新外部进度表完整 SHA；不 push、不自动进入下一阶段。
```

## V02 — ESTA速度内核

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_TODO_CN.md 的 V02。
完整阅读该计划及共同规则、VELOCITY_STA_STATUS_CN.md 和本阶段前置报告；首次执行还读取计划指定的旧研究经验与日志审计。核对 /home/yr/Desktop/Codev-autopilot 位于 research/sta-velocity-control，并记录 HEAD、工作区、递归子模块；不回退、不清理已有改动。
主线固定原位置 P、姿态控制、Z 速度 PID（除非本阶段明确获准）和角速度 PID；实际核实 MC_RTC_MODE=0、MC_STA_AXES=0、MC_RTC_DIV=1、MC_RATT_TEST=0，关闭旧实验起飞管理。仅 Iris Gazebo SITL，沿用项目启动器，不继续旧 ISTA 实验、不部署实机。
确认V01通过。在mc_pos_control范围实现独立StaVelocityControl纯C++14内核/包装，不接实际输出。采用s=v−v_sp（m/s）、a_sta和nu（m/s²）、lambda2（m/s³），旧nu算输出再提交；独立evaluate/commit/reset及三轴状态。
输出是加速度纠偏，不套用角速度g、不重复除质量。原加速度FF仅在适配层加一次；若复用纯核g=1，说明仅是接口恒等映射，并不证明真实加速度响应无滞后。
测试正负/零/非零nu、异常dt/参数/数值、状态隔离及陈旧候选；用独立双精度参考和独立ZOH对象验证恒定/斜坡扰动、变化目标、非零FF以及受约束/滞后情形。周期根据V00实际日志冻结。回归原速度PID和角速度内核，构建，核实新算法不可生效；本阶段不飞行。
记录实际非零测试数量、命令、退出码、未执行项与失败；依赖缺失标 blocked，未达标标 failed/needs_revision，不能伪造通过。
需要飞行时先冻结并提交准确场景/参数/阈值/种子/顺序/预算，在干净源码提交运行，再提交结果；失败停止，不自动重试、补飞、扩预算或改阈值。使用新外部数据目录并保留原始指纹。
完成 research/sta-velocity-control/reports/V02.md，审查 diff，明确文件列表提交，提交后核对并更新外部进度表完整 SHA；不 push、不自动进入下一阶段。
```

## V03 — 公共保护与日志

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_TODO_CN.md 的 V03。
完整阅读该计划及共同规则、VELOCITY_STA_STATUS_CN.md 和本阶段前置报告；首次执行还读取计划指定的旧研究经验与日志审计。核对 /home/yr/Desktop/Codev-autopilot 位于 research/sta-velocity-control，并记录 HEAD、工作区、递归子模块；不回退、不清理已有改动。
主线固定原位置 P、姿态控制、Z 速度 PID（除非本阶段明确获准）和角速度 PID；实际核实 MC_RTC_MODE=0、MC_STA_AXES=0、MC_RTC_DIV=1、MC_RATT_TEST=0，关闭旧实验起飞管理。仅 Iris Gazebo SITL，沿用项目启动器，不继续旧 ISTA 实验、不部署实机。
确认V02通过。实现加速度域公共保护及生命周期，明确限速、倾角、总推力、Z优先/XY余量与实际控制输出的关系；不能直接复用机体mixer正负位或原PID的2/Kp tracking ARW修改nu。
测试NaN使能、XY成对、地面抑制、起飞取消/接触/弹跳/超时、HTE、EKF各类reset、测量无效/恢复、退出/重入、armed参数暂存、同一sample failsafe二次update；每采样候选最多提交一次。
审计时间源，同时记录local_position.timestamp和timestamp_sample；保留默认PID旧dt语义，新算法检查raw_dt但不得clamp掩盖异常。实际输出/保护代理/理想候选分别命名，不把推力映射代理称实际加速度。
新增独立sta_velocity_ctrl_status，核实ULog格式长度、队列和注册；分析器覆盖错模式/错内环/错时间/缺样拒绝。先提交，在1次PID小速度任务中真实解码，核对PID等价并固定可实现的下游部分覆盖标准。MODE1仍不可用。
用PID证据固定V04量化安全、性能、非命令轴和日志条件，不用新算法结果定阈值。
记录实际非零测试数量、命令、退出码、未执行项与失败；依赖缺失标 blocked，未达标标 failed/needs_revision，不能伪造通过。
需要飞行时先冻结并提交准确场景/参数/阈值/种子/顺序/预算，在干净源码提交运行，再提交结果；失败停止，不自动重试、补飞、扩预算或改阈值。使用新外部数据目录并保留原始指纹。
完成 research/sta-velocity-control/reports/V03.md，审查 diff，明确文件列表提交，提交后核对并更新外部进度表完整 SHA；不 push、不自动进入下一阶段。
```

## V04 — ESTA X单轴

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_TODO_CN.md 的 V04。
完整阅读该计划及共同规则、VELOCITY_STA_STATUS_CN.md 和本阶段前置报告；首次执行还读取计划指定的旧研究经验与日志审计。核对 /home/yr/Desktop/Codev-autopilot 位于 research/sta-velocity-control，并记录 HEAD、工作区、递归子模块；不回退、不清理已有改动。
主线固定原位置 P、姿态控制、Z 速度 PID（除非本阶段明确获准）和角速度 PID；实际核实 MC_RTC_MODE=0、MC_STA_AXES=0、MC_RTC_DIV=1、MC_RATT_TEST=0，关闭旧实验起飞管理。仅 Iris Gazebo SITL，沿用项目启动器，不继续旧 ISTA 实验、不部署实机。
确认V03验收和日志规范已固定。只开放速度MODE1/AXES1，Y/Z速度PID、全部rate PID；3/7仍拒绝。X为本地NED北向，不是roll。
先验证正负加速度纠偏、模型方向和带内环/电机滞后的独立对象。X/Y目标必须都合法，不能为单轴制造非法半组NaN；保持原目标/FF和唯一发布者。
冻结一个安全候选和小幅零净位移速度正弦，固定yaw、约2.5m高度及起降；3个新配对开发种子，PID/ESTA各3次，共6次，无额外自动调参。
合成与生命周期/重启/切换测试通过后，先提交协议/源码再飞。解码X误差、Y/Z非命令轴、高度/yaw、位置偏移、nu、限制和真实输出；按预定配对规则验收，任何失败停止，不扩大XY。
记录实际非零测试数量、命令、退出码、未执行项与失败；依赖缺失标 blocked，未达标标 failed/needs_revision，不能伪造通过。
需要飞行时先冻结并提交准确场景/参数/阈值/种子/顺序/预算，在干净源码提交运行，再提交结果；失败停止，不自动重试、补飞、扩预算或改阈值。使用新外部数据目录并保留原始指纹。
完成 research/sta-velocity-control/reports/V04.md，审查 diff，明确文件列表提交，提交后核对并更新外部进度表完整 SHA；不 push、不自动进入下一阶段。
```

## V05 — ESTA XY双轴

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_TODO_CN.md 的 V05。
完整阅读该计划及共同规则、VELOCITY_STA_STATUS_CN.md 和本阶段前置报告；首次执行还读取计划指定的旧研究经验与日志审计。核对 /home/yr/Desktop/Codev-autopilot 位于 research/sta-velocity-control，并记录 HEAD、工作区、递归子模块；不回退、不清理已有改动。
主线固定原位置 P、姿态控制、Z 速度 PID（除非本阶段明确获准）和角速度 PID；实际核实 MC_RTC_MODE=0、MC_STA_AXES=0、MC_RTC_DIV=1、MC_RATT_TEST=0，关闭旧实验起飞管理。仅 Iris Gazebo SITL，沿用项目启动器，不继续旧 ISTA 实验、不部署实机。
确认V04通过。开放速度AXES3，X/Y独立参数、nu及原子提交，Z速度PID和rate PID保持不变。7仍明确拒绝。
冻结一轮内的X、Y正负和XY组合激励，先做独立模型与状态隔离/耦合保护测试；记录水平矢量限制及垂直推力优先对各轴的影响。
固定一组参数、3个新配对种子、PID/ESTA各3轮共6轮。先提交协议/源码再运行；每个窗口分别检查XY及非命令轴，复跑X，检查重启/1与3切换/armed修改拒绝/disarm清状态。
冻结合格XY配置，结论只写“XY ESTA + Z PID”，不能称完整三轴ESTA。
记录实际非零测试数量、命令、退出码、未执行项与失败；依赖缺失标 blocked，未达标标 failed/needs_revision，不能伪造通过。
需要飞行时先冻结并提交准确场景/参数/阈值/种子/顺序/预算，在干净源码提交运行，再提交结果；失败停止，不自动重试、补飞、扩预算或改阈值。使用新外部数据目录并保留原始指纹。
完成 research/sta-velocity-control/reports/V05.md，审查 diff，明确文件列表提交，提交后核对并更新外部进度表完整 SHA；不 push、不自动进入下一阶段。
```

## V06 — 脚本与任务回归

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_TODO_CN.md 的 V06。
完整阅读该计划及共同规则、VELOCITY_STA_STATUS_CN.md 和本阶段前置报告；首次执行还读取计划指定的旧研究经验与日志审计。核对 /home/yr/Desktop/Codev-autopilot 位于 research/sta-velocity-control，并记录 HEAD、工作区、递归子模块；不回退、不清理已有改动。
主线固定原位置 P、姿态控制、Z 速度 PID（除非本阶段明确获准）和角速度 PID；实际核实 MC_RTC_MODE=0、MC_STA_AXES=0、MC_RTC_DIV=1、MC_RATT_TEST=0，关闭旧实验起飞管理。仅 Iris Gazebo SITL，沿用项目启动器，不继续旧 ISTA 实验、不部署实机。
确认V05通过。为速度研究建立独立start.sh/switch.sh/fly.sh及简易中文README，沿用原项目启动器，不改变旧sim_scripts默认目标。落地上锁后切换，加载固定XY配置并核验rate实际PID，参数备份/恢复完整。
任务为hover、固定yaw低速figure8、平移伴随平滑heading变化。原位置P仍工作，原加速度FF仅使用一次；说明不同算法实际合成的速度目标未必逐样本相同。
冻结三任务×PID/ESTA×3个新配对种子=18次清单。先提交再运行，按任务逐门，失败立即停止。记录速度/位置误差、yaw/Z、nu、加速度/推力限制、实际模式和日志覆盖。
生成ULog指纹、metrics/result、参数和目标记录，README说明PlotJuggler应看的字段。脚本默认清单/预检，明确执行才飞，不自动扩展强机动或ISTA。
记录实际非零测试数量、命令、退出码、未执行项与失败；依赖缺失标 blocked，未达标标 failed/needs_revision，不能伪造通过。
需要飞行时先冻结并提交准确场景/参数/阈值/种子/顺序/预算，在干净源码提交运行，再提交结果；失败停止，不自动重试、补飞、扩预算或改阈值。使用新外部数据目录并保留原始指纹。
完成 research/sta-velocity-control/reports/V06.md，审查 diff，明确文件列表提交，提交后核对并更新外部进度表完整 SHA；不 push、不自动进入下一阶段。
```

## V07 — 速度分频与耗时（可选）

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_TODO_CN.md 的 V07。
完整阅读该计划及共同规则、VELOCITY_STA_STATUS_CN.md 和本阶段前置报告；首次执行还读取计划指定的旧研究经验与日志审计。核对 /home/yr/Desktop/Codev-autopilot 位于 research/sta-velocity-control，并记录 HEAD、工作区、递归子模块；不回退、不清理已有改动。
主线固定原位置 P、姿态控制、Z 速度 PID（除非本阶段明确获准）和角速度 PID；实际核实 MC_RTC_MODE=0、MC_STA_AXES=0、MC_RTC_DIV=1、MC_RATT_TEST=0，关闭旧实验起飞管理。仅 Iris Gazebo SITL，沿用项目启动器，不继续旧 ISTA 实验、不部署实机。
本次授权仅为V07，确认V06通过。新增独立MPC_VC_DIV=1/2/4，rate的MC_RTC_DIV固定1，不修改传感器/滤波。实测速度频率后命名。
仅速度纠偏及其积分/nu按N更新；位置P、FF、推力转换、约束、HTE、起降/故障仍每有效回调处理。保持未加FF的纠偏，不保持旧总推力；HTE导致的积分变化要同步缓存或使其失效并有测试。
原PID N1逐位等价；真实h、非均匀时间、重复/倒退/长停顿、保持期间新目标/FF/HTE/故障、约束区间汇总和无重复积分先离线验证。
冻结N1→2→4三门，每档PID/ESTA各3轮共18次，先提交再飞，前门失败不得降频。TV按真实更新，共同带宽频谱抗混叠；报告核路径与模块宿主墙钟，不当板级CPU结果。
记录实际非零测试数量、命令、退出码、未执行项与失败；依赖缺失标 blocked，未达标标 failed/needs_revision，不能伪造通过。
需要飞行时先冻结并提交准确场景/参数/阈值/种子/顺序/预算，在干净源码提交运行，再提交结果；失败停止，不自动重试、补飞、扩预算或改阈值。使用新外部数据目录并保留原始指纹。
完成 research/sta-velocity-control/reports/V07.md，审查 diff，明确文件列表提交，提交后核对并更新外部进度表完整 SHA；不 push、不自动进入下一阶段。
```

## V08 — 公平调参与正式协议

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_TODO_CN.md 的 V08。
完整阅读该计划及共同规则、VELOCITY_STA_STATUS_CN.md 和本阶段前置报告；首次执行还读取计划指定的旧研究经验与日志审计。核对 /home/yr/Desktop/Codev-autopilot 位于 research/sta-velocity-control，并记录 HEAD、工作区、递归子模块；不回退、不清理已有改动。
主线固定原位置 P、姿态控制、Z 速度 PID（除非本阶段明确获准）和角速度 PID；实际核实 MC_RTC_MODE=0、MC_STA_AXES=0、MC_RTC_DIV=1、MC_RATT_TEST=0，关闭旧实验起飞管理。仅 Iris Gazebo SITL，沿用项目启动器，不继续旧 ISTA 实验、不部署实机。
确认V06通过；只有V07也通过且用户选择纳入时才包含分频。比较速度PID与XY ESTA，其余环和Z速度PID固定；新实验不使用旧结果作为未见留出。
先冻结并提交等额训练协议：推荐每算法3候选×2训练场景×2种子=12次；选中各1候选后，每算法2场景×3独立验证种子=6次，共36次训练/验证。精确范围、失败惩罚、选择/早停、顺序和新种子登记在执行前固定，不给落后算法追加机会。
正式核心候选为5场景×2算法×20配对种子=200次：悬停、固定yaw8字、平移+航向变化、8字+平滑水平外力、8字+质量变化。DIV2/4若获准再各加1场景，总280次，不自动跑全组合。
外力单位/坐标和质量-惯量-重心/HTE说明完整；新场景未有安全先导证据时先提出准确额外先导预算待确认，不能直接使用正式种子。训练/验证/先导/正式互斥，说明20种子的精度依据和随机源限制。
冻结每轴速度RMSE、XY主指标、位置误差、约束/接受率、TV/频谱/成本、配对CI、多重比较和缺失处理；保存完整源码/参数/模型/插件/分析器及逐轮清单。
本阶段可执行已冻结预算内训练与验证，但不运行正式留出；报告下一阶段准确预算后停止。
记录实际非零测试数量、命令、退出码、未执行项与失败；依赖缺失标 blocked，未达标标 failed/needs_revision，不能伪造通过。
需要飞行时先冻结并提交准确场景/参数/阈值/种子/顺序/预算，在干净源码提交运行，再提交结果；失败停止，不自动重试、补飞、扩预算或改阈值。使用新外部数据目录并保留原始指纹。
完成 research/sta-velocity-control/reports/V08.md，审查 diff，明确文件列表提交，提交后核对并更新外部进度表完整 SHA；不 push、不自动进入下一阶段。
```

## V09 — 正式留出实验

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_TODO_CN.md 的 V09。
完整阅读该计划及共同规则、VELOCITY_STA_STATUS_CN.md 和本阶段前置报告；首次执行还读取计划指定的旧研究经验与日志审计。核对 /home/yr/Desktop/Codev-autopilot 位于 research/sta-velocity-control，并记录 HEAD、工作区、递归子模块；不回退、不清理已有改动。
主线固定原位置 P、姿态控制、Z 速度 PID（除非本阶段明确获准）和角速度 PID；实际核实 MC_RTC_MODE=0、MC_STA_AXES=0、MC_RTC_DIV=1、MC_RATT_TEST=0，关闭旧实验起飞管理。仅 Iris Gazebo SITL，沿用项目启动器，不继续旧 ISTA 实验、不部署实机。
确认V08协议、训练/验证和场景先导全部完成，明确准确预算与已冻结逐轮清单。只在对应干净源码/固件/参数/模型/插件和分析器上执行，内层实际PID和实际速度算法/轴/频率必须与任务标签一致。
按冻结规则执行，首个安全或必需数据失败即停止，保留已完成/未运行清单；不自动豁免、补飞、扩预算或调参，不继承旧M10豁免。
以独立运行/种子块统计，分开完成率与接受率，主指标按真实时间和预定窗口计算；每轴速度/位置误差、约束、TV/共同频谱与宿主成本一起报告，缺失不填成零误差，不只展示成功数据。
原始大日志外部保存，仓库提交配置、摘要/图表、失败列表、路径/指纹和复现方法；独立目录重分析验证结果。准确报告实际完成数、缺失和协议偏离，不强求ESTA所有指标更优，不执行E扩展。
记录实际非零测试数量、命令、退出码、未执行项与失败；依赖缺失标 blocked，未达标标 failed/needs_revision，不能伪造通过。
需要飞行时先冻结并提交准确场景/参数/阈值/种子/顺序/预算，在干净源码提交运行，再提交结果；失败停止，不自动重试、补飞、扩预算或改阈值。使用新外部数据目录并保留原始指纹。
完成 research/sta-velocity-control/reports/V09.md，审查 diff，明确文件列表提交，提交后核对并更新外部进度表完整 SHA；不 push、不自动进入下一阶段。
```

## 可选扩展：先做协议，不立即接入

### E01 — Z/XYZ 可行性与协议

```text
请仅为速度研究E01建立可执行子计划，不改生产代码、不飞行。
完整阅读VELOCITY_STA_TODO_CN.md共同规则和V06验收，核对research/sta-velocity-control。
审计Z速度的NED符号、重力与HTE积分转换、Z测量混合、Takeoff依赖Z Kp的ramp、推力限制/接触和失效策略；明确XY基准与Z纯PID对照。
拆成离线→Z小幅→XYZ子门，预先给出阈值、算法参数域、每门至少3配对重复及准确新增预算；如需改变上游模块列为单独授权事项。写E01_PLAN.md并更新进度，等待用户确认，不push、不启动实验。
```

### E02 — Proper-ISTA 速度方案

```text
请仅为速度研究E02建立理论/接入子计划，不改生产代码、不飞行。
阅读速度TODO、V06、原I00/I01和保护审计，核对分支。固定Proper Implicit文献版本，映射到s=v−v_sp和a/nu的m/s²接口；原ISTA的h*d只作独立离线机制对照。
明确新模式标识、独立速度状态和前馈时序，不能复制原角速度g或保护重算。拆分内核/独立参考、保护、X、XY及后续公平比较，固定每门测试、停止条件和新增预算。
写E02_PLAN.md并更新进度，待确认；不能以旧角速度算法已编译为由开放速度输出，不push。
```

### E03 — 内外环组合消融

```text
请仅设计速度PID/ESTA × 角速度PID/ESTA的2×2组合实验，不改控制、不飞行。
核验两层各自通过范围及冻结参数，固定同任务、相同新增调参预算、主指标、交互作用分析、独立种子及准确总次数。
保留两个单层变化对照，不将全PID对双层ESTA的结果直接归因于速度环。列出全部前置缺失，写E03_PLAN.md，等待执行授权，不push。
```
