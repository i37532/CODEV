# 速度环按轴消融：实时进度

更新：2026-10-08。**AX03固定参数开发矩阵通过**：H24/V24、48起降/接受、42配对、48独立回放；96份ULog指纹/解码通过。无失败/缺失/补飞/调参；未push、不自动AX04。
分支：research/sta-velocity-control。
规划核实基线：05a8ae3b3c00cf14dd575d87417296baa1996f69，已推送codev。
AX00计划/审计结果提交：**c5f240fb638fd94669d86c8f9e1c37d7c2efec38**，14个明确范围文件；AX01开工已核实与远端同步。
AX01源码/离线结果提交：**7e352a07a41df65fc56ca25b8a03b30c944bfb53**，30个明确范围文件；提交后工作区及33递归子模块干净，未push，领先已核实远端1提交。

| 阶段 | 状态 | 新飞行计划/实际 | 协议/源码SHA | 结果SHA |
|---|---|---|---|---|
| AX00 | passed（仅离线审计） | 0/0 | 审计源码基线05a8ae3b3c00cf14dd575d87417296baa1996f69 | c5f240fb638fd94669d86c8f9e1c37d7c2efec38 |
| AX01 | passed（仅离线） | 0/0 | 7e352a07a41df65fc56ca25b8a03b30c944bfb53 | 同一提交，无飞行结果提交 |
| AX02 | passed（工具/协议，仅离线） | 本阶段0/0；下一阶段48已冻结 | 9f514213a2d9b0d66674367c009e0d8886fe6c39 | ab9df703f837a3cb2b78a9295c5d4202e4f5a3ff |
| AX03 | passed（仅Iris开发准入，不保证性能优越） | 48/48；48起飞/接受，0失败/缺失，42配对 | 协议9f514213a2d9b0d66674367c009e0d8886fe6c39；实际干净飞行ab9df703f837a3cb2b78a9295c5d4202e4f5a3ff | 4d5e2a7f5dfee5b12615d8d07cbe3d3519f7bd55 |
| AX04 | not_started | 0/0；拟冻结320 | — | — |
| AX05 | not_started | 候选320/0，待AX04冻结 | — | — |

## AX03实际结果

- [AX03报告](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/AX03.md>)｜[只读复现/结果包](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/axis_ablation/ax03/README_CN.md>)。起点与48轮实际源码 **ab9df703f837a3cb2b78a9295c5d4202e4f5a3ff**，飞前/运行中干净；已为该HEAD重建固件，未回退或重建分支。
- 结果提交 **4d5e2a7f5dfee5b12615d8d07cbe3d3519f7bd55**，8个明确结果工具/文档文件，提交后工作区干净；未push。生产控制/参数/模型/AX02运行器及分析器/旧V08包未改。
- 唯一批次H51001–51003先24，再V51011–51013共24；各组PID先行，V第25轮是预算内安全门。48计划/48尝试/48真实起飞/48完成起降/48接受；H/V各21配对，共42。0失败/缺失/补飞/换种子/新增候选/新预算。种子现已使用，41001–41020仍隔离。
- 当前HEAD实际273 C++/658适用Python及SITL/Gazebo仅构建、6份旧H回放通过；新增结果工具12个不同Python用例通过（初次和最终重复运行不重复计数）。实际执行、独立回放、完整性检查均退出0；旧V08源码资格例外不计通过。
- 48独立完整回放指标/判定一致；1份JSON字节相同，47份仅cli_receipts.counts键顺序不同。96份启动/飞行ULog完整解码无corruption/dropout、真实模式/轴匹配；2782原始工件和134飞前工件指纹通过。下游匹配最低99.9889%、最大缺口20ms，不冒称所有下游/IMU无损。
- 水平XY相对PID：H的X/Y均值降低约33.5%/24.6%，V约27.4%/22.3%。含Z候选虽过冻结开发风险门，但XYZ的Z RMSE约为PID的3.24/3.43倍，Z纠偏TV/T约37.1/44.8倍；不称越多轴越好、全面胜出或正式显著性结论。
- 实测速度约100Hz，DIV1/rate PID；主窗限制比例0。含Z地面/ramp PID和有界接管保留，主窗phase3、XYZ正常pid_axes0。每轴参数跨组合不变；n=3/任务、仅IMU播种、PID先行和历史开发预算局限完整披露。
- 原始约5.5GiB数据：/home/yr/Desktop/codev doc/experiments/VELOCITY-AXIS-ABLATION-20261008/AX03/batch01；独立replay01、audit01和preflight01保留。EEPROM精确恢复06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，固件076c235017e34298fe57295126428de98266d569f6d60e21177e4399afbc1788，463仓库/7外部资产及33子模块一致，无残留仿真。
- AX04开发前置已满足，但未启动；正式候选320、旧V09正式200、ISTA/MATLAB/实机均未执行。本批预算耗尽，不能续跑；改善Z需另立有限调参和新验证协议，不改本批结果。
- 下方“新飞行0/AX03未启动/未push”等保留原时点含义；AX02在本阶段开始前已推送。

