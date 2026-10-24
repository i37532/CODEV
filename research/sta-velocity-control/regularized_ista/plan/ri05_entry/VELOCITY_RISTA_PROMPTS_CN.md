# 速度环 R-ISTA 专项：分阶段提示词

2026-10-24 最新授权：仅执行下方RI05提示词，A/XY（工具C/TEST6）通过后才B/XYZ（工具D/TEST8），每门9次、合计18上限。入口bbc5396c272666bd20f526a54113e9698e87c16b，保持原合格参数，不加载离线Z候选或Proper。当前离线准备中、0飞行；首败停批、不补飞/调参/扩预算/放宽规则、不push、不RI06或旧R04/R05。以下“未授权RI05”等是历史检查点。

2026-10-24 最新：Proper-ISTA独立速度对象离线筛选已完成，提交 **bbc5396c272666bd20f526a54113e9698e87c16b**。505个C++、24个Python通过；144条尝试、132完整（内含12不可行反例）、12极小数拒绝停止，144独立复算一致。Proper理想条件明显改善，但当前同λ下滞后/噪声未全面占优，**未取得速度飞行接入资格**。报告`/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/PROPER_ISTA_PROBE.md`按理想与工程限制分列。

本轮0飞行、不改生产/参数/模型、未push。后续先另行明确离线滞后/噪声与数值终点诊断；不直接替换MODE4、不自动沿用下方RI05提示词或旧飞行预算。历史RI04判决及下方计划保持，当前结论以实时进度顶部为准。

2026-10-24 后续离线修正完成：用户要求解释并修改Z误差较大，新增 **RI04_Z_BANDWIDTH（仅离线候选，不是新飞行验收）**；完整提交 **8ff776664b63bef1c630db8c625f095a028cfb6b**，入口8578560847bd32efa17b5f45d3ec413c2961a927。原RI04九轮判决/参数和生产公式保持不变。实际九轮主窗100%层内、8/12ms各半；相同λ导致R-ISTA局部反馈较弱，非旧ISTA恒定偏差；但额外MSE多数在任务谐波投影之外，不能断言全部差距仅由相位造成。
唯一解析候选Z lambda1=2.2470735044448613、lambda2=1.1647156696299077、epsilon=.02、限制4/6不变，固定10ms局部对齐；候选JSON与实际模型精确绑定，未接switch/runner、不可加载飞行。414个既有C++（未重建全部测试）、17个新Python通过，两纯核重新严格C++14编译；72条模型轨迹235206更新包含12条明确不可行反例。可行模型误差较原R-ISTA降低约7.47%–13.04%，但TV增加，实际交替周期仍略差于R-STA；不是Gazebo新性能结论。
报告：/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/RI04_Z_BANDWIDTH.md。新证据根RI04_Z_BANDWIDTH的27文件索引SHA=d9a9714a6907c77cd60a22033862b98beadd8d51eea4a78a7f38565d2e7b9a2e。新飞行/种子/预算0，无参数写入；工作区干净，领先跟踪分支3提交，未push、未开始RI05/RI06。若采用新候选，先补完整Z/HTE/起降接线回归，再另冻新有限批次；必须与旧同λ比较分开，披露额外离线开发。下方RI04验收记录仍有效，只适用于旧冻结配置。

2026-10-24 最新完成：**RI04 revision01 passed，仅固定参数 Z／Iris SITL 开发门**。新9尝试/9起飞/9接受、9独立回放、6对共78项风险检查通过；PID/R-STA/R-ISTA各3轮，82101–82103已消费。旧3次保留2接受/1失败、旧6次作废，历史共12尝试/11接受/1失败；未补飞、调参、扩预算或放宽门槛。
协议/全部新9轮源码 **a1c2046d94a6bbf061720385a5ad36110b1d0dc2**；独立结果提交 **8578560847bd32efa17b5f45d3ec413c2961a927**。107命令exit0，711 C++、912 Python＋6独立参考、SITL构建及历史回放通过，收尾15项测试exit0；准备失败保留，MATLAB未重跑。Z RMSE均值PID/R-STA/R-ISTA=0.00369169/0.00143525/0.00151296 m/s；R-ISTA对R-STA误差高5.41%、Z纠偏TV低12.09%，不宣称全面获胜或显著性。
报告：/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/RI04_REVISION01.md。完整证据、指纹和限制见实时进度。工作区干净，领先跟踪分支2提交，**未push、未执行RI05或旧R04/R05**；新9次授权已全部消费，无剩余试飞授权。以下“当前/最新/未验收”等执行检查点保留历史，不覆盖本完成记录；原冻结快照不改。

