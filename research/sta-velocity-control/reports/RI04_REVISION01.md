# RI04 revision01：R-ISTA Z 单轴验收报告

日期：2026-10-24。**passed，仅 Iris Gazebo SITL、固定参数 Z 开发门**。本批9计划/9尝试/9起飞/9接受/0失败/0缺失，9个独立进程回放一致，6对共78项开发风险检查通过。不是实机验收、正式留出试验或全轴验收；未push，未执行RI05或旧R04/R05。

## 1. 授权、版本与历史边界

用户明确授权新9次（PID/R-STA/R-ISTA各3），原RI04历史3次保留，旧未执行6次作废，总尝试上限12次。本批恰好用完新9次，没有补飞、换种子、调参、追加预算或放宽门槛。历史合计12尝试，旧1次失败仍在，不能称全部历史12次均成功。

- 分支：`research/ista-velocity-regularized`，仓库：`/home/yr/Desktop/Codev-autopilot`。
- 入口及已push的HTE修复：`bb56d1414cc0e7e196995f9281a0306ca7f46964`。入口工作区及33递归子模块干净。
- 本批协议/全部九轮飞行源码：**`a1c2046d94a6bbf061720385a5ad36110b1d0dc2`**，明确29文件提交。本轮生产、参数默认值、模型、上游均未改变；仅新授权/计划快照/运行分析与资格工具。
- 固件SHA-256：`0f3086306510311b69ee2ee8c6dd6f52412dd43c7d3f1436e725578dab6d7d62`。
- 干净qualification01：`9db3e23f349848337208f0f93a76212b410832c8754d64953068e8a28e2bcbe2`。
- 冻结清单：1049仓库资产、79外部资产、33递归子模块；SHA `21a6d96b25284ba5ddd5277e4cc05b8d1a7fb7735ac3e34f863a08d6a1a02a61`。
- 独立结果提交是本报告所在提交，提交后完整SHA写入外部实时进度；不能把结果提交当作飞行源码。可用 `git log -1 --format=%H -- research/sta-velocity-control/reports/RI04_REVISION01.md` 查询。

原失败报告 [RI04.md](RI04.md) 和 [HTE离线修复报告](RI04_HTE_FIX.md) 完全保留。旧3轮源码74327418e18eafd421e18b48fe3964fdad63cfb5、结果50f354678fafb3fd4d4a09530e340f0eefa60f55不改判、不混入新9轮。

## 2. 固定任务和配置

[明确授权](../regularized_ista/ri04_revision01/AUTHORIZATION_CN.md)、[冻结协议](../regularized_ista/ri04_revision01/PROTOCOL_CN.md)、[精确清单](../regularized_ista/ri04_revision01/manifest.json)、[本次计划快照](../regularized_ista/plan/ri04_revision01_entry/VELOCITY_RISTA_TODO_CN.md)。

MODE/AXES为PID 0/0、R-STA 3/4、R-ISTA 4/4。Z是本地NED向下速度轴；XY速度PID、原位置P、姿态/rate PID、两DIV1、旧实验起飞管理关闭。生产MODE4仍只允许已验收X/1和本次Z/4，3/7等其他掩码仍拒绝，默认PID未改。

127项完整参数与旧RI04逐项相同：Z lambda1/lambda2/epsilon/nu限/纠偏限为2/1/.02/4/6；PID Z P/I/D为4/2/0；HTE开启。没有加载源包高增益。原控制只输出m/s²纠偏，不套rate的g、不除质量、不重复FF。

仅使用项目 `./sitl/run.sh --headless --backend gazebo --model iris`、原empty_grey world和AX02软接触Iris。world SHA `09d9a334728b35a5ca0392e8751e3df5b8aea8b1d5019f8e850a4b0b8bc57b96`，模型SHA `fe9900329b47f3afb3f2aafac164af047a6feb0e676ea74e658ada5e887b5150`；插件、质量、惯量、估计器/滤波/land detector不变。

每轮重启，在首个完整自有日志后预热至少30s；起飞并一次目标交接到约2.5m、固定XY/yaw。在位置P和原有效速度FF之后叠加 `0.1*sin(2πt/8)*sin²(πt/32)` m/s 的32s Z小激励，90–92s完整观察，再降落上锁、完整尾窗和参数恢复。主窗32s、两个半窗各16s；未增加第二目标发布者。附加波形积分为零不代表真实位移严格回零，共同外部波形也不代表实际合成v_sp逐样本相同。

新种子82101–82103在全历史74091份JSON及源码/文档查重后登记，飞前再次查重。每块PID先行，次序PID/RSTA/RISTA、PID/RISTA/RSTA、PID/RSTA/RISTA；仅IMU显式播种，宿主调度及其他传感器不声称独立受控。

## 3. 实际逐轮结果

下表为主窗真实消费的 `v-v_sp` 时间加权速度RMSE，单位m/s；不是姿态角、位置或最大误差。

