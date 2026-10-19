# R03 revision05：保留完整X门，重新验证Z/XY/XYZ

2026-10-19。最新状态：**B/Z与C/XY完整通过**，D/XYZ尚未执行，R03整体尚未验收。下文准备阶段记录保留为历史。

## 范围、历史与授权

用户在总57次提案后要求“继续，后面不用我同意，一直到R03验收为止”。本次准确上限57=历史30+新27，范围内不逐门重复询问；首个安全/必需有效性/配对风险/清理失败仍停止，不补飞、调参、放宽阈值或无界扩预算。

入口分支research/sta-velocity-regularized；HEAD为7d865a085bc8cd39aa17d868162bafacddd6d37d，工作区干净、33递归子模块版本/工作区正常。历史累计30尝试、29起飞、26接受、4失败/无效，全部原判和数据保留。

保留revision04 A/X完整9接受、6配对决定、9独立回放及其原源码d6a80776b478adbbbe03a1967140d55c62bd618b；不是将零散旧接受拼成新门。revision04 B的五个接受不计入新B，旧run016不续跑。

新B/Z9→C/XY9→D/XYZ9，每门PID/硬sign ESTA/R-STA各3轮，同门同源码/固件；前门完整通过才扩大。新种子与准确ID/顺序见r03_revision05/manifest.json，旧原有种子包括预留未用均不复用。
仅Iris Gazebo Classic SITL、原位置P/姿态/rate PID、速度DIV1；默认PID。B入口生产已仅开放新MODE3的AXES1/4，后续3和7尚未开放；不实机、不ISTA、不自动R04/R05。

## 本版修订

上一版B第六轮理想nu的正常float32最终减法舍入约0.4975ULP，超过旧固定2e-7检查；实际C++核与日志21976不同候选的两路复算一致。详见R03_REVISION04.md，原失败不改判。

新版只接入numeric05的候选严格binary32及独立有理数整数RNE验算，保留double数学残差说明。固定SHA旧源上只替唯一候选拒绝AST节点，私有函数globals接线；不全局改np.allclose，不catch后跳过其余检查。
raw/Psi、限幅后applied、HTE、生命周期/时钟/reset/起降及全部既定数值风险门保持。控制律、dt、参数、epsilon、127项固定配置、模型/世界/插件和任务波形/窗口保持。

新工具和计划入口快照为r03_revision05与plan/r03_revision05_entry。授权记录AUTHORIZATION_R03_REVISION05_CN.md。新注册outcomes均unattempted，实际尝试另在新外部R03_revision05账本记录。
沿用prearm04预热reader和原0–500ms新鲜度、完整历史/歧义/reset检查；不将离线性能当在线保证。

## 已实际完成的初步检查

- protocol build退出0，历史五批账本/顺序/来源/恢复和30/29/26/4计数核验通过；新27项科学参数、任务、ID和顺序与旧BCD保持，仅换版本和新种子。
- protocol --prepare退出0，先全历史查重后登记。注册后再次真实扫描58808份JSON：无种子冲突或非法JSON；起飞前仍重查当前门。
- 新协议32项测试通过退出0。第一次因测试文件括号语法错误退出1、未执行测试；仅修正测试拼写，不修改实现/门槛。后续重复测试不额外累计。
- 根任务真实调用require_previous_gates(B)，独立核对旧A完整回放/原始指纹/六配对决定，与固定gate_pass精确一致；返回原A收据SHA 6e0498bf52c69239f13b294ce9059473827af8ec4e1b0595ef8dc2ccf659e8d2。
- 新27轮未启动。完整统一回归、版本化完整诊断、源码提交及干净资格仍待实际完成后追加。未执行MATLAB、实机、R04/R05。

初始磁盘约63GiB、tmpfs7.3GiB；每门/轮重新检查，不删除旧日志。参数原SHA仍需完整资格与每次恢复核验，不以文件存在代替实际生效。

大型证据根：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision05。
本报告后续只追加真实命令、退出码、测试数、逐门SHA/飞行/回放和失败；未发生的检查不填通过。

## 飞前分析链补强（零新飞行）

新分析53项、数值适配16项、运行器49项、回放42项、版本/资格审计25项分项测试实际退出0；新协议32项另已通过。统一回归会重跑，不重复相加为新的不同用例。旧numeric05 41、旧revision04 runner45/analysis48/replay38也真实回归退出0。

完整只读诊断覆盖revision04所有五份RSTA主日志：A003/A005/A009/B011/B015；整飞行提交候选分别10977/10798/10935/10931/11045，共54686个不重复候选。观察窗重复检查和B015第二导入顺序不计入该数量。后部height、landing、IMU、tail、CLI、rate等完整检查均执行；原四接受/一失败不改，所有新诊断accepted/flight_accepted/authority均false。B015 runner-first与analyzer-first metrics逐值一致、频谱SHA一致。