2026-10-24 当前授权更新：用户明确答复“授权新 9 次（推荐）”。RI04 revision01 新批上限9次（PID/R-STA/R-ISTA各3），历史3次保持原判、旧6次作废，历史总上限12次；新根VELOCITY-RISTA-20261024/RI04_REVISION01，候选82101–82103初步全历史74090份JSON查重无冲突，正式登记/飞前仍复查。入口bb56d1414cc0e7e196995f9281a0306ca7f46964已按上轮请求push。本轮不再改生产控制/参数/模型/门槛；先新协议和同门干净源码资格，首败停批、不补飞、不调参、不push、不RI05。当前in_progress，新增尝试/起飞/接受=0/0/0，未预填验收。旧批及下方历史“最新/未push/待授权”文字保留原时点，不覆盖本条。

2026-10-24最新：RI04 HTE/状态限幅交接**仅离线修复完成**，提交 **bb56d1414cc0e7e196995f9281a0306ca7f46964**。106条命令exit0，711 C++、904 Python＋6参考、SITL构建与历史回放通过；报告reports/RI04_HTE_FIX.md，完整证据/限制见实时进度。0新飞行/预算/种子，不push、不RI05。旧RI04仍failed/needs_revision（3尝试/2接受/1失败/6未执行），不改判；不能直接复制下面旧RI04提示词续飞或沿用旧资格。下一批需另获明确有限授权，冻结新清单/种子、同门干净源码和固件资格后才可执行。以下旧“未修复”等均是历史记录。

RI04收尾完整SHA：协议/源码 **74327418e18eafd421e18b48fe3964fdad63cfb5**，独立结果 **50f354678fafb3fd4d4a09530e340f0eefa60f55**。工作区干净、未push；Z门仍未验收，以下后续提示词不是执行授权。

2026-10-24最新：**RI04 failed/needs_revision，未验收**。源码74327418e18eafd421e18b48fe3964fdad63cfb5，3尝试/3起飞/2接受，R-ISTA Z首轮在StateLimit→首个有效HTE更新时因缓存无效故障锁定；6轮按首败规则未执行。2回放和1对13检查通过不等于9轮门槛。报告reports/RI04.md，完整源码/结果SHA见实时进度。仅做停止后的离线审计和结果提交，无生产修复/补飞/调参/扩预算，未push。需要另行明确离线修复和新有限批次，不能直接再次执行本RI04入口或进入RI05；下方全部入口记录/提示词仅保留历史与计划，不是续飞授权。

2026-10-24当前仅执行RI04：入口101d79701b09c764f14ba2290add4a524d44cf3f，RI03已push。Z门最多9次，先离线与冻结提交/同门干净资格，首个必需失败停批，无补飞/扩预算，不push、不执行后续阶段。实时状态以进度表顶部RI04记录为准，下方RI03未push等保留为历史。

2026-10-24最新：**RI03已通过，仅X/Iris开发门**，9/9接受、9独立回放、6对风险检查通过。实际九轮源码ec486cdb9b7957620d3d5d531d9665ee2e3b7e25，结果101d79701b09c764f14ba2290add4a524d44cf3f（初次协议35aea2d198cc3ca2e1c82b0c800b1e105a5b2cac）。报告reports/RI03.md、完整SHA及限制见实时进度。未push、不自动执行RI04或原R04/R05；9次已消费，不能重跑本批补样。下一步只能另行明确启动RI04并取得新Z门资格。下方入口/收尾/创建时说明均是历史，不覆盖此最新记录；原提示词保留供逐阶段使用。

2026-10-24本轮最新：用户明确启动RI03，入口e7fb67112e4cf605f5ddf362f120c320a64d2cf5（RI02已push）。仅新X门：先离线/冻结提交/干净资格，再最多9次PID/R-STA/R-ISTA；首败停批，无补飞或自动扩预算。不push、不执行RI04或旧R04/R05；下方收尾说明保留为历史。

