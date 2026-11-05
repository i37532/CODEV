# 速度环 R-ISTA 专项：实时进度

## RI07恢复准备：原200清单与版本更新授权（2026-10-26最新）

用户已单独授权清理历史ULog并再次执行原200次正式清单，原容量阻塞解除。已完成零飞行初步回归751个C++、1121个Python；新增正式顺序/参数恢复/独立回放接线44项通过。新运行器逐轮独立回放、首败停批，不调参、不改规则、不扩预算、不push。

启动器按当前Git提交重新构建版本元数据，用户明确答复“允许，仅更新版本并重新冻结”。保留RI06原固件SHA作为来源，工具提交后在同一干净源码重新构建及资格化RI07固件，200项统一使用该新SHA；生产控制、参数、模型、阈值和统计方案保持不变。当前0正式尝试，资格未完成，不能预填验收。

原plots01的56文件原字节暂存外部RI07/ri06_plots_preserved，收尾恢复；历史清理记录HISTORY-CLEANUP-20261026保留。仓库新快照plan/ri07-resume不覆盖旧版本。后续源码/结果完整SHA按实际记录；以下“当前blocked”等为历史时点。

## 2026-10-26：RI07 blocked_before_batch（当前）

仅启动审计，**计划200=A80+B120；0尝试/0起飞/0接受/0无效飞行，200未执行，新种子消费0**。入口HEAD bed13f0bc10029a278acfbad99b730e13b0f7e25，RI06已按随后请求push；本轮不push、不飞行、不改参数/门槛、不补飞、不扩样。

冻结全剩余容量：200×200 MiB+12 GiB=54,827,941,888 bytes（51.0625 GiB）；实际37,631,094,784 bytes，缺17,196,847,104 bytes（约16.02 GiB）。未删除旧数据或降低预检。1146仓库/79外部指纹全匹配，33子模块匹配且干净，固件b7548e2cc08208972e42501d1faf9e793a027224d30790264e9d16b316fcaaa1、参数06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc匹配，无模拟器残留。原plots01/56未跟踪文件保留，未夹带提交。

8项新增辅助预检测试exit0；只读审计exit2（明确blocked，非飞行失败）。没有新C++回归/构建、正式执行适配/资格、全历史种子复查、正式ULog或统计。报告research/sta-velocity-control/reports/RI07.md；原始入口证据regularized_ista/ri07/results/prestart01/evidence.json。明确8文件结果提交 **f2728792ed1d03d8e0919043c3bb310eba8e089a**（父bed13f0bc10029a278acfbad99b730e13b0f7e25），未push；不是可飞行源码资格。提交后仅原plots01目录未跟踪，不称工作区干净。

需要先解决存储（至少51.0625 GiB可用，建议55–60 GiB）和既有图表未提交状态，再补正式执行接线/测试/干净资格；200清单顺序和预算保持不变。下方RI06/RI05的“当前、未push、下一步”均保留历史时点。

## 2026-10-25：RI06完整验收通过（当前）

**passed，仅XYZ PID/R-STA/R-ISTA Iris SITL开发/独立验证。** 54计划/54尝试/54起飞/54接受，54独立完整回放、36配对/468项风险检查通过。0飞行失败/缺失/补飞/扩预算；参数逐字节恢复、无残留模拟器，原位置P/姿态/rate PID、DIV1/保护/合格模型不变。原始108份ULog共6,565,959,652字节外置，指纹全复核。正式A80+B120共200项全部unattempted，正式0次；不自动RI07/旧R04/R05/分频/实机。

- 训练协议/全部36轮源码 **160a595a42898f9a9990a6047f982dd5cbacfb8b**，固件b4e4fa9eaa7a298e893496bb2be05c2fd90aebd2b63993ebc488f9624cc274b8。
- 唯一选参/验证冻结/全部18轮源码 **16113b0ab3a0569755a11282dfc79cfed148f66b**，固件b7548e2cc08208972e42501d1faf9e793a027224d30790264e9d16b316fcaaa1。PID/RSTA/RISTA倍率1.1/.9/1.1，epsilon与限制固定，验证不重选，A另保持共同基准1.0。来源127参数、主半窗、全部阈值/顺序事前固定。
- 独立结果提交 **bed13f0bc10029a278acfbad99b730e13b0f7e25**，父16113b；明确11个结果/报告/审计文件。提交后工作区干净、33递归子模块匹配且干净，领先跟踪分支3提交，**未push**。不把结果SHA冒充已资格化的飞行固件。
- 四门qualification各124命令全exit0：751唯一C++/48目标、1128 Python/47套、6独立参考、18历史接受回放/2失败审计、严格C++14和SITL/Gazebo build-only。重复不算新增测试。收尾160项实际Python=146协议回归+14新增结果层负例，7命令全0；MATLAB未重跑。
- B独立验证每任务n3，H J均值PID/RSTA/RISTA=.006768453/.003966277/.003861729，V=.006742576/.003997731/.003723143m/s。RISTA相对RSTA低2.64%/6.87%，但平均纠偏TV/s高22.71%/19.03%；两差均低于预设.0005m/s实用差，不宣称正式显著性/全面获胜。A同参数开发每任务n2仍RISTA J略高，不能与B调优结论混称。
- 一次结果导出exit1（嵌套诊断inf）原20183字节完整保留，SHA3cefa7324fbb37176d8961b5043e2990d68e68075023e29a9ef4c9bca3053d96。仅结果层对12个精确估计器约束路径×54=648个正无穷作可逆显式标记；其他非有限值仍拒绝，不填0、不修改原指标/验收/冻结分析器，不增加飞行。真实输入重建与14项负例通过；初始导入/只读汇总/轮询错误也在报告披露。

报告 `/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/RI06.md`。最终包 `regularized_ista/ri06/results/final02/package.json` SHA d9351d9a4f76d66274739928b60cf8df6499f03ac21e6198f2e075ae6bd3e842；审计SHA cb83ffee8185fc336b3247c6781cf41fd41ab0a0d9aedbb211b977bd9ccd9997。外部根 `/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261025/RI06`。下一阶段准确候选预算200=A80+B120，20配对块/组、8主比较，需RI07明确启动与执行链资格，当前停止。

下方“当前/未起飞/资格中”等均为执行过程的历史检查点，不覆盖本完成记录。

## 2026-10-25：RI06训练36及水平验证9通过，最后VV资格进行中（历史检查点）

仅RI06：XYZ PID/R-STA/R-ISTA，训练36＋独立验证18，最多54新尝试，首个必需失败停批，不补飞；正式A80+B120只冻结、不执行。TH和TV各18尝试/18起飞/18接受，合计36独立完整回放一致、24配对风险检查通过；VH也已9尝试/9起飞/9接受、9独立回放一致及6配对检查通过。当前累计45接受/45回放/30配对，无飞行失败、补飞或额外预算；参数精确恢复、无残留模拟器。VV正在qualification01，尚0飞行；不预填后续通过。