| 轮次 | 配对种子 | 算法 | X RMSE | Y RMSE | Z RMSE | 结果 |
|---|---:|---|---:|---:|---:|---|
| run001 | 82101 | PID | 0.00831317 | 0.00846078 | 0.00338444 | 接受 |
| run002 | 82101 | RSTA | 0.00893860 | 0.00792562 | 0.00123805 | 接受 |
| run003 | 82101 | RISTA | 0.00838531 | 0.00822741 | 0.00129487 | 接受 |
| run004 | 82102 | PID | 0.00860543 | 0.00763677 | 0.00399306 | 接受 |
| run005 | 82102 | RISTA | 0.00697274 | 0.00828707 | 0.00179298 | 接受 |
| run006 | 82102 | RSTA | 0.00832131 | 0.00708120 | 0.00168845 | 接受 |
| run007 | 82103 | PID | 0.00975251 | 0.00827055 | 0.00369757 | 接受 |
| run008 | 82103 | RSTA | 0.00967878 | 0.00837474 | 0.00137924 | 接受 |
| run009 | 82103 | RISTA | 0.00828083 | 0.00863899 | 0.00145102 | 接受 |

9轮均起飞、完成任务、降落上锁，完整参数恢复。6对候选对同种子PID，各13项主/半窗三轴速度、位置和yaw风险检查全部通过；开发验收只要求不越界，不要求获胜。

## 4. 结果与代价

每算法3轮算术均值，J为每轮三轴速度RMSE算术平均后再取三轮均值。高度列是全观察窗相对名义2.5m的RMSE，包含主动升降，不能与32s Z速度跟踪误差混为一谈。

| 算法 | X速度RMSE | Y速度RMSE | Z速度RMSE | J（m/s） | 高度RMSE（m） | yaw RMSE（rad） |
|---|---:|---:|---:|---:|---:|---:|
| PID | 0.00889037 | 0.00812270 | 0.00369169 | 0.00690159 | 0.052233 | 0.00014973 |
| RSTA | 0.00897956 | 0.00779385 | 0.00143525 | 0.00606955 | 0.051689 | 0.00015152 |
| RISTA | 0.00787963 | 0.00838449 | 0.00151296 | 0.00592569 | 0.051531 | 0.00015054 |

R-STA、R-ISTA的Z均值分别比PID低约61.1%、59.0%。但R-ISTA比R-STA的Z误差**高5.41%**，三个种子分别高4.59%、6.19%、5.20%，不能写成新隐式算法在Z跟踪上胜出。R-ISTA的J低约2.37%来自综合三轴结果；X/Y仍是PID且存在耦合和未完全控制的随机性，不应将其直接归因为“Z算法提高了所有轴”。

| 算法 | Z纠偏TV/s | Z归一化推力TV/s | Z共同0–7Hz RMS | 纠偏路径median/p95（µs） | 模块median/p95（µs） |
|---|---:|---:|---:|---:|---:|
| PID | 0.089546 | 0.006509 | 0.021945 | 1.002 / 2.224 | 8.260 / 17.238 |
| RSTA | 0.396512 | 0.028704 | 0.026696 | 2.176 / 4.730 | 9.228 / 20.319 |
| RISTA | 0.348575 | 0.025237 | 0.026676 | 2.727 / 5.783 | 9.806 / 20.544 |

TV按真实更新序列计算；共同频谱使用冻结100Hz ZOH→513tap/8Hz抗混叠→25Hz、裁边2.56s方案，原生谱独立保留。R-ISTA的Z纠偏TV/s比R-STA低12.09%，但两者都比PID高；这不是能耗结论。R-ISTA路径中位数的三轮均值比R-STA高25.33%。表中耗时是“逐轮分位数的均值”，不是合并样本分位数；只是宿主墙钟，不是板级CPU或WCET。完整p99/max、逐轴位置、半窗、谱及原始指标见 [summary.json](../regularized_ista/ri04_revision01/results/summary.json)。

只有3个配对开发种子，未做显著性/正式泛化结论，未为了让R-ISTA获胜重新调参。

## 5. HTE修复是否真正被覆盖

修复来自入口bb56：仅StateLimit裁剪下一nu而未改变本拍实际纠偏时，允许缓存已闭合真实输出。HTE用实际纠偏/FF计算平移，实际nu独立平移；CorrectionLimit、OutwardFreeze、Latched或下游约束仍拒绝缓存，不用理想nu反算当前输出，也不把受保护输出叫严格隐式解。

新分析器在完整飞行组件中核对缓存真假、sample身份、前一闭合缓存和非零HTE；旧分析器/历史结果不改。新负例走真实components/full_analysis接线，覆盖实际8/12ms、连续HTE、伪造输出/下游保护缓存、候选/应用nu混用和虚假strict标记。

| R-ISTA轮次 | StateLimit-only有效缓存样本 | 子集内非零HTE检查 | 子集外非零shift | 子集公式最大误差（m/s²） |
|---|---:|---:|---:|---:|
| run003 | 128 | 10534 | 1 | 0 |
| run005 | 154 | 10366 | 1 | 0 |
| run009 | 141 | 10406 | 1 | 0 |

