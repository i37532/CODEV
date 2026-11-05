# PX4 速度环研究进度表

## 2026-09-28 V06 执行冻结

用户“ 不用我授权，跑完为止 ”授权本阶段普通离线修复和另冻有限新SITL批次。首个失败仍停批、原判/数据保留，不补飞/放宽门槛；不push、不进入V07，不扩上游估计器/land detector/实机/ISTA。

V05/E01-XYZ已通过；起点2b6cb940e7355197dc420328d6da44dda716cd56，research/sta-velocity-control，初始干净。本阶段只比较速度PID与合格XYZ ESTA，Z ESTA获准，位置P/姿态/rate PID不变。协议01：hover→figure8→heading，每任务3对，共18轮，新23001–23009；逐任务验收。新增默认关闭的SITL每帧目标适配TEST5/6/7，速度/加速度FF各一次；12秒settle后64秒任务、90秒观察，保留起降链、E01安全/性能阈值。v06/scripts默认清单，先提交再飞，当前未飞行/未验收；详见v06/protocol01及TODO当前节。

## 最新：E01-XYZ 三轴速度 ESTA 完成（2026-09-27，passed / Iris SITL only）

- 已插入并完成V05→E01-XYZ→V06中的三轴阶段。实际配置MODE1/AXES7；位置P、姿态、全部rate PID保留。地面/ramp及一次边界样本原速度PID，正常空中只计算三轴ESTA；独立ν/原子提交/HTE及生命周期已测试。
- 协议/运行源码 **`045f642bf2bad5e532761e59b3d6810be360be58`**；独立结果提交 **`2b6cb940e7355197dc420328d6da44dda716cd56`**。分支research/sta-velocity-control，最终工作区及33项递归子模块干净。未push。
- 新22001–22003，各PID→XYZ ESTA，**6/6轮、3/3配对通过**；每轮90–92秒观察，Z16秒→XY16秒→XYZ32秒及完整起降上锁。首批全部通过，新飞行失败0/补飞0/追加调参0/放宽门槛0。
- 干净源码实际 **190个不同C++、424个Python** 通过，SITL/Gazebo构建通过；6轮隔离完整回放逐字一致。12个ULog无记录dropout/解析损坏，310项原始工件指纹保留，432冻结资产复核通过。速度实际约100Hz，不是250Hz。
- XYZ组合窗口RMSE：X 0.032190→0.014576m/s（−54.7%），Y 0.030526→0.017192（−43.7%），Z 0.004068→0.009723（约2.39倍）。Z单独时非命令XY也退化；全64秒请求TV约7.52/7.72/48.04倍PID。均在预先加性开发门槛内，**不代表三轴性能全面优于PID**。
- 原参数逐字恢复，EEPROM `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`；核实速度0/0、TEST0、rate0/0/DIV1、RATT0/TKO0，无残留仿真。
- [完整报告](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/E01_XYZ.md>)、[合格XYZ配置](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/e01_xyz/qualified_xyz.json>)。原始数据 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260927/E01-XYZ`；离线开发失败及旧快照全部保留。
- 当前任务结束，不自动开始V06、ISTA、调参、分频或实机。下一步V06须明确选择合格XY或XYZ配置并冻结任务；旧V08/V09的XY范围不自动扩大。下方均保留历史时点含义。

## E01-XYZ protocol01已冻结（2026-09-27，飞前复核中）

- 协议/源码045f642bf2bad5e532761e59b3d6810be360be58，39个明确文件；MODE1/AXES7及三轴原子交接/保护、HTE、TEST4和独立完整分析链接入，默认PID/全部rate PID不变。
- 提交前190个不同C++、424Python及SITL/Gazebo构建通过；消息格式1475字节、队列8，参数未变。正在干净提交重新验证，不先称飞行通过。
- 新22001–22003，每个PID→XYZ ESTA，最多6次；90s观察中Z16s、XY16s、XYZ32s，新E01-XYZ/paired01。432资产冻结；沿用用户持续授权，不反复询问起飞，不补飞/放宽门槛，不push/V06/实机。
- 报告research/sta-velocity-control/reports/E01_XYZ_PROTOCOL01.md，旧失败与快照不覆盖。

## E01-XYZ 开始（2026-09-27，in_progress，尚未验收）

- 用户明确授权插入V05与V06之间并持续完成，普通修复及新冻结有限SITL批次不再逐次申请；失败仍停批留档，不放宽门槛，不push/实机/下一阶段。
- 起点 research/sta-velocity-control / af3edfd2bbaf3e9e6f012e77f3df92890c11615c，工作区干净，递归子模块版本已核对；此前V05三个提交已经按用户要求推送。
- V05 XY与Z03 Z单独通过，但当前AXES7仍拒绝。正在审计三轴统一起飞交接、HTE和原子保护；尚无新飞行、种子消耗或验收结果。
- 新TODO/提示词明确范围与持续授权；将另存仓库新快照，旧计划及下方历史记录不覆盖。

## 最新：V05 XY 双轴完成（2026-09-27，passed / Iris SITL only）

- 配置为 **XY ESTA + Z速度PID + 全部rate PID**，MODE1/AXES3；默认PID不变，7仍拒绝。独立Y参数/ν、原子提交、reset及切换/保存回归已完成；原X-only和Z-only路径保留。
- 实现/首批协议 **`fad638b592c21c4af57e7be418a4d51ffa1bc145`**；最终运行协议/源码 **`969ca4afe7163d27d83282ecff49f080599b41c5`**；结果提交 **`af3edfd2bbaf3e9e6f012e77f3df92890c11615c`**。均在研究分支，最终工作区和递归子模块干净，未push。
- 最终protocol02新21001–21003，每种子PID→XY ESTA，**6/6轮、3/3配对**通过；每轮重启、2.5m定高固定yaw、X32s/Y16s/XY16s、90s观察和降落上锁。没有追加调参或放宽门槛。
- X窗口X RMSE 0.045250→0.015211m/s（−66.4%）；Y窗口Y 0.050443→0.016976（−66.3%）；XY窗口X/Y分别−58.5%/−47.8%。单轴激励中的非命令水平轴误差增大，Z/yaw略退化但每个配对仍在预设门槛内。
- 同一64s水平加速度请求TV：X 6.399843→45.605265（7.13倍）、Y 6.235329→50.115767（8.04倍）。不声称所有指标优于PID、不是实机或论文显著性结论。
- 实际174 C++/421 Python、SITL/Gazebo构建通过；6轮独立回放指标完全一致。12份ULog无dropout/损坏，真实速度约100Hz/最大sample间隔12ms，任务内无故障/重算/回退/约束限制；452项源资产冻结，310原始工件和322验证/回放证据指纹。
- 首批protocol01因落地监视器仍要求60–62s而拒绝新90s任务，1次PID失败保留，0ESTA，剩余5次停止未补飞。新批仅离线修复工具接线后冻结；总计7尝试/6接受/1失败，不改判历史。早期编译与测试夹具失败亦保留。
- 用户持续授权V05范围执行，未逐次请求起飞。外部数据 `VELOCITY-STA-20260927/V05/paired01`、`paired02`、`replay02`；EEPROM完整恢复 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，核实速度模式0/轴0、TEST0、rate0/0/DIV1、旧起飞管理0，无残留仿真。
- [V05完整报告](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V05.md>)、[合格XY配置](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/v05/qualified_xy.json>)。本阶段结束，不自动进入V06/XYZ/实机、不push。下方均保留历史时点状态。

## V05 protocol02 冻结（2026-09-27，未验收）

- 首批 protocol01 仅PID/20001一次，0接受；90.16秒观察及三个激励完成后，旧落地监视器60–62秒契约拒绝新90秒任务。不是已证实PID失稳，未完成落地上锁，不能算通过；其余五次未执行，失败ULog/45原始工件指纹完整保留。
- 离线修复仅实验工具观测时长接线，另补Y全历史输出与时钟检查；不修改C++、控制dt、参数或数值门槛，不改判旧失败。
- 新冻结提交 **`969ca4afe7163d27d83282ecff49f080599b41c5`**：protocol02 新21001–21003，PID/XY ESTA共6次，外部V05/paired02；用户持续授权，无逐次申请。
- 离线174 C++/421 Python、SITL/Gazebo构建通过；新源码提交后再次完整验证。必须六轮/三对全接受才验收，结果另提交。
- [失败及修复报告](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V05_PROTOCOL01_FAILURE.md>)。不push、不进入V06。

## 最新：V05 XY 接线/协议已冻结，等待六轮验收（2026-09-27）

- 用户授权 V05 常规离线修复及新冻结 Iris SITL 批次持续推进，不再逐次申请起飞；每批失败立即停止、保留数据，不补飞或放宽门槛，不扩大 XYZ/实机/V06、不 push。
- 核对分支 `research/sta-velocity-control`，基线 `5cfc2ac088ad458522311659eefff465a219d46d`，进入时工作区/子模块干净，原基线已在此前推送。
- 协议/源码提交 **`fad638b592c21c4af57e7be418a4d51ffa1bc145`**，33个明确文件，MODE1/AXES3、独立Y参数、双轴原子提交，Z速度/全部rate PID；既有X/Z路径保留，7仍拒绝。
- 离线174个实际C++/399个Python通过，SITL/Gazebo构建通过；提交后正在干净SHA重建复核。ULog格式1435字节，队列8，EEPROM未变。
- 新20001–20003，按每种子PID→XY ESTA，共6轮；X32/Y16/XY16秒，90秒观察，固定原安全/配对门槛；外部V05/paired01。尚不能将接线/离线通过称V05完成。
- [飞行前报告](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V05_PROTOCOL01.md>)；正式结果另提交并补完整SHA。

## 最新：Z02/Z03完成（2026-09-27，开发验收通过，仅Iris SITL）

- 用户本轮授权持续完成Z轴替换，普通相关修复和新冻结批次未重复请求许可；没有扩展XYZ/ISTA/实机。
- Z02接线提交 `9bf317ea5a975908e63506a2acdd0c252af3acfb`；最终配对协议/源码 `d6ea312f7383b7492f554e00ee873a06270d7fe3`；结果提交 **`5cfc2ac088ad458522311659eefff465a219d46d`**，69个明确研究文件，工作区/递归子模块干净，未push。
- MODE1/AXES4仅Z速度，独立参数2/1/4/6；默认PID。地面/ramp原PID、单次连续交接、正常空中Z ESTA；XY速度和全部rate PID。HTE补偿/日志/状态及故障保护已接入，未把无输出当安全，未关闭上游保护。
- PID01误报pending失败保留，修复 `0d06ff47389e6cf2cf7046f20c6c855ecfd9d4d2`；PID02新18002接受，结果/离线候选筛选 `ff56d883bd080b0e159e257a288af859fec3427a`。原小增益在非零初态对象中漂移大，未硬飞。
- 正式本批新19001–19003各PID后ESTA，共6/6接受、3/3开发配对通过；每轮60s观察/32s Z小正弦/降落上锁完整。159不同C++/399Python、构建、6轮独立完整日志回放通过；候选/阈值未事后调整，未补飞。
- Z RMSE均值PID **.004072711**、ESTA **.009839158m/s**（ESTA约2.42倍）；Z请求TV **2.5493→135.6267m/s²**（约53.2倍）；高度RMSE **.042056→.040536m**。接入通过但性能未优于PID，不作论文显著性或实机结论，不自动追加调参预算。
- 真实约100Hz、最大12ms；3次ESTA各一次交接，nu/HTE逐样本核对通过。12份ULog均无dropout/损坏，310原始工件与313验证/回放证据指纹核验；新Z工作总8尝试/7接受/1失败保留，不混入旧X数据。仅IMU种子、固定顺序和n=3限制已披露。
- 外部 `VELOCITY-STA-20260927/Z03/paired01`；结果索引SHA `cbc2d7be7df306f1f2f7760882b3f8918fe8928bbdd3c97c377b34c3e8dedf85`。EEPROM恢复原 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，无残留仿真。
- [Z03完整报告](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/Z03.md>)、[使用与模式切换](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/z_velocity/QUICKSTART_CN.md>)。本次完成后停止；下方“尚未完成”等均保留历史时点含义。

## V04最终验收通过（2026-09-26，passed / Iris SITL only）

- 协议/源码 **85771e4cf02d0c959b0c79fcde41b9c88368554f**；结果提交 **9f0dff53a25e01fbd9acfb97d7ce8da67e96930f**。research/sta-velocity-control，明确64个研究文档/结果文件，提交后工作区与递归子模块干净，未push。
- 同一干净源码、protocol17，新17001–17003每个PID后ESTA X，计划6/执行6/接受6，3组配对全部通过；无补飞、调参、回退/中止，没有拼接旧批次。实际观察60.012–60.668s、每轮32s激励及降落自动上锁完成，独立完整链回放6次退出0。
- 干净构建及140不同C++/395Python通过（386通用+9接线），405资产一致；582份本批工件指纹核验。6轮无ULog dropout/损坏，降落无削顶/EKF故障/切换/reset/timing异常；输出发布边匹配100%，不冒称完整下游消费。EEPROM完全恢复原06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无残留仿真。
- X速度RMSE三轮均值PID0.0423446、ESTA0.0147017m/s，均值降低65.3%；加速度请求TV均值3.2525→22.5717m/s²（6.94倍），不声称全面胜出。Y/Z与yaw原配对门槛通过，非每项更好；速度环约100Hz，旧nu/FF/状态/模式真日志核对。仅IMU播种、PID先行、n=3开发限制已披露，不作论文泛化结论。
- [最终报告](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL17_RESULTS.md>)；原始series15、大日志仓库外。累计开发启动31/接受16/历史配对7，其余15未接受保留；本次只用新6轮/3组验收。默认PID、Y/Z速度及rate仍PID，不V05、不实机。
- Z工作已开始且Z01离线16项通过，但Z02生产接线/Z03真实Z飞行仍未完成。本次X结果不作Z验收；历史各条状态保留当时时点含义。

## protocol17冻结（2026-09-26，飞前复核）

- 源码/协议 **85771e4cf02d0c959b0c79fcde41b9c88368554f**，405资产，执行SHA79fd6151ae45da182e88a7358326f2dfa7075573dec241759513851f83712a5a。新17001–17003各PID后ESTA X最多6轮，新series15；持续授权精确绑定。13文件明确提交、未push。
- 提交前140不同C++/395Python及SITL/Gazebo构建通过，正在干净复核。run.py仅替换预解锁monitor来源，其他飞行步骤/参数/安全性能门槛保留；不提前宣称飞行通过。旧累计25/10/4组历史配对不变；Z仍离线原型、不V05/实机。

## protocol16结果 / prearm17修订（2026-09-26，持续推进）

- 结果/修订提交 **7a52969f0ca0171b457c0dca851e2f8c5ced3914**，执行源码 **5a1c60b726a74ab3e06b6c213378245e1da4a156**，未push。4次启动、前3完整起降并接受、16001配对通过；第4轮未解锁即Missing attitude interval，余2停。累计25尝试/10接受/4组历史配对，V04尚未完成新批三组；Z仍离线原型。
- 原预解锁参考可能起终点相同而无同刻姿态；新reference选择不晚于最后完整姿态组的真实位置样本，保留原姿态window/新鲜度/reset/安全、原live monitor/landing。9新测试、386Python通过；失败日志110时间前缀及4096字节枚举各复现旧3拒绝/新0拒绝，精确原实时前缀未存，不冒称精确重建。首截至ready回放0/0保留；后置诊断因第4轮无降落窗口退出1也如实记录。
- 飞前140不同C++/385Python及构建通过；前3独立回放均退出0、无接触削顶/EKF/reset/timing和dropout。324原工件指纹验证，参数完全恢复、无残留仿真。见V04_PROTOCOL16_RESULTS.md。
- 持续授权下准备protocol17新17001–17003各PID/ESTA最多6；仅接prearm17，不改控制/门槛，不续旧余量、不V05/实机。

## protocol16新批次冻结（2026-09-26，飞前验证）

- 源码/协议 **5a1c60b726a74ab3e06b6c213378245e1da4a156**，401资产，执行SHA8ae707be2d46c836048117891e34cea228bf5e9d081a9d8fba7d0aca1065cab4；新16001–16003每个PID后ESTA，最多6次，series14。13个研究文件明确提交、未push，工作区干净。
- 提交前140不同C++/385Python及SITL/Gazebo构建通过，正在干净源码复核。飞行脚本逐字相同，最终分析仅换height16目标窗口检查；原参数/安全性能门槛/模式范围不变。持续授权绑定已记录；飞前不称通过，旧累计21/7及3组历史配对不改判，不进入V05，Z仍离线原型。

## protocol15结果与目标窗口修订（2026-09-26，持续推进）

- 结果/修订提交 **a1465336513128ce04c1ac45a6cdbea00c235c8e**，源码/协议 **99a832ae109a850a0ba64b4daa26c3c45efee545**；未push。5轮完整起降，前4轮接受、15001/15002两组配对通过。15003 PID因交接前37.216s旧起飞目标/清空目标同刻而最终拒绝，余1未启动，不追认失败。累计21尝试/7接受/3组历史配对，不拼接替代同一新批三组。
- 原规则全日志拒绝扩大了目标使用窗口；新triplet16完整保留行/全局结构及时序检查，检查handoff_ready完整前驱组、窗口内及结束边界，窗口外未决歧义单列。原控制律/dt/参数/门槛不变，其他话题规则不改。12项新增测试、377Python回归和三批10轮隔离回放通过；真正旧三秒入口失败仍拒绝。飞前140不同C++/373Python及构建通过，结果阶段未重复C++。
- 五轮降落无削顶/EKF故障/切换/reset/timing异常，dropout0/无损坏，参数完全恢复。444项本批原工件指纹验证，工作区干净。报告V04_PROTOCOL15_RESULTS.md记录较低X误差同时加速度请求TV增大，未只选有利指标。
- 按持续授权继续：新冻结protocol16、16001–16003各PID/ESTA最多6轮、干净提交复核再飞。旧余1不续用，Z仍离线原型、不实机、不V05。

## protocol15新批次冻结（2026-09-26，飞前验证）

- 本轮确认前一轮属于实质进展：triplet15离线白名单与完整链回放已落盘。起点391ed95e5c07c8e86c8b6eefe172b629eb8eea6d，研究分支/工作区/递归子模块核对，无残留模拟器。
- 新协议/源码 **99a832ae109a850a0ba64b4daa26c3c45efee545**，13个明确研究文件，未push；395资产新增导航发布者/消息与消费代码，执行SHAdb192d49df8c0601ee78d17b78c501a78fac951aaa858177cd5f1c4eebfd0095。新15001–15003各PID后ESTA共6，外部series13，首必需或配对失败即停，不续旧5。
- 提交前实际140不同C++/373Python、SITL及Gazebo DONT_RUN构建通过，正在干净源码复核。此次只接隔离height15/handoff15单话题规则，保留所有行/拒绝歧义；原raw三秒入口、共同0.6/0.55参数、原增益/任务/数值门槛不变。本批尚未启动，不先称通过；旧累计16/3及1组合格配对不改判。Z仍离线原型，不实机、不V05。

## protocol14结果 / triplet15离线修订（2026-09-26，持续推进中）

- 最新提交 **391ed95e5c07c8e86c8b6eefe172b629eb8eea6d**，17个明确文件，主仓库/递归子模块干净，未push。执行源码 **e96c170166cabc0eb9e7c50a426a2a572111b3de**；14001首轮PID完成原始三秒入口301样本、60.480s观察/32秒激励及自动上锁，但最终position_setpoint_triplet同刻检查拒绝，退出1、余5不续。累计16尝试/3接受/1合格配对，V04仍未完成，不V05；Z仍离线原型。
- 121.216s两条导航目标发布时间相同、全部字段逐位一致、无时间倒退，发生在降落期。此话题只有发布时间，Navigator使用hrt_absolute_time；原通用严格递增在取观察窗口前误拒绝。新隔离triplet15仅允许此话题逐位完全一致的同刻记录，保留全64行；不同字段/NaN载荷/负零差异、倒退等拒绝，其他话题不放宽、不去重、不改控制dt/生产逻辑或数值门槛。
- 新7单测及全365Python回归通过退出0；首6测试有2个夹具get_dataset签名错误，修正后6过再扩7过。飞前140不同C++/366Python及构建通过，结果阶段未重跑C++不重复累计。五轮完整链隔离回放：series11仍3真1假，series12新候选通过但旧正式accepted保持false，原ULog/metrics指纹不变。不是追认历史失败。
- 本次主ULog84003823字节SHA9ba1ad8c7f4aab5122bb1a9455f521b2c18d69c2913bf1d287f3356aa0cda7a9，dropout0/无损坏，降落削顶/EKF故障/reset/timing均0。449项工件指纹全量核验；EEPROM完全恢复06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无残留仿真。[报告](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL14_RESULTS.md>)。
- 下一步无需再次普通授权：把triplet15隔离链接入新冻结分析/运行批次，准确新种子/最多6次、明确源码提交/干净回归后执行。原有有效1组不能替代新3组验收；不续旧5、不改判。Z02真实模块接线仍未完成，不能声称Z已飞行。

## protocol14接线与冻结（2026-09-26，飞前验证）

- 协议/源码 **e96c170166cabc0eb9e7c50a426a2a572111b3de**，13个明确新文件、工作区干净、未push。原始三秒门控已接入飞行入口，原最终验收器不变。344项资产；执行SHAb416bf9d236841744d6688197fdf5ba7c8819ada820383b8f3c0c8a8579a0ebf。
- 提交前140C++/366Python与构建通过；实际LandingLiveLog过滤器对series11四轮回放也保持3 ready/1 not-ready（4条回放核对不另当gtest数）。初次8项接线有1项测试预期文本把换行写成反斜杠n，修正夹具后全过，无飞行副作用。
- 持续授权新14001–14003各PID/ESTA最多6轮，series12；共同0.6/0.55下降参数及原候选/任务/门槛保留。正在干净提交验证，尚未本批飞行；旧累计15尝试/3接受/1配对不改判，余2不续用。Z仍离线原型，不实机、不V05。

## protocol13结果与原始入口门控（2026-09-26，in_progress / 本批停止）

- 结果/离线修复提交 **7ebdbd8768d43d984119528ae1e692acb34385e0**；执行源码 **ffbe1a2ec5ba0a6b96c78628e9be6b8f287ad3e3**，未push。4轮PID/ESTA均完整起降上锁，前三轮最终接受，13001一组合格配对通过；第4轮13002 ESTA因入口轨迹三秒窗口不满被拒绝，第5/6轮未启动，余量不续用。累计15尝试/3接受/1合格配对；V04未验收，不V05，Z仍离线原型。
- 四轮新公共0.6/0.55下降配置均无降落削顶、EKF故障、selector切换/reset、timing故障，ULog dropout0/无损坏；没有改全局land detector/生产控制/增益或验收门槛。第一合格配对X RMSE PID0.044490→ESTA0.014818m/s，约降低66.7%，只有一个开发种子，不冒称论文结论。
- 第4轮位置CLI44.084s与未来112ms目标44.196s拼接，导致47.084s提前宣告三秒收敛；原始44.084–44.184s共11样本目标高度误差>0.05，最大0.052648664m。原最终拒绝正确，不放宽5cm、不改判。离线最早47.196s才有完整三秒，只作反事实诊断。
- 新raw入口门控/advance_entry适配已实现，11负例/边界/接线测试通过，原10秒截止不延长；四轮原始回放保留3 ready/1 not-ready。飞前140C++/355Python；结果阶段实际140C++/358Python和构建通过，未累加历史测试。未跑MATLAB/旧七八批全量回放，不称已接入新飞行入口。
- 395项本批工件及174项上一批指纹核验，EEPROM恢复06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无残留仿真。报告：[protocol13](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL13_RESULTS.md>)。
- 后续普通步骤持续授权已覆盖：接新运行器/接线回归→新冻种子与最多6次→提交/干净复核再执行，不再逐批问用户，不续旧余量。共同起降前置已实证打通，Z02仍待真实模块接线。

## protocol13冻结（2026-09-26，飞前验证）

- 源码/协议 **ffbe1a2ec5ba0a6b96c78628e9be6b8f287ad3e3**，13个明确新文件，主仓库干净，未push。341项资产含原land detector/FlightTask路径；执行SHA3866a54cf632d44a218cabed7cc4711378accf5c656ea1846baa7e90241f20dd。
- 提交前实际140项不同C++、355项Python及构建通过；新增真实落地检测器5项、合法联动位置模块1项包含在140内。正在干净源码复核。持续授权13001–13003各PID后ESTA X共6，新series11，两方共同land_speed0.6/down_cap0.55，原控制/检测公式及验收门槛不变。
- 本批尚未启动；旧11失败不改判，Z仍离线原型，不V05、不实机。后续结果另记。

## protocol12失败与落地跨模块回归（2026-09-26）

- 结果/测试提交 **7f111ffab51d3f4dc597bd3f33f3c1b969780347**，未push。源码d43ba9043fb060f6b9082a09b0e1a5df641308d9，实际run01 PID/12001观察60.628s并触地，但未判落地上锁，最终日志超过原128MiB守卫而退出1；剩余5不复用。累计11尝试/0接受/ESTA0。
- 原0.5上限在本次降落削顶/EKF故障/reset/timing均0；但原land detector读取存储land_speed0.7，要求trajectory vz≥0.63，实录约0.5，in_descend始终false。这是上一轮审计遗漏跨模块联动，不是ESTA发散。未放大日志上限、未修改全局land detector或阈值。
- 新真实land detector/uORB5测试、位置模块新联动测试通过，验证合法land_speed0.6/下降上限0.55满足0.54下降意图。首版测试夹具遗漏hrt_init导致析构阻塞，终止自有测试后make退出2，补齐后5项全部通过。不称真实异步自动上锁验证通过。
- 主ULog134661449字节SHAb73d52811ce32c5825ba14307f6dc92d68aab523094f70e19c4957b42fd2dc40，dropout0/无损坏；174原工件指纹保存。EEPROM完全恢复、无残留仿真。[报告](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL12_RESULTS.md>)。
- 持续授权下准备protocol13：新13001–13003各PID/ESTA共6、series11，两方共同0.6/0.55，其余原门槛不变；先冻资产/回归/提交再飞，旧失败不改判。Z仍离线原型。

## V04公共下降限速新批次（2026-09-26，protocol_frozen）

- 协议/源码 **d43ba9043fb060f6b9082a09b0e1a5df641308d9**，research/sta-velocity-control，15个明确文件，未push。真实模块新增测试证明合法MPC_Z_VEL_MAX_DN=0.5限制下降目标/内部land_speed，存储MPC_LAND_SPEED仍0.7；没有修改生产控制律、默认参数、增益或安全/性能门槛。两算法共同改变下降任务约束，不冒称原0.7m/s任务同条件。
- 提交前134项不同C++、355项Python、SITL/测试/Gazebo DONT_RUN构建通过；正在干净提交复核。314项执行资产；protocol12执行SHA a8c67f55a681d524de9710f6e1fc9209eefff1bd28aacd59dbf7eb3085631580。初次缺冻结文件dry-run退出1无飞行副作用，完整生成后退出0。
- 持续授权下冻结12001/12002/12003，各PID后ESTA X，最多6次，新外部series10；首必需失败或配对失败即停，保留全部失败。沿用原唯一目标源、60秒观察/32秒小激励、模型/原内环PID及所有检查。两方profile1171。原10次失败不改判，尚未启动此批次，Z仍离线原型。报告：[飞前协议](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL12_PREFLIGHT.md>)。

## 单次PID触地诊断完成（2026-09-26，failed / evidence_obtained）

- 持续授权下冻结诊断1次、种子11001；协议/源码 **55073c29b74fadab5ca910847ebed332b040e204**，结果 **32f0ed0dd30520444e93d807c86ebc3ad1954e74**，research/sta-velocity-control；不push、不实机、不V05。不是正式配对，也不恢复旧余量；原V04九次加本次共10尝试/0接受/ESTA0，V04未通过，Z仍离线原型。
- 只额外启用SDLOG_PROFILE位10，保留旧位147→1171。原255槽已满，最终仅提速已有6实例EKF/3个IMU/加速度话题、不加FIFO、不挤掉原订阅；不改控制/参数默认/模型/任务/安全门槛。原MPC_LAND_SPEED仍0.7。参数位元数据扩至2047，默认1不变。
- 干净提交133个不同C++/351Python、构建通过，309资产及插件指纹检查。预热/起飞/60.480s观察完成；降落被ref_alt变化拒绝，执行退出1，预算用尽无补飞。三IMU于113.668s报Z削顶；1/2号Z加速度−186.6455m/s²；六EKF约108–116ms后报bad_acc_clipping，0→4→2并reset。真值发布时间显示约0.7m/s下降到0，仅离线诊断，不将timestamp_sample=0称精确同步。
- 修复后实录local_position、6实例位置和速度诊断无sample倒退，timing始终0；旧负dt缺陷在本次未复现，但真实切换仍触犯原门槛，不能称通过。主ULog77,859,649字节SHAb9f9aeb7d122be458d969037cae5d8da1b94483520d8b8db72c499c179d91ede，dropout0/无损坏；sensor_accel250Hz连续，EKF位置最大12ms，vehicle_imu有8ms间隔如实保留。
- 外部diagnostic11/diagnostic11_committed01/diagnostic11_verify01/diagnostic11_audit01及授权记录完整保存，175项指纹全量核验。EEPROM完全恢复SHA06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无残留模拟器。报告：[触地诊断](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_DIAGNOSTIC11_RESULTS.md>)。
- 下一步：先离线核实MPC_Z_VEL_MAX_DN=0.5（合法最小值）在真实模块中的限速/land_speed联动，再冻结相同公共下降限制下的新验证；不直接越过MPC_LAND_SPEED文档下限，不改PID/ESTA增益、reset/时间/性能阈值，不掩盖故障。0.5方案尚未通过测试或飞行，不能冒称已解决。普通相关步骤不再逐次申请授权。

## X/Z共同前置：selector时间交接修复（2026-09-26）

- 持续授权下完成真实上游缺陷修复，提交 **d882359ffd5d77e449a943b0d6732ae660cbb0fa**；起点01c70ee6f78459f3166500cc01e885426f9b6a91，research/sta-velocity-control，9文件明确范围，提交后主仓库/递归子模块干净，未push。
- series09原ULog的变化触发estimator_status_flags确认6实例113.444–113.464s短暂bad_acc_clipping，解释filter fault切换；旧低频status未捕捉不代表无故障。瞬时物理削顶峰值/触地完整因果尚缺高频输入证据，不冒称完全定位。
- 真实uORB/生产selector复现被拒绝过期消息仍覆盖上次发布/reset/实例基准的缺陷。五个发布路径改为前置检查、拒绝不变状态；健康判定/滤波/选源策略、控制律/dt/参数/模型/日志验收和原阈值不变。旧6项负对照全失败退出1预期；修复后最终10项通过，另106项原C++/16项Z/347Python和SITL/Gazebo DONT_RUN构建通过，总132项不同C++。未宣称完整异步多EKF/飞行通过。
- 外部selector11_old01（夹具HRT初始化缺失、终止−15）、old02（完整负对照）、fixed01及fixed02证据保留。旧/最终manifest SHA分别0a99ae4ac44374cc57ab36a0328accf2d55de823941bf4b18f9e4a90bcd4cd09、cc4eec89e7c61fefa044c3f7349b7e5ed7264a5944f20237cffe07524208c798，全量核验；原ULog SHA96db142fdfc5449c74ab0c86e46cae39d380caee51df31690280207b285a3403、EEPROM SHA06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc均不变。
- 新飞行/种子/ULog0。未重跑IMU11/姿态3专项、七八批完整回放或MATLAB，不累计历史测试数。V04仍9尝试/0接受/ESTA0，Z仍仅离线原型。
- 下一步冻结有准确预算的PID触地诊断，补充高频各实例/IMU削顶证据，核对修复后实际时序再决定最小处理；不能靠屏蔽削顶/允许负dt/放松reset验收。若考虑慢降，先审计本项目MPC_LAND_SPEED最小元数据0.6，不静默使用其他版本的0.3。Z02实际模块接线仍待完成。普通相关步骤沿用持续授权；不push、不实机、不V05。报告：[selector11](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_SELECTOR11_REPAIR.md>)。

## 当前优先：Z-only离线接入（2026-09-26）

- 用户先授权持续推进V04、普通相关修复/新SITL批次不再逐次申请，随后追加“另外，先开始接入z轴进行测试”。优先开展原E01的Z-only准备，X/Y速度与rate保留PID；不自动恢复旧批次剩余预算、不改变旧失败结论。新飞行仍需冻结新协议/准确预算并在干净源码运行；重大算法/验收范围改变另议。不push、不实机、不V05。
- 完成Z01离线原型，提交 **01c70ee6f78459f3166500cc01e885426f9b6a91**，分支research/sta-velocity-control，起点7dcf9994a52993958cd1aed4ca64070c62a30a49；8个明确文件，提交后主仓库和递归子模块干净。原v1计划/历史协议保留，外部TODO已添加最新范围说明。
- 复用生产STA纯核axis2，新增研究目录内测试专用C++14适配器：NED/推力符号、FF一次、旧nu输出/一次提交、PID加速度交接、竖直HTE连续补偿、上下推力和nu/加速度限幅、恢复方向、时间异常/事务/reset。真实PositionControl用于映射核对；不宣称推力代理是实际加速度。
- 实际新增16项Z gtest全部通过；106项既有C++及347项Python通过，总122项不同C++。两组2048步Z双精度序列和12条2500步独立对象轨迹包含在16项内，不另累计；既有PID两组2048步回归通过。SITL/测试/Gazebo DONT_RUN构建退出0；两次开发期double-promotion编译失败退出2已如实记录。
- 原型只有测试目标使用，生产selector仍拒绝AXES4/7，固件无原型符号；实际Z仍原PID，未完成模块接线/未飞行/新种子0。未重跑IMU专项11项/姿态专项3项或七八批完整ULog回放，未执行MATLAB；不借用历史数量充数。
- 证据：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/Z01/verify01，manifest SHA96cb4d650ec8742f4a65b3c2a3c21c79d6fa9ba03753eca818683cffa33a8e36全量验证通过，EEPROM前后SHA06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc不变；无活动px4/gzserver/gzclient。报告：[Z01](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/Z01.md>)。
- 下一步Z02：真实模块Z-only准入/增益/日志、起飞PID到ESTA交接和HTE/reset/failsafe/XY推力耦合回归。Z03飞行前还需解决或有证据隔离当前EKF/sample异常并冻结独立协议。V04仍9尝试/0接受/ESTA0，暂缓新飞行；下面“最新/待授权”记录仅保留历史时点含义。

- 最新结果HEAD：`7dcf9994a52993958cd1aed4ca64070c62a30a49`（2026-09-26，V04 protocol10 / series09，failed / needs_revision）。协议/源码提交 `d7090c4bc17eae80b88181c8e32dd0ac59d1b868`；用户“是”条件确认后在干净源码完成120个不同C++/347Python、构建及八批回放。新固件SHA29f0c6121f7d82b30693ce14bead61c15257c0fde5581521dbb22f72d4bc96ca，执行协议SHAca1c30db058dcc346130fa5062f6397591967b95df812ba5839e356900f28986。最多6次9901–9903各PID→ESTA，实际首轮9901 PID完成60.120s观察/32s激励，19次降落新匹配正常；113.444/113.448/113.460s主EKF 0→1→3→0，多类reset/ref_alt变化，113.448s样本时间倒退raw_dt≈−4ms、timing2/excitation_fault3；宿主113.624s检出xy_reset_counter变化而中止。没有落地上锁、0接受、ESTA0/配对0、余5停止；九批累计9尝试/0接受，不补飞不改判。原始完整检查独立拒绝reset与timing；selector还存在同刻不同实例消息，未去重或放宽。失败不是已修复的旧CLI/Gate混判，也未确认EKF切换根因。
- 本批执行退出1，隔离完整重分析缺landed_disarmed预期退出1；结果阶段347Python再通过/退出0，16项只读证据核对通过/退出0，不等于飞行通过。audit01的3个错误正向诊断假设及缺快照首次接线失败、输出截断解析失败保留；audit02如实记录拒绝，未修改控制/冻结验收器/参数/阈值。原始主ULog96db142fdfc5449c74ab0c86e46cae39d380caee51df31690280207b285a3403、35391199字节，启动ULog5c9a44d3da6f4517e2c53fce67bd7561d2a1584f4b812884101825a63798abbd；两者无dropout/损坏。94项直接工件、9份传递索引共2650条指纹、295项冻结资产、284份旧输入核验不变；EEPROM完整恢复SHA06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无残留模拟器。结果14个明确文件提交，diff审查及提交后主仓库/递归子模块干净，未push、不V05。报告：[protocol10结果](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL10_RESULTS.md>)。建议另行授权只离线审计selector触发条件、各实例IMU/创新及发布/采样时间交接；本轮未自动开展该新审计、上游修复或新批次申请。下方“准备中”及旧状态保留历史时点含义。

- 2026-09-26 protocol10 / series09 准备中：用户“是”条件批准9901–9903各PID→ESTA X最多6次，先冻结并验证干净源码。协议/接线提交 `d7090c4bc17eae80b88181c8e32dd0ac59d1b868`；提交前120个不同C++、347Python、八批回放/284原输入指纹通过。正在protocol10_committed01完成干净提交复核，尚未启动本批；首必需失败停批，不补飞/调参/push/V05。新landing10原始时间匹配强制接入，旧入口和旧8/0失败不改判。结果与完整SHA后续另记。

更新时间：2026-09-26。规划版本：v1（初始快照保留）。
仓库：/home/yr/Desktop/Codev-autopilot
分支：research/sta-velocity-control
规划时HEAD：866bba6e0d200d7a5137146c2a67a1a751e01233

[TODO及共同规则](</home/yr/Desktop/codev doc/plan/VELOCITY_STA_TODO_CN.md>)｜[阶段提示词](</home/yr/Desktop/codev doc/plan/VELOCITY_STA_PROMPTS_CN.md>)。

## 当前状态

- 最新离线修复HEAD：**ead33cba094f40dc943736e6ca5c29de81279cfd**（2026-09-26），起点7755b003868c25e105616483cd92d95151b7d68a。用户授权“先离线修复降落监视器的时间匹配，测试通过后再申请新批次”；仅新增landing10隔离策略/reader/monitor、禁用飞行草案、离线完整分析包装、回放/测试/文档，不修改生产控制/dt/参数/模型、旧运行器或冻结协议。原始唯一计划命令+此前/同刻AUTO_LAND+完成观察+armed/output0才能分类Gate2；晚到证据最多0.5s pending，不借未来状态，不当成功；真实故障/first_fail/retry/错误内环/reset/退出降落仍拒绝。原始reader从航向阶段持续使用；上锁须CLI和原始控制诊断已清零、无pending。仅landing宿主轮询sleep改0.1s，控制器dt及150s降落超时不变。
  最终120个不同C++（109控制+11转换链）、334 Python（302+新增32）通过，SITL/测试/DONT_RUN Gazebo只构建退出0。11项sanitizer重复不累计，2048帧旧源码等价及预期失败负对照保留。targeted01 24项中1错误文本断言失败（实际更早拒绝），修正断言后targeted02 30项通过；最终增补上锁/reader/必需字段回归，python_final03 334项、24.570s、退出0。完整验证当时332项，最后Python修改未冒称重跑C++。八批旧日志独立回放、284份原输入指纹不变；series05/06/08降落组件分别704/436/12条预期Gate，series06 reference变化仍拒绝，series08缺落地上锁仍失败；全部历史接受数不变。239份本轮直接工件索引及递归完整验证索引核验通过，参数06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc不变，无活动模拟器。15个明确文件提交，diff/最终源码指纹审查通过，提交后主仓库/递归子模块干净；不push。
  **新飞行0、已授权新预算0，V04仍failed/needs_revision，累计8尝试/0接受/ESTA0**。拟申请9901–9903各PID→ESTA X最多6次；22971份历史JSON无复用/未解释无效记录，旧M06空文件例外与IMU-only/PID先行偏差保留。proposal明确flight_authorized=false/execution_ready=false，series09未创建。需要用户条件授权后另冻protocol10配置、可执行运行器/最终分析器及来源/授权绑定、准确资产/源码提交并干净回归/飞前复查；禁止仅删禁用守卫启动。任一必需失败停，不重试/补飞/调参、不复用旧余5、不V05。报告：[landing10离线修复与新批申请](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_LANDING10_REPAIR.md>)。下方未修复/待定等记录保留历史时点含义。

- 最新结果HEAD：**7755b003868c25e105616483cd92d95151b7d68a**（2026-09-26），protocol09/series08实际源码 **a361ebda9783dc4bf65cbf6e57cce35520b0fa44**。用户回复“确认”后按9801–9803各PID→ESTA X最多6次执行，授权回执单独留档。首轮9801 PID完成60.172秒观察/32秒激励，计划降落初期被在线 `Unexpected excitation fault 2` 拒绝。归档CLI先读旧107.932s/nav4，再读新108.244s/Gate2；原始ULog108.244s已记录AUTO_LAND/nav18，表明宿主混合不同时间观测。只读复现，不据此补写落地或改判接受；未修运行器/检查器。计划6/尝试1/完整起降0/接受0/ESTA0/余5停止，累计8尝试/0接受，V04仍failed/needs_revision，不V05。
  实际命令调用2次：第一次外部环境遗漏已有pymavlink路径，在导入时退出1，无SITL/ledger/飞行预算消耗；修正外部显式环境后才执行唯一飞行，退出1。两次均完整留档，飞行失败后无重试/补飞。冻结最终分析因缺landed_disarmed继续拒绝/退出1；302项Python实际回归通过/退出0，18项只读诊断断言通过/退出0，不是完整飞行验收。前置干净提交120个不同C++和构建证据重新核验，本轮未重跑、不重复累计。主ULog SHA d94fd81e9826147b0a84d59042e62e85c8d699692d749626ae0e279215cc00e0；两份ULog dropout0/corruptionfalse；本次姿态同刻发布0，不能声称实际飞行覆盖该事件。276冻结资产、44原始工件、88结果工件及前置验证索引校验通过；参数恢复06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无活动模拟器。12个明确研究文件提交、diff审查通过，工作区及递归子模块干净；不改控制律/dt/参数/模型/门槛、不push。报告：[protocol09结果](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL09_RESULTS.md>)。下一步需另授权离线修订降落阶段跨话题观测/匹配及反例回归，再重新冻结新源码/种子/预算并取得飞行授权；不能直接续跑本批余5。以下“待授权/新飞行0/最新”等保留历史时点含义。

- 最新protocol09接线/冻结HEAD：**a361ebda9783dc4bf65cbf6e57cce35520b0fa44**（2026-09-26）。从f83ddbb0d265547e078c1cf96f8027f7af1777b3按用户“接入新运行器和完整分析链、回归、冻结并取得授权”完成20个明确研究文件提交。独立protocol09/flight10、在线预起飞/航向/交接capture及完整最终分析全部接通clock09；最新同刻组必须等更晚姿态发布才封口，尾组保留，原0.5s传输守卫不变；完整ULog仍查至落地上锁。旧入口/协议/生产控制/dt/参数/模型/数值门槛未改；没有把准备指令当作本批飞行批准。
  提交前protocol09_verify01和干净提交protocol09_committed01均**120个不同C++（109控制+11转换链）、302Python（277+新25）通过**，实际构建/SITL/DONT_RUN Gazebo及全验证器退出0；11个同转换链sanitizer重跑通过不重复计数，2048帧旧源码等价，旧源码缺陷负对照1项预期失败/退出1。真实ULog分段读取、完整分析正负例、实际monitor接线、6次mock预算/首次失败停止/EEPROM恢复均验证；合成来源正例不是新飞行。七批旧日志及新入口拒绝旧job复核，243份原输入不变，历史判定不变。开发test01的3失败（隐藏handoff旧检查、负例错误文本、尚无冻结文件）完整保留；test02的22项、test03的25项通过，未删测试或放宽门槛。
  新候选清单已登记：**9801 PID→ESTA X、9802 PID→ESTA X、9803 PID→ESTA X，最多6次**；首个必需单轮/配对失败停批，无补飞/重试/额外冒烟/调参，不复用旧五轮。登记前22023份JSON无冲突，后续复查通过，仅IMU播种及PID先行偏差继续披露。execution SHA `9e1e2a76a6498930a7af990b60b4c7ebabc7d1457c08b03d6e129cb767ca2921`；276资产manifest SHA `021397e64df8c13831277a37a92c20141eef7f1adf375d614557dd07b7210099`，6个插件依赖及receiver编译profile核验通过。干净源码固件SHA `651242b1967b67e9c2d68617e52e876e44da7949a0eb67d1ce8f98d62fdd22a2`；版本头为完整a361ebda9783dc4bf65cbf6e57cce35520b0fa44。提交后验证工件索引SHA `206765469f02ae20efb7bb6f4672c8bfd4a8f98f7efb3f17d5efc845ddf27a32`，提交前/后索引全量复核通过。
  编译/源码/模型/world/插件完整后验冻结见 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04/protocol09_clean_freeze.json`，SHA `bc7dd228bd2d52121075ab724ae0940ac4bee7c252cb883bc0a25c4e31a3dca1`。环境导出首次因gzserver --version打印11.10.2但返回255而中止，第二次严格JSON中转遇历史Infinity而中止；均未写冻结文件/启动仿真，最终记录原返回码并只导出有限摘要、哈希引用完整证据，未修改原数据。这两次是元数据导出失败，不冒称构建/飞行失败或通过。
  主仓库/递归子模块干净，EEPROM仍06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无活动模拟器；实际持久参数+默认rate0/0/1、RATT_TEST0、TKO_MGT0、速度0/0。**新飞行0、已授权预算0；6次仅冻结申请**。新series08目录不存在，旧7尝试/0接受/ESTA0及V04 failed/needs_revision保留，不V05、不push。下一步仅待用户明确批准上述源码/协议/准确清单，再记录仓库外授权回执并重复现场预检；旧字符串口令不能运行新批。报告：[protocol09实现](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL09_IMPLEMENTATION.md>)；[冻结清单与命令](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/v04/protocol09/README_CN.md>)。下方源码/飞行记录保留各自历史时点含义。

