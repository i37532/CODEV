# Proper-ISTA 速度环研究分阶段提示词

版本v1，2026-10-28。配套文件：`VELOCITY_PROPER_ISTA_TODO_CN.md` 和 `VELOCITY_PROPER_ISTA_STATUS_CN.md`。
每次只复制一个阶段。以下是未来执行提示词，**保存提示词不等于已经启动阶段或授权飞行**。本轮只建立计划，下一步建议PV00。

阶段命名PV避免与旧rate I阶段、速度R-ISTA RI阶段混淆。使用分支research/proper-ista-velocity，不覆盖旧MODE4。各阶段末提交是届时执行提示词的一部分，本次生成文档不自动commit/push。

## PV00 审计已有结果和问题复现

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_PROPER_ISTA_TODO_CN.md 的 PV00。
完整阅读本专项TODO、STATUS、PROMPTS及共同规则和本阶段前置报告；首次执行按阅读路线读取旧Proper探针/数值/日志/HTE经验。
核对 /home/yr/Desktop/Codev-autopilot 位于 research/proper-ista-velocity，记录HEAD、工作区、递归子模块；不回退、不清理、不夹带已有手册/图表。
只限项目Gazebo Iris SITL工程，保持原位置P、姿态/rate PID、两个DIV1、默认PID及已验收模型/起降链。保留速度MODE0/1/2/3/4含义，新模式先核对；不执行旧rate或RI/R阶段。
首先将新三文档plan/v1及专项入口纳入明确范围，不覆盖旧快照，不自动提交原有使用手册/图表。
读取PROPER_ISTA_PROBE协议/结果/原始停止证据、原Proper文献固定版本、实际rate核和独立double参考；保存来源SHA、公式编号、符号/单位/状态下标/输出与提交顺序，核对MODE5候选/参数/日志冲突。
先列出有限离线诊断矩阵和输出目录，再复现原144场景及针对性的滞后/噪声/周期单因素诊断。精确复现极小数停止输入，检查消减/中间溢出/下溢/次正规数及float/double敏感性；物理对象独立积分，不用虚拟状态自证。旧数据缺失如实报告，不把摘要当原始回放。
区分固定周期理想定理、代表8/12ms、真实日志时间回放、受限/滞后/噪声；不套来源高增益、不自动调飞行参数。给出数值等价修复假设、有效域、候选来源和PV01准入条件；如需改变控制律/加入正则化或conditioned变体，先报告新增范围。
仅离线审计/研究探针，不改生产控制律、参数默认、保护、上游或模型，不飞行。写reports/PV00.md及独立数学/数值接口契约。
记录真实命令、非零实际测试数、退出码、失败和未执行项；缺依赖标blocked，必需验证不通过记failed/needs_revision，不假通过。审查diff，明确文件列表提交本阶段成果并更新实时进度的完整SHA。不push、不自动下一阶段、不实机。
```

## PV01 独立速度内核

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_PROPER_ISTA_TODO_CN.md 的 PV01。
完整阅读本专项TODO、STATUS、PROMPTS及共同规则和本阶段前置报告；首次执行按阅读路线读取旧Proper探针/数值/日志/HTE经验。
核对 /home/yr/Desktop/Codev-autopilot 位于 research/proper-ista-velocity，记录HEAD、工作区、递归子模块；不回退、不清理、不夹带已有手册/图表。
只限项目Gazebo Iris SITL工程，保持原位置P、姿态/rate PID、两个DIV1、默认PID及已验收模型/起降链。保留速度MODE0/1/2/3/4含义，新模式先核对；不执行旧rate或RI/R阶段。
确认PV00通过。实现独立C++14 ProperIstaVelocityControl，s=v-v_sp，a/nu单位m/s²，仅输出纠偏，不用rate的g、不除质量、不重复FF；保留原ProperIstaRateControl和R-ISTA。
明确理想z/xi/nu_candidate与当拍输出、evaluate/commit/reset、三轴独立以及owner/轴/配置/reset代次/密封候选校验；新核无执行器准入。
覆盖三分支、精确正负边界与nextafter、非零nu、无效dt/参数/NaN/Inf、消减/上溢/下溢，以及跨对象/轴/陈旧/重复/篡改候选。数值修复必须有等价推导及常规域回归；不能用隐藏epsilon/死区/冲零掩盖错误。
用独立double单调求解和隐式残差、独立受扰对象验证；固定周期理论与变周期/滞后/噪声/限幅分列，完整复测旧极小数终点。参考不得复制生产同一解析式。未实际运行MATLAB要明确。
回归PID/R-STA/R-ISTA及适用旧核，实际非零测试和SITL构建，证明不可生效。写reports/PV01.md；不飞行。
记录真实命令、非零实际测试数、退出码、失败和未执行项；缺依赖标blocked，必需验证不通过记failed/needs_revision，不假通过。审查diff，明确文件列表提交本阶段成果并更新实时进度的完整SHA。不push、不自动下一阶段、不实机。
```