2026-10-24最新：RI02离线验收passed，完整提交SHA=e7fb67112e4cf605f5ddf362f120c320a64d2cf5。609项C++、354项Python、SITL构建及36份历史完整日志回放通过，旧失败保留；MODE4生产准入仍关闭、0新飞行。完整报告/限制见reports/RI02.md与实时进度。下一阶段只能另行明确启动RI03，并重新冻结仅X的准确协议及干净源码/新固件资格；本轮不push、不自动RI03/旧R04/R05。下方RI01及更早收尾文字仅为历史。

2026-10-24本轮：用户明确启动RI02，仅离线接线/回归；入口2f19cefc850ef4b77a8bcdc455aaec193f3da331（RI01已push）。本轮0飞行、不push、不自动RI03/旧R04/R05；下方RI01等为历史。

2026-10-24历史RI01收尾：RI01独立内核离线验收通过，517项C++、6项独立参考及SITL构建exit0；MODE4仍拒绝、0飞行，MATLAB未重跑。102对象须区分84条完整60s（含6条不可行）与18条数值域停止，详见reports/RI01.md。完整提交SHA见实时进度表；本次不push，不自动RI02或旧R04/R05。后续另行启动RI02时须处理数值域拒绝的工程策略，不可直接接管飞行。下方RI00/创建时记录为历史。

2026-10-23 执行更新：RI00离线审计已通过，报告和公式/接口在仓库reports/RI00.md及regularized_ista/ri00。完整提交SHA=e8e38752499c12b9c39bb7dc95da58f27ff029d4；RI01–RI07仍须另行启动，原R04/R05暂停。下方保留各阶段提示词，本次不push、不飞行、不自动下一阶段。

2026-10-23，v1。配套：`VELOCITY_RISTA_TODO_CN.md`、`VELOCITY_RISTA_STATUS_CN.md`。本次只建立分支/计划，不运行下列任务；每个代码块可单独复制，阶段通过后才启动下一段。

仓库 `/home/yr/Desktop/Codev-autopilot`，新分支 `research/ista-velocity-regularized`，初始基线 `a286e40ec8bfbb0500b1c24add18c1a98b908778`。后续实际HEAD按每阶段现场核对，不反复强行回退到创建基线。

新矩阵只含PID、R-STA、R-ISTA；旧ESTA仅保留代码/历史/离线回归。原R04/R05暂停，其后续职责改由RI06/RI07承担新协议；不得直接启动旧含ESTA清单。以下候选预算不是本轮起飞授权，也不继承旧连续执行/push许可。

## RI00 — 先审计来源、公式、接口与参数

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md 的 RI00。
完整阅读本专项三文档、共同规则和阅读路线，核对 /home/yr/Desktop/Codev-autopilot 位于 research/ista-velocity-regularized，记录HEAD、工作区、递归子模块。保留本轮未提交的计划/入口文档及用户改动，不回退或清理；本阶段明确纳入新三文档plan/v1和暂停旧R04/R05的仓库入口改动，不覆盖旧冻结快照。
确认R03最终验收及源码/固件版本限制；阅读R00/R01/R02、R03_ACCEPTANCE_CN、revision11/position11与旧日志/保护经验。完整核对 /home/yr/Desktop/STA-ISTA-MATLAB-PX4 的补偿ISTA、通用隐式核、MATLAB包装、C++、参数、模型、来源与测试，保存原始指纹。
统一包内e=v_sp-v与PX4的s=v-v_sp、a/nu单位和NED方向；逐式核对补偿输入平移、p隐式关系、nu候选进入当前输出、边界/更新顺序。区分原ISTA、Proper-ISTA和本次R-ISTA，不继承未经核实的论文保证。用独立探针审计理想恒定/斜坡扰动、非零nu、实际8/12ms与滞后/约束限制，不能把保存CSV称本次MATLAB重跑。
审计候选MODE4/参数/日志冲突、HTE、Z/XYZ seed、保护与同sample重算，冻结最小接口和首个离线候选来源；不直接加载源包高增益，不调飞行参数。新实验仅PID/R-STA/R-ISTA，原位置P、姿态/rate PID及DIV1保持。
只做离线审计/独立探针，不修改生产控制律、参数、模型或准入，不飞行、不登记试飞。写research/sta-velocity-control/reports/RI00.md，记录真实命令/数量/退出码/未执行项；审查明确文件提交，更新外部进度完整SHA。不push、不执行RI01或旧R04/R05。
```

## RI01 — R-ISTA 独立内核，暂不接执行器

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md 的 RI01。
完整阅读本专项三文档/共同规则和RI00验收，核对 /home/yr/Desktop/Codev-autopilot 的 research/ista-velocity-regularized 分支、HEAD、工作区与子模块，确认前置通过，不清理已有改动。
按RI00固定的补偿正则化隐式关系实现独立C++14速度核，s=v-v_sp，输出只含m/s²纠偏；不套rate的g、不除质量、不重复FF。明确p与nu_candidate决定理想输出，再由独立commit改变状态；三轴隔离、reset、owner/轴/配置与reset代次/密封候选校验。
测试层内/层外、精确±分支边界及nextafter邻点、正负/零/非零nu、无效dt/参数/NaN/Inf、求根相减和中间上溢/下溢、跨实例/跨轴/重复/陈旧/篡改候选。用独立double单调隐式求根及残差，不复制同一解析式自证；再和来源MATLAB fixture核对，能实际运行MATLAB才称重跑通过。
独立对象覆盖正负/零恒定扰动、斜坡扰动、变化目标/非零FF、非零nu和实际sample周期；固定周期理论与变周期/限幅/噪声/姿态电机滞后结果分列。保护后输出不当严格隐式解，结论不符预期如实修订。
回归PID/R-STA及旧ESTA兼容、适用rate内核，构建SITL并证明新核无可生效执行器路径。仅Iris SITL工程的离线工作，不飞行、不改默认PID/上游/模型。
写reports/RI01.md，记录真实非零测试/命令/退出码/失败/未执行项；审查明确范围提交并更新进度完整SHA。不push、不执行RI02或旧R04/R05。
```