独立审查额外实际1正例、12注入负例达到预期：包括±1ULP、应用状态冒充候选、参数/epsilon错误、raw/Psi、重复FF、applied、PID轴泄漏、rate/sample/HTE。唯一AST节点替换与逆变换等价、私有globals、原函数/np.allclose不变均已核查。
这些是离线分析核验，不是新飞行、闭环或任意平台浮点保证；lambda2来自冻结配置量化并由完整初始/前后参数与changed_parameters检查绑定，不是逐帧lambda2日志。

开发错误保留：运行器首次遗漏M00 Python依赖在导入前退出1；旧A→新B夹具顺序/历史计数使runner45中1项、replay38中2项初次失败，仅修测试期望；分析夹具初态跳变触发原连续性检查，改为连续状态；独立HTE负例向int64夹具写.01被截断，改为可表达的1后测试确实触发拒绝。没有修改控制或阈值来让测试通过。

| 证据（相对本版外部B根） | SHA-256 |
|---|---|
| offline_analysis01/evidence.json | d6382f8ca97c574d3bc89fec1b71243ee2cf71b684c03fedebf4e6486dd59c5c |
| offline_analysis01/historical_evidence.json | 20af90419c4de559b993156df6beb36914e8c0913e4a70677529b79247338bb0 |
| independent_numeric_review01/evidence.json | 44b5ace43ed722f882f26febf2bb61f39c47622912e8bb5af9d4d82c29c0c787 |

生产源码仍与本版入口逐字相同；三份外部计划和新增入口快照逐字核对一致。EEPROM仍为06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc。runner默认dry-run实际退出0且明确无参数/文件/进程/飞行变化。

### 首次统一验证的比对封装错误（保留）

B/verification01在两个numeric_full_chain命令均退出0后，最后比较历史诊断metrics时退出1：误使用协议专用allow_nan=False精确序列化，历史未选轴NaN/Inf字段不能被该序列化表示。两个完整链本身已完成且原判保持；不能把整体统一验证写成通过。尚未执行该次末尾SITL构建/总数汇总。
修复仅限诊断结果精确内容比较：保留NaN/Inf标记、符号、全部字段和数值类型，不归一化或扩大科学容差；协议/授权全局exact仍拒非有限值。补局部负例后重新运行新的verification目录。
另采纳审查建议，将资格入口C++最低用例数从历史475收紧至与新版verify一致的488；不是减少测试或改变控制。以上修订均在源码冻结/新飞行之前。

### 修订后统一验证通过（提交前）

局部诊断比对新增8个边界/负例，资格审计现33项实际通过，退出0；协议32项再次通过，未重复计数。B/verification02实际退出0：54条顶层命令全部0，488个不同C++、1430个Python用例，32768对原PID/ESTA主样本和256对同sample重算通过。SITL和DONT_RUN Gazebo构建通过；旧PID与旧失败B完整分析各两种导入顺序一致。全部输入、33子模块及EEPROM保持，新飞行0。
verification02/evidence.json SHA-256为ee71ea04ef3b8f56df457183eaafe9e10d4e26395833d98bd2884f01f72109c0。本次不是干净提交资格；之后必须在明确源码提交上重新构建/测试并绑定实际固件，不能用本次预提交固件启动飞行。

明确范围审查：仅新增revision05协议/工具/测试、授权、三份入口计划快照和本报告；B生产控制、参数默认、模型、旧算法和旧冻结目录未改。两个独立审查分别覆盖候选/完整分析链及预算/运行器/冻结/回放，未见阻断；cached diff空白检查通过。尚未push，R03尚未验收。

## B/Z门：9/9接受，6配对与9独立回放通过

源码提交 `e4987db64083482b3227ba01a7fdf3f027e006c6`，生产源码保持原B入口。干净qualification01真实54命令全0、488不同C++/1430 Python、32768+256逐样本回归；SITL/Gazebo构建通过。固件 `47aa3245b9933f51942fdf6ce36612e167af033a6ac82d05961d4df196e221ed`。独立审查核对799输入、418资格证据指纹和33子模块一致。

实际命令（在仓库根，沿README设置Python依赖）：

```bash
python3 research/sta-velocity-control/regularized_sta/r03_revision05/verify.py --gate B --qualify --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision05/B/qualification01'
python3 research/sta-velocity-control/regularized_sta/r03_revision05/runner.py --gate B --execute --source-head e4987db64083482b3227ba01a7fdf3f027e006c6 --qualification '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision05/B/qualification01/evidence.json'
python3 research/sta-velocity-control/regularized_sta/r03_revision05/replay.py --gate B --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision05/B/replay01' --finalize
```

