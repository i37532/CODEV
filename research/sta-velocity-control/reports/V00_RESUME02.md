# V00 恢复批次02 — 原速度 PID 基线通过

2026-09-21。**passed：新批次计划3次、实际3次、完成3次、接受3次、失败0次。**
三轮均完成预热、起飞、60秒悬停、降落上锁；每轮原分析器49项检查全通过。
只验收Iris SITL原PID基线，不代表新的速度控制器或实机通过；未执行V01、未push。
旧Takeoff测试失败和恢复批次01的world预检失败仍保留，不能将历史汇总写成从未失败。

## 1. 范围、版本与授权

- 用户同意“修复world核验、补齐工具测试后，重新冻结并执行三轮基线”，随后要求继续。
- 起点HEAD：22bf39a3b1361bf032923817bb1b37496e448297；research/sta-velocity-control，起始工作区干净。
- 协议/源码与全部三轮实际飞行提交：**7f0274c1a0ab129065a887d9c5546ad47dfa13bb**。
  提交后重建，三轮FW git-hash一致；三轮间工作区干净，固件指纹未变。
- 固件SHA-256：cc007b897d3c5158b31f803e50e74d3ed2ac38250f1c7919c756988dc3a526ed。
- 递归子模块版本与工作区均核对；sitl_gazebo为822050a7ab6fd87972e59f16312f451bce217a56。
  完整列表、OS/GCC/CMake/Gazebo/Python输出见verification04，继承原审计模型与随机源说明。
- 本轮只修复研究运行器的world证据核验，增加测试/协议/报告；生产Takeoff、PositionControl、
  ControlMath、HTE、failsafe、姿态与rate控制律、参数默认值、模型/插件均未改。
  上批已获授权的Takeoff测试修订、三个HIGH_RATE日志话题请求保持。
- Takeoff.cpp指纹仍为e8040562fb7d31d359e6ae5822f46e9f98ae01d7ea5a1d95a8ee7f0e81a74a6b。

world验证现读取实际gzserver argv、session和两项白名单环境变量，不依赖console是否打印world。
三轮均证实恰有一个属于本次launcher session的gzserver，argv为仓库sitl/worlds/empty_grey.world，
文件SHA为09d9a334728b35a5ca0392e8751e3df5b8aea8b1d5019f8e850a4b0b8bc57b96。
Iris模型Using路径独立核验，SYS_AUTOSTART=10016、quad_w；不是CODEV DP1000实机配置。

## 2. 冻结协议与运行方式

[协议](../v00/resume02/PROTOCOL_CN.md)、[机器清单](../v00/resume02/protocol.json)、
[参数与资产](../v00/resume02/frozen.json)。沿用批次01全部安全/数据阈值；只改变world核验方法和新授权批次。
三次新进程按run01→run02→run03执行；首次必需失败即停，不补飞/改阈值。此前失败不从历史中删除。
原默认随机引擎，seed=null；这是重启重复性检查，不是3个独立随机种子或正式统计试验。

位置P、XYZ速度PID、姿态及角速度PID保持。起飞前/落地后完整参数核验及实际ULog检查均证实：
MC_RTC_MODE=0、MC_STA_AXES=0、MC_RTC_DIV=1、MC_RATT_TEST=0、MC_STA_TKO_MGT=0。
所有冻结MC_/MPC_/SYS_VEHICLE_RESP参数无调参；ULog亦包含全部冻结控制参数，飞行中无关键参数修改。
SDLOG_PROFILE从131保留原位并OR16为147，SDLOG_DIRS_MAX=1000避免删除旧日志，SDLOG_MODE=1。
预热前logger重启为256KiB/1000Hz轮询，不改变控制周期。

唯一目标发布链是机载flight_mode_manager→位置/速度→姿态→rate；运行器只发送commander命令、
中性RC及GCS心跳，没有offboard、旧角速度激励或第二目标源。
MIS_TAKEOFF_ALT=2.5m；沿用CODEV起飞完成转POSCTL，再明确请求Hold并稳定3s，悬停后auto:land。
不把该设置冒称实际全程精确维持2.5m，实测高度见第4节。

实际命令（依赖环境见协议）：

