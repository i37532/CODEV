# 速度环正则化显式 STA：分阶段提示词

创建日期：2026-10-16。
配套：[TODO/技术约定/共同规则](VELOCITY_STA_REGULARIZED_TODO_CN.md)｜[实时进度](VELOCITY_STA_REGULARIZED_STATUS_CN.md)。

一次复制一个阶段。新分支已从 AX05 结果建立，不重新从 main 创建。
本次建文档不执行下列任何提示词；所有阶段均未开始。R00–R02 不飞行，R03–R05 只执行事前冻结的有限预算，不意味着全阶段自动授权。

## R00 — 来源、公式与接口审计

~~~text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_REGULARIZED_TODO_CN.md 的 R00。
完整读取专项三文档、旧速度计划全文及共同规则、主/AX实时进度，并按专项第4节读指定前置报告、日志审计、旧研究经验和新算法包；不把历史状态当现状。
核对 /home/yr/Desktop/Codev-autopilot 位于 research/sta-velocity-regularized，记录HEAD、工作区、递归子模块；分支已从0a5796c3ed69d2e415696cf2450fbde74d56e6ea建立，不回退、不清理、不删除重建。
核实 /home/yr/Desktop/STA-ISTA-MATLAB-PX4 的文件/模型/公式/参数/测试来源与SHA；包接口基于旧main-v2_gps，不当作当前PX4接线证明。保留初始plan/v1，新增r00_entry快照；提交仓库内尚未提交的规划快照，外部三份同步维护但不由主仓库直接跟踪，不覆盖源包。
统一s=v-v_sp、epsilon(m/s)、a_sta/nu(m/s²)、lambda2(m/s³)，旧nu算输出后一次提交。推导层内/层外与边界，复核5ms包参数到约10ms实测PX4的风险；用独立可运行探针验证局部离散模型，不把它当完整飞机稳定证明。
冻结旧PID/ESTA完整参数来源，提出epsilon数值域与离线候选；不加载包内高增益Z、-lambda*v、总加速度裁剪或PWM映射。
审计独立模式/参数名，MODE0/1不变、MODE2保留拒绝；检查HTE/Z/XYZ/XZ-YZ四处非线性、配置same/代次、强候选校验、原子提交、时间与日志规则。列出R01/R02准确改动与回归范围。
本阶段仅离线审计，不改生产控制/参数/模型，不飞行、不ISTA。记录实际检查/测试数、命令/退出码、失败和未执行MATLAB等事项，不能把旧CSV或前次测试算成本次通过。
写research/sta-velocity-control/reports/R00.md，审查明确文件列表提交，核对完整SHA并更新本专项外部进度。不push、不执行R01。
~~~

## R01 — 独立新内核，不接执行器

~~~text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_REGULARIZED_TODO_CN.md 的 R01。
完整读专项三文档/共同规则与R00报告，确认前置通过；核对 /home/yr/Desktop/Codev-autopilot 的 research/sta-velocity-regularized 分支、HEAD、工作区和递归子模块，不回退或清理。
实现独立命名C++14正则化显式STA纯核。s=v-v_sp，rho=sat(s/epsilon)，Psi=sqrt(max(abs(s),epsilon))*rho；a_sta=-lambda1*Psi+nu_old，nu_candidate=nu_old-h*lambda2*rho。纯核不重复加FF，不移植ISTA、rate g、质量或电机映射。
保留原PID/硬sign ESTA路径与默认值。epsilon有限且严格正，采用有推导的数值稳定分段式；evaluate/commit/reset、三轴状态与强owner/axis/revision/payload校验明确。
测试层内/层外、±epsilon边界与nextafter邻点、正负/零/非零nu、异常dt/参数/输入、极小epsilon、溢出/下溢，以及重复/跨轴/跨对象/reset回同值/epsilon-only修改后的陈旧候选拒绝。
用独立双精度参考、性质测试及独立ZOH对象核对；覆盖恒定/斜坡扰动、变化目标、一次非零FF、噪声、约束与姿态/电机滞后。固定周期理论与实测变步长健壮性分开；记录离线候选搜索预算并冻结首轮epsilon。
回归旧速度PID/ESTA及适用rate内核，构建SITL并证明新核无实际可生效输出路径。本阶段不飞行、不修改上游/模型，未执行MATLAB如实记录。
写reports/R01.md，记录真实非零测试数、命令/退出码、失败和未执行项；审查明确范围提交，更新外部进度完整SHA。不push、不执行R02。
~~~

