# 速度环 STA 研究

## 2026-10-08：AX02工具与48轮协议冻结通过（仅离线）

[AX02报告](reports/AX02.md)、[独立入口与清单](axis_ablation/ax02/README_CN.md)：PID/X/Y/Z/XY/XZ/YZ/XYZ固定每轴参数，H24→V24；V首PID为预算内安全门。273 C++/658适用Python、构建及6份旧日志只读回放通过，协议源码 `9f514213a2d9b0d66674367c009e0d8886fe6c39`。新48项全部未尝试，不自动AX03、不push；V08正式200次不变。下方记录保留历史含义。

## 2026-10-05：AX01全掩码离线实现通过，V08正式包保持

[V08报告](reports/V08.md)：公平训练/独立验证和三类安全先导已完成，正式200次协议已冻结但尚未运行；结果05a8ae3b3c已推送。下方旧“最新”保留历史含义。

[按轴消融专项](axis_ablation/README_CN.md)：[AX01报告](reports/AX01.md)完成Y/XZ/YZ实际接线，261 C++/629适用Python通过；保留[AX00审计](reports/AX00.md)。新八组统一参数矩阵尚未飞行验收，默认PID、MODE2拒绝；0新飞行，不自动AX02、不push。开发候选48次、正式候选320次，不改变V08/V09的200次冻结包。

**最新：V07速度分频与耗时已通过开发验收。** [最终报告](reports/V07.md)：第七批18/18轮、9/9配对及独立回放通过，231 C++/503 Python。实际100/50/25Hz；原速度PID对XY ESTA+Z PID，rate全部PID。日志记录链修复完成，前六批失败保留。ESTA的XY误差/TV仍高于PID，不称性能优胜或板级CPU收益。参数已恢复、默认PID，未push，不自动V08/ISTA/实机。[结果与指纹](v07/RESULTS_CN.md)。以下“最新/当前”等保留历史时点。

**最新：V06与SITL软着陆专项已完成开发验收。** [V06报告](reports/V06.md)：新合格接触条件下悬停、固定yaw8字、平滑转向8字共18/18轮、9/9配对及独立回放通过；196 C++/467 Python。ESTA三任务速度RMSE和请求TV均高于PID，不能称性能全面胜出。全部rate PID、默认PID保持，参数完整恢复；旧失败保留，不push、不自动V07/实机。

[软着陆专项报告](reports/V06_SOFT_LANDING.md)：独立6轮/3对通过，只改 opt-in 派生模型接触，不改原控制律/模型默认或健康门槛。[打开Gazebo、切算法、任务及PlotJuggler指南](v06/scripts/README_CN.md)。protocol03本批18轮预算已耗尽，重复实验需另冻新清单，不覆盖旧结果。

## 此前阶段（以下状态保留当时含义）

**当前：E01-XYZ 三轴速度 ESTA 已完成开发验收。** [E01-XYZ报告](reports/E01_XYZ.md)：同一干净源码`045f642bf2`，新22001–22003，PID/XYZ ESTA各3轮，6/6轮与3/3配对及6轮独立回放通过；190 C++/424 Python。XYZ组合窗口X/Y误差降低约54.7%/43.7%，但Z误差约2.39倍、全窗请求TV约7.52/7.72/48.04倍PID，不称全面性能改善。位置P、姿态、全部rate PID保持；默认和实验后参数已恢复PID。[合格XYZ配置](e01_xyz/qualified_xyz.json)。当前路线V05→E01-XYZ→V06，本阶段停止，不push、不执行V06/实机。以下“当前/此前”等保留历史时点含义。

**当前：V05 XY ESTA + Z PID 已完成开发验收。** [V05报告](reports/V05.md)：最终新21001–21003、6/6轮与3/3配对通过，174 C++/421 Python及6轮独立回放通过。X/Y受激励轴误差明显降低，但请求TV约为PID的7–8倍，非命令轴/yaw略有退化且在预设门槛内。保留首批1次工具接线失败；全部rate仍PID，默认PID，未push、不自动进入V06。[合格XY配置](v05/qualified_xy.json)、[冻结protocol02](v05/protocol02/execution.json)。

