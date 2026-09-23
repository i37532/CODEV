# V04 protocol08 / series07：姿态发布时间同刻，按协议停止

2026-09-23。**failed / needs_revision，V04 未通过。** 用户授权新批次后，完成重新冻结、协议提交、干净提交构建和离线回归，实际启动首轮PID。起飞及高度交接完成，悬停中因两条姿态消息发布时间相同触发既定严格递增检查；只完成约13.228s观察，未完成32s激励或降落。剩余五轮停止，ESTA未飞行，无补飞、调参、阈值修订、push或V05。

## 1. 冻结和版本

- 起点：IMU0转换修复 `1f743f779f591abd57585911f391f64f292497f9`；`research/sta-velocity-control`，初始主仓库及递归子模块干净。完整读取速度计划/共同规则、进度表、修复及前批报告；不回退、不清理旧数据。
- **协议/实际执行源码提交：`8df90c62a148d9b4b18c18e0c96796f1cebf932b`**。12个明确文件先提交，随后在干净提交重建、回归和飞行。仅隔离新批次入口/清单/资产，原运行及分析规则除绑定名称外逐字相同，并有测试；本轮未改生产控制/估计器/模型/参数默认值。
- [新协议](../v04/protocol08/README_CN.md)：9701 PID→ESTA、9702 PID→ESTA、9703 PID→ESTA，共最多6次。登记前21566份JSON无复用，登记后21569份，启动前21599份仍通过；仅允许新协议自身登记排除，历史空M06诊断例外保留。IMU显式播种，不宣称其他随机源独立；PID先行顺序偏差披露。
- 253项冻结资产包含修复后的Simulator、加速度驱动、VehicleIMU/Integrator、EKF消费者与消息/夹具，飞后全部一致。frozen.json SHA `2d2a08c935333c442bc26e65cbb2838c3eaa8fdafb3e57467e0811c2be318641`；execution SHA `fcffd1d0ce5f5cf1020516c88dcd27c681a6d318a5202ba82325187fc471afc8`。
- 固件SHA `9a18f907affbd4231e62603d2bd5db884887ef37343d88712e93b59ccd589f0a`，版本头与执行SHA一致。Gazebo子模块 `822050a7ab6fd87972e59f16312f451bce217a56`、ECL `b3fed06fe822d08d19ab1d2c2f8daf7b7d21951c`；完整递归版本及编译命令见冻结/验证证据。
- 项目启动器 `./sitl/run.sh --headless --backend gazebo --model iris`，实际Iris10016/quad_w、empty_grey.world、Gazebo Classic11.10.2、1倍速，不是DP1000。原位置P、Y/Z速度PID、姿态、全部rate PID不变。ESTA X候选λ1=1、λ2=.2、ν限.4/纠偏限.8不改，未实际运行ESTA。

## 2. 实际执行

| 项目 | 结果 |
|---|---|
| 计划 / 尝试 / 接受 | 6 / 1 / 0 |
| 完整观察 / 完整起降上锁 | 0 / 0 |
| ESTA / 配对 | 0 / 0 |
| 后续未执行 | 5，首个必需条件失败后停止 |
| ready / takeoff_command | 30.056s / 30.056s |
| reposition_command / handoff_ready | 38.436s / 38.756s |
| hover_start | 47.016s |
| 两条姿态发布时间 | 同为60.128s |
| 宿主最后检查位置样本 | 60.244s，即观察开始后13.228s |

运行器退出1，原错误 `ValueError('Empty/nonmonotonic vehicle_attitude')`。没有hover_end、land_command或landed_disarmed。最后记录仍为armed、AUTO_LOITER、空中；正常关闭自有SITL不等于完成降落。原始result和ledger失败保持，未更换目录/令牌续跑。

## 3. 原始日志说明了什么

[只读诊断](../scripts/audit_v04_protocol08_failure.py) 实际解码两份ULog，另外直接遍历ULog二进制记录，独立核对姿态消息原始时钟和载荷，未排序、去重、插值或补造数据。

| 原始记录偏移 | 发布时间timestamp（µs） | 采样时间timestamp_sample（µs） |
|---:|---:|---:|
| 18470941 | 60128000 | 60124000 |
| 18472270 | 60128000 | 60128000 |