一次选参已按原评分完成，PID/RSTA/RISTA索引=2/0/2（倍率1.1/.9/1.1，epsilon和限制不变），训练输入42项SHA绑定，selection.validation_used=0，验证没有重选。仅selection.json及VH/VV两个冻结文件明确提交 **16113b0ab3a0569755a11282dfc79cfed148f66b**；146项RI06离线测试exit0，工作区干净，生产/工具逻辑未改。VH同源码资格d4ca835aadbd6f0a2d61d87d3b916148641fea15768d16fc836e36e6a8f8ad57通过，固件b7548e2cc08208972e42501d1faf9e793a027224d30790264e9d16b316fcaaa1。TV同源码资格774803cd18d1a9bee0a143a8dc2f801b7e46dd86562e8de0e452fb84302d0c00；各完整124命令/751 C++/1128 Python/6参考，不把重复执行累计为新增用例。

TH/qualification01已真实exit0、clean/approved=true：124命令全部0，751唯一C++/48目标、1128 Python/47套、6独立参考、18历史成功回放及2失败审计，SITL/Gazebo build-only通过。源码160a595a42898f9a9990a6047f982dd5cbacfb8b；固件b4e4fa9eaa7a298e893496bb2be05c2fd90aebd2b63993ebc488f9624cc274b8；资格SHA e4a2c541c44f55e57a53457905be29b6f0ce41c85aa3c8ef99a40a0d0e98e225。新增146项Python不与历史重复执行累计。资格阶段零飞行。

协议/工具提交 **160a595a42898f9a9990a6047f982dd5cbacfb8b**，入口152e5bc9b31f4b2b373671abfd116288131872d8；研究分支正确、提交后干净，33递归子模块未改，生产控制/参数默认值/模型/保护差异为空。31个明确新文件包括三文档ri06-entry快照。未push。

三候选为基线统一倍率 .9/1/1.1；PID缩放XYZ P/I/D，两种STA缩放三轴λ1/λ2，epsilon与限制固定。TH18→TV18→一次选参并提交→VH9→VV9；固定评分、风险门、统计8比较/20块/缺失规则，不要求R-ISTA获胜。
初始79002份JSON查重无冲突/坏JSON；提交前79550份复查通过。训练84001–84002、验证84101–84103、正式A85001–85020/B85101–85120隔离，H/V共享同组块相关；正式零飞行。

`RI06/offline01`完整exit0：751唯一C++/48目标、1088 Python、6独立参考、18历史成功日志回放及2失败审计；之后新增参数事务/统计/打包离线测试，TH最终同源码资格已通过，不拿旧dirty构建作为起飞资格。两次命令环境遗漏分别缺pymavlink/numpy，均在离线导入时退出1、未飞行，补齐既有PYTHONPATH后通过；未安装/替换依赖。
数据根 `/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261025/RI06`；协议见仓库 `regularized_ista/ri06/PROTOCOL_CN.md`。下面RI05等“当前/最新/未push”是历史检查点，不覆盖本节。

## 2026-10-24：RI05最终通过（当前）

**A/XY、B/XYZ passed；18计划/18尝试/18离地/18接受，18独立完整回放、12对156项风险检查通过。** 0飞行失败/缺失，另有1次历史B启动入口拒绝，不改判。原18预算全部消费，无补飞/调参/扩预算/门槛更改；不push、不执行RI06/旧R04/R05、不分频/实机。

- A飞行源码3e633a0d2aba1326d3f79b0033f59787cc479c44，结果de1823566ec6c89cd416252db079d2044f41f905。B恢复协议/实际飞行源码 **32a266f6162f1e09667ec92eeb0ad25abfee7ea7**；最终独立结果提交 **152e5bc9b31f4b2b373671abfd116288131872d8**（父32a，8个明确结果/报告文件）。B固件b356efaa4f46644b26b480b54a1e8ce93bf04b8294cdb54f428cabfe3784fa0c；两门版本分列，不混为同版本试验。
- B qualification02完整118命令全exit0，751唯一C++/982 Python/6参考、18历史接受回放/2失败审计、严格C++14及SITL/Gazebo build-only通过。资格SHA25da01ec4ae4e6bf86d8bde62f8e4d609c3753cc60bf34a5d74195133e7cd9f3，绑定新干净源码/固件。
- B原run010–018一次执行，9接受/9独立回放/6对78项，全部精确恢复BSON，无残留模拟器；18份B ULog指纹复核。ledger SHA a0c470fa2e0a4c42cef02fa9d36b45606bc07bde8ab02ad55167088c20e5c2fb，replay SHA58d76cb24dfe72a6b23b1714959389da8a94b0cf91c47b23efbb869b449f69f1。收尾87项结果层/归档/导出测试exit0；新56项不重复累计，MATLAB未重跑。
- B主窗J均值PID/RSTA/RISTA=0.007249965/0.003835714/0.003914100 m/s；RISTA相对PID低46.01%，相对RSTA高2.04%。RISTA相对RSTA X低3.40%、Y高8.07%、Z高3.03%，Z纠偏TV低13.77%；只为n=3配对开发描述，不宣称全面胜出/显著性。部分rate→actuator覆盖及HTE子集边界如实披露。
- 报告`research/sta-velocity-control/reports/RI05.md`；最终收据/127项完整XYZ配置在`regularized_ista/ri05/results/final01/`，无新飞行授权，不可盲目导入实机。原归档1805字节/SHA不变，已移至dry_run01.log；旧停止和迁移收据保留。

验收、审查和明确范围结果提交已完成；提交后工作区干净、33递归子模块匹配且干净，领先跟踪分支10提交，未push。1164项冻结资产/最终固件/参数及外部摘要引用只读核对通过。后续RI06需其自己的协议/新预算，不自动运行。下方全部“最新/未飞行/停止”是历史检查点，当前状态以本节为准。

## 2026-10-24：RI05 B原九项恢复授权（最新）

恢复协议/工具/证据已明确7文件提交 **32a266f6162f1e09667ec92eeb0ad25abfee7ea7**（父f4ade4bde0d6c1b409d6ca2044e44db6aeed64a3）；提交后工作区干净、原1085/79资产与33子模块不变。旧stdout已原1805字节/SHA移动为dry_run01.log，迁移收据保留旧路径/失败；全历史77930份扫描0冲突/0坏JSON，原登记不变。56项新离线测试通过（归档23+结果导出33），首次环境漏配的导入失败0测试已保留。当前在新干净SHA运行D/qualification02，尚未起飞；不预填新资格通过。接下来固定此源码，仍仅原D9项、首败停止，未push。

