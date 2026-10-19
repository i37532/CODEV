# R03 revision04：新36轮逐门验证

2026-10-19。当前 **A/X门通过**，B/Z正在离线准备，B/C/D均未飞行；**不代表完整R03通过**。下方飞前记录保留，实际执行结果在后续各节。

## 范围与预算

用户在总51次预算提案后授权：“继续，后面不用我同意，一直到R03验收为止”。
本版只执行新36项，R03累计上限 **51＝历史15＋新36**；保留历史14起飞、12接受、3失败/无效，不拼入新门。
首个安全、必需有效性、开发风险或清理失败停止当批；不补飞、换种子、调参、放宽阈值或自动扩大预算。
范围内修复和逐门推进无需再次询问，但本版不自动执行R04/R05或实机部署。

仓库为 `/home/yr/Desktop/Codev-autopilot`，分支 `research/sta-velocity-regularized`；入口完整HEAD：
`62e4fb00a11d68ee4fa2a8e69b677b7699ced171`。入口工作区干净、33个递归子模块版本与工作区正常；没有回退或清理已有历史。

| 门 | 新算法轴 | 配对种子 | 本门准确次数 | 开始条件 |
|---|---|---|---:|---|
| A | X / AXES=1 | 71201–71203 | 9 | 干净源码资格通过 |
| B | Z / AXES=4 | 71211–71213 | 9 | A的9接受、6配对和9独立回放通过 |
| C | XY / AXES=3 | 71221–71223 | 9 | B同样通过 |
| D | XYZ / AXES=7 | 71231–71233 | 9 | C同样通过 |

每门PID、硬sign ESTA和R-STA各3轮，按准确manifest顺序。只有完整新36轮与逐门检查通过才验收R03。
旧revision03的run008和29个未执行项不续跑，旧失败不改判。源码、固件及分析器的实际资格由各门新提交绑定，不使用旧资格代替。

## 不变项与本版工具接线

限定项目启动器下Gazebo Classic Iris SITL。原位置P、姿态及rate PID、速度DIV1、全部127项参数与epsilon、目标波形/窗口、模型/插件、数值安全及科学门槛保持revision03。
A门生产控制路径与入口逐字一致，新算法仍仅开放X；后门只在前置验收后开放相应生产准入并回归。

新版运行器直接使用已冻结的 `r03_prearm04`：从warmup开始持续解析同一owned reader，prearm再读一次捕获的尾部；仍在选取reference后读取CLI时间，执行原0–500ms新鲜度判据。
完整历史、reset、同刻匹配歧义及128MiB限制不变。新逐段时序收据用于可复核证据，不将离线速度当在线通过保证。
原prearm04离线修复与全部旧冻结版本只读保留。

## 已完成的飞前检查

- 新协议64项离线测试通过，退出0；初轮夹具mock范围错误及authority文案修订在外部开发记录保留，未变科学参数/种子/门槛。
- 首次新种子查重57,587份JSON，注册后复查57,593份，无冲突或非法JSON。只豁免本版4份准确SHA登记，无旧种子迁移或目录豁免；运行前仍须复查。
- 新运行器45项离线测试通过，默认dry-run退出0；飞行主体与revision03保持一致，预算/历史绑定与prearm04接线更新。
- 新分析器48项、独立回放38项和版本边界审计17项通过，退出0。合计212个分项Python用例；后续统一验证会重跑这些用例，不能重复相加。独立review02确认8份相关源码首尾SHA保持。
- 分析器以真实factory产生的合成ULog收据覆盖连续预热、一次prearm尾读、500ms精确边界、无文件/半header/尚无姿态、CLI时间尚未出现，以及后续多topic/多read形状。完整真实飞行和归档回放仍待执行；夹具不算物理飞行。
- 离线开发失败全部保留：分析夹具复用publish_seq、分析器最初误绑定未封口heading函数、测试误跟踪原函数global而非实际local import，以及回放夹具缺少新收据/第三历史批hash合约。均在冻结前修订；未改变原控制、阈值或旧判。最终显式绑定实际原 `v04_live_clock09.replay`。
- 初始可用磁盘约65GiB、tmpfs约7.4GiB，未删除日志；每门、每轮重新检查现场余量。
- EEPROM预期SHA-256：`06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`。文件指纹不等于新飞行实际生效参数。

上述分项不是飞行验收。提交前统一验证已完成：`r03_revision04/verify.py --gate A --output .../R03_revision04/A/verification01`，退出0，46条命令全0；475个不同C++、1245个Python用例通过，32768对旧路径主样本及256对同sample重算保持一致。SITL与DONT_RUN Gazebo构建通过，旧完整ULog按runner-first/analyzer-first两种导入顺序只读诊断一致，原失败不改判。输入指纹、33子模块及EEPROM保持，新飞行0。

另新增版本目录外只读结果汇总工具及18项独立测试，退出0（不包含在1245中）；缺账本保持unknown/pending，仅已有gate_pass并由原replay完整复核一致才显示通过，不生成验收收据。根审查修正了初版误写的回放路径，实际应为 `replay01/summary.json`；负例覆盖错误文件名与错误计数类型。A门冻结660个仓库资产，`freeze.py --gate A --check`退出0，生产路径和旧树无改动。

该提交前验证不生成可飞资格，不能代替之后干净提交上的重构建与资格。实际提交SHA、逐门尝试/起飞/接受/回放与结果将在发生后追加；未执行项不得填通过。