- 两条四元数/载荷不同，采样间隔4ms，quat_reset_counter均3。这是**不同采样的消息发布时间相同**，不是同一消息被读两遍，也不是采样时间倒退。
- 整段12536条姿态记录：发布时间相等1次、倒退0次；采样时间非正间隔0次，间隔4–8ms。只读连续解析器与独立完整ULog的1049个字段数组完全相同；完整日志也复现同一拒绝，不是未完成文件尾部误读。
- [EKF2Selector::PublishVehicleAttitude](../../../src/modules/ekf2/EKF2Selector.cpp) 检查timestamp_sample递增后，以hrt_absolute_time写发布时间；观察到的不同采样同发布时间与该实现相容。**具体调度过程未跟踪，不能据此宣称所有同刻发布都合法或忽略所有重复时间戳。** 原协议data()要求timestamp严格递增，因此本次按冻结规则确实不通过。
- 已记录区间primary始终0；起飞后参考及位置/速度reset不变，任务yaw冻结后heading reset也不变。未出现上批的降落主EKF切换，但**本轮未飞到降落，不能据此验证IMU0修复的降落效果**。
- 两个ULog dropout均0、无解析损坏。实际速度MODE/AXES=0/0，rate MODE/AXES/DIV=0/0/1，MC_RATT_TEST=0、MC_STA_TKO_MGT=0、SDLOG_PROFILE147；3027条起飞后有效速度诊断中首次失败/重算/控制fault/failsafe/timing均0。速度及rate发布序列连续；实际速度采样8/12ms，rate4ms。
- 激励时间仅记录0–9.8600006s，未达到32s；不计算/报告原32s主RMSE、60s观察指标、配对改善率或完整下游覆盖。不把部分健康日志等同整轮安全验收。

15项只读诊断断言通过只说明证据核对成功，**不是15项飞行验收通过或新增gtest**。完整新批分析器在独立目录重放仍accepted=false、缺hover_end，退出1；旧结果未改判。

## 4. 实际验证及退出码

环境和命令前缀见新协议。外部总目录为 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04`。

| 命令/输出目录 | 结果 / 退出码 |
|---|---|
| verify_v04_protocol04.py --output .../protocol08_verify01 | 222Python中1项新增夹具历史文件名引用错误；1，保留失败 |
| 同上 .../protocol08_verify02 | 109个不同C++/222Python、SITL/测试/DONT_RUN Gazebo构建通过；0 |
| verify_v04_imu0_repair.py --output .../protocol08_imu01 | 11个真实链C++与同11个sanitizer、2048帧等价；0 |
| 干净提交 .../protocol08_committed01 与 .../protocol08_imu_committed01 | 再次109+11不同C++、222Python、全部构建与转换链检查通过；各0 |
| run_v04_protocol08.py --execute --authorization V04-protocol08-series07-six-attempts --output .../series07 --source-head 8df90c62a148d9b4b18c18e0c96796f1cebf932b | 首轮日志必需条件失败、余五轮停止；1 |
| analyze_v04_protocol08.py .../series07/run01 --output .../protocol08_reanalysis01 | 不完整观察，accepted=false；1（预期） |
| audit_v04_protocol08_failure.py .../series07/run01 --output .../protocol08_audit01 | 15项只读证据检查成功；0 |
| python3 -m unittest discover -s research/sta-velocity-control/scripts -p 'test_*.py' -v | 结果阶段222项通过；0 |

120个不同C++=109原控制/保护/生命周期/姿态+11转换链；多次执行及sanitizer重复不累计。原PID两组各2048步等价继续通过。旧Simulator运行新方向/clipping测试预期1失败/退出1，独立保留为负对照，不能称旧实现安全通过；历史失败日志分析同样预期拒绝。未执行MATLAB/Octave、ISTA、V05或实机。

## 5. 原始数据与完整性

大型日志留在新series07，仓库[results08](../v04/results08/)仅小证据/索引。验证、失败夹具、诊断与重分析全部保留。

- 主ULog `12_25_16.ulg`，18543593字节，SHA `de1f5a137d2d583621d684e751004cc18bc620d41850412368e39f6cb7380d34`。
- 启动ULog `12_25_15.ulg`，192990字节，SHA `1ef6a9fd58ae673d6c297a04a6cec1f9488bde5bf6f1b7440c4db8f0af1220ae`。
- 新41份原始工件全量指纹通过，索引SHA `f9738998cf36f140e52da8334b89b6285370b28a5270eaead7f08831c9ab7d33`。
- 另263份离线验证/诊断工件全量校验通过，索引SHA `aa71f001fcd9d9e90e632e2502486a5535344c093399f678d2cefb43c475b777`。
- 原42份上批工件、59份EKF审计、175份IMU0链审计、84份转换修复工件及本批253资产全部未变。
- 原EEPROM逐字节恢复，SHA仍 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`；无残留模拟器。

## 6. 结论和停止点

本批1尝试/0接受，累计七批7尝试/0接受、ESTA累计0；前批series05曾完整飞完但日志验收失败的事实保持。V04仍failed/needs_revision，不是依赖缺失blocked。

结果另作明确范围提交，完整结果SHA写外部实时进度表；不修改已冻结执行资产。下一步建议**先离线审计姿态发布时钟与采样时钟的不同语义**，覆盖同刻不同sample、重复sample、倒退、缺样、reset和异步配对，再决定是否修订日志规则；不能直接删除检查、去重原始记录、续跑五轮或把本轮改判通过。此处停止，不push、不V05。