- 最新离线修订HEAD：**f83ddbb0d265547e078c1cf96f8027f7af1777b3**（2026-09-26），起点5f791eac46d004dfaf4bde818e35039eae6382ee。用户仅授权姿态双时间检查离线修订；clockcheck09仅白名单vehicle_attitude:0允许发布同刻，sample严格递增，完整边界/前驱/reset、同刻候选歧义及唯一输出键检查已实现。沿用20ms新鲜度/250ms覆盖等旧数值并明确其双时间应用，不改变控制律/dt/参数/数值安全阈值。3个共享研究分析助手增加显式opt-in，默认旧行为；历史protocol08入口逐字保留，新增版本化height检查。最终109个不同C++、277Python（原234+新43）及SITL/测试/DONT_RUN Gazebo构建通过，总退出0；未重跑11项IMU专项、MATLAB或完整异步EKF仿真。开发期空窗口夹具、协议继承加载及旧入口逐字契约各一次失败均保留；未删除旧测试或放宽门槛。七批原日志回放完成：series07双时间/航向检查通过但一处实际消费关联歧义明确拒绝唯一匹配，仍缺完整观察/降落；series06降落reference变化继续拒绝。series05原PID组件metrics/checks/输出匹配及高度结果等价，不能改判其历史整轮失败。243份原输入指纹不变；919份本轮工件归档，索引SHA b7628c1ab6c306dd908fd14d74a5c6516b639aff4a2dccea654d6278496422c5。旧253资产仅3个研究助手有意变化，其余250一致，旧快照不重写、不可直接复用飞行。EEPROM未变、无活动模拟器；18文件明确范围提交、diff/指纹检查通过、工作区及递归子模块干净。不push。新飞行/种子/预算0；V04仍failed/needs_revision，累计7尝试/0接受/ESTA0，本批1/0及余5停止不变。报告：[clockcheck09离线修订](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_CLOCK09_REPAIR.md>)。下一批前须新运行器/完整分析同政策接线及连续日志/端到端回归、明确歧义口径、另冻干净源码/固件/资产/新种子清单预算并获飞行授权；不自动续飞或V05。下方旧记录与里程碑飞行SHA保留历史含义。