## R02 — 公共保护、交接、HTE 和日志，先离线

~~~text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_REGULARIZED_TODO_CN.md 的 R02。
完整读专项三文档/共同规则及R00/R01、必要的V04最终日志规范/V07/AX01报告；确认前置，核对研究分支research/sta-velocity-regularized、HEAD、工作区和子模块。
按审计确定的独立标识接线新R-STA配置与日志，但生产入口仍拒绝实际生效，只有离线夹具可访问；PID/旧ESTA含义不变、MODE2仍拒绝。epsilon/variant进入有效性、same比较、armed暂存取消、disarm生效、保存重启和代次。
同步HTE当前纠偏、Z/XYZ/XZ-YZ接管seed的非线性定义，测试非零s/nu/FF、倾斜、HTE改变下的有界连续性。保留旧路径浮点顺序；不只是替换数学内核。
保持纠偏限幅后一次FF、原推力/倾角/Z优先约束；三轴独立和原子提交，同sample最多一次，未选PID轴正常运行。覆盖NaN XY配对、起飞取消/接触/弹跳/超时、测量恢复/EKF reset、退出重入、故障latch/termination和同帧failsafe二次update。
新增必要算法版本/epsilon/候选与应用状态日志，区分推力代理和实际加速度；核实ULog格式长度、生成、队列、双时钟与更新号。保留已修正白名单/同刻歧义/reset边界规则，禁止通用去重。
建立独立regularized_sta默认dry-run运行/分析入口及完整参数备份恢复；测试错模式/轴/内环/时间/缺样/未接管负例，旧日志只读回放不改判，旧脚本默认目标不变。
至少两组各2048步固定序列回归PID/旧ESTA及既有掩码，执行实际非零PositionControl/ControlMath/Takeoff/RateControl和日志测试并构建。本阶段0飞行，新算法仍不可实际接管。
写reports/R02.md，记录真实测试、退出码、未执行项和R03准入缺项；审查明确范围提交，更新完整SHA。不push、不执行R03。
~~~

## R03 — X → Z → XY → XYZ 固定形式开发验证

~~~text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_REGULARIZED_TODO_CN.md 的 R03。
完整读专项三文档/共同规则、R00–R02及AX05报告，确认前置；核对research/sta-velocity-regularized、HEAD、工作区/子模块和真实模型/参数。
本阶段候选总预算36：X、Z、XY、XYZ四门，每门PID/旧ESTA/R-STA各3次，共9次；每门3个全新配对种子，不同门互斥。先冻结准确清单/波形/窗口/参数/epsilon/安全及日志门槛/顺序/停止规则并提交，不能以候选预算代替manifest。
先完成该门离线接管/切换回归，再逐门开放新模式AXES1→4→3→7；前门全部通过才扩大。2/5/6继续明确拒绝新算法，旧ESTA能力保留。每门首个PID是预算内安全门，不增加额外先导。
固定旧与新STA同lambda/nu及纠偏限制，只改正则化；每轴epsilon跨组合不变。原位置P/姿态/rate PID、速度DIV1、原HTE/FF/保护/合格软接触模型保持，不照搬包内高增益、不飞行搜索参数。
沿用项目Iris Gazebo启动器，唯一目标源、每轮重启预热、完整参数备份恢复；真实日志核对rate PID、mode/axes、接管阶段、实际PID计算轴和更新序列。
记录逐轴速度/位置/Z/yaw、偏差/方差/RMSE、nu/HTE/限制、真实输出TV及共同带宽/原生频谱，独立完整ULog回放与指纹核对。共同外部轨迹不等于实际v_sp逐样本相同。
首个安全或必需有效性失败停止本批并保留未执行项，不补飞/换种子/改参数/放宽门槛；性能未赢按冻结开发风险门处理。需新批或调参时报告新范围和准确预算，不解释为无限重试。
写reports/R03.md，分列A/B/C/D及各门源码/协议/结果SHA、真实测试/退出码、计划/尝试/起飞/接受/缺失；不足36不能称四门完成，不混源码拼重复。结果另提交并更新进度，不push、不执行R04。
~~~