**此前：Z 速度 ESTA 接入及 Z03 开发验收已完成。** [Z03报告](reports/Z03.md)：同一干净源码`d6ea312f73`、新19001–19003，PID/Z ESTA各3轮，6轮及3组配对全部接受；159个不同C++/399Python、独立6轮回放通过。仅Z速度替换，XY速度和全部rate仍PID。Z速度RMSE均值PID .004073、ESTA .009839m/s，ESTA请求TV明显更大，**不代表性能优于PID**。默认仍PID；历史失败保留，未push、不实机、不扩大XYZ。

此前 [V04 X单轴报告](reports/V04_PROTOCOL17_RESULTS.md)：新17001–17003的6轮及3组配对已通过；不是本次Z配对样本。[Z接线设计](z_velocity/Z02_DESIGN_CN.md)、[当前Z路线](z_velocity/PLAN_CN.md)、[Z使用说明](z_velocity/QUICKSTART_CN.md)。

## 历史进展（下列“最新”等保留当时含义）

最新：[protocol16结果与预解锁参考修订](reports/V04_PROTOCOL16_RESULTS.md)。3轮接受/1组配对，第4轮在起飞前因零宽姿态参考窗口失败，余2停。新参考只选真实更早位置、保持原全部安全/时间规则，9新测试/386Python及真实日志前缀复现完成；旧失败不追认。累计25/10、4组历史配对，未完成新批3组。Z仍离线原型；以下均历史记录。

最新：[protocol15结果与任务窗口日志检查](reports/V04_PROTOCOL15_RESULTS.md)。5轮完整起降、前4接受/2组配对通过，第5轮交接前正常目标清空的同刻记录导致全日志规则拒绝，余1停止。已离线修订前驱/窗口/结束边界完整检查，377Python及10轮隔离回放通过；不追认旧失败，准备新三组批次。Z仍离线原型，未接执行器。以下状态保留历史时点含义。

最新：[protocol14结果与导航目标同刻策略](reports/V04_PROTOCOL14_RESULTS.md)。PID完整起降、raw三秒入口通过；最终被降落期两条逐位相同的目标发布记录拒绝。已做单话题隔离修订/7项测试及365Python回归、五轮完整链回放；未改旧失败或其他话题规则。V04累计16尝试/3接受/1配对，仍待新批次三组验收；Z仍只有离线原型。

当前进展：[protocol13实际结果与入口修复](reports/V04_PROTOCOL13_RESULTS.md)。4轮PID/ESTA均完成起飞—观察—降落上锁，3轮最终接受、1组合格配对；第4轮三秒入口窗口提前112ms，原最终检查正确拒绝，余2停止。实际起降链已打通，原始逐样本入口门控已离线回归；V04仍待3组合格配对。Z01已完成离线原型，Z尚未驱动执行器。以下“最新”等保留历史时点含义。

分支：research/sta-velocity-control；规划起点866bba6e0d200d7a5137146c2a67a1a751e01233。

最新诊断：[单次PID触地高频证据](reports/V04_DIAGNOSTIC11_RESULTS.md)。干净源码55073c29b7、种子11001，完成60.480s观察后因降落EKF参考/reset变化停止；已捕捉−186.6m/s²触地加速度、3个IMU削顶和6实例故障。selector修复后本轮无sample倒退，但仍不是飞行验收通过。原9次加诊断1次合计10尝试/0接受，未补飞；下一步离线验证合法公共下降速度上限0.5m/s，不改控制律/门槛。详细状态以下方最新报告为准。

共同试飞前置修复：[selector时间交接与削顶定位](reports/V04_SELECTOR11_REPAIR.md)。原ULog确认6实例短暂bad_acc_clipping；旧selector过期消息污染发布/reset基准已用真实uORB复现并修复，负对照6/6失败、最终10项通过，总132C++/347Python及构建通过。尚未验证新飞行或消除物理削顶；V04仍未通过，Z生产准入保持关闭。

当前优先：[Z速度ESTA离线原型Z01](reports/Z01.md)，用户追加提前开展Z-only测试。新增16项Z测试及106项既有C++/347Python、构建通过；生产仍拒绝Z/XYZ，尚未模块接线或飞行。后续按[Z路线](z_velocity/PLAN_CN.md)推进，V04仍未通过；普通相关修复/新批次授权沿用用户最新指令，但须新冻协议预算，不恢复旧余量。以下均为历史时点记录。