用户明确回复“YUNXU”（允许）：仅修正dry-run stdout归档、补接线回归后恢复原run010–run018。入口f4ade4bde0d6c1b409d6ca2044e44db6aeed64a3、研究分支正确、工作区与33递归子模块干净，磁盘约49GB。A已通过，B仍0尝试/0飞行；本轮尚未迁移或起飞。总预算仍18、B原9不增加；原种子/参数/任务/阈值/严格scanner不改。

恢复规则另存ri05/results/recovery01/RECOVERY_CN.md；旧停批和原快照保留。先归档接线测试、原字节改名及严格历史复查，明确提交后取得qualification02新干净源码/固件资格，再执行原九项。新的首个必需失败仍立即停止，不无限重试、不调参/扩预算/换种子，不push、不RI06/旧R04/R05。

## 2026-10-24：RI05 停批收尾（最新，覆盖下方执行检查点）

**A/XY passed；B/XYZ needs_revision / stopped_before_batch；RI05未整体验收。** 总18计划/9尝试/9离地/9接受，A的9独立回放和6对78项风险检查通过；B 0尝试/0飞行/0接受、9未执行，另有1次启动预检拒绝，不能当作飞行失败。原本18上限不变，不补飞、不扩预算、不改判。

A飞行源码 **3e633a0d2aba1326d3f79b0033f59787cc479c44**，独立结果 **de1823566ec6c89cd416252db079d2044f41f905**。B源码 **6faad54e1ea1041c144d79c97df9475a19b90290**；干净qualification01通过118命令、751 C++/982 Python/6参考及构建/历史回放，固件de8d6c94107c30301a530a8bd25f076591344250d0f5f2a6ff5e4074bb3c3e62。各版本分别披露，不拼为同版本18轮。

停止原因是**代理把dry-run混合stdout误存为实验历史树内的.json**，不是实际种子冲突或控制算法飞行失败。首次execute在seed历史必需预检exit1，尚未创建D/batch01、ledger或启动模拟器/参数备份。只读扫描77929份记录，matches=[]，唯一invalid_json是RI05/D/dry_run01.json（1805字节，SHA874270526d0fd015624f187fbb5a2e75af6abd6d0c19e84f55c25aeb53c0a956），原文件完整保留。EEPROM仍06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无残留模拟器。

AXES7已开放且离线通过，但**没有XYZ飞行验收配置**。报告research/sta-velocity-control/reports/RI05.md及ri05/results/D_PRESTART_CN.md；停批结果完整SHA **f4ade4bde0d6c1b409d6ca2044e44db6aeed64a3**（父6faad54e1ea1041c144d79c97df9475a19b90290），明确5个结果/报告文件提交。31项结果层单测及1350项只读资产/日志/链接/状态核查exit0，后者不是新增控制器单测。提交后工作区干净、33递归子模块一致且干净，领先跟踪分支8提交。本次未实施修订/重试/调参/换种子，未push、不RI06/旧R04/R05。

下一步最小范围：明确记录并允许原stdout证据按原字节归类为.log，保留原路径/哈希/本次失败，补归档与种子扫描接线回归、重验源码/资格，再定义原未执行9项的恢复规则；不要求新增9次预算，不泛化忽略坏JSON或放宽白名单。本次在首个必需预检失败处停止。以下“已启动/下一步”等都是历史时点，不构成自动重试授权。

## 2026-10-24：RI05 执行入口（历史）

B/XYZ干净`D/qualification01`已exit0、success/clean/approved=true，118命令全0、751 C++/982 Python/6参考、18历史接受回放/2失败审计及构建通过。飞行源码 **6faad54e1ea1041c144d79c97df9475a19b90290**，固件 **de8d6c94107c30301a530a8bd25f076591344250d0f5f2a6ff5e4074bb3c3e62**，资格SHA `33c3317c41e68a096a3bdfd65efe0fcca433d7f17796d2dce641270b1a3d3f71`。dry-run exit0后已显式启动冻结D最多9轮，按`D/batch01/ledger.json`记录实际尝试/接受，不预填通过；仍首败停批、无新预算、未push。

B/XYZ协议/源码已明确12文件提交 **6faad54e1ea1041c144d79c97df9475a19b90290**（父de1823566ec6c89cd416252db079d2044f41f905），提交后工作区干净。生产唯一行为放行SITL/DIV1 MODE4 AXES7，默认值/数学/保护/固定127参数/模型/冻结工具均不变；7个冻结资产差异全部在约定范围。`D/preflight02`完整118命令exit0：751 C++、982 Python、6参考、18历史接受回放及2失败审计、构建通过。首次遗漏PYTHONPATH退出1与为补XYZ首次StateLimit→HTE测试主动中止preflight01退出130均保留、不计资格。现在运行本门干净`D/qualification01`，尚0次B飞行；本阶段实际9/18，首败停批，不push。

A/XY独立结果已明确8文件提交 **de1823566ec6c89cd416252db079d2044f41f905**，与飞行源码`3e633a0d2aba1326d3f79b0033f59787cc479c44`分开。报告`reports/RI05.md`暂为A通过/B准备中；31项结果层测试、外部完整摘要/档案索引引用及18ULog指纹通过。提交后工作区仅B授权的七个生产/测试文件在开发，不清理；未push。

A/XY（工具C）已真实passed：9尝试/9离地/9接受，9独立解码一致、6对78项风险检查通过，参数精确恢复、无剩余模拟器；18份ULog指纹复核通过。全部源码`3e633a0d2aba1326d3f79b0033f59787cc479c44`、固件`cbf94950e6ae5fcaac5e7bbb18cbb58ae00d1723ccee64da730831edceba93e9`；回放摘要SHA`e45ce23f6f7996f3306d2202d8c10e9ebea7c13a4cf7f70fa5489c002dec3647`。B/XYZ仅现在开始准入与离线回归，尚0尝试；本阶段累计9/18上限，不调参、不补飞、不push。以下为历史执行检查点。

`C/qualification01`已真实exit0、success/clean/approved=true：733 C++、982 Python、6独立参考、18接受回放及2失败审计，源码`3e633a0d2aba1326d3f79b0033f59787cc479c44`。现在显式启动A/XY（工具C）最多9次；实际尝试/接受以外部`RI05/C/batch01/ledger.json`为准，不预填通过。B/XYZ仍关闭，首败停批，不push。

XY协议/源码已提交 **3e633a0d2aba1326d3f79b0033f59787cc479c44**（父bbc5396c272666bd20f526a54113e9698e87c16b）；37个明确文件，提交后工作区干净，未push。`C/preflight02`完整exit0：733个C++/48目标、982个Python、6个独立参考、102对象轨迹、18份历史接受日志重放及2类历史失败审计，SITL/Gazebo构建通过。`preflight01`目录包装拒绝失败完整保留，未改判旧失败。当前在该干净提交运行`C/qualification01`，尚未获准起飞，尝试/起飞/接受仍0/0/0。冻结1085仓库/79外部资产和33子模块；XYZ生产准入仍关闭。