- 最新离线审计HEAD：**5f791eac46d004dfaf4bde818e35039eae6382ee**（2026-09-23），起点7cad95b02ead3362f8955da4ca78e78b017ddfae。按用户“先离线审计发布时间与采样时间的验收语义”完成源码/时钟/uORB/logger及七批原ULog审计；同刻发布不等于重复采样，不能据此改判旧失败，也不能仅将<=改成<，还需定义同刻关联、窗口边界/reset、新鲜度与指标口径。新增只读审计和12项反例；109个不同C++、234Python及SITL/测试/DONT_RUN Gazebo构建通过，未重跑11项IMU专项。收尾指纹命令首次漏PYTHONPATH依赖导入失败，补齐后退出0；不计功能测试失败或飞行。14份原输入、19个源码、65份新外部工件及253冻结资产核验不变，EEPROM未变，无活动模拟器。9文件明确范围提交、diff检查通过、工作区干净；未改生产/现有验收器/协议/参数，未push。新飞行/种子/预算均0；protocol08仍1尝试/0接受/余5停，累计7尝试/0接受/ESTA0，V04仍failed/needs_revision，不进入V05。报告：[双时间语义审计](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_CLOCK_SEMANTICS_AUDIT.md>)。下一步需另授权离线修订姿态白名单及歧义处理；不能直接续飞。下方旧“最新”与里程碑结果SHA保留其历史/飞行结果含义。

- 最新结果HEAD：**7cad95b02ead3362f8955da4ca78e78b017ddfae**（2026-09-23），协议/实际源码SHA **8df90c62a148d9b4b18c18e0c96796f1cebf932b**。protocol08/series07新授权9701–9703最多6次，干净提交完成120个不同C++（109控制+11转换链）/222Python、构建及sanitizer/2048帧旧源码等价后实际执行。首轮PID起飞/交接成功，47.016s进入观察，60.128s两条vehicle_attitude发布时间相同触发冻结严格递增检查，60.244s宿主检出；实际采样分别60.124/60.128s递增、载荷不同，原始二进制记录与两种解析核对一致。已记录区间无primary切换/reference或位置速度reset/控制fault，但任务仅13.228s观察、9.86s激励，未到降落，不能评价此前IMU0修复的降落效果。计划6/尝试1/完整观察0/完整起降0/接受0/ESTA0，余5停止；累计7尝试/0接受，V04仍failed/needs_revision。15项只读诊断通过不等于飞行验收；完整分析缺hover_end仍拒绝。41原始工件/263验证工件及旧42/59/175/84工件、253执行资产指纹核验通过；EEPROM完整恢复、无残留模拟器。结果13个明确文件提交、diff审查通过，工作区干净；本轮未改生产控制或日志门槛、未补飞、未push、不V05。报告：[protocol08结果](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL08_RESULTS.md>)。下一步建议先离线审计发布时间与采样时间语义再决定规范修订，不直接删检查或去重原始日志。下方in_progress及旧HEAD保留历史含义。

- 2026-09-23 新授权批次 in_progress：用户明确“重新冻结并授权新批次”，从IMU0转换修复1f743f779f591abd57585911f391f64f292497f9建立protocol08/series07并提交 **8df90c62a148d9b4b18c18e0c96796f1cebf932b**。9701–9703各PID→ESTA X，共最多6次；第一次必需单轮/配对失败即停，不补飞、不复用旧五轮。原参数/场景/数值/日志门槛全部不变，降落EKF切换仍拒绝。253项资产明确包含修复链与消费者；登记前21566份JSON无种子复用。提交前109个控制C+++11个转换链C++、222Python及构建通过；2048帧原源码等价、sanitizer及旧源码负对照通过预定检查。一次新增测试旧文件名引用错误已修复，失败保留，无飞行。协议已提交，正在干净提交验证，正式结果及第二提交SHA待更新；旧失败不改判、不push、不V05。下方记录保留历史时点含义。

