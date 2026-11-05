# R03 上游时间链：离线修复与诊断协议

## 状态与范围

入口 `09c96f3cd0481f8b6672aa047cd7d49ffd21fc03`，分支 `research/sta-velocity-regularized`。用户已明确允许IMU→EKF→调度链专项诊断及必要最小修复，原安全门槛不变。历史累计52尝试/51起飞指令/46接受/6失败；A/X、B/Z、C/XY保持各自历史版本结论，D及R03未验收。

本报告先记录离线实施和冻结方案，**不是新飞行通过**。仅Iris Gazebo Classic SITL；不硬件、不ISTA、不R04/R05。所有原失败/未执行保留。源码与结果完整SHA在真实提交后记入外部进度，不虚构本报告自身SHA。

## 已证明的问题与尚未证明的部分

旧run030在降落时发生主EKF因timeout切换、真实ref_alt改变，原验收正确拒绝。IMU0及其EKF出现24ms的采样至发布年龄；原raw gyro仅约1Hz，因此不能从旧日志判定首次28ms发布停顿由哪一处触发。

离线真实C++对象/真实uORB/真实WorkQueue负对照证明另一条明确的恢复缺陷：7条输入排队后，旧`VehicleIMU::Run()`成功发布一次便返回，仍有6条输入但需要新的callback或backup调度才能继续。旧版本2个真实测试中单样本通过、7积压预期失败，make退出2；这不是把复制的数学函数当生产测试。

最小生产修复位于 `src/modules/sensors/vehicle_imu/VehicleIMU.cpp`：成功Publish后若gyro仍updated，ScheduleNow再返回。只添加7行含注释；不改变采样时间、积分dt、均值追赶、数据gap、校准、backup超时、EKF超时、控制参数或控制律。正常无积压不额外调度；有积压时排队让消费者有机会先消费，而非一次Run连续发布覆盖队列。

该修复的红→绿证据只证明积压恢复，不声称已完整归因或消除原首次28ms停顿。

## 日志与时限测试

- 新SITL可选 `SDLOG_PROFILE` bit11=2048，默认仍1；只把已有sensor_gyro实例0/1/2的记录间隔设0。没有增加/挤出话题、改变队列、打开FIFO日志调度、改变传感器物理频率或噪声。其他板型仅做真实预处理排除检查，未硬件构建/运行。
- 原实际运行profile1041保留全部位，新诊断3089。1171满槽与1041实际配置均有真实C++对照；实例3仍原1Hz记录，其他话题顺序/间隔保持。
- EKF2Selector新增测试独立二进制，test-only HRT wrapper只影响当前测试线程。真实UpdateErrorScores的10/20/50ms精确边界及±1µs、新status恢复、fault、多实例独立均覆盖；Selector.cpp及其生产阈值不变。
- 新gyro覆盖沿用旧vehicle_imu的12ms双时钟、完整边界组/封口后继规则。不去重、不改时间、不插值补样，不把高频日志等同无损消费。

## 实际分项证据