## RI02 — 保护、起降交接、日志与工具，先离线

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md 的 RI02。
完整阅读三文档/共同规则和RI00/RI01、R02、R03最终日志链报告；核对 /home/yr/Desktop/Codev-autopilot 的 research/ista-velocity-regularized、HEAD、工作区、子模块，确认前置通过。
把经审计的新模式/配置/requested/effective/pending/reject、参数代次/armed暂存取消/disarm生效/重启保存接线，但生产准入仍关闭。MODE0/1/2/3语义不变，默认PID；新实验不含旧ESTA统计组。
专门定义R-ISTA理想p/a/nu_candidate与保护后的输出/nu关系，不照搬R-STA旧nu输出及冻结后重构。测试饱和方向/反馈有效性/脱离限幅、水平矢量与Z优先、一次FF、HTE和Z/XYZ seed，保护后不声称满足原隐式方程；三轴整体有效才原子提交。
覆盖地面/ramp/假离地/取消/弹跳/超时、EKF各reset、半组NaN/纯加速度、无效恢复/退出重入、故障/termination、同sample二次update、跨起飞reset、末轴失败不部分提交。保持原位置P、姿态/rate PID、DIV1和现有起降/模型/估计器，不额外引入起飞管理。
新增所需诊断并验证ULog实际格式长度/生成/注册/队列，区分双时钟、真实更新、候选/应用/发布输出。实现独立regularized_ista工具默认dry-run，完整参数备份恢复，复用R03最终相对预热/增量读取/白名单/同刻组/完整边界reset/落地尾窗链；错模式/轴/内环/时间/缺样/未接管负例，历史日志全链回放不改判，不放宽数值规则。
PID和R-STA各至少两组2048步逐样本回归，旧ESTA只离线防退化；实际非零PositionControl/ControlMath/Takeoff/RateControl、模块/参数/分析测试和SITL构建。证明新模式仍不可接管；本阶段零飞行。
写reports/RI02.md、记录实际数量/命令/退出码/失败/未执行项，审查明确提交并更新完整SHA。不push、不执行RI03或旧R04/R05。
```

## RI03 — R-ISTA X 单轴开发验证

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md 的 RI03。
完整读三文档/共同规则、RI00–RI02验收和R03最终任务/阈值证据，核对 /home/yr/Desktop/Codev-autopilot 的 research/ista-velocity-regularized 分支、HEAD、工作区、子模块。只在Iris SITL执行，本阶段候选上限9次，不继承旧自动扩预算或push授权。
仅开放经审计新模式AXES1；X是本地NED北向，不是roll。Y/Z速度PID、原位置P/姿态/rate PID、MPC_VC_DIV=MC_RTC_DIV=1、旧起飞管理关闭，其他新掩码拒绝。合法XY目标、唯一发布者、一次FF不变。
先合成方向、真实sample周期与内环电机滞后独立模型、模式/重启/armed修改/disarm/reset/故障/termination和完整接线回归。冻结一组共同来源参数、小幅零净位移X激励、定高约2.5m/固定yaw/起降/主半窗、原安全/非命令轴/日志数值阈值及来源。
全历史查重新种子并登记：PID/R-STA/R-ISTA各3个配对开发轮，共9，PID先行，准确顺序和停止/缺失规则先固定。先提交协议/源码/模型/分析器/参数指纹，在同门干净源码取得真实资格后沿用项目启动器执行。不要飞旧ESTA，不拿历史R03成功补样本。
首个安全或必需有效性失败立即停批，不补飞/换种子/调参/扩预算/改门槛。解码真实模式、X误差、Y/Z非命令轴、位置/高度/yaw、p/理想与应用nu、输出/限制/HTE/接管/时间；9接受、9独立回放、6对PID开发风险检查全部通过才验收，性能不必赢。
写reports/RI03.md，保留所有失败/未执行/指纹与参数恢复，记录真实非零测试、命令及退出码；审查单独结果提交，更新协议/源码与结果完整SHA。不push、不执行RI04或原R04/R05。
```