三命令实际exit0。准确run010–018九轮，PID/ESTA/RSTA各3，全部起飞、观察、降落上锁、完整日志接受；6项配对风险检查通过。独立9子进程重解码全部exit0，metrics逐值精确一致、频谱SHA一致，输入保持。共18份ULog（每轮启动与主日志），不是只有9份。参数每轮精确恢复，末尾无残留进程，EEPROM SHA仍为06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc。

| B证据 | SHA-256 |
|---|---|
| qualification01/evidence.json | 220680bb2a2f851a6de8d752d601dd86393804b1be63f7a563fbd28fb215c23f |
| batch01/ledger.json | 275d512c8b157e2070eb456b65c45afce4ddca4b7e89d942134ad7da4c5cb611 |
| replay01/summary.json | 08933485a9e18e129f266fccae4404ef664b87f967d27be67acaa01aac5559ef |
| gate_pass.json | 198c15655a94abdd8a6b96e78c70e2c91556fa27842e3e425fe494d6c1d73886 |

主窗32s，各算法n=3的描述性均值；速度RMSE单位m/s，Z纠偏TV/T单位m/s³：

| 算法 | X RMSE | Y RMSE | Z RMSE | 三轴均值J | Z纠偏TV/T |
|---|---:|---:|---:|---:|---:|
| PID | 0.00726350 | 0.00791830 | 0.00414773 | 0.00644317 | 0.0913940 |
| ESTA | 0.00724080 | 0.00776818 | 0.01047500 | 0.00849466 | 4.2720442 |
| RSTA | 0.00739399 | 0.00756599 | 0.00156083 | 0.00550694 | 0.4171647 |

此工况RSTA的Z误差低于另两者，控制变化量低于硬sign ESTA、仍高于PID；不是全面最优、显著性或实机结论，TV不是能耗。旧B五个接受未拼入，新B没有失败或补飞。

可追溯索引：`regularized_sta/results/R03_revision05_B.json`；包含全部18日志/参数恢复/逐轮指标及资格、回放与门收据。外部完整只读汇总B_result01退出0，SHA `7e51ffc63455dde8d7a767adc88369dee53a6890a096e3554166901a3c302b2b`，只确认保留A与新B，不宣称全R03通过。该后处理工具41个临时夹具测试exit0；曾发现并修复输出目录符号链接边界问题，仅影响汇总输出保护，不改冻结实验/原始数据。

累计39尝试/38起飞/35接受/4历史失败；本版9/27接受，C/D18未执行。下一步只开放C/AXES3，先离线验证/冻结/提交/干净资格，不自动开放7或进入R04/R05。

## C/XY准备：只增加双轴准入，离线验证通过

B结果明确提交为 `947412cd340e0368dc7c9d8a873a069bbc157eda`。在B完整门证据通过后，生产仅将MODE3准入从1/4增至1/4/3；参数文件只改说明文字，所有默认值和数学控制/保护/dt不变。MODE2及MODE3的2/5/6/7仍拒绝，XY运行时Z速度及角速度仍PID。

新增13项真实生产路径测试（Integration4、Param2、Module7），不用测试friend放行：X/Y独立增益/epsilon/旧nu、一次FF、非均匀sensor时间、未选Z的PID/HTE、水平向量/垂直优先约束、同sample和末轴故障原子拒绝、落地取消/接触重入、armed暂存/取消/disarm、生效与BSON重启。闲置XY PID的NaN探针仅直接作用测试对象，不误用参数重载重置被测配置。`pid_calls`为模块update次数，不是PID核次数。

`verify.py --gate C --output .../R03_revision05/C/verification01` 实际exit0，54命令全部0，501不同C++/1430 Python、32768主样本对/256同sample重算、SITL/Gazebo构建及两顺序完整日志链通过。证据SHA `747b32fa2fc73a2bd7cffd2646713233f284d5bb06ece97559d9614c2370960b`。未新增飞行；尚不能代替干净源码资格。

`freeze.py --gate C` 实际exit0，724仓库资产；绑定已通过B与保留A、原任务/参数/插件、准确9项顺序与预算。独立只读审查五文件无阻断，diff检查通过。本次仅五个准入/测试/说明文件、C冻结和报告；旧版本、B冻结、参数/模型/任务/阈值保持。提交之后再干净资格并执行C9。

## C/XY门：9/9接受，6配对与9独立回放通过