## R04 — 公平调参与正式协议，不运行正式留出

~~~text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_REGULARIZED_TODO_CN.md 的 R04。
完整读专项三文档/共同规则、R03、AX05和V08报告；确认四门通过，核对research/sta-velocity-regularized分支、HEAD、工作区和子模块。
分开两类研究：A为XYZ旧ESTA/R-STA同lambda/限制/保护及R03固定epsilon的数学形式对比；B为XYZ PID/旧ESTA/R-STA各自调参。不能把B调优结果当只改公式；旧数据只作开发知识。
先冻结并提交等额训练协议：每算法3候选×2场景×2种子=12，三算法36；选中各1候选后2场景×3独立种子=6，三算法18，总54。固定范围/候选生成/权重/失败惩罚/并列与早停/顺序/种子，披露历史额外预算。
只执行准确预算内训练与验证；失败消耗额度，不给落后算法额外机会，不反复使用验证集挑下一候选。位置P/姿态/rate PID、DIV1、模型/传感器/FF/保护保持，只搜索被批准的速度增益与epsilon。
正式候选A为2算法×H/V×20新配对块=80，B为3算法×H/V×20新配对块=120，总200；A/B种子互斥、组内同块跨H/V，开发/训练/验证/正式互斥。全历史查重，不占用V09的41001–41020及旧AX种子。
依据开发数据说明n与配对精度不确定性，在正式前固定准确预算。固定时间加权逐轴RMSE/J、Z与位置误差、真实更新TV、频谱/成本、接受率、8个候选主比较的配对CI/多重比较/重采样和缺失规则，不预设新算法获胜。
保存源码/固件/模型/world/插件/完整参数/分析器/manifest指纹，正式outcomes均unattempted。若XYZ前置或训练/验证不合格则报告needs_revision，不静默改为XY。
写reports/R04.md，记录真实测试、命令/退出码、尝试/失败/未执行和下一阶段准确预算；区分训练协议、选参/正式协议及结果提交，更新完整SHA。本阶段不跑正式留出、不push、不执行R05。
~~~

## R05 — 新正式对比与报告

~~~text
请仅执行 /home/yr/Desktop/codev doc/plan/VELOCITY_STA_REGULARIZED_TODO_CN.md 的 R05。
完整读专项三文档/共同规则、R03/R04报告及正式协议；核对research/sta-velocity-regularized、冻结干净源码/固件、子模块、模型、参数、分析器和manifest指纹。
仅执行R04已准确冻结并具备资格的正式清单，候选A80+B120=200；不扩展旧320轮消融、V09、分频、ISTA或实机。
严格按组/任务门/顺序运行，每轮重启预热、备份恢复；位置P/姿态/rate PID及DIV1保持，真实mode/axes/接管阶段必须与日志一致。首个安全或必需有效性失败停批，不补飞、改阈值、调参、换种子或扩预算。
真实解码全部ULog、独立回放及指纹核对，按预注册窗口和真实消费目标计算逐轴/J/位置/高度/yaw、偏差与方差、TV/频谱、限制/接受率及宿主成本。
按预注册配对块/CI/多重比较/缺失方法报告实际n，失败不填0，不把高频采样当独立重复；所有尝试/失败/无效/未执行保留。TV不是能耗，宿主耗时不是板级CPU，不能把SITL外推为实机通过。
大型日志外置；仓库保存完整配置、SHA索引、metrics、图表/简明中文总结和可复现分析入口。写reports/R05.md，明确A/B实际计划/尝试/接受、预算偏离与未完成项，不足预算不称全矩阵完成。
审查明确范围结果提交、核对完整SHA并更新专项进度。不push，不自动启动其他研究。
~~~

## 通用停止语义

以上提示词不要求每轮重复询问起飞，但只覆盖被启动阶段的已冻结清单。修订若超出范围/预算或需要上游改动，先报告；没有新授权不自动扩展。依赖缺失为blocked，检查失败为failed/needs_revision，性能不胜出是科学结果而非必须“修到赢”。