仅RI05，A/XY→B/XYZ，每门三算法各3次=9、共18上限。内部C/D分别对应A/B，TEST6/8原64秒任务。入口bbc5396c272666bd20f526a54113e9698e87c16b、research/ista-velocity-regularized，工作区和33递归子模块干净；磁盘52GB可用。RI03 X与RI04 revision01 Z通过，当前in_progress，0尝试/0起飞/0接受；不预填通过。保持原合格参数和内环PID，Proper与离线增益候选不纳入。先A，B准入保持关闭；每门先独立冻结提交与干净资格，首败停批，不补飞、不调参、不扩预算、不push、不RI06或旧R04/R05。下方历史授权/结果保持。

## 2026-10-24：Proper-ISTA 速度对象离线筛选（最新）

- 状态 **offline_complete / integration_not_qualified**，不是飞行验收或RI05。完整提交 **bbc5396c272666bd20f526a54113e9698e87c16b**，父8ff776664b63bef1c630db8c625f095a028cfb6b；research/ista-velocity-regularized，15个研究文件，提交后干净、领先跟踪分支4提交，未push。
- 实际重新严格C++14编译三个未改数学核，72新桥接C++＋433既有C++重执行=505；18模型Python＋6分析器=24，均exit0。既有测试二进制未全重建；未新构建固件、未MATLAB重跑。33递归子模块匹配且干净。
- 144条尝试，132条完整36s，12条零扰极小数被原核数值域拒绝停止；完整132条内含12条控制能力不足反例。495167次有效更新，144/144独立指标复算、173档案指纹和11文档链接核验通过；所有旧尝试和检查器修订保留，不将重复运行算新样本。
- 固定同λ、交替8/12ms、尾窗12–36s：理想目标RMSE R-STA/Proper=0.00050444/0.000002285m/s；两级滞后=0.00050320/0.00597640；噪声=0.00052249/0.00068900。固定周期斜坡理论关系复现，但Proper滞后输出TV明显更大，float/double物理轨迹差异也已披露；不是公平调参后的最终排名，不保证接入优于R-STA。
- 报告：`/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/PROPER_ISTA_PROBE.md`。外部证据：`/home/yr/Desktop/codev doc/experiments/VELOCITY-PROPER-20261024/PROBE/`；最终attempt02摘要SHA=ed98eb5e97ec26b2c330829f2b8f160941ae907c223c6815b590287a4bea583d，replay02索引SHA=0b6068bcfdd9451dc57bf3a9dbff4e96b5a1accb1c40b69a4b18ad95ef25ece3；收尾final_checks02 exit0。
- 0新飞行/参数写入/种子消费；生产控制律、模型、准入和默认PID不变，MODE4仍R-ISTA。下一步建议独立离线研究滞后/噪声及极小数处理，不自动实施、不飞行、不启动RI05/RI06或旧R04/R05。下方历史结果不改判。

2026-10-24 后续离线修正完成：用户要求解释并修改Z误差较大，新增 **RI04_Z_BANDWIDTH（仅离线候选，不是新飞行验收）**；完整提交 **8ff776664b63bef1c630db8c625f095a028cfb6b**，入口8578560847bd32efa17b5f45d3ec413c2961a927。原RI04九轮判决/参数和生产公式保持不变。实际九轮主窗100%层内、8/12ms各半；相同λ导致R-ISTA局部反馈较弱，非旧ISTA恒定偏差；但额外MSE多数在任务谐波投影之外，不能断言全部差距仅由相位造成。
唯一解析候选Z lambda1=2.2470735044448613、lambda2=1.1647156696299077、epsilon=.02、限制4/6不变，固定10ms局部对齐；候选JSON与实际模型精确绑定，未接switch/runner、不可加载飞行。414个既有C++（未重建全部测试）、17个新Python通过，两纯核重新严格C++14编译；72条模型轨迹235206更新包含12条明确不可行反例。可行模型误差较原R-ISTA降低约7.47%–13.04%，但TV增加，实际交替周期仍略差于R-STA；不是Gazebo新性能结论。
报告：/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/RI04_Z_BANDWIDTH.md。新证据根RI04_Z_BANDWIDTH的27文件索引SHA=d9a9714a6907c77cd60a22033862b98beadd8d51eea4a78a7f38565d2e7b9a2e。新飞行/种子/预算0，无参数写入；工作区干净，领先跟踪分支3提交，未push、未开始RI05/RI06。若采用新候选，先补完整Z/HTE/起降接线回归，再另冻新有限批次；必须与旧同λ比较分开，披露额外离线开发。下方RI04验收记录仍有效，只适用于旧冻结配置。

2026-10-24 最新完成：**RI04 revision01 passed，仅固定参数 Z／Iris SITL 开发门**。新9尝试/9起飞/9接受、9独立回放、6对共78项风险检查通过；PID/R-STA/R-ISTA各3轮，82101–82103已消费。旧3次保留2接受/1失败、旧6次作废，历史共12尝试/11接受/1失败；未补飞、调参、扩预算或放宽门槛。
协议/全部新9轮源码 **a1c2046d94a6bbf061720385a5ad36110b1d0dc2**；独立结果提交 **8578560847bd32efa17b5f45d3ec413c2961a927**。107命令exit0，711 C++、912 Python＋6独立参考、SITL构建及历史回放通过，收尾15项测试exit0；准备失败保留，MATLAB未重跑。Z RMSE均值PID/R-STA/R-ISTA=0.00369169/0.00143525/0.00151296 m/s；R-ISTA对R-STA误差高5.41%、Z纠偏TV低12.09%，不宣称全面获胜或显著性。
报告：/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/RI04_REVISION01.md。完整证据、指纹和限制见实时进度。工作区干净，领先跟踪分支2提交，**未push、未执行RI05或旧R04/R05**；新9次授权已全部消费，无剩余试飞授权。以下“当前/最新/未验收”等执行检查点保留历史，不覆盖本完成记录；原冻结快照不改。

RI04 revision01 qualification01已真实通过：107命令exit0，711 C++/48目标、912 Python/39套＋6独立参考、9历史接受回放和2失败审计；clean/approved=true，源码a1c2046d94a6bbf061720385a5ad36110b1d0dc2。已显式启动最多9次运行器；实际状态以新根B/batch01/ledger.json为准，不预填接受。首败停止、不补飞、不push。

本批协议/源码已明确29文件提交：a1c2046d94a6bbf061720385a5ad36110b1d0dc2（父bb56d1414cc0e7e196995f9281a0306ca7f46964），提交后工作区干净，未push；冻结1049仓库/79外部资产和33子模块，生产差异为空。飞前离线711 C++、912 Python＋6参考及9旧回放已实际执行，但预检包装错误保留为失败；正在该干净提交运行qualification01，尚无起飞资格，新增尝试/起飞/接受仍0/0/0。