```bash
python3 research/sta-velocity-control/scripts/verify_v00.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V00/verification04'
# 提交7f0274c1a0之后，确认干净再构建，不启动额外模拟器：
DONT_RUN=1 make px4_sitl_default gazebo_iris -j4
python3 research/sta-velocity-control/scripts/run_v00.py --execute \
  --source-head 7f0274c1a0ab129065a887d9c5546ad47dfa13bb \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V00/series02'
```

以上均退出0；series02_execution.log保留终端输出。所有目录为新建，旧目录拒绝覆盖。
只读参数归档后每轮停机恢复原EEPROM完整1129字节；最后前后SHA一致：
06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc。无残留模拟器，旧日志保留。

## 3. 真实测试与退出码

| 检查 | 实际不同用例数 | 退出码 |
|---|---:|---:|
| make px4_sitl_default -j4 | 构建 | 0 |
| make tests TESTFILTER=PositionControl -j4 | 构建并重复执行15项，不累计 | 0 |
| PositionControl / ControlMath / Takeoff | 15 / 9 / 8 | 各0 |
| RateControl / RateControlDispatcher | 1 / 4 | 各0 |
| 飞行前Python工具测试 | 25 | 0 |
| 提交后DONT_RUN Gazebo构建 | 无额外飞行 | 0 |
| dry-run | 不运行模拟器 | 0 |
| 新批次三轮运行与原ULog验收 | 3轮，每轮49项 | 0 |
| 飞行后Python工具回归 | 31（含新增6项统计勘误测试） | 0 |
| audit_v00_results.py离线补充审计 | 三份原日志重解码，不飞行 | 0 |

共37个不同C++用例，不将重复执行算成更多用例；最终31个Python与C++分开计数。
新增world测试覆盖正确路径但无console依赖、错误argv/环境、无/多实例、错session、非session leader、
相对路径和错误进程等；真实/proc读取测试没有启动模拟器。
未开展MATLAB、新控制律单测、速度ESTA飞行、正式留出或硬件测试；本阶段无这些通过声明。

## 4. 三轮基线指标

窗口为各自60秒悬停。NED X/Y/Z速度误差：最终发布v_sp减最新不晚于它的实测v，按实际时间加权。
本批匹配时间差全部为0，但V00没有内部速度诊断，仍不冒称证明了精确被消费状态/全部内部更新。
均值、标准差、最大误差、位置/姿态/加速度需求/推力等完整值见各runNN_metrics.json。

| 轮次 | 悬停秒 | 速度RMSE X/Y/Z（m/s） | 位置RMSE X/Y/Z（m） | 悬停估计高度均值（m） |
|---|---:|---|---|---:|
| 01 | 60.392 | 0.011073 / 0.007252 / 0.005238 | 0.035290 / 0.015977 / 0.081290 | 1.924 |
| 02 | 60.392 | 0.011218 / 0.007880 / 0.005187 | 0.034977 / 0.017029 / 0.081342 | 1.934 |
| 03 | 60.480 | 0.011236 / 0.007532 / 0.005119 | 0.035157 / 0.015806 / 0.080989 | 1.947 |

**高度限制必须公开：**虽然起飞参数为2.5m，随后原流程进入Hold的实际估计高度不是2.5m。
相对预热地面Z的悬停高度范围分别[1.825,2.011]、[1.836,2.019]、[1.850,2.028]m；
符合事前冻结的进入悬停±0.5m、悬停±1m包络，但不能称精确2.5m定高任务。
这些是估计器相对高度，不是Gazebo真值；位置RMSE针对实际发布位置目标，不是对2.5m的绝对误差。
V00保留既有起飞/Hold语义，未为了高度数字调参或改控制逻辑。

三轮全飞行无failsafe/failure_detector/rate fault/termination，悬停有效PID更新连续；
倾角≤15°、位置/速度/高度及yaw边界、有限归一化输出均通过。
没有算法性能胜出比较，只有原PID基线；三轮默认随机源结果不作独立样本置信区间。

## 5. 周期、日志与覆盖

- 位置状态、最终位置/速度目标及姿态目标约100Hz，周期8/12ms交替，平均10ms、最大12ms。
  位置timestamp和timestamp_sample在记录中一致；不能假定速度环250Hz。