- 最新获准离线修复HEAD：1f743f779f591abd57585911f391f64f292497f9（2026-09-23）。用户明确“授权修复转换链”；起点e9d824d06d5b253937d739da57f53bd531169fb6、研究分支/工作区及递归子模块干净，完整读取计划/共同规则/进度及前置报告。生产仅Simulator加速度块：有限超量程先物理单位限幅再int16，保留正常量化与原驱动clipping；共享向量NaN/Inf拒绝、不发布零/伪新样本，原错误计数累计，last-valid时间及blocked/stuck原语义保持。IMU1/2有限浮点、驱动/积分器/陀螺/EKF/控制器/参数/模型/协议/阈值不改。11个真实链C++（原4+新7）及同11个Simulator转换sanitizer通过；2048帧与冻结旧Simulator输出记录完全一致。冻结旧源码运行新方向/clipping用例预期1失败/退出1，负对照保留。原109个不同C++/211Python、SITL/测试/DONT_RUN Gazebo构建通过，退出0；重复不累计。单无效帧后加速度真实8ms、20帧无效后FIFO84ms及原积分器恢复有测试，不称缺样即安全或异步时序完全等价。三轴±250脉冲反向/漏报修复，裁幅仍损失面积，不能保证EKF不切换或证明旧飞行唯一根因。新84份外部工件、旧42/59/175份及199项资产指纹核验通过；旧资产表未列转换源码，后续必须新冻提交/固件/依赖，不能据旧匹配续跑。EEPROM未变、无残留模拟器。15个明确文件提交、diff/证据审查及提交后工作区检查通过；未push，无新飞行/种子/预算，不V05。V04仍failed/needs_revision，本批1尝试/0完整起降/0接受、ESTA0、余5停及累计6尝试/0接受不变。报告：[IMU0转换链修复](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_IMU0_CHAIN_REPAIR.md>)。本次标offline_passed仅指授权修复与离线回归；新批次须另冻并获准。下方“未修复/待授权”等均保留历史时点含义。

- 最新离线验证HEAD：e9d824d06d5b253937d739da57f53bd531169fb6（2026-09-23）。按用户“先离线验证 IMU0 转换链”，实际编译调用未修改的Simulator::update_sensors、PX4Accelerometer及VehicleIMU::Run，经真实uORB复现三轴±250m/s²单个4ms脉冲在IMU0反向积分、clipping仍0；IMU1/2浮点链保留方向。+16g已超int16正端，NaN/Inf等也触发原转换行诊断。4个正常C++用例、1个缺陷复现用例按预期通过；同4项sanitizer重复运行不累计，10个非法输入分别预期退出1，不能称生产实现安全通过。原109个不同C++/211个Python及SITL、DONT_RUN构建通过。verify01–05编译/链接/测试队列隔离失败完整保留，06/07成功；175份本轮外部工件、199冻结资产、42原始工件、59前次审计工件指纹校验通过，EEPROM不变、无残留仿真。16个明确研究文件提交，提交后工作区干净；无生产/参数/协议/门槛修改、无新飞行、未push。仅验证至vehicle_imu发布边界，未执行EKF融合/selector或真实接触模型；旧HIL峰值缺失，尚不能证明旧降落切换唯一根因。V04仍failed/needs_revision，本批1尝试/0完整起降/0接受、ESTA0、余5停止及累计6尝试/0接受不变。建议另行授权上游仿真转换修复及离线回归，尚未实施、不V05。报告：[IMU0转换链离线验证](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_IMU0_CHAIN_AUDIT.md>)。下方“最新”均保留历史时间点含义。

- 最新离线审计HEAD：ef12d22419dfb0ab91dea21cd976f86da113b7fa（2026-09-23）。按用户“先离线审计降落期EKF切换与目标补偿”，读取series06原始ULog：主EKF0→1符合较低相对误差选择条件；本次旧缓存XYZ/yaw仅补偿一次，下一份新目标不重复补偿，Z误差当帧连续。切换前真值已下降转回升，发现Simulator IMU0无检查float→int16转换风险并合成复现，但原HIL峰值缺失，不能确认旧飞行因果。109个不同C++/211个Python及SITL、DONT_RUN构建通过，18项只读证据检查成功；sanitizer越界退出1为预期风险检出，不是生产实现通过。199冻结资产、42原始工件、59本轮外部工件校验通过，EEPROM未变。仅提交研究脚本/探针/文档/证据；无生产/参数/协议/门槛修改，无新飞行、无新预算，原本批1尝试/0完整起降/0接受/ESTA0/余5停止及累计6尝试/0接受不变。建议先离线验证真实FIFO转换链，尚未授权修复或降落reset豁免。V04仍failed/needs_revision，未push、不V05。报告：[降落EKF审计](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_LANDING_EKF_AUDIT.md>)。下方“最新”保留历史时间点含义。

- 最新结果HEAD：1032dcf56cb62a713c8ae00ce402d4c3160ca71f。protocol07/series06已执行并停止：PID首轮起飞、60.388秒观察/32秒激励完成，降落111.656s真实主EKF 0→1，ref_timestamp及位置/速度/航向reset变化，112.028s宿主检出中止。计划6/尝试1/完整起降0/接受0/ESTA0/余5停止；无补飞。两项日志修复在本轮部分窗口验证通过，但原始流也拒绝降落切换，不是打印精度问题。109C++/204Python及干净构建通过，13项只读诊断成功不等于飞行验收；V04仍failed/needs_revision。参数完整恢复、无残留模拟器、工作区/递归子模块干净，未push、不V05。报告：[protocol07结果](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL07_RESULTS.md>)。下方in_progress及旧HEAD保留当时记录。

- 2026-09-23 新批次 in_progress：用户再次明确“重新冻结并授权新批次”。新protocol07/series06已冻结并提交658e57e8ff549cdb89780c61c53ca8b3ec4faa0d；清单9601、9602、9603各PID→ESTA X，共最多6次，任一必需单轮/配对失败停止，无补飞/额外调参。只接入logcheck07两项已验证检查，生产控制/参数/阈值不改。注册前21469份JSON无种子复用，199项资产冻结；提交前109C++/204Python与构建通过。正在干净提交重建复核，尚未启动本批；旧失败/接受数保留，不push、不V05。最终运行数与结果SHA另更新。下方此前“最新”保留历史含义。

- 最新 HEAD：2f273cff7f54d929bcfe8558285c5af3e111aaff（V04 logcheck07 离线修复）。按用户“离线修复这两类日志检查”实现事件专用时间语义与固定编译接收器坐标参考，新增15项Python回归；最终109个不同C++/195个Python及SITL、DONT_RUN Gazebo构建通过。独立旧日志重分析 revised_checks_passed=true，但 accepted=false、历史不改判。无飞行、无新种子/预算、无控制律或阈值修改；旧批仍0接受/ESTA0，V04仍failed/needs_revision。提交后工作区干净，未push。报告：[V04_LOGCHECK07_REPAIR](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_LOGCHECK07_REPAIR.md>)。以下旧HEAD/未修复等条目保留历史时间点含义，不代表当前状态。

- 分支已建立并切换，原角速度研究分支保留。
- V00 passed：另获授权修复world核验并重冻3次预算后，恢复批次02三轮起飞—60秒悬停—降落上锁及49项/轮日志检查均通过。
- 37个不同C++用例、飞行前25/最终31个Python工具用例通过；历史Takeoff测试失败及批次01启动失败记录保留，不改成通过。
- V01 passed：仅PID可生效的速度选择框架、独立参数与选择日志已实现；44个不同C++及37个Python用例通过，两组各2048步与V00参考逐样本一致，唯一一次PID起降/60秒悬停及实际ULog验收通过。
- V02前置已恢复：候选来源/轴/载荷绑定修复，原3项失败探针重跑通过，补齐54组合的独立双精度对象证据。原失败记录不变。
- V03 passed：用户明确“运行”另授权protocol02一次预算，干净提交上完成原PID起飞、60.2秒观察（完整32秒小速度激励）、降落上锁及实际ULog验收。82个C++/52个Python通过。旧protocol01离地前中止保留；累计尝试2/接受1，不改判旧失败。
- V04 failed / needs_revision：已接入仅SITL MODE1/AXES1的ESTA X路径，默认PID；92个不同C++/57个Python通过。首轮PID相对高度1.9669m低于2.0m入口，并发现起飞同帧二次update及激励锁止。计划6/尝试1/完整0/接受0/未执行5，ESTA飞行0，不续跑、不V05。
- 原PID数学/起飞逻辑保留、参数字节恢复、旧日志保留。V03及以前已按用户后续要求push；本次V04不push。下方各历史记录的“未push”描述保留当时事实。
- V04 REPAIR01：用户另授权先修复、暂不飞行；目标缓存/本帧抑制分离、明确fallback目标、激励失败通知和时钟分离、首次失败日志及最终输出检查完成。104个不同C++/58个Python通过，仅离线通过，不改判V04。
- V04 protocol03 / series02：用户批准正常计划降落Gate2分类后，隔离高度任务运行器/分析器完成，104个不同C++/89项Python及干净构建通过。新批首轮PID起飞后约1.60m发生heading_reset_counter 2→3（约0.376°），触发冻结reset计数门槛；1尝试/0接受、后续5停止、ESTA飞行0。日志与原EKF首次空中航向对齐机制一致，无控制器故障或同帧重算证据，但不能改判通过或补飞。
- 当前HEAD：110e3f667eaca57280519621d52fe6f63413a774（protocol06/series05结果）。用户重新冻结并授权9501–9503共6次；干净协议源码c9030688efffce4984f39f3aa08fe270eda7206c上109C++/180Python与构建通过。首轮PID完整起飞、60.160秒观察/32秒激励及降落上锁，但命令日志检查拒绝，1尝试/1完整/0接受、余5停止，ESTA0。只读定位事件同刻时间和接收器一ULP表示差异，未修检查器/未续飞；V04仍failed/needs_revision。工作区/递归子模块干净、未push，领先本地跟踪引用16提交。
- 主线：位置P保留、速度先X再XY ESTA、Z速度PID、姿态和角速度PID；未批准Z/Proper-ISTA/双层组合执行。
- 旧I05剩余17轮继续保持未执行，不属于新速度研究任务；旧数据只作经验，不能算新速度样本。

## 里程碑

| ID | 功能 | 状态 | 协议/源码SHA | 结果SHA | 实际尝试/接受 | 报告 |
|---|---|---|---|---|---|---|
| V00 | 审计与原速度PID基线 | passed | 7f0274c1a0ab129065a887d9c5546ad47dfa13bb | b11068e2ddb0c6734ae566045dc096eaf7a7c834 | 新批3/3接受；旧1启动失败保留 | [V00](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V00.md>) |
| V01 | 选择框架/PID等价 | passed | e28dd90617988788399b0c54c95e97ad80001d3c | 6c5b914ef2b1aff7de7ce90cb6eae4d8764265f7 | 1/1接受 | [V01](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V01.md>) |
| V02 | ESTA速度内核 | passed（修订后） | 3d7b5a0dfcf36be5ae678a76c9d8c1f0f52b3eba（历史） | 修复d5fb5c5c2b89c33a23cac7af1c2e79d1d5c89e5b；失败审计保留 | 0/0（离线） | [V02及勘误入口](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V02.md>) |
| V03 | 保护/日志/分析器 | passed（protocol02） | 5e637e20c60ea7e812252f49eda6ac6f7433531b | 21e56a17ff7cbac5f7fe2fe6e2c8420748f317cf | 新批1/1接受；旧批1次离地前中止保留 | [V03](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V03.md>) |
| V04 | ESTA X | failed / needs_revision（计划降落监视器混合旧nav与新Gate） | a361ebda9783dc4bf65cbf6e57cce35520b0fa44；旧协议保留 | 7755b003868c25e105616483cd92d95151b7d68a；旧结果保留 | 本批1尝试/0完整起降/0接受、余5停；累计8尝试/0接受、ESTA0 | [最新结果](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL09_RESULTS.md>) |
| V05 | ESTA XY | pending | — | — | 0/0 | 未生成 |
| V06 | 名义任务/脚本 | pending | — | — | 0/0 | 未生成 |
| V07 | 速度分频/耗时 | optional_pending | — | — | 0/0 | 未生成 |
| V08 | 等预算训练/正式冻结 | pending | — | — | 0/0 | 未生成 |
| V09 | 正式留出 | pending | — | — | 0/0 | 未生成 |
| E01 | Z/XYZ | awaiting_scope_approval | — | — | 0/0 | 未生成 |
| E02 | Proper-ISTA速度版本 | awaiting_scope_approval | — | — | 0/0 | 未生成 |
| E03 | 内外环2×2组合 | awaiting_scope_approval | — | — | 0/0 | 未生成 |

状态：pending、in_progress、passed、failed、needs_revision、blocked；可选阶段另用optional_pending/awaiting_scope_approval/skipped_by_scope。blocked必须说明缺失依赖；未满足必需验收不能写passed。

## 阶段记录模板

每完成一阶段追加，不覆盖历史失败：

- 阶段/日期/状态：
- 开始分支/HEAD/工作区：
- 实际修改范围：
- 预注册协议/参数/种子/任务预算：
- 构建/单测命令、退出码、实际用例数：
- 实际计划数/尝试数/完成数/接受数/未运行数：
- 失败、缺失及协议偏离：
- 外部数据路径、ULog及汇总SHA-256：
- 对照参数与实际速度/角速度模式：
- 协议/源码提交完整SHA：
- 结果提交完整SHA及提交后检查：
- 报告链接与未执行项：
- 下一阶段是否准入：通过不表示自动授权。

## 规划检查记录

2026-09-19：核实新分支和HEAD，阅读原里程碑及ISTA后续经验，检查PositionControl、模块Run/HTE/Takeoff/failsafe及测试注册。计划文档与链接/快照一致性校验不属于飞控单测。
新目录尚无执行脚本；所有拟议参数和日志仅是设计草案，不可直接当已实现命令使用。

## V00 执行记录（2026-09-19审计，2026-09-21收尾）

- 起点分支research/sta-velocity-control，HEAD d00417ed1ccb779d6f7d3573328657f6ae9629a5，工作区干净；递归子模块及内部工作区均干净。
- 已完整读取速度计划/共同规则/状态、旧共同规则和I00/I01/M09/M10/I05日志审计与续跑实现报告。
- 三份外部计划与plan/v1起初逐字节一致；本实时表自此次更新起与历史初始状态不同是预期，禁止覆盖初始快照。
- 修改范围：README、reports/V00.md、v00接口审计/小型证据和三个离线脚本；共12个仓库文件。
- 原PositionControl/ControlMath/Takeoff和模块、HTE/failsafe/时间接口已审计；保留源码参考副本、模型/world、参数BSON和插件/固件指纹。
- make px4_sitl_default -j4：0；make tests TESTFILTER=PositionControl -j4：0。
- PositionControl 15/15、ControlMath 9/9、RateControl 1/1、RateControlDispatcher 4/4通过；Takeoff 1/2通过（退出1）。
- verification02/03重复结果一致，不将重复执行累计为更多唯一用例。verify_v00.py总退出1；Python归档器6项测试通过（退出0）。
- capture_v00.py最终audit03退出0；开发期版本命令返回255、错误文件名、BSON尾随字节解析失败均有记录和保留目录。
- 失败根因：Takeoff.cpp第46行的零初值来自317ee4c9cca25c33bc4ef81fc48056fb1d82800d（2021-11-08），旧测试未对应更新；不是此次研究引入。
- 计划最多3轮，实际尝试0/完成0/接受0/未执行3；未冻结可执行飞行协议，PID-only运行器尚未完成。没有ULog或新基线指标。
- 原始数据：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260919/V00。
- 157份外部证据SHA校验通过；索引SHA256：2b7dcd5e265ee3730e0b7ecd1373a004a7bdfec426f5e71031eac900d711a11a。
- 固件SHA256：db49db4d7ff1f92a3738c8259de845ac77971a1d0feee552e2a050cff35c0c20。
- 当前仅核对静态默认/持久化覆盖；MC_RTC_MODE=0、AXES=0、DIV=1、MC_RATT_TEST=0、MC_STA_TKO_MGT=0尚未用运行参数和日志实证。未设置/保存飞行参数，原BSON保持不变。
- 提交：8462f8139e88b8976dcd89424c3c04525489b72b，docs(research): record V00 audit with failing legacy takeoff test。
- 提交性质：失败审计/WIP，不是通过或飞行协议提交；未push，未进入V01、未启动旧ISTA实验或实机。
- 下一步需明确Takeoff应保留CODEV零初值还是改变起飞行为；建议先保留生产行为并审查补齐测试，获准后继续V00。不得用放宽检查或删除失败换通过。

## V00 恢复批次01（2026-09-21）