外部证据根：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_upstream08/`。

| 分项 | 实际结果 | 证据 |
|---|---|---|
| 真实IMU修复回归 | 7个C++通过，构建/二进制exit0 | offline_imu01/green01 |
| Selector边界/原发布链 | 15新＋15原C++通过，exit0 | offline_selector01/verify02 |
| Logger实际配置/默认回归 | 8个C++通过，构建/测试/两种预处理exit0 | offline_schedule01/logger02 |
| 两次诊断协议/运行器 | 27＋22 Python通过，exit0 | offline_diagnostic_design01后续实施收据及统一验证日志 |
| 完整分析接线/拒绝负例 | 31 Python通过，exit0 | offline_analysis01/tests03 |
| 资格/范围/真实测试数量负例 | 24 Python通过，exit0 | test_verify.py，最终统一验证再次执行 |
| 新gyro时钟/边界负例 | 13 Python通过，exit0 | test_timing.py，最终统一验证再次执行 |

这些分项不冒充完整统一资格，重复执行不重复计为不同测试。完整构建、原Position/ControlMath/Takeoff/Rate、PID/ESTA/RSTA固定序列、旧功能回归及三份旧ULog两种加载顺序由新verify.py执行；统一结果以真实外部收据为准。

已保留的开发失败：IMU首次编译错误；测试未初始化HRT worker导致夹具挂起（不是生产故障）；旧版本7积压预期失败；Selector第二suite重复启动WQ夹具错误；新增资格测试mock执行口滞后；分析测试首次缺外部Python依赖。都不累计为通过。

历史回放入口另有一次实现错误：顶层save重定向不足以隔离嵌套baseline，错误改写run028派生v00_metrics的limitations文字。检测到后立即停止；按已有独立副本恢复原SHA，并核对冻结189项全部一致。ULog、数值、原判未变。事故记录 `offline_analysis_root01/INCIDENT_CN.md` 保留；现完整复制sidecars到新目录、只读原ULog，负例验证嵌套写入只触及副本。不能称首次错误回放也“只读通过”。

## Lockstep与历史适用性

真实功能测试使用test构建，明确未启用ENABLE_LOCKSTEP_SCHEDULER；默认SITL构建启用真实lockstep。测试的1s backup、稳定4ms配置及低均值是隔离积压的夹具，不是生产时限改动或原事故完整复现。

WorkQueue只有未注册时才注册component，队列排空才注销；本修复在当前Run内追加队尾，有限积压可以排空，缺accel无Publish不反复自排。真实静止积压消费者逐条接收已验证。但外部callback并发可能提前把IMU排在消费者前，queue1覆盖风险不能靠这些测试彻底排除。后续需实际gyro/IMU/EKF时钟、sample与dt、missed_imu/time_slip等证据，不能只看动画。

上游变更影响各算法共同输入时间链。旧ABC各9轮仍归属原固件，不能改写成新固件验收。若采用最小ABC每算法1轮共9工程桥接，必须独立冻结并全部过原门槛；不能混成新固件每算法n=3统计。若要求四门全部同一最终固件各3次，则需完整36新轮。本两次诊断尚未给任一方案签发验收资格。

## 已冻结的有限诊断

独立目录 `regularized_sta/r03_upstream08`，准确清单为PID→旧XYZ ESTA两次，同一个全新配对IMU种子、同一新干净源码/固件、原D/TEST8任务与127控制/任务参数。完整协议见该目录PROTOCOL_CN.md与manifest.json。

累计上限54=历史52+诊断2。新增只是日志profile1041→3089；两轮 `accepted=false`、`accepted_for_R03=0`，不抵扣D完整门或ABC桥接。第一轮任何必需失败即停，无自动第三次、补飞或换种子。没有观察到故障只能说明本次未复现。

新运行器默认dry-run；SHA封印旧飞行函数，私有副本只变一处authority调用，逆AST证明其余主体不变。完整监视、预热、500ms、模型、起降、参数恢复与原科学/风险链保留；新来源/预算/清单/固件/33子模块/日志配置/资格均独立核验，旧06资格不可借用。

飞行前仍必须：明确范围提交→该干净提交重构建与完整非零资格→全历史种子复核、原参数备份与容量/进程预检。只有这些完成才允许本两轮；截至本报告初稿没有新起飞。

## 统一预提交验证（2026-10-20）

实际命令（工作目录仓库根，PYTHONPATH含`.px4-python`、研究scripts及M00外部Python依赖）：

```sh
python3 -B research/sta-velocity-control/regularized_sta/r03_upstream08/verify.py --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_upstream08/diagnostic01/verification02'
python3 -B research/sta-velocity-control/regularized_sta/r03_upstream08/freeze.py --check
git diff --check
```

三条命令实际exit0。verification02共65条子命令全0，541个不同C++测试、1258个Python测试，32768主样本对和256同sample重算；6次历史完整CLI回放（028/029/030各两种加载顺序）、默认SITL及Gazebo仅构建通过。782仓库资产冻结复核一致，33递归子模块及原EEPROM SHA保持。收据SHA：`2cefef768dc88921ce41ab0f0bee3e2de2a927fc843b76b31902d6ea592730ae`。这是`clean=false`的预提交验证，不能替代干净提交资格；新增飞行0。

保留前一次verification01的实际exit1：各测试/构建已运行，但验证过程中协议文档改变，末尾输入指纹检查正确拒绝。其收据SHA `f416209cb0208e4537c98472e0975b68d28ac0f5e97553d8ff7082529f78e9d0`，不计为通过。verification02期间不再修改冻结输入，随后独立freeze检查通过。

只读执行链交叉审查未发现阻断：新资格绑定、两次账本、canonical参数、原BSON恢复、旧科学检查和诊断非接受标签均已检查。仅11个生产/测试路径在上游授权范围内；不修改Selector.cpp、控制律、模型或旧冻结协议。MATLAB、硬件、实际飞行、R03完整验收均未执行；提交后仍须运行`verify.py --qualify`，成功方可启动本两次诊断。

## 两轮诊断与独立回放结果（2026-10-20）

干净提交 `1273eed615cf36845c0ad61f23e44a6edcb15089` 的新资格实际通过：`qualification01/evidence.json` SHA `1d0c7ff6929924c20326156ea9bbfb271c5040352adf5cadf32c7097f406eded`，固件 SHA `92ac4af2cfd48f7e721f48e25e4a6577a9f501dbfa8eb7fb9b332460cfce47c8`，clean/approved 均为 true。新运行器严格执行两次且仅两次：`diag001` PID、`diag002` 旧三轴 ESTA；两次均完成起飞、TEST8 任务、降落并上锁，参数恢复精确、无残留模拟器，账本 success=true，`accepted_for_R03=0`。

两轮均使用 `SDLOG_PROFILE=3089`。原始陀螺三个实例均为约 250 Hz，最大 publication/sample gap 为 4 ms，dropout=0、corruption=false；两轮没有主 EKF 切换、`ref_alt` 变化或原 24 ms age 事件。独立锁步审计分别对两份主 ULog 解码一次，clock/boundary 原谓词均通过，source ULog/result/job 首尾 SHA 不变。实际同刻 publication 组已保留，不做排序、去重或插值。

独立回放 v1 首次按 `allow_nan=false` 比较而拒绝，错误原因是原指标中存在 12 个合法 `+Infinity`（未设置的上限字段），不是飞行或科学检查失败。v2 仅在指标比较器中加入严格的非有限值分类：同路径同类 `+Infinity`/`-Infinity`/`NaN` 可相等，有限值按 `float.hex()`（含符号零）比较，类型、数组顺序、重复键和 ULP 漂移仍拒绝；协议/授权的有限 JSON exact 比较保持不变。v2 四个独立进程均 exit0，两个诊断各两种导入顺序，`numeric_equal=true`、谱 SHA 一致、原始整批和双 ULog 指纹未变。回放 summary SHA `88830fc70aa6bc8874603a032ca82ca53e1163d99d23c615b8dc428a0dfc8992`。诊断和回放仍不产生 R03 接受。

需要特别保留的风险：PID 这轮的非主 EKF1/2/4/5 `time_slip` 分别由 0 增至 4 ms 再至 8 ms；旧 run028/029/030 三份 ULog 的六路 `time_slip` 均为 0。当前数据没有 filter fault、primary 切换或安全门失败，但 publication/sample 日志不能证明 WorkQueue 消费顺序，也不能把该变化唯一归因于 7 行重新调度或日志负载。该信号作为正式四门前的公开限制，不新增事后阈值，不改判两轮诊断。

后续必须使用同一最终源码/固件重新冻结 A/B/C/D 四门各 9 轮（每算法 3 个新配对种子）；旧 ABC 27 轮、两轮诊断和旧 D 失败均不混入新矩阵。若新门前发现必需安全/有效性失败，按首败规则停止并保留全部数据。