## PV02 保护 HTE 起降和日志工具

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_PROPER_ISTA_TODO_CN.md 的 PV02。
完整阅读本专项TODO、STATUS、PROMPTS及共同规则和本阶段前置报告；首次执行按阅读路线读取旧Proper探针/数值/日志/HTE经验。
核对 /home/yr/Desktop/Codev-autopilot 位于 research/proper-ista-velocity，记录HEAD、工作区、递归子模块；不回退、不清理、不夹带已有手册/图表。
只限项目Gazebo Iris SITL工程，保持原位置P、姿态/rate PID、两个DIV1、默认PID及已验收模型/起降链。保留速度MODE0/1/2/3/4含义，新模式先核对；不执行旧rate或RI/R阶段。
确认PV01通过，完整读RI04_HTE_FIX契约及RI07最终日志链。接线独立模式/参数/代次/requested/effective/pending/reject，保持生产准入关闭。
重新推导Proper理想候选与应用输出/nu关系、HTE平移、Z/XYZ seed和有界交接，不能照搬R系列公式。覆盖StateLimit后的HTE缓存、过期/代次/倾角/FF、不可行变换、饱和方向/反馈有效性和脱离限制；三轴整体裁决原子提交，同sample最多一次。
离线覆盖ground/ramp/假离地/取消/弹跳/超时、空中误判、EKF reset、半组NaN/纯加速度、退出重入、无效恢复、故障/termination、armed暂存取消/disarm/重启和跨起飞reset。
新增独立Proper诊断，不重定义旧ri_*；核对ULog长度/生成/注册/队列。独立工具默认dry-run，沿用相对预热/增量解析/白名单/同刻歧义/完整边界reset/落地尾窗与精确参数恢复；负例和可用历史日志完整回放，不改判历史。
PID/R-STA/R-ISTA各至少两组2048步逐样本回归，实际PositionControl/ControlMath/Takeoff/RateControl/模块/参数/分析测试与SITL构建。基于旧PID与离线证据固定PV03数值门槛和日志合同。
写reports/PV02.md，证明新模式仍不可接管；不飞行。
记录真实命令、非零实际测试数、退出码、失败和未执行项；缺依赖标blocked，必需验证不通过记failed/needs_revision，不假通过。审查diff，明确文件列表提交本阶段成果并更新实时进度的完整SHA。不push、不自动下一阶段、不实机。
```

## PV03 Proper X 单轴

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_PROPER_ISTA_TODO_CN.md 的 PV03。
完整阅读本专项TODO、STATUS、PROMPTS及共同规则和本阶段前置报告；首次执行按阅读路线读取旧Proper探针/数值/日志/HTE经验。
核对 /home/yr/Desktop/Codev-autopilot 位于 research/proper-ista-velocity，记录HEAD、工作区、递归子模块；不回退、不清理、不夹带已有手册/图表。
只限项目Gazebo Iris SITL工程，保持原位置P、姿态/rate PID、两个DIV1、默认PID及已验收模型/起降链。保留速度MODE0/1/2/3/4含义，新模式先核对；不执行旧rate或RI/R阶段。
确认PV02验收和数值安全/日志门槛冻结。仅开放新模式AXES1，X为NED北向；Y/Z速度PID、全部rate PID，其他Proper掩码拒绝。
先完成合成方向、真实周期/带姿态电机滞后对象及模式/保存重启/armed修改/disarm/reset/故障/termination全接线测试。保留合法XY目标、一次FF与唯一发布者。
固定来源参数、小幅零净位移X任务、固定yaw/约2.5m高度、主半窗和既定数值风险门槛。候选PID/R-STA/R-ISTA/Proper各3新配对轮，共12；全历史查重新种子，PID先行，准确顺序/有限预算/资产先提交。
取得同门干净源码和真实固件资格后沿用项目启动器执行，首个安全或必需有效性失败停批，不补飞/换种子/调参/扩预算。保存失败/未执行和完整参数恢复。
解码X误差、Y/Z非命令轴、位置/高度/yaw、理想和应用状态/输出、限制/时序。12接受/12独立回放/9对PID风险检查通过才验收，不要求Proper胜出。写reports/PV03.md，协议源码与结果分开提交。
记录真实命令、非零实际测试数、退出码、失败和未执行项；缺依赖标blocked，必需验证不通过记failed/needs_revision，不假通过。审查diff，明确文件列表提交本阶段成果并更新实时进度的完整SHA。不push、不自动下一阶段、不实机。
```