2026-10-24 当前授权更新：用户明确答复“授权新 9 次（推荐）”。RI04 revision01 新批上限9次（PID/R-STA/R-ISTA各3），历史3次保持原判、旧6次作废，历史总上限12次；新根VELOCITY-RISTA-20261024/RI04_REVISION01，候选82101–82103初步全历史74090份JSON查重无冲突，正式登记/飞前仍复查。入口bb56d1414cc0e7e196995f9281a0306ca7f46964已按上轮请求push。本轮不再改生产控制/参数/模型/门槛；先新协议和同门干净源码资格，首败停批、不补飞、不调参、不push、不RI05。当前in_progress，新增尝试/起飞/接受=0/0/0，未预填验收。旧批及下方历史“最新/未push/待授权”文字保留原时点，不覆盖本条。

## RI04 HTE／状态限幅交接修复（2026-10-24，最新）

- **passed_offline_only：离线修复完成，RI04飞行仍failed/needs_revision、未验收。** 用户本轮仅授权离线修复直到完成；实际新增飞行/种子/预算均0，没有续跑旧6轮、调参、push或进入RI05/旧R04/R05。
- 完整提交SHA：**bb56d1414cc0e7e196995f9281a0306ca7f46964**；父50f354678fafb3fd4d4a09530e340f0eefa60f55。分支research/ista-velocity-regularized，明确11文件提交后工作区干净。唯一生产行为是允许StateLimit-only闭合事务缓存真实纠偏用于HTE；原输出/下游限幅、外推冻结、失效身份/生命周期和不可行平移仍拒绝，参数/控制律/上游/模型/默认PID均未改。
- verification02真实106命令全exit0：**711唯一C++/48目标、904 Python/38套＋6独立参考**；严格C++14、SITL/Gazebo仅构建、9历史接受完整回放和2失败审计通过。旧代码红测真实复现，最终新增13个C++与32个Python通过；多轮不重复累计用例。所有编译/夹具开发失败保留。
- 真实失败边界414候选及seed与独立求根一致；实际输出c与裁剪nu分别有界平移，严格隐式标志不重标。模块下一拍输入只是从日志重建的代表输入，不冒充原首次调用完整输入。固定工况的映射连续不保证下一拍推力不变或新飞行必过；原ν较早到限幅的系统因果仍未证明。
- 最终证据SHA256：12dc58701362cb96e9f7eced821d85679efbb8e0060c5570a38c848a63956f1b；修复固件061e2a374defd80a32476710b6d6dd78b71950b2532d051ba7e598e944a0c402。这是入口HEAD+已测试补丁构建，不是新干净提交的飞行资格；approved/flight_authorized均false。1082输入/33子模块首尾一致，EEPROM仍06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，日志格式1018/1475B、队列8不变。
- 原RI04的1880文件/3链接全部原样保留、不改判；新1609证据文件索引SHA256为5e7e1dd566235fb679eed0d749572bbce5e340152057fa1c7e2921ef6e52da8c。报告：/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/RI04_HTE_FIX.md；外部证据：/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI04_HTE_FIX。
- 下一步需另获新有限批次授权，再冻结新源码/固件资格、准确清单/新种子及历史查重、参数/模型/分析器和首败停止规则；不能直接续飞旧批或混源码补齐。MATLAB未重跑、不实机。下方记录全部保留为历史。

## RI04 停批收尾（2026-10-24，历史）

- **failed/needs_revision，未验收**。9计划/3尝试/3起飞/2接受/1失败/6未执行；PID、R-STA各1轮接受，R-ISTA首轮起飞期控制更新故障，立即停批。无补飞/换种子/调参/扩预算/放宽阈值；没有gate_pass。2独立接受回放和1对13项风险检查，不满足9/9/6要求。
- 协议/实际全部三轮源码：**74327418e18eafd421e18b48fe3964fdad63cfb5**；固件ec20b8dfb05fb10bb605395db4360e3af1daf882a2187ccc06ad95865d8b35a5。独立结果完整SHA：**50f354678fafb3fd4d4a09530e340f0eefa60f55**（11个明确结果/报告文件，父为上述飞行源码）；结果提交不作为新的飞行源码。提交后工作区干净、33子模块版本/内部状态不变，本地领先跟踪分支2提交，未push。
- qualification01真实103命令exit0，698唯一C++/48目标、872直接Python/36套＋6独立参考，SITL/Gazebo仅构建、9历史接受回放及1旧失败审计通过。收尾结果层24测试exit0。离线通过不能代替失败的飞行验收。
- 故障：38.924s真实8ms Z seed，随后414次有效候选；41.384s首次ν限幅至−4使HTE缓存无效；43.076s首个有效HTE到来被该缓存条件拒绝，源码调用顺序与边界日志支持Numerical→Measurement组合故障10、first_fail56及同帧重试失败。没有记录首abort调用栈，推断边界已披露；ν为何早达限制的系统原因尚未因果证明，未实施修复。Gazebo真值约上升1.735m，主激励未开始。
- 两份失败ULog及所有未执行项保留；独立bisection重算414候选，最大差4.576e−7。2接受回放全部metrics/谱一致，原batch176文件/3链接未变；失败审计40文件/1链接未变。六份ULog SHA索引在ri04/results，外部总索引1880文件/3链接全部重新核验通过；6脚本语法、4严格JSON、24项测试收据和9个报告链接复核通过。
- 三轮完整参数恢复精确，EEPROM仍06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc；无自有PX4/Gazebo残留。失败轮停止SITL不代表完成降落或实机安全策略。
- 报告：/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/RI04.md；证据根：/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI04；源码/参数/模型/阈值停批后保持。仍为research/ista-velocity-regularized，默认PID；新AXES4虽可选但未通过Z门，不应使用为合格配置。未push、未执行RI05或旧R04/R05。
- 种子82001已使用，82002/82003注册但未尝试；剩余6轮不是续飞许可。下一步须明确离线修复和新源码资格/新准确预算，不能在本失败批次自动继续。

## RI04 执行入口（2026-10-24，历史）