源码提交 `a3bd03e6009a52a2430b6c3f918872d73f71b495`。在此干净提交运行 `verify.py --gate C --qualify --output .../C/qualification01` 退出0：54命令全0、501不同C++/1430 Python、32768+256回归及构建通过。实际固件 `0d0663fcd4f65ec601a010a15c7ff9cc54e48817526345ba47ca5e91791ded99`。

`runner.py --gate C --execute --source-head a3bd03e6009a52a2430b6c3f918872d73f71b495 --qualification .../C/qualification01/evidence.json` 退出0，run019–027共9尝试/9起降/9接受、6配对通过。`replay.py --gate C --output .../C/replay01 --finalize` 退出0，9独立解码全部指标精确一致、频谱SHA相同、输入保持。共18份ULog，逐轮完整参数恢复，末尾无残留模拟器；EEPROM原SHA保持。没有补飞/失败/参数调整。

| C证据 | SHA-256 |
|---|---|
| qualification01/evidence.json | cd3454e90d5d2187da6c0ac762cfda6812129e862c95de0ead4c323cbbfbe87a |
| batch01/ledger.json | 5d4cde3a10adf70eb200aee867da7bc173f685d055a7cf701023166961db8b7e |
| replay01/summary.json | 7c5a4f63ba2a72da31b241a4226fb809038a5f41c45c46fdb3d0fdcc90aa6a14 |
| gate_pass.json | b31d060ad6569f222335b1bb7618e93664f9ecb881d77758296e638fd0bdcef8 |

主窗64s，各算法n=3描述性均值；速度RMSE单位m/s，纠偏TV/T单位m/s³：

| 算法 | X RMSE | Y RMSE | Z RMSE | 三轴均值J | X/Y纠偏TV/T |
|---|---:|---:|---:|---:|---:|
| PID | 0.00973792 | 0.00991328 | 0.00279201 | 0.00748107 | 0.112536 / 0.110225 |
| ESTA | 0.00667264 | 0.00694693 | 0.00278800 | 0.00546919 | 0.217283 / 0.223693 |
| RSTA | 0.00520436 | 0.00500684 | 0.00278057 | 0.00433059 | 0.144019 / 0.145477 |

此开发工况RSTA水平速度误差低于另两者，水平纠偏变化量低于ESTA但高于PID；Z仍为PID，不能把这门称为三轴RSTA。位置/高度/yaw及限制按冻结门槛通过，全部逐轴指标在 `regularized_sta/results/R03_revision05_C.json`。外部只读汇总C_result01退出0，完整摘要SHA `b740e7cc644d4274f15eb8a107561ce0a5d995f061b3593e5a30540a9da5e08d`。n=3不作显著性/普适性结论，TV不是能耗。

累计48尝试/47起飞/44接受/4历史失败。本版18/27接受，D9未执行；先完成D三轴离线测试、冻结与干净资格，再按清单进行最后9次。保留旧A原证据，不混旧B接受。

## D/XYZ准备：三轴准入与离线验证

C结果提交 `4763af0c2babbdd661fac7fb862b023fd2d7db49` 后才应用D。生产仅在累计1/4/3准入表达式后增加7，元数据仅说明；默认PID/参数/保护/时间/控制律不变，MODE2及2/5/6仍拒绝。原先用7表示未开放的两处负例改为5，保留armed拒绝、取消、effective及generation不变检查，不删除负例。

新增12个实际测试（Integration5、Param2、Module5）：三轴独立增益/nu、旧nu输出与一次FF、8/12ms、地面/ramp原PID逐样本等价及唯一有界交接、真实机载HTE只调整Z、向外冻结/垂直优先、同sample或末轴异常无部分提交、时间/reset/内环/HTE故障、三宽度原子生效、0/1/3及1/4/3/7 BSON保存重启、接触弹跳/termination/disarm。正常三轴的`pid_axes=0`与有限输出辅助探针验证不依赖闲置PID；地面/起飞仍保留真实PID。模块`pid_calls=1`不是计算一次PID核。

`verify.py --gate D --output .../D/verification01` 实际exit0：54命令全0，513不同C++/1430 Python、32768+256逐样本回归，SITL/Gazebo及完整日志两导入顺序通过；证据SHA `21938778adca2bf7ab999b8c50bb9d66fa5fea3508121cabff322c78071a62ca`。生产/参数/旧算法回归均非零实际执行。独立审查实际五文件与已审补丁逐字一致，无阻断；这是离线证据，不是D飞行通过。

本次范围仍为五个准入/说明/测试文件、D冻结及报告；之后必须在明确干净提交上重新资格，再启动已登记D9，不改变任务、增益、epsilon、阈值或预算。