## PV04 Proper Z 单轴

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_PROPER_ISTA_TODO_CN.md 的 PV04。
完整阅读本专项TODO、STATUS、PROMPTS及共同规则和本阶段前置报告；首次执行按阅读路线读取旧Proper探针/数值/日志/HTE经验。
核对 /home/yr/Desktop/Codev-autopilot 位于 research/proper-ista-velocity，记录HEAD、工作区、递归子模块；不回退、不清理、不夹带已有手册/图表。
只限项目Gazebo Iris SITL工程，保持原位置P、姿态/rate PID、两个DIV1、默认PID及已验收模型/起降链。保留速度MODE0/1/2/3/4含义，新模式先核对；不执行旧rate或RI/R阶段。
确认PV03通过。保留X，仅新开放AXES4，XY速度PID，其他Proper掩码仍拒绝。先离线回归X，验证NED Z方向、独立状态、地面/ramp有界接管、HTE/StateLimit缓存、垂直优先、落地尾窗和跨起飞reset。
冻结XY保持、小幅平滑升降回原高度、唯一目标/一次FF、主半窗和既定数值门槛；任务Z目标跟踪与相对2.5m偏离分列。
候选四算法各3新配对轮共12，参数来源预定、PID先行，全历史查重种子和精确顺序/预算先提交；同门干净源码/固件资格后飞。
首败停批，不补飞/调参/改阈值/模型/land detector。完整记录HTE、交接、nu、限制、XY/yaw和恢复；12接受/12回放/9对PID风险检查通过才验收。
写reports/PV04.md，单独结果提交，不自动扩大XY。
记录真实命令、非零实际测试数、退出码、失败和未执行项；缺依赖标blocked，必需验证不通过记failed/needs_revision，不假通过。审查diff，明确文件列表提交本阶段成果并更新实时进度的完整SHA。不push、不自动下一阶段、不实机。
```

## PV05 Proper XY 和 XYZ

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_PROPER_ISTA_TODO_CN.md 的 PV05。
完整阅读本专项TODO、STATUS、PROMPTS及共同规则和本阶段前置报告；首次执行按阅读路线读取旧Proper探针/数值/日志/HTE经验。
核对 /home/yr/Desktop/Codev-autopilot 位于 research/proper-ista-velocity，记录HEAD、工作区、递归子模块；不回退、不清理、不夹带已有手册/图表。
只限项目Gazebo Iris SITL工程，保持原位置P、姿态/rate PID、两个DIV1、默认PID及已验收模型/起降链。保留速度MODE0/1/2/3/4含义，新模式先核对；不执行旧rate或RI/R阶段。
确认PV04通过，严格A→B，前门失败不得扩大。
A仅新AXES3：每轮含X/Y正负及固定yaw低速H轨迹窗口，Z速度PID；B仅A通过后开放AXES7，同水平8字叠加已定义小幅平滑升降V任务。2/5/6不开放。
回归1/4/3/7、独立nu/三轴原子提交、水平矢量/Z优先、HTE/有界起降、保存重启、armed暂存取消/disarm、故障/termination、跨起飞reset；全轴正常只算所选算法。
每门四算法各3个新配对种子=12，共24；参数跨门固定，准确任务/窗口/阈值/顺序/预算/资产先冻结并提交，各自干净源码取得资格后才飞。多窗口必须包含在预算内，不偷偷加起降。
首败停批，无补飞/调参/放宽门槛。每门12接受/12回放/9对PID风险检查，逐轴/位置/高度/yaw/输出TV与代价如实报告；不同版本分列，不拼旧成功。
写reports/PV05.md分列A/B，冻结合格完整XYZ配置和局限，单独结果提交。
记录真实命令、非零实际测试数、退出码、失败和未执行项；缺依赖标blocked，必需验证不通过记failed/needs_revision，不假通过。审查diff，明确文件列表提交本阶段成果并更新实时进度的完整SHA。不push、不自动下一阶段、不实机。
```