- 用户仅授权 RI04 Z 门，最多9次新配对开发尝试；PID/R-STA/R-ISTA各3，首个安全或必需有效性失败停批，不补飞、不调参、不扩预算、不push、不进入RI05或旧R04/R05。
- 入口HEAD：101d79701b09c764f14ba2290add4a524d44cf3f；分支research/ista-velocity-regularized。入口工作区和33个递归子模块干净、版本匹配；上一条push请求已经成功，远端同名分支同步至该HEAD。
- RI03 X已通过，当前RI04为in_progress，0尝试/0起飞/0接受。先新增仅SITL AXES4并回归X，审计隐式Z seed/HTE/起降边界，固定既有参数、阈值和准确清单；干净协议提交及真实资格完成前不启动Gazebo飞行。
- 新证据根目录：/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI04；本阶段计划快照存regularized_ista/plan/ri04_entry，不覆盖旧快照。下方RI03未push等为历史时点记录。
- RI04协议/源码完整SHA：**74327418e18eafd421e18b48fe3964fdad63cfb5**（35个明确文件，父101d79701b09c764f14ba2290add4a524d44cf3f）；提交后工作区干净、未push。preflight01真实103条命令exit0，698唯一C++/48目标、872 Python/36套＋6独立参考，9历史接受日志回放与1旧失败审计、SITL/Gazebo构建通过；暂存时发现的5处EOF空行已修订并重新冻结，最终必须以正在运行的本门干净qualification01为准。目前仍0飞行。
- qualification01现已通过：相同103条真实命令exit0，698 C++、872 Python＋6独立参考；clean/approved均true，9份历史回放与旧失败审计保持原判。固件ec20b8dfb05fb10bb605395db4360e3af1daf882a2187ccc06ad95865d8b35a5，冻结ca23e7b3f08da19e451aa8bdbe943afbf71b40c15b1f04a90cf035042e55d9ad。已明确启动本门最多9次运行器；实际尝试/接受以B/batch01/ledger.json为准，不能在完成前预填通过。

## RI03 完成记录（2026-10-24，最新）

- 状态：**passed，X单轴开发门**。9计划/9尝试/9起飞/9接受，9独立完整回放、6对共78项风险检查通过；无飞行失败/缺失/补飞/预算偏离。仅Iris SITL，不代表Z/XY/XYZ或实机通过。
- 初次协议源码：35aea2d198cc3ca2e1c82b0c800b1e105a5b2cac；飞前回放接线修订及实际全部九轮源码：ec486cdb9b7957620d3d5d531d9665ee2e3b7e25；独立结果提交：**101d79701b09c764f14ba2290add4a524d44cf3f**（7个明确文件）。结果提交不是飞行源码。
- qualification02：95条命令exit0，675唯一C++/48目标、799直接Python＋6独立double参考；SITL/Gazebo仅构建通过。3历史接受回放和1旧失败审计保持原判；收尾另7项结果序列化/保护测试exit0。
- 固件SHA-256：5a0dd562fa0f5555e833cf26915a7c6fd72dbbb3823722a15bce77e773bbb058。冻结966仓库/79外部资产，33递归子模块一致且内部干净；默认PID不变，生产只新增SITL MODE4/AXES1，Y/Z和rate PID、两DIV1及旧起飞管理关闭均真实核验。
- X RMSE三轮均值(m/s)：PID .03713879、R-STA .00814576、R-ISTA .00792461。R-ISTA对R-STA低2.7149%，但第三种子X更差1.8611%；宿主路径中位数均值高17.36%，不称全面胜出或显著性结论。
- 9轮同种子配对，81001–81003已消费；18份ULog、2528文件SHA索引保留。独立回放结果逐值/类型/谱一致，原始输入首尾指纹不变；完整参数恢复、无残留自有进程。rate→actuator约93.43%–94.10%为部分覆盖，不假称全链100%。
- 外部证据：/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI03/；报告：/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/RI03.md；摘要/指纹在regularized_ista/ri03/results。
- 所有离线构建/工具/资格及结果JSON导出失败均记录，未改判历史失败；MATLAB未重跑。当前分支research/ista-velocity-regularized，提交后工作区干净，领先跟踪分支3提交；**未push、未执行RI04或原R04/R05**。本次9次授权已全部消费，无剩余试飞授权。

## RI03 执行入口（2026-10-24，历史检查点）

- 用户仅授权RI03：新X门PID/R-STA/R-ISTA各3次，共最多9次；先冻结协议/源码和干净资格，首个安全/必需有效性失败立即停批，不补飞、不扩预算、不push、不进入RI04/旧R04/R05。
- 入口HEAD=e7fb67112e4cf605f5ddf362f120c320a64d2cf5，research/ista-velocity-regularized；工作区干净、33递归子模块匹配且内部干净。RI02已随后push，下方未push是历史收尾记录。
- 当时in_progress，飞行尝试/起飞/接受=0/0/0；新种子81001–81003全历史查重并登记，准确9轮已冻结。675个C++/789个Python及6项独立参考、3份旧X日志与1份旧失败审计通过；当时正在新干净源码取得资格，尚不能称飞行验收。
- RI03协议/源码提交：35aea2d198cc3ca2e1c82b0c800b1e105a5b2cac（35个明确文件，父e7fb67112e4cf605f5ddf362f120c320a64d2cf5），提交后工作区干净，未push。外部证据根目录 VELOCITY-RISTA-20261024/RI03；原失败记录保留。
- 飞前回放接线补丁/重新冻结提交：ec486cdb9b7957620d3d5d531d9665ee2e3b7e25（6个明确文件）。qualification01的95条命令通过但审查发现回放授权路径遗漏，不用于起飞；已补10项真实复制/分析入口负例，工具73项通过，正运行该干净新提交qualification02。仍0飞行，预算9不变、未push。

## RI02 完成记录（2026-10-24，历史；关闭准入等描述是当时状态）

- 状态：passed，仅离线接线/回归；MODE4生产准入仍关闭，默认PID。0新飞行/种子，不push、不执行RI03或旧R04/R05。
- 完整提交SHA：e7fb67112e4cf605f5ddf362f120c320a64d2cf5；父提交2f19cefc850ef4b77a8bcdc455aaec193f3da331，59个明确文件。分支research/ista-velocity-regularized，提交后工作区干净，33递归子模块匹配且内部干净；本地领先codev同名跟踪分支1个提交，未push。
- 完成MODE4请求/有效/暂存/拒绝及完整参数代次、保存重启接线；私有准入默认false、无生产writer，测试友元仅离线打开。MODE0/1/2/3及所有PARAM_DEFINE默认值不变。
- 新隐式保护保留候选nu参与当前理想输出，不以保护nu重算当前理想a；完整反馈/三轴验证后原子提交。Z/XYZ使用真实h隐式seed；HTE平移带sample/代次身份的已应用纠偏缓存；同sample重算和失败不重复积分、不虚增真实更新序号。
- qualification02：62条命令全exit0，43个真实目标609唯一C++用例（新92、既有517）；PID/R-STA/旧ESTA共24组2048步逐位回归，49152主样本＋384同sample重算。严格C++14和SITL构建通过，6项独立double参考通过。
- tools_attempt09：50条命令全exit0，348项Python（新73＋旧275）；36份历史ULog完整链回放，科学数值/类型和谱一致。另审计1份旧失败ULog完整文件及67333572字节精确前缀，不改判、不当新样本。新旧合计354项Python；源码首尾SHA一致。
- selection/status实际格式长度1018/1475B，均含topic名与NUL，小于1500；queue均8，实际uORB夹具128消息无丢样。ri_valid仅最终完整成功事务；失败第一次调用的全部候选不单独持久化，真实MODE4飞行日志吞吐未验证。
- 独立工具默认dry-run，execute硬拒绝；完整参数备份恢复用离线BSON及fake CLI验证，没有写真实EEPROM。原配置仍固定rate PID、DIV1、旧起飞管理关闭。
- 保留所有构建/夹具/描述比较失败及主动中断记录。6177文件外部SHA索引、原包30文件、79外部资产已复核；原R03的865资产中852未变，13个本阶段授权源码/测试变更逐项记录，旧冻结清单与旧判决不改。
- 固件SHA256：91bd5c08873d026481e46c837a4e3fc50c07ef2c4fe74a7204eac3a746b01386；入口HEAD＋指纹补丁构建，不是本结果提交的干净飞行资格。EEPROM前后06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc不变。
- 外部证据：/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI02/；报告：/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/RI02.md。收尾12份Python语法、4份JSON、25本地Markdown链接及全部6177证据指纹复核通过，diff检查exit0。
- 未执行：任何新飞行、真实MODE4完整飞行ULog、MATLAB/Simulink重跑、调参、板级CPU/实机、RI03及旧R04/R05。对象复跑仍是84完整轨迹（含6不可行反例）与18极小数域停止，不称全部收敛。