- 用户授权保留现有起飞逻辑，修订并补齐测试，然后继续三轮基线；历史失败保留。
- 起点8462f8139e88b8976dcd89424c3c04525489b72b，研究分支、工作区/子模块均已核对。
- Takeoff.cpp及全部控制数学未变；TakeoffTest修改3项旧数值断言并新增6个用例，现Takeoff8/8通过。
- PositionControl15、ControlMath9、Takeoff8、RateControl1、Dispatcher4，共37个不同C++用例通过；16个Python工具测试通过，构建与验证命令退出0。
- HIGH_RATE日志增录位置状态、最终位置/速度目标、trajectory_setpoint；原profile位保留并OR16；没有控制调度变化。
- 协议/源码提交：178c9a41c9dd19031f6b4c9202c19d1db2c6231e，干净提交重建后启动，固件与控制台SHA一致。
- 预算run01→run02→run03，最多3次；原默认随机引擎seed=null，不称3个独立种子。1倍Iris SITL，预定2.5m/60s悬停/降落。
- 实际尝试1、起飞0、完成0、接受0、未运行2；总执行退出1。run01在起飞前报Actual model/world not confirmed。
- 根因：运行器错误要求console包含empty_grey.world；原启动器使用环境变量指定world时不会打印该路径。Iris模型Using路径正确。没有证据显示飞行不稳定或实际world选错。
- 严格停止后续尝试，不重试/补飞/扩大预算。未冻结新的修复批次，不能自动继续。
- 短启动ULog真实解码：MODE0/AXES0/DIV1、armed0、fault0；实际参数旧激励/起飞管理为0，Iris10016。无飞行周期/RMSE指标。
- 数据：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V00；verification01/02/03和series01全部保留。
- ULog SHA256：75d7d67c7ba05fc9d6b69e84cc8dcda1b0a70b63c776cb4be84c07e93edbb05c，181541字节，dropout0，仅启动数据。
- 固件SHA256：8525398de7f0723479795841f86d4c18c8c1a468bd494a579ff8036fe71548b5。
- 原参数完整字节还原，前后SHA256：06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc。旧7个日志目录保留，无模拟器残留。
- 新171份证据索引全量核验通过；索引SHA256：86ffed1c67db2ff31d580dc003b4cba1fdb0b2637f490e23f606d4dd9521484f。
- 结果提交：22bf39a3b1361bf032923817bb1b37496e448297；报告 [V00_RESUME01](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V00_RESUME01.md>)。
- 提交后明确文件范围、diff检查、证据与参数SHA核验通过，工作区干净；未push、未执行V01/旧ISTA/实机。
- 下一步：修复world实际进程证据核验并补工具回归，重新冻结准确批次/预算需用户授权。本次启动失败不得从历史记录删除。

## V00 恢复批次02（2026-09-21，passed）

- 用户明确同意修复world核验、补齐工具测试并重新冻结三次基线预算；随后要求继续。新预算独立于旧失败批次，未擅自补飞。
- 起点22bf39a3b1361bf032923817bb1b37496e448297，research/sta-velocity-control；起始工作区和递归子模块均干净。
- 新增world进程证据核验与9项测试，确认自有session、唯一gzserver、实际绝对world argv、白名单环境及SHA；不再依赖未打印的console world字符串。
- 协议/源码提交及三轮实际飞行HEAD：7f0274c1a0ab129065a887d9c5546ad47dfa13bb。提交后DONT_RUN重建，飞行在干净源码运行。
- 原Takeoff生产逻辑、控制律/增益/模型/插件未变；保留上批测试修订和三个高频话题请求。
- 构建、37项C++（Position15/ControlMath9/Takeoff8/Rate1/Dispatcher4）、飞行前25项Python均退出0；飞行后增加6项勘误测试，最终31项Python通过。
- 计划3次，实际3次，起飞3次、完成3次、接受3次、失败0、未运行0。run_v00总退出0；每轮原ULog分析器49项检查通过。
- 悬停60.392/60.392/60.480秒；完整起降。MODE0/AXES0/DIV1、RATT_TEST0、TKO_MGT0；无failsafe/fault/termination。
- 实测位置/速度状态与输出约100Hz，周期8/12ms；角速度诊断250Hz、无序号缺失；ULog dropout均0。
- actuator精确输出匹配覆盖92.48%/92.84%/89.91%，匹配差0、最大间隔8ms；不能称下游完整无损。
- 起飞参数2.5m，原起飞后转Hold；实际估计悬停高度均值1.924/1.934/1.947m，符合冻结包络，但不称精确2.5m定高任务。
- 默认随机引擎seed=null，三次重启不称独立配对种子。无算法胜出/实机安全结论。
- 保留原分析JSON；另补描述性勘误：sat_bits!=0误计入valid位，原1.0不是真实饱和率。三轮sat_bits全1、有效反馈100%、真实方向饱和0%。
- perf原正则未匹配cycle time，补充审计读真实计数，约100.013/99.997/99.983Hz；sim elapsed=0不等于CPU零成本。两项均非门槛，原3/3判定不变。
- 数据根：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V00，新增verification04、series02、series02_descriptive_audit；全部历史保留。
- 完整飞行ULog SHA：da2b22b5b1a6d5fcf8766b545a4b1c91e66a10ba309c6c65ada8b00ee6522404；6b5148ee48ecd5916c74461d46808cb6a7e644e6545e22b4e54b4cdc58960041；6896b183ec61c61b5dc5005631f5a97761a1f74a109d87318894b8fb245c188f。
- 139份外部文件SHA逐份核验通过；索引SHA：1476a920cad70649dca65aa9106455d493e531f5ba0f90f138e53c1a2d4aedaf。
- 固件SHA：cc007b897d3c5158b31f803e50e74d3ed2ac38250f1c7919c756988dc3a526ed；原EEPROM完整恢复SHA：06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc。
- 结果提交：b11068e2ddb0c6734ae566045dc096eaf7a7c834，17个明确范围研究文件；提交前diff/指纹审查通过，提交后工作区干净。
- 报告：[V00_RESUME02](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V00_RESUME02.md>)；入口V00.md和README已更新。
- 未push、未执行V01、未继续旧ISTA、未部署实机；下一阶段前置验收满足，但仍须用户明确开始。

## V01 执行记录（2026-09-21，passed）

- 起点research/sta-velocity-control，HEAD b11068e2ddb0c6734ae566045dc096eaf7a7c834；当时工作区/递归子模块干净，与本地codev跟踪分支同步。上文V00“未push”保留为历史收尾记录，之后用户已要求并完成push。
- 完整阅读速度计划/共同规则、实时进度表、V00及恢复批次02验收；首次V00已读取指定旧研究经验和日志审计。
- 新增MPC_VC_MODE/MPC_VC_AXES及selector/dispatcher，明确requested/effective/pending/reject。仅0/0合法，MODE1/2及所有非零axes显式拒绝，默认PID不变。
- 原PID函数体仅改名；原参数更新、状态处理、failsafe函数逐字节核对不变。新增最小velocity_ctrl_selection日志及注册，保留既有profile位。
- 两组各2048步与V00冻结PositionControl/ControlMath/Takeoff参考比较：有限浮点逐位一致，NaN语义一致，含FF/ARW/HTE/ramp/reset及同帧失败后第二次update。参考只进入测试，不进入SITL固件。
- verification01保留首次测试链接失败（make退出2）；补齐功能测试parameters链接依赖后verification02通过。不是飞行失败，没有自动补飞。
- make px4_sitl_default、make tests TESTFILTER=VelocityControl、verify_v01.py及提交后DONT_RUN Gazebo构建均退出0。
- 44个不同C++用例：PositionControl15、ControlMath9、Takeoff8、RateControl1、Dispatcher4、VelocityControl6、VelocitySelectionParam1；37个Python用例通过。重复运行不累计为更多不同用例。
- 协议/源码及唯一实际飞行提交：e28dd90617988788399b0c54c95e97ad80001d3c；26个明确文件。干净提交重建并运行，固件git-hash及SHA与记录一致。
- 固件SHA-256：0b0689dcea1393c63c217472cbfbcf00788552e3269e61b80341f7f9c8188459。Gazebo子模块822050a7ab6fd87972e59f16312f451bce217a56；实际Iris10016/quad_w、empty_grey.world，沿用项目启动器。
- 预注册1次，实际尝试1/完成1/接受1/失败0/未运行0；run_v01.py退出0。seed=null，原默认随机源，不声称独立配对样本。
- 起飞30.564s、Hold37.704s、悬停42.284–102.336s（60.052s）、108.456s落地上锁；继承V00的49项门槛和新增选择日志验收均通过。
- 实际MPC_VC_MODE/AXES=0/0；MC_RTC_MODE=0、MC_STA_AXES=0、MC_RTC_DIV=1、MC_RATT_TEST=0、MC_STA_TKO_MGT=0。飞行关键参数不变，位置P、Z速度PID、姿态及rate PID保持。
- 全飞行7789条选择状态、100Hz、最大间隔12ms、发布序号连续；requested/effective均0，pending/reject均0，enabled时pid_calls均1。rate日志250Hz且序号连续，无fault/failsafe/termination。
- ULog dropout0；actuator匹配覆盖92.44%、匹配输出逐位一致，不能称下游完整无损。三个非必需话题因订阅上限未记录，必需9个话题均真实解码。
- 速度RMSE X/Y/Z=0.010751/0.008080/0.005138m/s；悬停估计高度均值1.9477m、最大倾角0.7413°。保留原起飞转Hold，不能称精确2.5m任务或算法性能胜出。
- 正确解释饱和valid位：反馈100%有效、方向饱和0%；原V00分析器描述字段保留，另存勘误。模拟perf elapsed=0不等于CPU零成本。
- 外部数据：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V01；verification01/02、构建/执行日志、series01原始日志/参数/CLI全部保留。
- 完整飞行ULog series01/run01/12_26_21.ulg，30198450字节，SHA-256：6114d45bb3f4e4a5f50061b689084541f6e86caa07681cd2de987dcf25dff4eb。
- 67份外部证据逐份SHA校验通过；索引SHA-256：456a4b94269d2df947da5ecc8e7400a006869c30108d1c9afd661b11d497edfe。
- 原EEPROM完整1129字节恢复，前后SHA-256：06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc。旧日志保留，无模拟器残留。
- 结果提交：6c5b914ef2b1aff7de7ce90cb6eae4d8764265f7；10个明确文件，仅报告/README/小型JSON、XML及指纹索引。提交前diff检查和证据核验通过，提交后工作区干净。
- 报告：[V01](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V01.md>)。未执行MATLAB、新速度算法飞行、V02、旧ISTA或实机部署；未push。
- V02前置满足，但不自动开始，仍需用户明确授权。

## V02 执行记录（2026-09-21，passed）

- 起点6c5b914ef2b1aff7de7ce90cb6eae4d8764265f7；research/sta-velocity-control及递归子模块干净，且与codev跟踪分支同步。完整阅读速度TODO/共同规则、实时表和V01；首次V00读取的旧研究经验/日志审计不被重写。
- 新增测试专用C++14 `StaVelocityControl`：`s=v-v_sp`（m/s）、`a_sta`/`nu`（m/s²）、lambda2（m/s³）；evaluate用旧nu，commit一次写入，三轴状态/实例隔离，reset和配置改变均使旧候选过期。
- 内核没有角速度g、力矩归一化、质量除法、推力/姿态/限幅/保护或生产前馈注入。未来适配器只能将原a_ff加一次；本阶段仅离线验证该组成，不能据此称真实响应无滞后。
- 内核仅在BUILD_TESTING下建库，不属于生产PositionControl目标。生产PositionControl、selector、参数、日志、位置P、原速度PID、Z速度PID、姿态/rate PID均未改；MODE1/AXES1仍被V01 selector拒绝。默认SITL固件nm查询无StaVelocityControl符号。
- V00/V01实测速度周期冻结为8/12ms、平均约10ms，内核参考/对象采用该矩阵，未套用rate的4ms。
- 新增StaVelocityControl 7个实际C++用例全部通过：旧nu/一次commit/FF、正负零误差、轴隔离与陈旧候选、非法输入/参数/dt/溢出下溢原子拒绝、384步binary64参考、常量/斜坡扰动与非零FF的理想/受限ZOH对象、模式仍拒绝。
- 实际回归通过：VelocityControl6、PositionControl15、ControlMath9、Takeoff8、RateControl1、RateControlDispatcher4、StaRateControl11；加新增7共61个指定C++用例。RateControl筛选还运行2个既有ISTA/Proper-ISTA目标并通过，但不计速度ESTA验收数。
- 项目`.px4-python`环境下所有最终测试和`DONT_RUN=1 make px4_sitl_default gazebo_iris -j4`退出0；明确未启动仿真。开发期保留C++14初始化列表、float-equal、过紧float-vs-double容差、未转义管道筛选及系统Python缺toml/empy等失败事实，均未飞行。
- 计划/实际飞行0/0/0/0；无新种子、ULog、外部实验目录或MATLAB/Octave运行。V01数据及指纹不变。
- 提交：3d7b5a0dfcf36be5ae678a76c9d8c1f0f52b3eba，6个明确范围文件；diff检查、提交后主仓库/递归子模块清洁核对通过。未push、未开始V03、未部署实机。
- 报告：[V02](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V02.md>)。V03离线保护/日志前置满足，但仍须用户明确授权。

## V03 前置复核（2026-09-21，needs_revision）

- 当前准入以下述证据为准，上文V02 passed与未push保留为历史收尾描述，不作为现阶段准入。
- 起点3d7b5a0dfcf36be5ae678a76c9d8c1f0f52b3eba，research/sta-velocity-control；起始主仓库/递归子模块干净，与codev跟踪分支同步。完整读取外部速度计划/共同规则、实时表与V02报告。
- 实际核对GCC11.4.0、Gazebo11.10.2及全部递归子模块；未修改src/msg/sitl/模型/内环控制。Gazebo仍822050a7ab6fd87972e59f16312f451bce217a56。
- 新建audit_v03_preflight.py与未注册进固件的CandidateAuditTest.cpp；逐字节核对原内核/原测试/selector/PositionControl/CMake与V02提交一致。
- preflight01：独立g++链接缺失RTTI符号，退出1，测试0；按既有gtest选项补-fno-rtti/-fno-exceptions后另存preflight02。初次日志/旧status=in_progress均保留，按命令退出码识别工具编译失败。
- preflight02：C++14编译退出0，实际10项C++测试，原7项通过、新3项失败，进程及运行器退出1；无disabled。未重跑完整SITL或全部历史用例。
- 失败：跨实例候选被接收、修改axis后跨轴提交被接收、a_sta变为NaN后仍提交有限nu_next。前两项使目标nu从-0.5变为约+0.492；第三项从+0.5变为约+0.492。
- 这些是显式错误调用复现，非已发生的飞行故障；原ESTA公式未被推翻。缺少候选来源/完整性约束，需在内核契约或完整验证的适配器中解决。
- V02独立对象勘误：对象测试只演化一个velocity，doubleEsta与float共享它；没有独立推进的double对象轨迹。受约束例仅检查有限/饱和/RMSE>0，不能据此给稳定性或性能验收结论。
- 同一候选重复commit已有保护，但同sensor sample重新evaluate的去重仍属V03待实现内容，不算本次3项失败之一。
- 只读BSON与生成默认：MC_RTC_MODE0/MC_STA_AXES0/MC_RTC_DIV1/MC_RATT_TEST0/MC_STA_TKO_MGT0，MPC_VC_MODE/AXES0/0；七项无持久化覆盖。runtime_verified=false，无新运行参数或ULog验证，最近实测仍V01。
- 原BSON字节不变，SHA256 06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc。
- 数据：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V03/preflight01与preflight02；45份证据全量指纹核验通过。索引SHA256 bb8892c4d952fad0954ca3fdd6eed412d51f2c1421c9b086d3392266f65d1541。
- 计划1次PID小速度任务：尝试0/完成0/接受0/未运行1；未冻结可执行飞行协议，未使用预算，无新ULog/MATLAB/实机/旧ISTA/V04执行。
- 未完成保护、sta_velocity_ctrl_status、真实ULog分析器和V04门槛；不是依赖缺失，状态needs_revision，不写passed或blocked。
- 提交1a1b3c4278ad50e0adbacb394ff5021dd82c6ae8：9个明确范围研究文件，失败审计提交；报告[V03](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V03.md>)及V02历史正文上方勘误入口。提交前diff/指纹审查通过，提交后工作区干净；未push。
- 恢复要求：修订候选接口并补独立对象证据，再继续本次V03保护/日志/回归和协议冻结；前置恢复前不启动飞行或进入V04。

## V03 功能、协议01失败与订阅修复（2026-09-22）

- 用户要求继续后，修复V02候选来源/轴/载荷绑定，补54组合独立float/double对象与原3失败探针；旧数据/初始计划不覆盖。
- 新增测试专用加速度域保护：old nu输出、候选/applied分离、一次FF、NED方向冻结、限幅、逐sample去重、armed配置暂存、地面/退出/reset/故障生命周期。不改原PID，不把mixer机体系位套给NED。
- 生产MODE1/2仍拒绝；SITL无StaVelocityControl/Protection符号。新增PID诊断及默认关闭的SITL X激励、真实ULog拒绝型分析器。
- 初次79个C++/48个Python、SITL/Gazebo只构建通过；PID两组各2048步逐位等价。协议/源码提交d5fb5c5c2b89c33a23cac7af1c2e79d1d5c89e5b，干净提交重建再次通过。
- 固件SHA51a1040645c60db004ebd5eba39f6a057cff77507a1853d9b0dceda1ed5c7a1f；Iris10016/quad_w、empty_grey.world，原启动器；默认随机源seed=null。
- 准确预算1次，实际尝试1、离地0、完成0、接受0。30.916s发出起飞命令，首次监控inner_mode=-1中止，退出1；没有Hold/32秒激励/降落验收，不补飞。
- 实际rate为PID0/axes0/div1，MC_RATT_TEST/TKO_MGT0，消息measurement/output有效、fault/abort/termination0；速度PID valid1但inner_valid0。CLI仍landed/contact，takeoff_time0。不是飞行不稳定证据。
- 根因：原rate诊断32队列、250Hz生产，新速度诊断100Hz每次读1条造成约124ms积压，超过100ms门槛。这是本次新增订阅代码问题，未改上游控制算法。
- 用户在失败后再次要求继续；修复为最多32次有界读取，保留最新并在读取后核对年龄；新增真实消费时间/序号/读数日志。100ms阈值不变，消息格式由1113增为1208字节，低于1500。
- repair_verification02全部退出0：82个不同C++、50个Python。新增3项真实uORB功能用例复现旧124000us滞后、验证修复和burst/过期/未来边界；原PID/参数/起飞回归仍通过。修复源码没有飞行。
- 原ULog155537与9181060字节均保留，SHA分别99883783cfff92cb1cc6b2e11d606d8ed2c5b52e79201955127d1e0e6dc5ebf2、b576c517ba9d8965214ff41238ed3d2dd1aab2923266167bbac8dbdd6194fc2f。
- 主日志真实解码：2930条速度诊断约100Hz、7325条rate诊断250Hz、记录区间内序号连续、dropout0。无完整主窗口，不能给激励RMSE/下游覆盖验收。原消息无消费inner时间戳，不能仅靠旧ULog精确复原每次年龄。
- 参数完整恢复SHA06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无残留模拟器，旧日志不删除。
- 新数据根/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260922/V03；274份外部文件全量SHA通过，索引SHA721a3f451e10fae584024fe5bccaa963e2e88eeb6a789c83b0b22387bf4fbe58。
- 开发错误包括常量头/路径/浮点警告、Python依赖搜索路径、真实uORB测试stub链接顺序、启动短ULog缺话题异常；均如实记录，并与实际失败尝试分开，不假称零失败。
- 结果及局部修复提交970adacafb850002820c8ff5f2522b2ff1944096，共21个明确文件；diff及指纹检查通过，提交后工作区/子模块干净。协议01/frozen保持原始状态，不能在新源码上原地复用。
- 报告research/sta-velocity-control/reports/V03.md；新预算需明确确认后另冻新协议与新数据目录。V03未验收，V04不准入。不push、不实机、不MATLAB/旧ISTA。