最新实际结果：[protocol10 / series09](reports/V04_PROTOCOL10_RESULTS.md)。源码d7090c4bc17eae80b88181c8e32dd0ac59d1b868干净验证120个不同C++/347Python后获准执行；首轮PID观察60.120s/激励32s完成，新降落匹配19次正常，随后真实EKF 0→1→3→0、reset与raw_dt=−4ms触发拒绝。1尝试/0接受、ESTA0、余5停止，累计9/0；原日志/参数恢复/失败诊断保留。V04仍未通过，不push、不V05，不自动续飞或修上游。下方状态保留历史时点含义。

2026-09-26 新批次接线：[protocol10 / series09](reports/V04_PROTOCOL10_IMPLEMENTATION.md)。用户条件确认9901–9903各PID→ESTA X最多6次；新降落匹配已接入独立运行/完整分析链。提交前120个不同C++、347 Python及八批回放通过；必须再于干净提交复核才能飞行，首必需失败停批，不push、不V05。下方状态保留历史时点含义。

最新离线修复：[降落时间匹配 landing10](reports/V04_LANDING10_REPAIR.md)。原始命令/状态/诊断匹配、有界 pending、故障锁存与上锁竞态保护已实现；120 个不同 C++ / 最终 334 Python 及只构建通过，八批回放不改判。无新飞行，V04 仍未通过；拟申请 9901–9903 各 PID→ESTA X 最多 6 次，须授权后另冻可执行协议并干净提交复核，入口当前禁用。不 push，不续旧五轮、不 V05。

最新飞行结果：[protocol09 / series08](reports/V04_PROTOCOL09_RESULTS.md)。用户确认后按冻结源码 a361ebda9783dc4bf65cbf6e57cce35520b0fa44 执行，首轮 PID 完成 60.172 秒观察/32 秒激励，但降落监视器将旧 Hold 与新 Gate=2 混合判断而中止；未完成降落上锁。1 尝试/0 接受、ESTA 0、余 5 停止；累计 8/0，V04 仍 failed/needs_revision。302 Python 与 18 项只读诊断通过，不等于飞行验收；失败/导入错误均保留、参数恢复，未修运行器或续飞、不 push、不 V05。以下“最新/待授权”等保留历史时点含义。

最新离线修订：[姿态双时间clockcheck09](reports/V04_CLOCK09_REPAIR.md)。显式白名单、同刻候选歧义、完整边界/reset及唯一输出键检查已实现；43项新增测试，最终109C++/277Python及只构建通过，七批回放完成。默认旧入口保持，原243份输入不变，所有历史失败不改判，无飞行/新预算/新种子。下一批先接线并另冻新协议/资产、取得授权；V04仍未通过，不push。下方“最新/未实现”保留历史时点含义。

最新离线审计：[发布时间与采样时间](reports/V04_CLOCK_SEMANTICS_AUDIT.md)。七批原始日志及实际时钟/发布/消费/检查链复核：同发布时间不等于重复采样；不能只放开等号，需同时处理匹配歧义、窗口reset及重复输出键。新增12项反例，109C++/234Python与只构建通过。未改既有验收、未飞行、旧失败不改判；V04仍未通过、余5停止，不push。修订实现/新飞行须另授权。

最新批次：[protocol08 / series07结果](reports/V04_PROTOCOL08_RESULTS.md)。IMU0修复后重新授权9701–9703最多6次，协议提交8df90c62a1及干净构建、120个不同C++/222Python通过。首轮PID起飞/交接后悬停约13.228s，两条姿态发布时间同为60.128s而采样时间递增，触发冻结日志检查，余5停止。1尝试/0接受、ESTA0；未完成激励/降落，不能评价IMU0修复降落效果。独立原始记录复核，无本轮生产或检查器修改，参数恢复、不push、不V05。下方记录保留历史时点含义。

最新获准修复：[IMU0转换链离线修复](reports/V04_IMU0_CHAIN_REPAIR.md)。只改Simulator加速度块：有限超量程先限幅再转整数，非有限向量拒绝并累计错误，保留原有效路径和clipping机制。真实链11个C++用例及sanitizer通过，2048帧与冻结旧源码等价；原109C++/211Python及构建通过。无新飞行，V04仍未验收；不能据此保证EKF不切换，旧预算不续跑。