外部数据根：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision04`。
协议证据为 `offline_protocol01/evidence.json`，SHA-256：
`aa6691744b6650f0f6e5e662090a8dbbb3fff0168331c0394c08f968bcaf1d6f`。
运行器分项日志为 `A/development_checks/runner01.log`、`runner_dryrun01.log`。

飞前记录当时新尝试/起飞/接受为0、36项未执行；实际计数以下方新结果为准。未执行MATLAB、新ISTA实验、实机、R04或R05。

## A门：真实九轮与独立回放通过

协议/飞行源码：`d6a80776b478adbbbe03a1967140d55c62bd618b`；固件SHA-256：
`50b747719dff4905ea1ed80f23897880e8f12176fb4db6b747701fe4214f71f1`。
干净 `qualification01` 再次实际完成46命令、475不同C++/1245 Python及32768+256逐样本回归，全部退出0。
资格approved=true、clean=true；资格中的new_flights=0只描述飞前，不能代替之后飞行计数。

`runner.py --gate A --execute --source-head d6a80776b478adbbbe03a1967140d55c62bd618b --qualification .../A/qualification01/evidence.json`
退出0：**9计划、9尝试、9起飞、9完整降落上锁、9接受、0失败、0缺失**。
三种算法各3轮，六项同种子STA对PID风险检查全部通过。每轮参数精确恢复、无残留模拟器，现场EEPROM仍为原指纹。
前三算法首个配对块以及其余两块没有补飞、改参数或改阈值。

`replay.py --gate A --output .../A/replay01 --finalize` 退出0：九个独立分析进程均退出0，
全部metrics值/类型/列表顺序一致、频谱SHA一致；原始整批文件指纹保持，独立重算六项配对决定一致。
`gate_pass.json` 已生成并由只读摘要再次完整核验。原15次历史仍单独保留。
R03当前累计24尝试、23实际起飞、21接受、3历史失败/无效；新矩阵9接受、剩27项，预算不变51。

以下为本门32秒主窗、每算法n=3的描述性均值。速度RMSE单位m/s，J是每轮三轴RMSE算术平均；X纠偏TV/T为m/s³，不是能耗。

| 算法 | X RMSE | Y RMSE | Z RMSE | J | X纠偏TV/T |
|---|---:|---:|---:|---:|---:|
| PID | .036241 | .008024 | .002592 | .015619 | .119338 |
| ESTA | .009987 | .007802 | .002632 | .006807 | .197844 |
| R-STA | .009439 | .007896 | .002563 | .006633 | .140294 |

本次X任务中R-STA的X误差与X输出变化量均小于硬sign ESTA，但Y误差不是更低，X输出变化量仍高于PID。
这是3个开发配对块的结果，不作统计显著、全轴优势或实机结论。预解锁每轮具体时序见各metrics的prearm_preparation；不拿单轮20ms推断所有运行时延。

| 证据（相对本版外部根） | SHA-256 |
|---|---|
| A/qualification01/evidence.json | 125a08ea3ce3848e665fa542876a82f52b50984781056ec1bdc35865fb8c68f4 |
| A/batch01/ledger.json | 9cd60d44d94c7ca8334647dbb7a5963709e75de861c45ef3546c6ef2afcb7a10 |
| A/batch01/journal.jsonl | 23c41181632b59a3a5d1f3ab35f58f7ec36be34530f8136e1c8bd3a498050a6b |
| A/replay01/summary.json | b1ec614842f397d5e50f872378222442f8c5d5596a536f9379ea5d4385027d44 |
| A/gate_pass.json | 6e0498bf52c69239f13b294ce9059473827af8ec4e1b0595ef8dc2ccf659e8d2 |

完整逐轮结果、18份归档ULog指纹与指标入口见 `regularized_sta/results/r03_revision04_A.json`；大型日志仍外置。
本结果提交只记录A，不开放B；后续须另行应用Z生产准入和测试、冻结B并在干净提交重新资格，无需用户重复授权。

## B门飞前准备（尚未飞行）

A结果提交为 `155807308d313494187ce36ca1edd5bf87ebd7fd`。只有A九轮及独立回放已通过后，才应用此前外部草稿：
唯一生产逻辑改动为SITL的MODE3准入从AXES1累计为1/4；MODE2及2/3/5/6/7仍拒绝。
参数文件只改说明文字，不改变数值/default；XY继续速度PID，全部rate继续PID。

新增Z真实生产准入测试不调用测试专用admit：覆盖正负目标、FF一次、8/12ms非均匀sample、仅XY PID、
地面/ramp/单帧有界交接/空中/接触/重入、状态与参数暂存取消/disarm/BSON重载、原子故障与同sample、真实HTE消息。
现有X测试和离线全轴测试保留。旧全轴friend测试不冒称当前XYZ生产开放。

开发失败与修订完整保留：

- `B/verification01` 在historical_ax01的构建命令退出1：新增模块测试中float/double混用触发`-Werror=double-promotion`；仅补明确类型转换。
- 随后定向构建退出0；`development_checks/integration01.xml`实际32项中31通过、1失败；param01的9项和module01的20项通过。
- 失败断言误在PositionControl层读取仅由MulticopterPositionControl发布时填写的diagnostic.raw_dt，值为0。源码审计确认真实guard按sample差积分；改为底层从真实nu候选增量验证8/12ms、模块测试额外检查发布raw_dt。未改任何生产时间语义或宽限阈值。
- 完整 `B/verification02` 已退出0：46命令全部成功，488个不同C++、1245个Python测试、32768对旧路径主样本及256对同sample重算通过，SITL与DONT_RUN Gazebo构建通过。没有B飞行；下一步冻结、提交后重新干净资格，不能使用A的固件资格启动Z飞行。