## RI04 — R-ISTA Z 单轴开发验证

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md 的 RI04。
完整读三文档/共同规则、RI03验收、RI02保护与既有Z/起降报告；核对 /home/yr/Desktop/Codev-autopilot 的 research/ista-velocity-regularized、HEAD、工作区、递归子模块，确认X门通过。
新开放AXES4，保留已验收X，其他新掩码拒绝；XY速度PID、原位置P/姿态/rate PID、两个DIV1、旧实验起飞管理关闭。先离线复跑X，重点验证NED Z方向、独立nu、地面/ramp到Z有界接管、HTE、垂直推力优先、落地尾窗和跨起飞reset；不改land detector/模型/上游。
冻结R03式XY保持、小幅平滑升降回原高度、唯一目标/一次FF、主半窗及全部安全/非命令轴/日志门槛。沿用固定参数来源，不抄源包高增益。PID/R-STA/R-ISTA各3新配对种子，共9次，全历史查重，PID先行准确顺序/预算先提交。
同门干净源码/资格后用项目Gazebo Iris启动器执行；首个安全或必需有效性失败停批，不补飞/调参/放宽阈值。任务Z目标跟踪与相对2.5m高度偏离分别报告，分析XY/yaw、p/候选和应用状态、限制/HTE/输出/时序。每轮参数精确恢复；9接受/9独立回放/6对PID风险检查通过才验收。
写reports/RI04.md，实际非零测试/命令/退出码/失败/缺失如实记录，审查单独结果提交并更新两个完整SHA。不push、不执行RI05或旧R04/R05，不实机。
```

## RI05 — R-ISTA XY、XYZ 顺序验收

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md 的 RI05。
完整读三文档/共同规则、RI03/RI04验收及R03最终XYZ/日志链，核对 /home/yr/Desktop/Codev-autopilot 的 research/ista-velocity-regularized、HEAD、工作区、子模块。严格A→B，前门不合格不得扩大。
A：开放新AXES3，复跑X/Y正负及固定yaw低速水平8字；Z速度PID。B仅A通过后开放AXES7，水平8字叠加既有小幅平滑升降，检查Z限幅对XY、三轴nu隔离/原子提交、HTE/起降有界接管。XYZ正常运行只算所选算法，不用闲置PID做正常输出。
保持原位置P/姿态/rate PID、DIV1、旧起飞管理关闭、一次FF和合法XY；回归新1/4/3/7、PID/R-STA、保存重启、armed修改与disarm切换、故障/termination、重新解锁reset。2/5/6仍不开放。
每门PID/R-STA/R-ISTA各3个新配对种子=9，合计18；参数跨门固定，不飞旧ESTA。每门先离线模型/接线和实际非零测试，再准确冻结任务/阈值/种子/顺序/有限预算/资产并提交，干净源码取得资格后沿用项目Iris启动器执行。
首个安全/必需有效性失败停批，不补飞/换种子/调参/扩预算或放宽规则。每门9接受、9独立回放、6对PID风险检查；逐轴/位置/高度/yaw、p/nu/限制、输出/接管/真实模式/覆盖/时序与TV如实报告，版本不同分别披露，不拼旧成功数据。
写reports/RI05.md分列A/B，冻结合格XYZ完整配置及局限；保留原始ULog/指纹/失败/缺失、参数恢复，审查明确结果提交并更新完整SHA。不push、不执行RI06或旧R04/R05，不分频、不实机。
```