最新离线验证：[IMU0真实转换链](reports/V04_IMU0_CHAIN_AUDIT.md)。原Simulator→FIFO驱动→VehicleIMU的合成三轴冲击复现反向积分且clipping丢失；4个正常用例、1个缺陷复现、10个预期sanitizer拒绝，原109C++/211Python及构建通过。已证实链路缺陷，未证实旧飞行唯一根因；没有生产修复/协议修改/新飞行，V04仍未通过。下方保留历史结论。

最新离线审计：[降落期EKF切换与目标补偿](reports/V04_LANDING_EKF_AUDIT.md)。本次旧缓存目标只补偿一次、新目标不重复补偿；切换符合较低相对误差选择，切换前真值已有垂向回升。发现IMU0整数转换风险并合成复现，尚未证明是旧飞行根因。109个C++/211个Python通过；无生产修改、无协议豁免、无新飞行，V04仍未通过。

最新批次：[protocol07 / series06结果](reports/V04_PROTOCOL07_RESULTS.md)。重新冻结授权9601–9603共6次、干净协议提交109C++/204Python通过后，首轮PID完成60.388秒观察/32秒激励；降落时真实EKF primary 0→1，伴随参考及多类reset变化，按原门槛停止。1尝试/0完整起降/0接受、余5停止，ESTA0；两项日志修复在本轮部分窗口中通过，不能据此改判整轮。参数已恢复，未push、未V05。以下均保留历史状态。

当前离线修复：[事件时间戳与接收器坐标检查](reports/V04_LOGCHECK07_REPAIR.md)。新增隔离分析器与15项测试，109个C++/195个Python及构建通过；上一轮日志通过新版离线检查，但历史接受仍为0、V04仍未验收。未修改控制律/阈值、未飞行、未push。下面保留各批次当时状态。

当前：[protocol06 / series05结果](reports/V04_PROTOCOL06_RESULTS.md)。新授权六次批次首轮PID完成起飞、60.160秒观察/32秒激励及降落上锁，但最终命令日志验收未通过；1尝试/1完整/0接受、余5停止、ESTA0。定位到事件同刻时间与接收器浮点参考两处工具适配问题，未修订或续飞。109个C++/180个Python及干净构建通过，不等于V04验收通过；不push、不V05。以下各“最新/最近”条目保留为历史记录。

最新离线修订：[目标交接修订报告](reports/V04_HANDOFF06_REPAIR.md)。改为保留原POSCTL本地XY目标、明确整数经纬度单次COMMAND_INT、应答及原始下游读回；25项新增测试，最终109个C++/172个Python及构建通过。新入口禁用、预算0、无飞行；旧失败不改判，V04仍未飞行验收。需要另冻结并获准新批次，不能续跑旧五轮。

最近飞行：[protocol05 / series04结果](reports/V04_PROTOCOL05_RESULTS.md)。获准新六次后，干净提交109个C++/147个Python及构建通过；首轮PID离地并完成航向准入，但POSCTL正常清空Navigator航点，运行器错误依赖该航点而中止。1尝试/0接受、余5停止、ESTA0；未发高度命令，V04仍未验收。当时仅只读诊断，未修复或续飞。

历史修复：[CLI/raw精度修复报告](reports/V04_CLI_PRECISION_REPAIR.md)。表示层已修复，原始坐标严格检查不变；当时109个C++/141个Python及仅构建通过，无新飞行。下方各申请和状态保留当时事实。

历史：protocol04获准后执行series03，首轮PID因CLI经纬度打印舍入与原始ULog参考的精度不一致而中止；原始坐标未变，已解锁但未检测离地。1尝试/0接受、余5停止、ESTA0；参数恢复、旧失败保留，当时工具尚未修复。见[protocol04实际结果](reports/V04_PROTOCOL04_RESULTS.md)，V04仍未验收。以下为历史记录。

V00–V03已通过，历史失败保留。V04 **failed / needs_revision**：SITL X单轴接入及92个C++/57个Python测试通过，但首轮PID未满足冻结的悬停入口高度，并发现起飞同帧二次update和激励锁止；按协议停止剩余5轮。ESTA实际飞行0次，不能宣称性能或飞行安全验收通过。默认仍PID，不进入V05。默认研究范围为XY速度PID/ESTA比较；Z、Proper-ISTA与双层组合须单独授权。

