# 速度环 R-ISTA 专项：实时进度

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
| RI04 Z | failed/needs_revision；首败停批 | 9，3已尝试，6停止 | 3/3/2，1失败、6未执行 | 源码74327418e18eafd421e18b48fe3964fdad63cfb5；结果50f354678fafb3fd4d4a09530e340f0eefa60f55 |
| RI04 HTE离线修复 | passed_offline_only，不代替Z飞行验收 | 0 | 0/0/0 | bb56d1414cc0e7e196995f9281a0306ca7f46964 |
| RI05 A/XY→B/XYZ | not_started/not_started | 9+9 | 0/0/0 | — |
| RI06 公平调参/正式协议 | deferred，待接入合格 | 36+18 | 0/0/0 | — |
| RI07 正式比较 | deferred，待RI06合格 | 80+120 | 0/0/0 | — |
| 原R04/原R05 | paused，旧含ESTA清单不执行 | 不激活 | 本轮0/0/0 | 旧记录不改 |

RI03本次9次已全部消费，剩余飞行授权为0。创建时36+54+200=290是候选总量，不代表后续已获授权；RI03已登记并使用81001–81003。后续种子仍须全历史查重，不得复用本批、R03历史或正式预留种子。

## 下一步

**HTE交接离线修复已通过，RI04飞行仍未验收**。当前不再运行原批剩余6轮；下一步须另获新有限批次授权并冻结验证协议，在新干净源码重新取得资格，不能把离线通过或旧样本当新飞行。RI05前置未满足，原R04/R05暂停，不push、不实机。

后续每阶段记录完整源码与结果SHA、实际非零测试/退出码、计划/尝试/起飞/接受/缺失、原始ULog指纹、失败和参数恢复；不能在此预填通过。既有R-STA R03通过不代表R-ISTA已接入。

## 文件入口

- TODO：`/home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_TODO_CN.md`
- 提示词：`/home/yr/Desktop/codev doc/plan/VELOCITY_RISTA_PROMPTS_CN.md`
- 仓库快照：`/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/regularized_ista/plan/v1/`
- 源包：`/home/yr/Desktop/STA-ISTA-MATLAB-PX4/`
- R03结论：`/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/R03_ACCEPTANCE_CN.md`