## RI02 执行入口（2026-10-24，历史）

用户本轮仅授权RI02离线保护/日志接线。入口HEAD=2f19cefc850ef4b77a8bcdc455aaec193f3da331，research/ista-velocity-regularized；工作区干净、33递归子模块匹配且内部干净。RI01已按随后请求push到codev同名分支，下方未push是历史阶段收尾记录。本次0飞行/种子，不push、不自动RI03/旧R04/R05；开始时尚未运行RI02测试，不能预填通过。

## RI01 完成记录（2026-10-24，历史）

- 状态：passed（仅独立内核/离线），本阶段不push、不进入RI02/旧R04/R05。
- 入口 research/ista-velocity-regularized / e8e38752499c12b9c39bb7dc95da58f27ff029d4，工作区干净，33递归子模块一致且内部干净；RI00已按用户随后请求push。新ri01_entry快照保留入口，v1/ri00_entry不覆盖。
- 新增独立C++14 RegularizedIstaVelocityControl，仅BUILD_TESTING。补偿p隐式关系、候选nu进入当前输出、独立提交、三轴隔离和密封事务通过；MODE4仍拒绝、实际固件8010行符号无新核，生产准入/参数/默认PID/模型/上游不变。
- verification03真实57条子命令全部exit0；38个目标517个唯一C++用例=36新核+481旧回归，6项Python独立oracle，SITL构建与严格C++14编译通过。3888单步、360边界/邻点、两组2048序列不重复算成测试用例。
- 独立对象720组单步，3990行保存MATLAB R-ISTA fixture；MATLAB/Simulink未运行。102轨迹559827有效更新：84条完整60s（含6条不可行限幅反例），18条零扰极小数值触发域拒绝，不能称全部收敛。最大双闭环速度差1.620864e-7m/s；固定h与变h/约束/噪声/滞后结论分列。
- tests_attempt01的链接/测试构造问题、verification01/02严格编译告警及rho浮点边界修复全部保留；最终verification03指纹绑定。8个尝试目录497文件SHA索引已归档，大数据外置。
- 外部证据：/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI01/；报告：/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/RI01.md。
- 固件SHA256：53f5e57b939b1bb393fedfad9dadc16bb6fa19dc3c7b45c822b6b39229098049，构建于入口HEAD+明确工作区补丁，非结果提交的干净飞行资格；EEPROM前后SHA不变。
- 实际新计划/尝试/起飞/接受=0/0/0/0，新种子0。新核真实sample去重、保护/HTE/seed/日志及数值域拒绝工程策略留RI02，未自动执行。
- RI01完整提交SHA：2f19cefc850ef4b77a8bcdc455aaec193f3da331（父提交e8e38752499c12b9c39bb7dc95da58f27ff029d4，80个明确文件）。提交后工作区干净，33递归子模块版本/内部状态不变；本地领先codev同名跟踪分支1个提交，未push。

历史更新：2026-10-23 当时状态为RI00离线审计通过并提交、未push、RI01未启动；不是当前状态。

## RI00 完成记录

- 入口 HEAD：a286e40ec8bfbb0500b1c24add18c1a98b908778；33递归子模块匹配且内部干净；原五份计划/入口保留纳入，v1未覆盖，另存ri00_entry。
- 最终证据audit02：2项原包CTest、12项新增Python测试、4896单步核对、90条独立对象轨迹，probe退出0；7980行是已有MATLAB CSV，不是本次MATLAB重跑。六条预定不可行限幅反例明确不收敛，不称跟踪成功。
- 数学：理想恒扰平衡s=0，不再是旧h*d；斜坡仍有epsilon及h相关偏差。HTE/seed/保护不能照搬R-STA，候选事务需加强；未继承Proper论文保证。
- 原包30文件指纹、865仓库与79外部冻结资产重新匹配；MODE4真实selector仍拒绝，生产控制/参数/模型/准入未变。
- 外部证据：/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261023/RI00/audit01、audit02，两者完整保留。
- 报告：/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/RI00.md；公式/接口与小证据在regularized_ista/ri00。
- 实际新尝试/起飞/接受=0/0/0，新种子0；未运行MATLAB、新PX4构建、生产整套回归或Gazebo。未push，未启动RI01/原R04/R05。
- RI00 完整提交 SHA：e8e38752499c12b9c39bb7dc95da58f27ff029d4（49个明确文件，父提交a286e40ec8bfbb0500b1c24add18c1a98b908778）。提交后工作区干净、生产路径差异为空、33子模块内部干净；50个Markdown目标及JSON/脚本语法/证据指纹检查通过。未push。

## RI00 执行入口（2026-10-23）

用户已明确仅授权 RI00。入口 HEAD a286e40ec8bfbb0500b1c24add18c1a98b908778，分支 research/ista-velocity-regularized；工作区原有五份计划/入口 Markdown 保留并纳入本阶段。33 递归子模块版本一致。已完成离线审计；新飞行/种子均0，不修改生产、不push、不启动后续阶段。下方创建时记录仅保留历史。

## 建分支时仓库与范围（历史，非最新状态）