2026-09-23更新：用户批准正常计划降落Gate=2分类后，protocol03运行器/分析器完成，104个C++/89个Python及干净构建通过。新series02第一轮PID已起飞，但在约1.60m发生EKF航向reset（约0.376°），触发冻结的reset计数不变检查；**1尝试/0接受、后续5停止、ESTA仍0**。没有控制器故障或首次失败重算证据，但不改判通过、不补飞。旧protocol02兼容失败与旧飞行数据全部保留。

- [初始TODO快照](plan/v1/VELOCITY_STA_TODO_CN.md)
- [初始阶段提示词](plan/v1/VELOCITY_STA_PROMPTS_CN.md)
- [初始状态快照](plan/v1/VELOCITY_STA_STATUS_CN.md)：只是2026-09-19编制状态，后续不可据此推断实际进度。
- [外部实时进度表](</home/yr/Desktop/codev doc/plan/VELOCITY_STA_STATUS_CN.md>)
- [V00报告（基线通过）](reports/V00.md)
- [V01报告：选择框架、逐样本等价及一次冒烟](reports/V01.md)
- [V02报告：离线 ESTA 速度内核](reports/V02.md)
- [V03：公共保护、日志与一次PID验证](reports/V03.md)
- [V04：X单轴接入、首轮PID失败与停止记录](reports/V04.md)
- [V04修复：上游目标缓存与同帧重算离线回归](reports/V04_REPAIR01.md)
- [V04 protocol09接线回归与待授权新批次](reports/V04_PROTOCOL09_IMPLEMENTATION.md)：新实时/完整分析链与clock09接通；9801–9803、最多6次，仅申请，未飞行。
- [V04 protocol09冻结清单/门禁/命令](v04/protocol09/README_CN.md)
- [V04 protocol03实现与日志修订](reports/V04_PROTOCOL03.md)
- [V04新批次：起飞航向reset失败及停止记录](reports/V04_PROTOCOL03_RESULTS.md)
- [V04起飞航向对齐离线审计与新准入设计](reports/V04_HEADING_AUDIT.md)：109个C++/99个Python通过，未改生产控制；protocol04仅设计，无新飞行授权，V04仍未通过。
- [V04 protocol04运行器/日志分析器与新批次申请](reports/V04_PROTOCOL04_IMPLEMENTATION.md)：独立接线、只读连续ULog取证、一次任务yaw冻结；完成离线验证后申请9301–9303共6次，不自动飞行。
- [V04新高度任务/验证协议（设计冻结，飞行待授权）](v04/protocol02/README_CN.md)
- [V04协议修订记录及飞前待办](reports/V04_PROTOCOL02.md)
- [V04飞前生命周期审计：正常降落与零fault规范冲突](reports/V04_PROTOCOL02_PREFLIGHT.md)
- [V04冻结协议（本批已停止，不得直接续跑）](v04/protocol01/README_CN.md)
- [V03历史前置审计：失败复现与V02勘误](reports/V03_PREFLIGHT.md)
- [V03冻结协议与日志说明](v03/protocol01/README_CN.md)
- [V03修复后单次验证协议及运行入口](v03/protocol02/README_CN.md)
- [V00恢复批次02：三轮指标、覆盖与勘误](reports/V00_RESUME02.md)
- [V00恢复批次：测试已修订，启动预检失败](reports/V00_RESUME01.md)
- [V00接口审计、Takeoff勘误与恢复条件](v00/INTERFACE_AUDIT_CN.md)

V00核对后将计划和基线工具纳入明确范围提交。后续reports/、scripts/、configs/、evidence/按阶段创建，不预填成功报告。plan/v1为初始快照，修订另存版本，已执行依据以对应提交协议/阶段报告为准。大型日志放仓库外VELOCITY-STA实验目录。

当前默认速度配置为MPC_VC_MODE=0/MPC_VC_AXES=0。实验MODE1/AXES1（X）或AXES4（Z）仅在SITL且各自配置有效时准入；3/7和MODE2仍拒绝。X为本地NED北向、Z为向下，均不是机体角速度轴。本次Z研究不push。