## V03 protocol02 恢复验收（2026-09-22，passed）

- 用户明确回复“运行”，授权修复后重新冻结一次PID验证；不复用旧预算，不覆盖旧失败。起点970adacafb850002820c8ff5f2522b2ff1944096，研究分支和主仓库/递归子模块干净。
- 仅新增protocol02、独立续跑入口及2个协议/入口测试；新旧场景/参数/阈值/默认随机源逐项一致。实际控制源、模型、world、插件没有进一步变化。
- 协议/源码提交及实际飞行HEAD：5e637e20c60ea7e812252f49eda6ac6f7433531b；先提交，再干净源码构建与验证。固件SHA8c546c79a257e52dccb2ef0b55af7c704703a53e7564be9e9ae9b6101f2ebcab，启动前后相同。
- verify_v03提交前/提交后均退出0：82个不同C++、52个Python；PID两组各2048步等价、1208字节ULog格式、无生产STA速度符号及Gazebo只构建通过。不重复累计测试数量。
- 原启动器Iris10016/quad_w、empty_grey.world；Gazebo子模块822050a7ab6fd87972e59f16312f451bce217a56；seed=null，不主张独立随机样本。
- 计划1、尝试1、完成1、接受1、失败0、未执行0，运行退出0。起飞30.096s，Hold37.248s，观察41.836–102.036s（60.2s），108.176s降落并上锁；无追加尝试。
- 实际速度MODE/AXES0/0、rate MODE0/AXES0/DIV1，RATT_TEST0、TKO_MGT0；本次默认关闭激励项置1，SDLOG_PROFILE147保留既有位。位置P、XYZ速度PID、姿态和角速度PID不变，ESTA仍不可用。
- 6020条观察窗诊断约99.997Hz、sample间隔8/12ms、序号完整，完整32秒激励3200条；整段飞行7808条内环消息年龄0–4ms、最多一次读4条，未放宽100ms门槛。
- 49项基线及选择/诊断验收通过，fault/failsafe/termination0；rate250Hz序号完整，ULog dropout0。local/attitude输出精确匹配6020/6020，误差0；actuator覆盖92.43%、误差0、最大间隔8ms；motor_limits约226.69Hz，不称下游完整无损。
- 激励32秒消费状态速度RMSE X/Y/Z=0.045573/0.007666/0.003354m/s；60.2秒观察=0.033778/0.007186/0.005413m/s。约束和有效方向饱和0%，最大倾角1.032°，yaw RMSE0.0001281rad，估计悬停均高1.934m；不是精确2.5m任务/算法胜出结论。
- 原预定V04安全、逐轴性能/非命令轴和日志门槛保持；当前只用PID证明日志标准可实现，未用ESTA数据改阈值。V04接线仍须新阶段验证和明确授权。
- 新外部目录：VELOCITY-STA-20260922/V03下resume02_verification01、resume02_verification_committed01、series02。112份新增文件及旧274份指纹全量复核通过。
- 新索引SHA17057de5b04f8317f2f1b7c1e3ddf3f1fe77ab9c59f9179f52eb6ee80f7dd6f9；完整ULog33686029字节SHAdd45489184f23f2b82081cad097c4948b21b3222d325b2ade8e4a80febbcc357；启动ULog199612字节SHA13883341e2f4017bc19d877e919a7ce4e680df76a5b46b7585ce894651b56f4b。
- 原EEPROM完整恢复SHA06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无残留模拟器；历史失败与日志保留，不覆盖初始plan/v1快照。
- 结果提交：21e56a17ff7cbac5f7fe2fe6e2c8420748f317cf，15个明确范围报告/小证据文件；diff检查、提交后工作区/子模块核对通过。
- 报告research/sta-velocity-control/reports/V03.md；不push、不V04、不MATLAB/旧ISTA、不实机。当前V03通过仅为下一阶段前置，不表示自动授权执行。

## V04 X单轴执行（2026-09-23，failed / needs_revision）

- 用户授权仅V04；完整读取速度计划、共同规则、进度和前置报告。开始HEAD21e56a17ff7cbac5f7fe2fe6e2c8420748f317cf，research/sta-velocity-control分支，主仓库/递归子模块干净并与本地远端跟踪引用同步；未回退/清理旧改动。
- 实现SITL限定MODE1/AXES1及独立X参数、armed暂存/disarm生效、生命周期保护、候选/提交状态与日志；MODE2、AXES3/7拒绝，默认PID。X是NED北向，不是roll。原位置P、Y/Z速度PID、姿态/rate PID、Takeoff/HTE/估计器/land detector不变。
- 唯一候选lambda1=1、lambda2=.2、nu限.4m/s²、纠偏限.8m/s²；FF只加一次，不除质量或角速度g。独立滞后对象和正负/坐标方向通过，不等同完整Iris飞行证明。
- 预算6次，种子9101 PID→ESTA、9102 ESTA→PID、9103 PID→ESTA；历史21021个JSON未发现复用。第一次种子审计被旧0字节M06诊断文件阻止，核实并明确排除后再审计，历史错误/例外保留。仅显式IMU种子，其他噪声仍默认引擎，不主张全部独立。
- 原启动器Iris/empty_grey.world，派生模型只替换隔离IMU库filename，原方程/频率/模型子模块不改；Gazebo版本822050a7ab6fd87972e59f16312f451bce217a56。唯一trajectory源和小幅32秒X速度正弦、60秒观察、起降及V03安全/配对/日志阈值飞前固定。
- 协议/源码提交67b07d75a98bc3ddf502a779e6cf80f068a1e0e6；在该干净提交重建并验证后运行。固件SHA7236e9a9d1b5b9198cc54e8761e548ecda3a5dcc088b9eafc25d1be611e22c99。
- verify_v04.py退出0：92个不同C++；Python discovery57项退出0，结果收尾复跑仍57/57，不重复累计。PID两组各2048步位级一致，参数BSON重载/切换、保护/无效/重复sample/受约束/独立滞后对象、旧速度核及rate核回归通过。ULog格式1316字节，Gazebo DONT_RUN构建退出0。
- 开发verification01断言混淆公共耦合、verification03/04夹具类型/字段及重复测试发现问题均保留；最终以verification_committed01的非零计数为准。不MATLAB/Octave/实机。
- run_v04.py退出1：计划6、尝试1、起飞1、完整任务0、接受0、未执行5；首轮seed9101 PID，30.968s起飞、38.120s Hold、42.720s高度1.9669m（门槛2.0–3.0m）失败。hover_start事件先于入口检查，不算成功悬停。无降落上锁，宿主停止自有SITL，未自动重试或修改阈值。
- ULog真实解码实际速度MODE0/AXES0，rate MODE0/AXES0/DIV1、RATT_TEST0、TKO_MGT0、SDLOG_PROFILE147。主日志4100条速度/10251条rate状态，发布号连续，两个ULog dropout0。
- 31.988s一次pid_calls=2、update增量2是原同帧重算，不是丢发布；最终valid/fault正常不能否认首个update失败。该帧触发激励器重复sample抑制，激励始终0/time=-1，没有完整32秒指标；0.5s在线轮询未捕获短帧，离线才发现。未完整还原首次无效输入根因，不将失败归咎ESTA。
- 实际ESTA飞行0、成对比较0、同/跨种子创新一致性未验证；剩余5轮停止。既有入口高度失败及单帧正常调用条件均未满足，不能仅放宽高度继续。
- 只读audit_v04_failure.py两次解码命令退出0；第一次错误命名missing，第二次更正为non_unit_deltas并给出重算时间，两个输出均保留且都accepted=false。解码成功不是飞行通过。
- 数据/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04。主ULog12967151字节SHA264c87938aefcb2beed91cce6f3955813a37fbeae1a73c2e26aa57bd55bb30e9；启动ULog170387字节SHA0f365d2b0a35046d3f3519f1bc8923cd46588dba75610c6bb4086437c8bd7868。
- 243份外部文件指纹全量核验退出0，索引SHA0d7b8e61172ce2cef7133b81c09544250b1150f208750ce1d34f86557e6051c7。原1129字节参数完整恢复SHA06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无残留模拟器。
- 结果提交640a5857a28b8045ea91690a33748446ba4ce275；17个明确范围文件，仅报告/README/只读诊断/小型证据，不追改冻结协议。diff检查、Python语法、提交后工作区及递归子模块检查通过。
- 报告[reports/V04.md](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04.md>)。不push、不V05、不实机、不旧ISTA。建议先离线审计第一次update失败及同帧重算/激励生命周期、原Takeoff转Hold与入口协议一致性；任何上游修改、新预算或门槛修订须另授权、另冻协议，不能删除本次失败换通过。

## V04 REPAIR01（2026-09-23，仅修复离线通过）

- 用户先要求离线定位，再回复“允许”授权修复并完成离线回归、暂不飞行。起点640a5857a28b8045ea91690a33748446ba4ce275，research/sta-velocity-control，工作区/递归子模块干净；旧预算和失败不变。
- 前置offline_rootcause01用当前及V00冻结内核7项诊断定位：地面抑制污染持久目标缓存，ramp恰无新目标时清除Z加速度，导致无有效Z指令；原200ms迟滞内零初始化目标重算，实验激励第二次同sample调用又误报时钟。7项属上一轮诊断，不计入本次104项。
- 修复Run仅对本帧副本做地面/接触/ramp处理，EKF调整仍保存在原缓存；Takeoff状态机/ramp、PID/ESTA数学、HTE/滤波/参数更新函数不变。正常核心逐样本等价，不宣称修复后的异常模块行为与旧版等价。
- failsafe从第一失败帧生成明确NaN/停速/下降目标，保持报告迟滞，不再意外请求世界原点和零yaw；计入导数有效性。最终PID/ESTA重算仍无效则不发布；无输出不是安全悬停，实验须中止，非实机安全保证。
- 激励abort不推进sample时钟，真实控制失败仍锁止；重复/倒退/长间隔/开始后门禁丢失仍拒绝。新增first_fail/first_input/retry_result/excitation_fault，生成ULog格式1403字节、队列8；真实uORB和合成ULog解码通过，未取得新飞行/实际logger日志。
- 新增12项回归：10个真实Run/uORB模块用例及2个激励用例；测试中仅替换备用定时器调度/取消，同步运行控制，不代表实机调度验证。覆盖50Hz目标/8–12ms回调的ramp相位、reset/新旧目标、地面/退出重入、缺测恢复、迟滞边界/非法输入、无效重算不发布、ESTA无二次提交及disarm清零。
- 最终verify_v04_repair.py --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/repair_verification03'退出0；104个不同C++、58个Python（含1项新ULog字段编解码）；原PID两组各2048步位级回归通过，make px4_sitl_default和DONT_RUN=1 Gazebo构建均0。没有启动Gazebo或飞行，没有MATLAB/Octave/实机/旧ISTA。
- 旧verify_v01/verify_v04的failsafe不变断言作为历史约定保留；新入口明确记录本次获准的语义修改，不静默改旧协议。01/02/03分别为102/57、104/57、104/58，不重复累计数量。
- 开发夹具问题（缺MODULE_NAME、未初始化HRT阻塞、诊断队列读旧帧、yaw断言/故障注入不当、异步队列退出及合成日志padding）如实写报告。早期探索仅部分工具记录，未假称完整外部归档；最终三组命令/输出/XML完整保留。
- 新外部130份诊断/验证证据全量SHA通过，索引ff79b1dac7e94be24e6679eb960574484a5e36b1ae21050a696d26d6c4c8ee24；旧243份指纹仍一致。EEPROM未变，SHA06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc。提交前固件SHA1faf92cf4607af9f35570d759e1177ada92ad949257778e2a4f539d3639802b1，没有在该固件上飞行。
- 修复提交65d1b5c4e2177547e369ba2a750581f1bb894c56，18个明确范围文件；diff检查及提交后主仓库/子模块核对通过，未push。报告[reports/V04_REPAIR01.md](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_REPAIR01.md>)。
- 本次新飞行0，V04旧尝试1/接受0/剩余5停止、ESTA飞行0；下一步另冻实验2.5m目标、唯一发布链、稳定入口/超时和新预算，不直接续跑，不放宽旧门槛，不V05。

## V04 protocol02设计冻结（2026-09-23，awaiting_authorization / implementation）

- 用户要求重新冻结高度任务与验证协议后申请新批次。开始HEAD65d1b5c4e2177547e369ba2a750581f1bb894c56，研究分支/工作区/递归子模块干净；完整阅读计划及共同规则、状态、V04/REPAIR01。
- 不改生产控制、Takeoff/导航参数、模型/插件、候选或旧协议/数据。新增protocol02设计、只读检查器、12个协议单测、种子/资产证据和报告；原位置P、Y/Z速度PID与全rate PID保持。
- 原起飞完成后用一次明确DO_REPOSITION目标替代当前位置Hold；估计高度目标2.5m，入口2.0–3.0m且|vz|<0.2m/s连续3秒，准备完成才写hover_start。既有12秒等待/32秒激励不变，门禁后10秒内未准备好则停止，60秒观察完整覆盖激励。
- 冻结本仓库原始param4弧度语义、NED/global高度转换、ACK+目标回读和参考/reset拒绝；不引入额外trajectory/attitude/rate目标发布者。first_fail/retry_result/excitation_fault为新必需证据，缺字段不补零，最终成功不掩盖首次失败。
- 拟申请新预算6次：9201 PID→ESTA、9202 PID→ESTA、9203 PID→ESTA。每轮/配对任一必需失败即停止，旧剩余5次不用、不额外冒烟/补飞/调参；固定先PID顺序的偏差披露。仅IMU显式播种。
- 只读种子审计21,068份历史JSON，匹配0、无未解释无效JSON；既有M06空诊断例外保留，旧V04数据包含在审计中。飞前需复查新种子是否被其他任务使用。
- 12个新增协议/转换测试通过；完整Python工具发现实际70项（原58+新增12）通过，退出0，输出存protocol02/python_tests.log。不把静态协议检查称作新运行器/分析器已实现。
- 120份设计时资产指纹核对、递归子模块及参数字节检查通过。EEPROM仍06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc；新series02路径仅预留未创建。
- 本轮C++/构建/Gazebo/飞行/MATLAB均0；此前REPAIR01的104项C++不记成本轮。当前执行入口/分析器仍为旧协议，禁止直接用于新批次。
- 设计提交2fc381789770cdc38f82f123b1cdef3f7cacc9e6，9个明确文件；diff及提交后工作区/子模块干净，未push。报告[reports/V04_PROTOCOL02.md](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL02.md>)，协议[v04/protocol02/README_CN.md](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/v04/protocol02/README_CN.md>)。
- 等待用户有条件授权：先按冻结设计补齐隔离入口/分析器，完成离线回归及干净执行源码提交/构建/指纹，再执行最多6次；任何门槛失败停止。当前未获新飞行授权，V04仍failed/needs_revision，不V05、不旧ISTA、不实机。

## V04 protocol02飞前生命周期审计（2026-09-23，needs_revision）