- 仓库：`/home/yr/Desktop/Codev-autopilot`。
- 分支：`research/ista-velocity-regularized`。
- 创建基线/当前HEAD：`a286e40ec8bfbb0500b1c24add18c1a98b908778`，已验收R03结果；不是新R-ISTA实现或飞行提交。
- 原分支：`research/sta-velocity-regularized`，保持该提交和历史结果；没有删除重建/回退。
- 分支创建前工作区干净，33个递归子模块无增减/版本偏离；当前新增计划/入口文档尚未提交或push，不称“当前工作区干净”。
- 本专项仅PID、R-STA、R-ISTA参与新实验；旧ESTA只保留代码/历史与离线回归。原R04/R05暂停，后续由RI06/RI07另冻三算法协议，旧冻结包只读。
- 本轮仅规划，控制代码/参数/模型/日志实现未变；未构建、未运行算法单测/Matlab/仿真、未登记新种子、未创建实验批。

## 建分支时实际核对（历史）

1. Git现场核对并从指定完整SHA新建分支；HEAD未改变。没有提交、推送或启动RI00。
2. 阅读当前R03验收、R02保护/日志、旧计划共同规则与R04/R05内容，并核对源包补偿ISTA/通用隐式核/C++接口、参数和验证说明。
3. 在源包运行 `sha256sum --check SHA256SUMS.txt`：**29/29 OK，exit0**。这仅证明包内列出文件完整，不是算法回归/Matlab重跑/PX4适配通过。
4. 当前selector/元数据只到MODE3，MODE2仍拒绝；候选MODE4留RI00全链冲突审计，不在本轮开放。R-STA接口s=v−v_sp；包内e=v_sp−v，转换已列TODO待RI00正式审计。
5. 初次组合只读命令因工作目录下相对报告路径不存在exit2，已改真实路径重新读取；分支创建命令后的名称检索无匹配使组合exit1，随后独立核实新分支创建成功。不把这些检索当算法测试。
6. 收尾文档一致性校验实际exit0：三文档与plan/v1逐字节一致；8个阶段/8段完整提示词；36+54+200=290候选预算；旧三文档暂停入口、33子模块、基线与旧分支HEAD、Markdown链接全部核对；仓库仅5个Markdown文件改动，无控制代码变更。此为文档检查，不是算法测试或任何RI阶段通过。`git diff --check`亦exit0。

## 阶段状态

| 阶段 | 状态 | 新飞行候选 | 实际尝试/起飞/接受 | 源码/结果提交 |
|---|---|---:|---|---|
| 建分支与计划 | 纳入RI00明确范围提交 | 0 | 0/0/0 | 完整SHA见顶部RI00记录 |
| RI00 来源/接口审计 | passed（仅离线） | 0 | 0/0/0 | 完整SHA见顶部RI00记录 |
| RI01 独立内核 | passed，仅离线 | 0 | 0/0/0 | 完整SHA见顶部RI01记录 |
| RI02 保护与日志离线 | passed，仅离线 | 0 | 0/0/0 | e7fb67112e4cf605f5ddf362f120c320a64d2cf5 |
| RI03 X | passed，仅X/Iris开发门 | 9，已全部消费 | 9/9/9 | 源码ec486cdb9b7957620d3d5d531d9665ee2e3b7e25；结果101d79701b09c764f14ba2290add4a524d44cf3f |
| RI04 Z 原批（历史） | failed/needs_revision；原判保留 | 原9，3已尝试，旧6作废 | 3/3/2，1失败 | 源码74327418e18eafd421e18b48fe3964fdad63cfb5；结果50f354678fafb3fd4d4a09530e340f0eefa60f55 |
| RI04 HTE离线修复 | passed_offline_only，不代替Z飞行验收 | 0 | 0/0/0 | bb56d1414cc0e7e196995f9281a0306ca7f46964 |
| RI04 Z revision01 | passed，仅Z/Iris开发门 | 新9，已全部消费；历史总12 | 9/9/9；9回放/6对检查 | 源码a1c2046d94a6bbf061720385a5ad36110b1d0dc2；结果8578560847bd32efa17b5f45d3ec413c2961a927 |
| RI04 Z局部增益修正 | offline_candidate_only；未接生产/飞行 | 0 | 0/0/0 | 8ff776664b63bef1c630db8c625f095a028cfb6b |
| RI05 A/XY→B/XYZ | passed，固定参数开发 | 9+9；原18全部消费 | A 9/9/9；B 9/9/9；各9回放/6对通过 | A源码3e633a0d2aba1326d3f79b0033f59787cc479c44；B实际源码32a266f6162f1e09667ec92eeb0ad25abfee7ea7；最终结果见顶部 |
| RI06 公平调参/正式协议 | passed，已push | 36+18，全部消费 | 54/54/54 | bed13f0bc10029a278acfbad99b730e13b0f7e25；飞行源码见顶部RI06记录 |
| RI07 正式比较 | blocked_before_batch，存储不足 | 80+120，全部未尝试 | 0/0/0 | 阻塞审计提交见顶部；不是飞行资格 |
| 原R04/原R05 | paused，旧含ESTA清单不执行 | 不激活 | 本轮0/0/0 | 旧记录不改 |

RI03本次9次已全部消费，剩余飞行授权为0。创建时36+54+200=290是候选总量，不代表后续已获授权；RI03已登记并使用81001–81003。后续种子仍须全历史查重，不得复用本批、R03历史或正式预留种子。

## 下一步

RI06已通过；RI07因完整剩余存储预检不足，0次飞行后停止。先提供足够磁盘空间或明确替代存储位置，再处理现有图表工作区、完成正式执行适配和干净资格。不能通过缩减200清单、删历史或降低容量余量规避。原200正式任务全部未执行，不能用已有开发图表代替。

### RI04完成时的下一步（历史，保留）

若采用新增局部增益候选，必须先补新配置下的模块Z seed/HTE/限幅/起降接线验证，再另冻新的有限飞行批次与干净资格；不能用原九轮验收替代。候选模型通过不是R-ISTA飞行已胜出，也不授权自动执行RI05/RI06。

**RI04 Z revision01 已通过，RI03 X 已通过；RI05尚未启动，也未获本轮授权。** 当前停止，不再飞原批作废6轮或重跑新9轮。若后续明确启动RI05，须按XY→XYZ顺序分别冻结新清单/种子/预算，在各自干净源码取得资格；本次Z通过不代表XY/XYZ通过。原R04/R05暂停，不push、不实机。

后续每阶段记录完整源码与结果SHA、实际非零测试/退出码、计划/尝试/起飞/接受/缺失、原始ULog指纹、失败和参数恢复；不能在此预填通过。既有R-STA R03通过不代表R-ISTA已接入。

## 文件入口

- TODO：`/home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md`
- 提示词：`/home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_PROMPTS_CN.md`
- 仓库快照：`/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/regularized_ista/plan/v1/`
- 源包：`/home/yr/Desktop/STA-ISTA-MATLAB-PX4/`
- R03结论：`/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/R03_ACCEPTANCE_CN.md`