## RI06 — 三算法公平调参、冻结新正式协议

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md 的 RI06（修订后R04的职责，不运行旧R04清单）。
完整读本专项三文档/共同规则、RI05、原R03、V08/AX05相关参数与统计经验；核对 /home/yr/Desktop/Codev-autopilot 的 research/ista-velocity-regularized、HEAD、工作区、子模块，确认XYZ已通过。所有旧数据均已见开发知识，不是新留出。
只比较PID/R-STA/R-ISTA，XYZ速度环；原位置P、姿态/rate PID、DIV1、保护/限制/合格模型/软着陆链固定。旧ESTA不进入新矩阵，仅保持离线兼容。
先提交等额训练协议：每算法3候选×H/V两场景×2新训练种子=12，共36；训练选定各1候选，再每算法H/V×3独立验证种子=6，共18，总54。候选范围/生成/epsilon自由度、目标权重、失败惩罚、并列/无合格候选/早停、准确顺序与种子登记先固定。验证不反复换候选，不单给落后算法追加机会，披露历史额外开发预算。
A组保留共同安全有效域内同lambda/epsilon/限制/保护的R-STA与R-ISTA，说明两者差异还含补偿预测，不称单纯Euler离散化效应；B组各自等预算选参。A固定配置与B优化配置分离，不把调优参数冒充只改形式。
正式候选A=2算法×H/V×20新配对块=80，B=3算法×H/V×20新配对块=120，总200。训练/验证/正式A/正式B种子隔离，同组跨任务保留块相关；H为固定yaw水平8字，V叠加平滑小升降。用开发方差说明n与精度限制，正式前冻准确清单，不新增扰动/质量/分频。
冻结逐轴时间加权RMSE、J、Z/非命令轴、位置/高度/yaw、接受率/限制、TV/频谱/成本口径、主半窗、失败与日志/缺失处理、8个主比较的配对CI/多重比较及重采样种子次数、最小实用差。不得要求R-ISTA必胜或看正式数据追加样本。
仅执行已冻结54预算内训练/独立验证，首个安全或必需有效性失败停批并保存，不补飞。通过后冻结正式源码/固件/参数/模型/world/插件/分析器/manifest，outcomes全unattempted。本阶段不运行正式留出。
写reports/RI06.md，记录真实测试/命令/退出码/实际次数/失败/缺失和下一阶段准确预算；审查明确提交、更新进度完整SHA。不push、不执行RI07或旧R05，不实机。
```

## RI07 — 新正式实验与报告

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md 的 RI07（修订后R05的职责，不运行旧含ESTA清单）。
完整阅读三文档/共同规则、RI06验收和最终正式协议，核对 /home/yr/Desktop/Codev-autopilot 的 research/ista-velocity-regularized、干净冻结源码/固件/工作区/子模块/模型/参数/分析器指纹。本次只执行RI06准确清单，候选200；不扩大V09、旧320消融、分频、ISTA其他变体或实机。
A为R-STA/R-ISTA同参数结构比较，B为PID/R-STA/R-ISTA公平调参后比较，分别按冻结任务门/种子块/顺序执行，不混参数和源码。原位置P/姿态/rate PID、DIV1、保护/模型保持；每轮重启、相对日志预热、备份恢复，核实真实模式/轴/接管/目标/更新序列。
首个安全或必需有效性失败停批，保留所有尝试/无效/未起飞/未执行，不自动补飞、改参数/门槛、换种子或扩样。科学指标不要求新算法胜出，失败不填0，不挑有利配对子集。
真实解码全部ULog、独立回放/指纹与统计复算；按预注册时间窗、逐轴/J、配对块/CI/多重比较和缺失规则分析。报告位置/高度/yaw、候选与应用nu/输出、限制/接受率、真实更新TV、共同带宽及原生谱、宿主成本和实际n，说明接受条件化偏差与随机源限制。
大日志外置，仓库存参数/路径/SHA-256索引、metrics/图表摘要与复现入口。写reports/RI07.md和简明中文总结，明确预算偏离/未完成项，不足清单不能称完整正式矩阵通过；不把保护后结果当严格隐式理论，也不宣称实机结论。
记录真实命令/非零测试/退出码、审查明确范围结果提交、更新完整SHA后停止。不push、不自动其他阶段、不硬件部署。
```