- 用户回复“允许”，有条件授权补齐接线/离线验收后执行最多6次；本设计同时要求改变冻结规则时再次申请。开始HEAD2fc381789770cdc38f82f123b1cdef3f7cacc9e6，研究分支及工作区/递归子模块干净；完整阅读计划/共同规则、状态、V04/REPAIR01及protocol02。
- 接线前发现协议要求excitation_fault整个armed区间为0，但模块激励gate要求AUTO_LOITER；正常AUTO_LAND变为gate=false，生产激励器即使波形已完成也锁存Gate=2至disarm。这是设计规范遗漏正常退出语义，不是新飞行失稳证据。
- 新增独立C++14探针直接包含生产VelocityDiagnosticExcitation.hpp，10ms严格递增，60秒合法门禁覆盖完整波形后模拟降落门禁；没有复制控制算法或运行PX4/Gazebo。
- 6项实际探针5通过/1失败：正常降落fault2/output0/time48与原零值断言冲突；提前门禁、真实Clock组合3、Controller组合6及disarm清零行为均确认。g++退出0、探针与审计入口退出1；失败按原规范保留，不改期望换通过。这6项是独立探针检查，不冒称6个gtest。
- Python实际70项回归通过，退出0；不推翻生命周期规范失败。本轮未执行完整104项C++、SITL/Gazebo构建、MATLAB或飞行；没有新运行器/分析器完成声明。
- 新外部目录VELOCITY-STA-20260923/V04/protocol02_lifecycle_audit01，编译日志/探针日志/证据/二进制4份SHA全量通过；小证据纳入protocol02_audit01。生产src/msg/sitl/Tools及protocol01/02设计字节未变。
- 新预算计划最多6、启动0/飞行0/接受0/未运行6，9201–9203未消耗；旧剩余5不复用，series02未启动。EEPROM仍06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc。
- 建议但未生效：完整激励/观察且唯一计划land命令+实际AUTO_LAND确认后，可将单独Gate2记为预期结束；此前门禁丢失、所有Clock/Controller及首次失败/重算仍拒绝。保留原始fault，不改控制器/参数/性能门槛/预算。需用户批准，再另存修订协议并补边界测试。
- 失败审计提交a367c7afa561e5f3829f39ad6092b51e63afd2bf，7个明确研究文件，diff及提交后工作区/子模块核对通过，未push。报告[reports/V04_PROTOCOL02_PREFLIGHT.md](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL02_PREFLIGHT.md>)。
- 这不是可飞源码或阶段验收提交。V04仍failed/needs_revision；暂停等待最小日志分类修订批准，不擅自修改冻结规则、不V05、不旧ISTA、不实机。

## V04 protocol03执行与series02停止（2026-09-23，failed / needs_revision）

- 用户批准前述最小计划降落分类。新增独立run_v04_protocol03/run_v04_flight03、height/ACK/entry纯函数、真实ULog分析器、资产/种子审计与19项专属测试；只允许完整观察/激励+唯一计划land+实际AUTO_LAND后的单独Gate2，原始位保留，其余故障仍拒绝。
- 不改控制律、Takeoff、导航/估计器、默认值或候选；生产仅logger高频注册增加position_setpoint_triplet/vehicle_command_ack，保留SDLOG_PROFILE其他位。
- 源码/协议提交965052446cf0d52c32e1e5641d90db0f96e9a5b4，明确14文件；提交前最终与提交后干净验证均104个不同C++、89项Python、SITL/DONT_RUN Gazebo构建通过（全部退出0），消息格式1403字节。19项专属计入89，模拟预算测试不算飞行。
- 新六次授权清单9201/9202/9203各PID→ESTA，最大6、无补飞/额外调参。series02实际run01 seed9201 PID，30.008s起飞命令；36.860s heading reset 2→3、delta0.006559979rad≈0.375859°、相对地面1.599521m。37.120s宿主检出并停止自有仿真，命令退出1；实际已起飞，不称地面预检失败。
- 同期mag_aligned_in_flight 0→1、主估计器保持实例1，与固定ECL爬升约1.5m后首次航向对齐机制一致。未发送高度reposition，未观察/激励/正常降落；不是已经证实PID或ESTA失稳，但冻结reset规则被违反，必须failed。
- 真实主ULog起飞后速度诊断712条/最大间隔12ms，rate1781条/最大间隔4ms，序号连续；实际全PID，首次失败0、重算0、pid_calls1、valid1、各故障和激励0。两个ULog dropout0、指纹一致；没有完整RMSE窗口，不报告ESTA性能。
- 计划6/尝试1/完整0/接受0/未执行5，ESTA0、配对0；旧失败1次另存不合并。所有新旧失败保留，不能直接续跑或重新使用seed9201作为全新种子。
- 外部series02及protocol03_verify01/02/committed01、protocol03_flight_audit01/02保存；149份原始/验证工件SHA核对通过，仓库results03提交小证据/索引。参数全字节恢复06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，自有仿真无残留。
- 只读失败审计退出0；最终工具回归89项退出0，diff及明确9文件结果提交bf98350bfdc50e5c4af5e01dbd48b06a167322a0。报告[新批结果](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL03_RESULTS.md>)。提交后主仓库/递归子模块干净，未push。
- 后续尚未获准：先离线审计首次空中航向对齐的阶段/幅值/计数、delta_heading目标处理及冻结策略，再另立准确协议/新批次授权；不能关闭EKF、静默重置参考或豁免本轮换通过。不V05、不ISTA、不实机。

## V04 起飞航向离线审计 / protocol04设计（2026-09-23）

- 用户另要求“先离线审计正常起飞航向对齐的处理，再修订协议”。从bf98350bfdc50e5c4af5e01dbd48b06a167322a0开始，完整阅读计划/共同规则、进度及protocol03报告；没有新飞行授权，不复用旧剩余预算。
- 固定源码确认ECL内部延迟地形高度大于1.5m且尚未空中磁对齐时提出reset请求，成功后置位mag_aligned_in_flight。主估计器切换也会改变公共heading计数，不能只凭小delta或计数增量认定正常。
- 只读解码7份历史PID日志并核验原始SHA；首次起飞对齐约0.066°–0.376°，高度约1.57–1.60m。两份V00降落另有主估计器0→2和位置/速度/参考变化，新规范不豁免。不同源码历史数据仅开发诊断，不计新配对样本、不改旧验收。
- 目标补偿分布在FlightTask/MPC/姿态模块；MPC仅补旧缓存，同时间戳/较新目标不再次加delta。series02实际reset帧目标同时间戳、发布yaw未跳；不声称全链严格无扰。新增2项真实Run/uORB回归确认单次补偿及新目标不重复补偿。
- protocol04仅准备段允许至多一次证据完整的首次磁对齐；相同健康primary、0→1标志、heading/quat单次计数及delta一致、无p/v/reference变化等均必需。新增5°/1–3m/0.5s pending等工程检查，披露开发数据依据；不放宽原候选/性能/安全门槛。
- 对齐确认后POSCTL连续稳定1s、目标新鲜且yaw差≤1°，一次固定对齐后task_yaw；原地面/全局参考与prearm yaw保留，不叠加delta、不动态重冻。其后直到降落上锁任何reset仍失败。保留准备总超时150s和原窗口。
- status/selector/status_flags/event_flags按真实发布语义分别检查，事件话题不要求不存在的心跳。新增10项纯规范测试不等于在线采集器/全状态机已实现；旧运行器不能直接用于新协议。
- 最终heading_verification02实际106个不同控制相关C++、99个Python，另现有AttitudeControl3项，共109个C++；全部退出0。SITL和DONT_RUN Gazebo构建通过，没有启动Gazebo；两组各2048步PID回归保留。未做完整EKF/FlightTask仿真、MATLAB、实机/ISTA/V05。
- 7日志审计退出0；81份本轮外部工件SHA全量核验通过，旧日志不改。EEPROM仍06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc；src仅两项测试，生产控制/估计器/Takeoff/参数/模型不变。
- 审计/设计提交57bf4892a8698938db421da78ec8afee21c8c39e，13个明确文件；diff审查通过，主仓库与递归子模块干净，未push。报告[起飞航向审计](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_HEADING_AUDIT.md>)；protocol04 SHA c071d1648ee260fcfde411514d11feef6926cf165113739c61bbfd63b4d1db8d。
- 本次尝试0/新种子0/预算0，旧失败不改判；V04仍failed/needs_revision。下一步先实现隔离protocol04运行器/ULog分析器并完成离线回归，再冻结全新种子/准确六次清单/目录/干净执行源码并申请飞行；拟议预算不等于已授权，不自动续飞、不V05。

## V04 protocol04实现与新批次申请（2026-09-23，offline_passed / awaiting_flight_authorization）

- 用户要求实现新版运行器和日志分析器，离线验证后再申请新批次。开始57bf4892a8698938db421da78ec8afee21c8c39e，研究分支、主仓库和递归子模块干净；完整读取计划/共同规则/状态及前置航向审计、protocol03报告和protocol04设计。只授权实现/离线，未授权飞行。
- 新增隔离run_v04_protocol04/run_v04_flight04、v04_heading_stream、v04_task04、analyze_v04_protocol04/core04、准确协议加载/种子资产捕获及验证器。原protocol03运行器/分析器/已执行规则不覆盖。src/msg/sitl/Tools无改动，生产控制/EKF/Takeoff/参数/模型/日志配置不变。
- 只读自有logger连续ULog完整记录，绑定primary及计数/标志；缺失/切换/额外reset拒绝。真实sample连续性、消费input_timestamp关联、原40ms间隔/0.5s确认仍严格；独立0.5s在线传输年龄保护不替代原始日志门槛。不强制flush、不新增估计器发布、不退回快照放行。
- 解锁前取准确ULog位置样本固定地面/reference及旧yaw，首次对齐确认、POSCTL连续1秒稳定后只固定一次task_yaw。保持唯一navigator→FMM目标链，原起飞及一次DO_REPOSITION、2.5m/3秒入口/60秒观察和32秒X激励/计划降落不变。
- 新版分析器按原selection_gate正确区分enabled调用1/disabled调用0，完整发布序列上核对Δupdate_seq=pid_calls；旧通用分析器一律1的实现不追改。主窗口不删样/补零，新旧enabled PID/ESTA数值结果一致。自有session关闭、异常清理及全EEPROM恢复有离线故障注入覆盖。
- 本轮32项专属Python，最终全部131项；106个控制C+++3个姿态C++共109个不同用例通过，两组各2048步PID等价保持。SITL与DONT_RUN Gazebo构建通过，无Gazebo启动。批次/任务夹具均离线合成，不计飞行。
- 开发中一项合成reset注入在上锁窗口后10ms导致期望错误，调整注入回降落区间，未改门槛。verify04新增启动失败夹具把bytes错mock成str，131项1项error、验证退出1，原日志保留；修正mock接口后verify05全部通过。重复用例不累计为更多独立测试。
- 实际旧series02 ULog1049个字段数组与独立pyulog解码一致；首次对齐可分类，但仅0.088s安静段、旧飞行不合格。新版整轮分析旧失败记录仍accepted=false/退出1（预期拒绝，缺hover_start），不改判成功。其余验证命令及总验证器退出0。
- 冻结160项资产；提交前种子审计21143份JSON、无历史复用/无未解释无效JSON，保留旧空M06诊断例外。最后只读检查21154份仍通过；仅IMU显式播种，其他随机源/调度不独立，固定PID先行偏差披露。拟议9301 PID→ESTA、9302 PID→ESTA、9303 PID→ESTA，最多6次、无补飞/额外调参、首个单轮/配对失败停。
- 新目录/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series03仍不存在；实际启动0/飞行0/种子消耗0。旧两批失败及停止预算全部保留，不自动续跑。
- 实现提交5b5dc2c0d05986cc7cded7e4477ad79ae4315ce9，23个明确研究文件；diff/提交后工作区和子模块核对通过，未push。执行设计SHA d910b97a31075d609668d6b955d1dc2f2c779a7ff164a06b03afeda2337d7238；160项资产快照SHA001cdd319bca80873e6e42c5683532deb114f6230daf7d219fd2b91cba7f45c7。
- 提交前验证01–05全保留，270份工件指纹及旧series02的149份工件全量核验通过。仓库索引SHA62e2e8de2856255a79ee2f7a86983bce5466e4a1d136a5bfd7d0eaa015d3659b；EEPROM始终06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc。
- 干净提交后再运行verify_v04_protocol04.py --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/protocol04_committed01'：109C++/131Python通过，总退出0；新固件build_git_version核对当前完整SHA。外部evidence.json SHA f89a48bf45781e68d9c141b8fa21f17fd19ab12ca1e4b51a41405ddcdf1b93f7，artifacts.sha256索引SHA4c0b536030615788f717aa2cd90e8492f5075fa61190301a7026cb07095ec9c1，全量校验通过，160项资产仍匹配，无残留模拟器。
- 报告[protocol04实现/准确申请](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL04_IMPLEMENTATION.md>)。离线实现通过不等于V04飞行通过；等待用户明确批准这6次新预算，届时再核对干净源码/固件/种子后执行。不push、不V05、不ISTA、不实机，未运行MATLAB。

## V04 protocol04 / series03执行与停止（2026-09-23，failed / needs_revision）

- 用户对前述准确六次申请回复“允许”；完整阅读计划/共同规则/进度及前置实现，核对研究分支、HEAD、干净主仓库/递归子模块、资产/种子/固件、EEPROM、新目录和进程。原execution.json未追改，通过精确令牌执行这次明确授权。
- 协议/实际源码5b5dc2c0d05986cc7cded7e4477ad79ae4315ce9，固件SHA4d94c6c768dd4bb72039d49a5aab5511e54d6a15cb24bc8717c5e9546aafa027；原Iris项目启动器，实际MODE0/AXES0、rate0/0/1、RATT_TEST0、TKO_MGT0、SDLOG_PROFILE147。位置P/原速度PID/姿态/rate/Takeoff/EKF/模型不变。
- 清单9301 PID→ESTA、9302 PID→ESTA、9303 PID→ESTA，最多6。实际run01 PID尝试1、检测离地0、完整0、接受0、ESTA0、配对0、未执行5。30.056s起飞命令事件，30.172s解锁，30.456s CLI监控触发ref_lat检查；未重试/补飞/扩大预算，9301一次已消耗。
- 根因是工具精度：原始ULog纬度47.3977508、CLI打印47.397751，差约2e-7超1e-7门槛；经度差约3e-7同类问题。生成uORB打印为%.6f。原始参考与reset计数全不变；同timestamp原始样本通过、归档CLI样本重现异常。不是已经证实PID失稳或EKF重置，合成测试遗漏真实打印/精确参考组合。
- 原始ULog两份196307/9115271字节，dropout0、无解析损坏；主日志SHAe31d4e5fe706d36d6ddf245d1596fef44808ef5a7e179362b501caeefa4cfaa3，启动SHA34d2dc25a3529fa613991714cd106c99e3cdeb5b540ff5192aa87d5ce7a10d63。命令后速度42条/最大12ms、rate104条/最大4ms、序号连续、无first_fail/retry/fault；landed/contact1、takeoff_time0。
- 没有首次空中对齐/一次task_yaw、高度命令、3秒入口、60秒观察、32秒激励或正常降落；不计算RMSE/改善率。唯一在线回放年龄40ms不足以证明完整飞行传输性能；配对种子创新/跨种子检查未执行。
- run_v04_protocol04退出1；只读audit_v04_protocol04_failure的8项诊断检查通过退出0（不是8个gtest/飞行通过）；本轮Python discovery实际131项通过退出0。独立完整分析accepted=false、缺hover_start退出1，预期拒绝。前置干净109C++/131Python/SITL构建证据指纹复核通过，本次未重复C++或编译。
- 外部series03、protocol04_flight_audit01、protocol04_reanalysis01及命令日志全部保留。32份原始工件索引SHA592adebfcf2e4a9bc15334787e16e73a34b292e36b8dcb112da891aa9f0d5db7，额外证据索引SHA93d445c1f725b75c148138c32be651d9aea1ccaf4c9de3cf50221360f71cf1d4，全量指纹通过；EEPROM完整恢复SHA06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无残留仿真。
- 结果提交e9e3d233d5a4aad1289aad1e84412296e5b0f721，13个明确研究文件，只读审计、报告入口、小证据及索引。diff/语法/指纹审查通过，提交后工作区/递归子模块干净；不push。报告[protocol04结果](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL04_RESULTS.md>)。
- 工具尚未修复，协议未改，不把失败改判通过。下一步需另授权CLI/raw表示一致性修复与真实打印链/原始微小reset拒绝回归，离线通过后再冻结并申请新批次；不能直接续跑剩余5次。不V05、不ISTA、不实机、不MATLAB。

## V04 CLI/raw精度修复（2026-09-23，offline_passed / awaiting_new_batch_approval）

- 用户回复“允许”，仅授权检查器精度修复、离线回归，通过后申请新批次。起点e9e3d233d5a4aad1289aad1e84412296e5b0f721，研究分支/主仓库/递归子模块干净；完整阅读计划/共同规则/状态及protocol04失败报告。
- 新check_cli_reference把原始参考按实际uORB格式打印后与CLI值精确比较：经纬度6位、参考高度4位，计数/ref_timestamp精确；缺失/非有限拒绝。实际monitor和height entry均接线，参考本身不舍入/重冻。原check_reference保留供历史错误复现。
- 原始v04_heading_stream.replay及最终分析器未改，原始坐标/reset仍逐样本精确不变；CLI隐藏的单double-ULP变化仍拒绝，时间/元数据/缺样/对齐/安全/性能门槛不变。src/msg/Tools/sitl/冻结protocol04均字节未改，不涉及飞控/模型/默认参数修复。
- 新10项Python实际全部通过，独立使用libc snprintf核对正负/零/舍入边界邻点及实际生成格式；真实归档CLI/ULog同sample、生产monitor原始回放接线、高度入口、缺失非有限/微小raw变化/缺样拒绝均覆盖。不是飞行、不称高频宿主实时性通过。
- verify_v04_protocol04.py --output '.../V04/cli_precision_verify01'总退出0：109个不同C++、141个Python、两组2048步PID回归、SITL及DONT_RUN Gazebo构建通过。起始HEAD加修复工作区完成，不冒称未来干净飞行协议已验证。无新测试失败；旧series02/03整轮分析仍accepted=false/退出1（预期缺完整窗口），旧失败审计8项退出0，未改旧判定。
- 新启动0/飞行0/种子消耗0，无新增ULog；原series03的32份工件SHA仍全部一致，EEPROM仍06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无残留仿真。外部cli_precision_*证据保留，91份本轮工件指纹核验通过，索引SHA001174a941c72042235a4df5cd62f48ed4d0b0a268d24ec0f7e7211a602e0334。
- 提案9401 PID→ESTA、9402 PID→ESTA、9403 PID→ESTA，最多6，拟series04未创建。注册前21203份JSON扫描无复用，已提交历史源seed相关文本未命中；旧M06空诊断例外保留。仅IMU播种、固定先PID顺序偏差继续披露；飞前重扫，不能声称所有随机源独立。
- proposal.json明确flight_authorized=false/execution_ready=false；本轮没有protocol05可执行冻结配置。需新预算授权后另冻配置/入口、源码/资产提交和干净重建回归，再执行；原候选/任务/门槛不变，任一必需失败停，无补飞/冒烟/调参，旧剩余5次不复用。
- 修复提交85b8647644c5d316d41005ce0ddd26f250fa5a81，12个明确研究文件，diff/指纹检查通过、提交后工作区/子模块干净；未push。报告[CLI精度修复](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_CLI_PRECISION_REPAIR.md>)。不V05、不ISTA、不实机、不MATLAB。