## PV06 等预算调参与正式协议

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_PROPER_ISTA_TODO_CN.md 的 PV06。
完整阅读本专项TODO、STATUS、PROMPTS及共同规则和本阶段前置报告；首次执行按阅读路线读取旧Proper探针/数值/日志/HTE经验。
核对 /home/yr/Desktop/Codev-autopilot 位于 research/proper-ista-velocity，记录HEAD、工作区、递归子模块；不回退、不清理、不夹带已有手册/图表。
只限项目Gazebo Iris SITL工程，保持原位置P、姿态/rate PID、两个DIV1、默认PID及已验收模型/起降链。保留速度MODE0/1/2/3/4含义，新模式先核对；不执行旧rate或RI/R阶段。
确认PV05 XYZ通过。仅PID/R-STA/R-ISTA/Proper四算法，原位置P/姿态/rate PID、DIV1、保护/模型/合格起降链固定；旧数据都是已见开发知识。
先提交新等额训练协议：每算法3候选×H/V×2训练种子=12，共48；一次选定后每算法H/V×3独立验证种子=6，共24，总72。固定参数范围/自由度、R系列epsilon处理、目标权重、失败惩罚、并列/无合格/早停、顺序与新种子。披露历史额外开发，不能单给落后算法追加机会或用验证反复换候选。
仅执行冻结72预算内训练/验证，首个安全/必需有效性失败停批，不补飞。Proper不带epsilon，不能把不同结构同lambda称纯Euler消融；默认不新增结构飞行组。
冻结候选正式H/V×四算法×20新配对块=160；Proper对其他三算法×两任务共6主比较。训练/验证/正式种子互斥，同组H/V保留块相关，用开发方差说明n/精度限制，正式前固定全部预算。
冻结时间加权XYZ RMSE/J、主/半窗及权重边界、Z/非命令轴、位置/高度/yaw、接受率/约束、真实更新TV、共同带宽/原生谱/宿主成本；落实配对CI、多重比较、重采样次数/种子、实用差与缺失选择偏差。不得要求Proper必须获胜。
保存源码/固件/参数/模型/world/插件/分析器/逐轮manifest指纹，正式outcomes全unattempted。写reports/PV06.md，报告下一阶段准确预算后停止，本阶段不运行正式留出。
记录真实命令、非零实际测试数、退出码、失败和未执行项；缺依赖标blocked，必需验证不通过记failed/needs_revision，不假通过。审查diff，明确文件列表提交本阶段成果并更新实时进度的完整SHA。不push、不自动下一阶段、不实机。
```

## PV07 正式比较与报告

```text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_PROPER_ISTA_TODO_CN.md 的 PV07。
完整阅读本专项TODO、STATUS、PROMPTS及共同规则和本阶段前置报告；首次执行按阅读路线读取旧Proper探针/数值/日志/HTE经验。
核对 /home/yr/Desktop/Codev-autopilot 位于 research/proper-ista-velocity，记录HEAD、工作区、递归子模块；不回退、不清理、不夹带已有手册/图表。
只限项目Gazebo Iris SITL工程，保持原位置P、姿态/rate PID、两个DIV1、默认PID及已验收模型/起降链。保留速度MODE0/1/2/3/4含义，新模式先核对；不执行旧rate或RI/R阶段。
确认PV06通过，完整读最终正式协议；核对冻结源码/固件/工作区/子模块/模型/参数/分析器指纹。仅执行最终明确清单，候选160，不扩展旧RI07/AX/V09、分频、其他变体或实机。
按预注册任务门/配对块/平衡顺序执行PID/R-STA/R-ISTA/Proper，同源码/模型/外环/DIV1。每轮重启、相对预热、完整备份恢复，核对真实模式/轴/接管/目标与更新序列。
首个安全/必需有效性失败立即停批，保留所有尝试/无效/未起飞/未执行；不补飞、换种子、改参数/规则/阈值或扩样。性能没有赢不等于无效。
实际解码全部ULog、独立回放与指纹和统计复算，按预注册时间窗/配对CI/多重比较/缺失规则；报告逐轴/J、位置/高度/yaw、理想/应用状态和输出、限制/接受率、TV/谱/宿主成本及实际n。失败不填0，不挑有利样本，不把工程保护结果当严格隐式理论。
大型数据外置，仓库保存配置/路径/SHA索引、指标/图表/复现入口。写reports/PV07.md和简明中文总结，明确预算偏离与缺失，不足清单不能称全矩阵通过；单独结果提交并停止。
记录真实命令、非零实际测试数、退出码、失败和未执行项；缺依赖标blocked，必需验证不通过记failed/needs_revision，不假通过。审查diff，明确文件列表提交本阶段成果并更新实时进度的完整SHA。不push、不自动下一阶段、不实机。
```