## AX02实际结果（历史时点）

- [AX02报告](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/AX02.md>)、[独立入口/精确清单](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/axis_ablation/ax02/README_CN.md>)。起点7e352a07a41df65fc56ca25b8a03b30c944bfb53；保留旧快照，新增ax02/plan_entry三文档。
- 协议/源码 **9f514213a2d9b0d66674367c009e0d8886fe6c39**（41文件）；在该干净提交复核通过。报告/证据结果 **ab9df703f837a3cb2b78a9295c5d4202e4f5a3ff**（5文件），提交后工作区干净；33递归子模块匹配且干净。未push。
- 独立运行器/八套完整固定参数/全掩码分析/默认dry-run。仅增加默认关闭的SITL任务8：旧固定yaw水平8字叠加≤.1m平滑升降；控制律/原保护/内环/上游/模型默认/V08包不改。
- H51001–51003先24项，再V51011–51013共24项，8组×2任务×3种子=48。第25项V-PID为预算内安全门；总42配对，必要失败即停，原始记录保留，不补飞/扩预算/调参。每轴增益跨组合固定，统一候选尚未获矩阵飞行资格。
- 最终干净复核273 C++/658适用Python，SITL及Gazebo DONT_RUN构建、6份旧H ULog只读回放通过，退出0。独立滞后对象144000步；真实Run/uORB V任务全8掩码64000回调+另PID8000回调，不是飞行证据。
- 36332份JSON完整查重，无目录排除；只豁免两份精确指纹设计记录，六种子仅注册未使用，41001–41020禁用。冻结463个仓库资产/7个外部插件依赖；execution SHA256 ba1ce4086e175eb30668c7ce3afcdbd734c31af5a5dc83adb4db7dfb45b7681a。
- 原始证据：/home/yr/Desktop/codev doc/experiments/VELOCITY-AXIS-ABLATION-20261008/AX02/clean01；134工件SHA核验通过。EEPROM前后06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc相同，ULog格式1475字节/队列8，无残留仿真。
- 早期Python路径、测试float编译告警、非布尔update标志检查缺口及修正全部披露。旧V08“生产源码自V07不变”断言仍保留并明确不适用，不计通过；旧日志不改判。
- 尝试/起飞/接受0/0/0；48项全部未执行，无MATLAB/实机/ISTA/调参/AX03/push。下一阶段须明确启动AX03、核对干净HEAD并重建其固件，再绑定精确48项凭据；本次不自动执行。
- 下方AX01/AX00和创建时“当前/未push/候选未登记”保留当时含义，不覆盖本段最新状态；AX01在本轮开工前已经推送。

## AX01实际结果（保留当时记录）