- trajectory_setpoint为50Hz；rate诊断为250Hz，三轮完整飞行publish_seq无缺号，ULog dropout均0。
- mc_pos_control的perf调用数增量对应约100.013/99.997/99.983Hz，与发布频率相符。
  perf快照有CLI边界偏差；模拟elapsed=0不等于实际CPU耗时为零，不提供板载耗时结论。
- 三轮motor_limits记录约227.50/228.11/219.08Hz，最大日志间隔8ms；不是完整250Hz记录。
- actuator按timestamp_sample与rate诊断精确交集：13962/15098（92.48%）、14017/15098（92.84%）、
  13595/15120（89.91%）；都超过事前80%门槛，最大匹配间隔8ms，匹配输出逐位一致，最大差0。
  未匹配样本未插值、未伪称通过逐条比较；不能从dropout=0推导所有话题无丢样。
- 所需8个连续话题全部满足每窗口至少600点、最大间隔≤250ms。
  控制台仍有两个非必需vision轨迹话题超过订阅数的警告，未删日志或假称全部profile话题成功。

## 6. 飞行后描述性统计勘误（不改变验收）

保留飞行源码和原v00_metrics.json，不追改原文件；新增独立audit_v00_results.py和6个测试，
离线产生descriptive_audit.json。**原判定3/3通过，新补充审计不设新门槛、不替换原判定。**

1. 原consumed_mixer_saturation_fraction用sat_bits!=0，误把bit0的valid标志当成饱和。
   原字段三轮均1.0，实际含义只是“原始位非零率100%”，不能报告为饱和100%。
   按MultirotorMixer.hpp定义，bit1–10才是电机/轴/推力饱和位；三轮悬停sat_bits全部为1，
   有效反馈100%，有效样本上的真实方向饱和比例均0%。没有以此事后更改通过门槛。
2. 原perf正则匹配cycle而实际名称是cycle time，导致原描述字段为空；
   补充审计提取控制台两次真实计数，给出第5节近似频率，不声称原字段已记录成功。

复核命令（只读原始结果，在新目录输出，退出0）：

```bash
python3 -m unittest discover -s research/sta-velocity-control/scripts -p 'test_*.py' -v
python3 research/sta-velocity-control/scripts/audit_v00_results.py \
  '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V00/series02' \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V00/series02_descriptive_audit'
```

重分析使用另一个不存在的输出目录，勿覆盖已冻结证据。原判定分析器固定在飞行源码提交中，
后续使用它时应结合本勘误，不能复述错误字段名所暗示的饱和率。

## 7. 原始指纹、历史与提交

外部数据根：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V00。
本次verification04、series02、series02_descriptive_audit共139份文件纳入
[SHA-256索引](../v00/resume02/results/artifacts.sha256)。大型ULog只放外部，仓库只放摘要/索引。

| 完整飞行ULog | 字节 | SHA-256 |
|---|---:|---|
| run01/06_44_48.ulg | 29722613 | da2b22b5b1a6d5fcf8766b545a4b1c91e66a10ba309c6c65ada8b00ee6522404 |
| run02/06_46_39.ulg | 30447795 | 6b5148ee48ecd5916c74461d46808cb6a7e644e6545e22b4e54b4cdc58960041 |
| run03/06_48_33.ulg | 30110419 | 6896b183ec61c61b5dc5005631f5a97761a1f74a109d87318894b8fb245c188f |

每轮预热前的短启动ULog也保存于result.json及索引，未丢弃；原参数备份、完整运行参数、CLI、
world进程证据、样本和构建/测试日志全部保留。
V00历史累计：初次审计0尝试；批次01为1次启动失败/0起飞/2未运行；本批3次完整接受。
不能把旧批次未执行2次算成本批额外余额，也没有补飞或扩大本批3次预算。

结果提交仅含研究工具的描述性审计、测试、报告和小型证据，明确路径暂存并审查diff。
本结果提交完整SHA在提交完成后填入外部VELOCITY_STA_STATUS_CN.md，不在本文件伪造自身SHA。
V00前置验收通过，**不自动执行V01**；未push、未部署硬件、未恢复旧ISTA实验。