起飞阶段确实触及nu限幅；不能因主激励窗约束占比为0就说整个起飞无限幅。子集外每轮1条边界保留并由完整生命周期检查处理，不冒称HTE子集公式覆盖全部发布/边界。候选p/a/nu和保护后应用值分别验证，原隐式残差和数值容差未放宽；该结果证明本批覆盖并通过所修交接，不证明任意工况均安全。

## 6. 日志、周期、恢复与独立回放

- 实测速度更新约99.99831–100.00172Hz；非假定250Hz，传感器/滤波和DIV不改。
- 9轮主激励窗约束占比均0，完整安全/故障/重试/时钟/reset、唯一目标和模式检查通过；原数值门槛不变。
- 位置控制输出精确配对覆盖均100%、差0；含边界最大空洞12–16ms。rate→actuator覆盖约93.43%–94.75%，仍是下游部分覆盖，不重建缺行、不声称全链100%。
- 每轮旧参数全量BSON精确恢复，最终EEPROM SHA为 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`；运行器退出0，无自有模拟器残留。
- 9个独立分析进程重新解码，全部JSON数值/类型/顺序及spectra字节与在线结果一致；另独立重算6对风险，原批全部输入前后指纹一致。回放不复制可复用授权，不增加飞行。
- [gate_pass](../regularized_ista/ri04_revision01/results/gate_pass.json)只在9接受/9回放/6对/恢复全部满足后生成。

## 7. 真实验证命令、退出码和失败保留

在仓库根，Python依赖沿用项目环境：
`PYTHONPATH=$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python`，构建器另将`.px4-python/bin`置于PATH。

| 操作 | 实际证据/结果 |
|---|---|
| protocol.py --prepare | exit0；准确9轮登记，初始outcomes全部unattempted |
| tools/verify_tools.py --output …/tools_attempt01 | 91真实Python，exit0（包含在后续总数，不重复累计） |
| freeze.py --write | exit0；1049/79/33冻结，后来只check、不覆盖 |
| test_protocol.py / test_freeze.py / test_receipt.py | 40/31/32，均exit0，属于整套回归子集 |
| verify.py --qualify --gate B --output …/B/qualification01 | **107条命令全部exit0，711唯一C++/48目标、912 Python/39套、6独立oracle** |
| 严格C++14、make px4_sitl_default -j4、DONT_RUN=1 make px4_sitl_default gazebo_iris -j4 | qualification中实际执行，exit0；build-only不是额外飞行 |
| runner.py --gate B（默认dry-run） | exit0，无参数/进程/飞行副作用 |
| runner.py --gate B --execute --source-head a1c2046d94a6bbf061720385a5ad36110b1d0dc2 --qualification …/B/qualification01/evidence.json | exit0；9尝试/9接受，无额外飞行 |
| tools/replay.py --gate B --output …/B/replay01 --finalize | exit0；9独立进程、6对共78项、输入/频谱一致 |
| results/verify.py --output …/result_checks02 | 15个结果层测试、旧1880/1609档案核验，exit0 |
| results/collect.py | exit0；完整指标/日志索引/结果/新档案索引 |

qualification还包括9历史接受完整回放、2失败边界审计、模型102轨迹559827更新。84条完整轨迹包含6条不可行限制反例，另18条极小数值域停止，不写成102条全部收敛；MATLAB保存fixture核对不等于本次MATLAB重跑。

准备期间的错误全部保留：[准备记录](../regularized_ista/ri04_revision01/PREPARATION_CN.md)。一次过早调用缺登记文件退出1；preflight01因旧夹具输出目录保护退出1；preflight02的107子命令均0，但收尾缺冻结清单使外层退出1。修正新工具入口顺序后，真正起飞用的是干净qualification01。收尾result_checks01的11单测通过，但旧索引list/dict格式不兼容使外层退出1；补4项负例后result_checks02的15项及两种索引核验通过。均不伪称通过，不改历史数据，不补飞。

## 8. 证据与后续边界

外部完整数据：`/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI04_REVISION01`。18份原始ULog见 [SHA索引](../regularized_ista/ri04_revision01/results/ulog_index.json)。新2695文件/9链接档案索引SHA为 `d282e292d140f05018f2b39102a69d622b99e1537506c8ebcbd828023ebf4bba`；[档案入口](../regularized_ista/ri04_revision01/results/archive_reference.json)。日志留在外部，仓库仅提交工具、配置、摘要、索引和报告。

旧RI04的1880文件/3链接和HTE修复的1609文件全部重新核验未变，结果收据见 [verification.json](../regularized_ista/ri04_revision01/results/verification.json)。

收尾只读复核exit0：新2695文件/9链接全部SHA与索引一致，结果JSON严格解析、3个结果脚本语法及35个报告/入口链接通过；freeze --check、diff --check、生产零差异和33子模块清洁检查通过。

RI04 Z开发门完成，既有RI03 X结论保持；RI05仍未启动、其飞行未授权。未实机、未运行MATLAB/Simulink、未执行旧ESTA新比较/调参/分频/正式留出，不push。后续如启动RI05，必须按XY→XYZ新门冻结清单、参数、种子和干净源码资格，不把本次Z通过视为全轴通过。