## V04 protocol05 / series04执行与停止（2026-09-23，failed / needs_revision）

- 用户对9401–9403各PID后ESTA、最多6次新预算回复“允许”。完整阅读计划/共同规则/前置修复/状态，从85b8647644c5d316d41005ce0ddd26f250fa5a81开始，核对研究分支、干净主仓库/递归子模块。不复用历史剩余预算。
- 新隔离protocol05配置/运行器/分析器、资产/种子审计和6项专属测试，11文件明确提交95cc6fe33db5051774174219e73a724a851c64ad；未改生产控制、模型、旧协议。170资产冻结SHA0e876083273d02968108296ed68c32c4613a2b693206d5ae8ab4a50f5c4e3ce1、execution SHAa61ffac6b782ad91d744a1cf1af65c0150a8b4ebc088c64611cf9f060248a143。注册审计21210份JSON，飞前再扫通过。
- 初次专属测试6中5过1失败（尚未捕获frozen.json）；捕获后precommit验证109个不同C++/147个Python通过。干净提交后protocol05_committed01重新实际109C++/147Python及SITL/DONT_RUN Gazebo构建通过，总退出0；原始失败日志均保留，重复执行不累计独立用例。
- 原项目Iris启动器，实际MODE0/AXES0、rate0/0/1、RATT_TEST0、TKO_MGT0、profile147；固件SHAcef3f8520fe5f51de2d2aae2a47e71fcd7b67b020f020af2c318067262ba0d82。默认PID、原Takeoff/位置/姿态/EKF不变。唯一ESTA候选与任务/安全/性能门槛不变。
- 计划9401 PID→ESTA、9402 PID→ESTA、9403 PID→ESTA共6。实际run01 PID尝试1、离地1、完整0、接受0、ESTA0、配对0、余5停止；无补飞/调参/扩预算。30.076s起飞事件，31.228s检测离地，36.684s同primary首次磁对齐约−0.145°/1.557m，36.916s POSCTL，38.044s安静1.128秒后固定task_yaw。
- 随后运行器在高度命令前报Invalid navigator target。ULog/CLI均显示POSCTL正常清空Navigator current.valid、lat/lon为NaN；本地trajectory仍合法（XY/yaw有限，35个Z=NaN样本用有限vz制动）。运行器等待POSCTL却要求有效Navigator航点，目标接口前提矛盾，不是CLI精度回归或已经证实PID失稳。原高度单独修改命令复制旧triplet XY，不能简单跳过检查继续。
- 起飞事件后速度803条/最大12ms、rate2007条/最大4ms、序号连续，控制/first-update/retry/failsafe均0、实际内环PID。原始reference和pv reset计数不变；航向原始回放通过。在线27次年龄28–68ms，仅本段有效。无DO_REPOSITION、无32秒激励/60秒观察/正常降落，不计算RMSE。
- 两ULog无dropout/解析损坏：主11545414字节SHA88b9cd401f5e410dac6b50f6ee07073597b01a7a7e910646fe89d321f429e086；启动206779字节SHA07f2dff288574f49f5b9f1a18b1ad1a77fb7af5bb444d0601031684fa122d833。种子配对/跨种子检查未完成，仅IMU显式播种，固定顺序偏差仍披露。
- 运行器退出1。只读诊断首版10项9过1失败（误要求Z始终有限），纠正为合法Z/vz语义后新目录10项通过退出0；两份记录保留、飞行门槛未改。完整独立分析仍accepted=false/缺hover_start退出1（预期拒绝）；结果阶段147项Python通过退出0。未运行MATLAB。
- 外部series04共34原始工件，索引SHA905e1ca1bf5acbbf74668af4d720b0a71b6213f5182979ce3354c8672711a67e；其余164份验证/诊断/重分析工件索引SHAa825928a9c32925aa11c40bcf9a38d779231768b8f78ac261e4da248d9e3c06a，全部核验。EEPROM全字节恢复SHA06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无残留仿真。
- 结果提交2522940fbc0038e1dd170a7207e74190d86552ab，14个明确研究文件：报告/入口、只读诊断、小证据与指纹。diff审查通过，生产/运行器/冻结协议未改，提交后主仓库和递归子模块干净；未push。报告[protocol05结果](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL05_RESULTS.md>)。
- 四批累计4尝试/0接受、ESTA0；历史失败不改判，剩余5不可继续。下一步另授权后先离线修订POSCTL→AUTO_LOITER目标交接，覆盖有效XY来源/坐标/唯一发布者/真实命令读回的完整状态链，再独立申请新预算。不自动修复/飞行、不V05、不ISTA、不实机。

## V04 handoff06目标交接修订（2026-09-23，offline_passed / awaiting_separate_batch_freeze）

- 用户仅授权“先离线修订目标交接逻辑并补齐测试”。开始2522940fbc0038e1dd170a7207e74190d86552ab，研究分支及主仓库/递归子模块干净；完整读取速度计划、共同规则、状态及protocol05报告/前置规范。未恢复旧预算。
- 审计Navigator POSCTL清空triplet、明确XY/高度单独修改分支、Commander模式ACK、Loiter复制、MAVLink整数接收与FlightTaskAuto回投影。补充：NaN XY可能触发FlightTask本地位置锁定，并不必然failsafe，但不能保证保持此前POSCTL目标。源码/模型/参数/估计器/Takeoff/控制律均未改。
- 新独立v04_handoff06、flight06、两层分析器、只读审计/25项测试、协议草案和C++14投影编解码探针。原04/05脚本及冻结文件保持字节不变。新入口在任何进程/文件/连接副作用前拒绝启动，协议flight_authorized=false、execution_ready=false、maximum_attempts=0、jobs/seeds为空。
- 沿用原航向准入，在原始机载ULog中一次固定当前合法trajectory XY保持目标，原reference不变；ECL等距方位反投影，明确COMMAND_INT整数经纬度/AMSL高度/原冻结yaw弧度，唯一发布链仍Navigator→FMM。source目标≤40ms，在线tail年龄≤0.5s；不替换为实际位置或真值。
- 5秒内组合新鲜地址正确ACK、AUTO_LOITER与明确目标读回；异步先后仅pending，不重发或延长原150秒准备期。拒绝/重复/未来ACK、倒退/超时、发送不确定、准入后目标丢失锁存。CLI6/4位表示比较与raw精确比较分开，原微小reset/坐标变化仍拒绝。
- 新接口编码误差≤0.02m；入口/观察段trajectory/消费p_sp XY与编码目标差≤0.05m。原2.5m/3秒入口/60秒观察/32秒激励及安全、性能、时间/保护条件不放宽。观察半开窗口不纳入恰好hover_end的正常计划降落。
- 只读series04主ULog SHA88b9cd401f5e410dac6b50f6ee07073597b01a7a7e910646fe89d321f429e086；38.096s sample消费38.084s目标，原XY(-0.0130653,0.0329855)m编码偏差0.003474m。pymavlink实际生成/解码COMMAND_INT包，无网络发送；C++探针链接真实ECL并用生成MAVLink C编解码核对24组向量，不冒称24个gtest。
- targeted01的16项通过；targeted02的23项22过1错误（新检查误把hover_end计划降落算进悬停），保留日志；纠正半开边界后targeted03/04分别24/25项通过。最终verify03实际109个不同C++、172个Python（含新增25项）及SITL/DONT_RUN Gazebo构建通过，总退出0；两组各2048步PID回归/消息1403字节保留。重复运行不累加独立用例。
- 真实命令前回放、二进制编码、实际库函数与合成后续状态链分别披露；没有实例化整套Navigator/Commander/FlightTask异步进程来验证真实响应。完整新分析器对旧series04仍accepted=false、缺hover_start退出1（预期拒绝）；旧失败不改判。不运行MATLAB/旧ISTA/实机。
- 外部handoff06_targeted/verify/audit/reanalysis保存全部失败和证据，228份工件SHA全量通过，索引SHA7812c8a27ed605c2cdd3fc594b2b5eb9b9958aeee7d9b15ae355b5e45879a2bc；离线源码资产索引SHA04a02b5e6417ff6d14e3721283d08d7dee5486b38fb84f82fe7022b434dcfce7。原series04的34份工件SHA不变。
- 新启动0/飞行0/种子0/ULog0，原EEPROM SHA06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc完整不变，无残留仿真。V04仍须真实验收，四批历史4/0与ESTA0不变。
- 明确18文件提交5beaecfd7376178259b547e0f4d1d79156aab70a，diff审查、指纹及提交后主仓库/递归子模块核对通过；未push。报告[目标交接离线修订](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_HANDOFF06_REPAIR.md>)。
- 到此停止。新批次需另行确定准确种子/清单/预算/目录与执行资产，干净源码重建/复核后再获准执行；目前没有六轮飞行申请或可直接运行的批次。不能续跑旧剩余五轮，不V05。

## V04 protocol06 / series05执行与日志拒绝（2026-09-23，failed / needs_revision）

- 用户明确要求“重新冻结并授权新批次”；从5beaecfd7376178259b547e0f4d1d79156aab70a开始，完整阅读计划/共同规则/状态/handoff06报告，核对research/sta-velocity-control及干净主仓库/递归子模块。只执行V04新批次，不续用旧剩余预算。
- 新协议/源码提交c9030688efffce4984f39f3aa08fe270eda7206c，12个明确研究文件；独立06批次、07授权飞行入口、06分析器，复用已离线验证handoff06，旧入口仍禁用、旧冻结文件不变，生产控制/模型/编译参数均未改。
- 185项资产冻结SHA34735620d2cb903354c097029186c4afa44d129c88eb9452fdfdca1c7e678478；execution SHA77617c14d3c0ee13e0d7a1dc60e87e7ffccdf4a14b41e062f84b54e718da0af8。种子注册前21314份JSON无复用、注册审计21317份，飞前重扫通过；仅IMU显式播种及PID先行偏差继续披露。
- 清单9501 PID→ESTA、9502 PID→ESTA、9503 PID→ESTA，共6。实际run01 PID尝试1/完整任务1/接受0、ESTA0/配对0，后续5立即停止，无补飞/调参/预算扩展。五批累计5尝试/1完整/0接受，旧失败不改判。
- 起飞事件30.084s，明确XY命令38.744s、实际命令38.756s、ACK38.764s、handoff_ready39.064s；原XY保留，编码偏差.004569m。观察47.576–107.736s共60.160s，完整32秒激励，115.324s降落上锁。启动器success=true不等于整轮accepted。
- 实际MODE0/AXES0、rate0/0/1、RATT_TEST0/TKO_MGT0/profile147；原项目Iris10016/quad_w/empty_grey.world/1倍速。固件SHA004eb35b5bd91dd895794923a551ce2db67619ed6f9e236aeb10d23715f53448。默认PID和原位置/姿态/起飞/EKF保持，未飞ESTA。
- 最终错误Empty/nonmonotonic vehicle_command。原始起飞22和解锁400同为30.200s，ACK同为30.208s；事件不同、没有时间倒退。新handoff分析器通用data()严格递增要求不适合该事件前缀，合成测试此前未覆盖。
- 另独立诊断发现整数经度85456078：Python除法8.5456078与实录8.545607799999999相差−1ULP。实际接收器含-freciprocal-math；两种离线表达式探针表明实际数值优化选项逐位复现原始值。尚未修复两种检查、不改变生产编译器选项、不放宽阈值、不改判本轮。
- 提交前protocol06_verify01和干净提交protocol06_committed01均109个不同C++/180Python、SITL及DONT_RUN Gazebo构建通过，退出0；8项新增批次接线测试含授权/预算/失败停止和参数恢复。两组2048步PID回归保留，消息1403字节不变。结果阶段180项Python再通过，不累计重复数量。
- run_v04_protocol06退出1；只读audit_v04_protocol06_failure的13项诊断通过退出0，两种探针编译/运行均0（不是新增gtest）；隔离重分析仍accepted=false、相同错误，退出1预期。临时解码漏pyulog路径退出1和JS不支持NaN解析前置失败均披露，无飞行副作用。
- 未接受运行仅描述：32秒X/Y/Z速度RMSE .046067/.008181/.002172m/s；高度RMSE .029205m、最大误差.066740m，yaw RMSE .0001603rad，最大倾角1.0591°。8524条飞行诊断无首次失败/重算，观察6016条约100.003Hz、最大12ms；内环年龄0–4ms。
- 原49项基线检查通过；local/attitude匹配100%、actuator91.503%且误差0/最大8ms；饱和有效位分离后真实饱和0%。两ULog dropout0/无损坏；在线171次回放年龄28–220ms。完整新增handoff/height验收在首个事件检查处停止，不声称尚未执行的检查通过或ESTA胜出。
- 外部series05及protocol06_verify01/committed01/audit01/reanalysis01保存；主ULog36005502字节SHAd8d97dfd7b54fb512c42669e1b874ea49911abe332495b893a269f0ce5e82f16，启动205136字节SHAb1c0bcb78b6b9180c1047db4a6bc402d6325e771c68347efd452d86b123ce340。
- 50原始工件索引SHA20fb1b88f85f457acf3637d361fc0361f8913f44110d92db873dbb30fc22686e；另173证据索引SHA0587642a4dd1a172320841ee10896b5c96c5d55d42c010d615f20b09a721d5d6，全量核验通过，旧series04指纹不变。EEPROM完整恢复SHA06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无残留模拟器。
- 结果提交110e3f667eaca57280519621d52fe6f63413a774，14个明确文件，仅只读审计/表达式探针/报告入口/小证据，冻结185项资产全部不变。diff审查、提交后主仓库/递归子模块检查通过，未push。报告[protocol06结果](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/V04_PROTOCOL06_RESULTS.md>)。
- 下一步需另行获准离线修订事件话题及实际接收器数值参考，再决定新飞行协议/预算；本轮余5不可自动继续。不V05、不旧ISTA、不MATLAB、不实机。
# Z02 当前进度（2026-09-27，offline passed）

## Z03最新：PID02通过，三对Z ESTA协议已冻结

- PID02源码 `746f94f05b49bbed577126765097284de31f4e0e`，新18002、1/1完整接受；60.072s观察、32s Z激励、降落上锁通过，Z RMSE .00459433m/s。
- 结果/非零起飞ν离线筛选提交 `ff56d883bd080b0e159e257a288af859fec3427a`。两候选×两滞后共4条C++对象轨迹，选2/1/4/6，原1/.2非零初态漂移被离线排除，没有将其硬飞。
- 新三对协议源码 `d6ea312f7383b7492f554e00ee873a06270d7fe3`，19001–19003每个PID后ESTA Z共6次，475资产；X/Y、rate PID。原数值验收门槛不变，正在干净源码验证。
- Z03尚未完成；在持续授权内通过飞前检查即运行，不push、不实机。旧PID01失败完整保留。

## Z03进行中：PID01失败已修复，PID02冻结

- PID01源码 `b8e864944cf18ce743a7db9899275b90ae1d9207`，18001、预算1，实际1/0接受，地面起飞阶段因inactive ESTA配置误报pending停止；没有ESTA飞行，原数据保留。
- 修复/结果 `0d06ff47389e6cf2cf7046f20c6c855ecfd9d4d2`；158 C++/386 Python及构建通过，新增纯核/真实模块2项，不修改PID数学或验收门槛。
- 新PID02协议源码 `746f94f05b49bbed577126765097284de31f4e0e`；新18002、预算1，相同任务/参数/门槛；449项资产冻结，正在干净源码验证，通过即按持续授权执行。
- [失败与修复报告](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/Z03_PID01.md>)；Z03未完成，不push。

- 用户授权持续完成 Z 替换，普通修复/新冻结 Iris SITL 批次不再逐次申请；不 push、不实机、不扩大 XY。
- 实现提交 `9bf317ea5a975908e63506a2acdd0c252af3acfb`，17 个明确文件，提交后干净。
- 新 MODE1/AXES4、独立 Z 参数默认关闭；地面/ramp 原 PID、连续交接、空中 Z ESTA，XY/rate PID 不变。
- HTE ν 补偿、NED Z 限幅/故障/重算保护与 z_phase/z_hte_shift 日志；TEST2 垂直任务入口。
- verify06 实际156个不同 C++、386 Python，SITL/Gazebo只构建及PID 2×2048逐位回归通过，退出0。
- 新飞行0，EEPROM完整恢复/未变。编译/夹具早期失败保留，未改门槛换通过。
- [Z02报告](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/Z02.md>)。
- 下一步 Z03 PID-only小垂直任务→冻结安全候选及三对PID/ESTA；原V04已通过，不重新开分支。