- 报告：[AX01.md](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/AX01.md>)；起点c5f240fb638fd94669d86c8f9e1c37d7c2efec38，保留旧快照并新增plan/ax01_entry。
- Y/XZ/YZ实际模块、选择器、混合PID、耦合保护、Z有界交接、HTE、消息元数据及离线脚本/轨迹解析已接通。MODE0/AXES0默认，MODE2拒绝；新2/5/6仅DIV1，旧PID/X/XY分频保留；未选中轴PID正常工作，不将未知轴映射X。
- 最终offline03实际261个不同C++、629个适用Python用例，命令退出0；PositionControl15/ControlMath9/Takeoff8/RateControl1，SITL和DONT_RUN Gazebo构建通过。两组2048步×5旧路径共20480样本对照；独立滞后对象48000步；实际Run/uORB夹具880条状态解析通过，非飞行ULog。
- 消息生成格式1475字节、队列8，生成参数元数据默认0/0/1通过。源码/原始日志/XML/固件指纹见仓库ax01/evidence.json；外部数据为 /home/yr/Desktop/codev doc/experiments/VELOCITY-AXIS-ABLATION-20261005/AX01/offline01–03。
- 原V08“生产源码自V07起全不变”检查在offline01失败，保留原判/原文件；仅在新AX验证器明确排除这一条不适用源码资格检查，未算通过。其余适用旧分析/日志测试通过；不称旧621用例全部通过，更不称AX源码具备V08冻结源码资格。
- 初次半NaN目标状态变更负例及修正、Makefile过滤器误用、测试double-promotion编译失败均记录。默认PID及已有1/3/4/7专用控制函数未改；上游/传感器/land detector/模型/rate/姿态/V08正式包零diff。
- EEPROM前后06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc相同。无飞行、无新种子、无调参、无实机/MATLAB；未执行AX02或正式留出，未push。
- 统一每轴候选只获离线支持，尚无新八配置飞行资格。下一阶段须另行AX02完整运行器/ULog分析链、精确任务/阈值/参数/模型资产、种子再查重和48项清单冻结；不能直接飞行或据此宣称性能优于PID。

## AX00实际结果（保留当时结论；当前实现见上）

- 报告：[AX00.md](</home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/reports/AX00.md>)。已核对分支、HEAD、工作区和33递归子模块；保留此前规划，新增plan/ax00_entry快照，不覆盖v1。
- 实际链接现有C++ selector/保护/内核，82条断言通过；112项源指纹/快照/参数/隔离证据检查通过，退出0。不是整套PX4单测或飞行通过。探针首次编译1、误调用127及修正均记录。
- 当前支持PID/X/XY/Z/XYZ，2/5/6在selector/保护拒绝；模块默认组装X不等于非法请求实际切X。新混合轴需补分派、接管、HTE和分析链。
- 统一候选为XY PID2.16/.48/.24、Z PID4/2/0，XY ESTA .5/.1/.4/.8、Z ESTA2/1/4/6。V08 ESTA文件中旧水平PID1.8/.4/.2不能带入混合组造成混杂；新候选未作为统一矩阵验收，AX00没有写入飞控。
- 36282份JSON种子检查，无候选历史冲突、无新非法JSON；1个历史空诊断明确例外。候选510xx/520xx仍未分配，41001–41020继续禁用，飞前须再查重。
- 生产src/msg/Tools/sitl/ROMFS/boards和V08冻结包无差异；EEPROM只读SHA06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc一致。没有本次live effective验证，模式依据现有代码及历史真实日志/参数证据。
- 本次新尝试/起飞/接受均0；未构建完整SITL、未运行历史231/621套件、未重解码ULog、未MATLAB、未飞行/实机。下一步仅可另行开始AX01离线实现，不自动执行。

## 创建时记录（以下为规划时状态，不覆盖当前结论）

- 原V08已完成并push；V09原200次未执行，协议不变。
- 当前代码已有PID及X/XY/Z/XYZ；Y/XZ/YZ需实现测试，不是假定现已可用。
- 采用固定每轴参数的消融，不按每组合重新调参；Z候选在V08水平参数下尚待统一验证。
- 默认候选开发48次、后续正式320次，均不是本次已授权飞行预算。种子510xx/520xx只是待查重候选，不是已注册/已验证全新。
- 本次未运行构建、控制单测、Gazebo、飞行、调参；仅文档核对不计入阶段通过。
- 新TODO/提示词/进度的仓库v1为创建时快照，后续新增快照，不以实时状态覆盖。
- 本次仅规划，不自动提交/push。后续明确启动AX00，完成后再按阶段推进。

## 执行后必须填写

起点与实际源码完整SHA；参数/模型/分析器/manifest指纹；真实测试数/命令/退出码；
尝试/起飞/接受/缺失；失败及是否停批；原始数据目录；协议/结果提交SHA；
依赖和未执行项；下一阶段准入。保留历史记录，不覆盖失败原判。
