# R03：XYZ降落期EKF超时的离线审计

2026-10-20。**R03尚未验收；此次不是打印误差。状态为needs_revision（上游原因/范围），不是预算待批准。** 本文只报告已发生的revision06 run030与只读审计，不修改控制律、参数、传感器、估计器、模型、监视器或原判，不签发新飞行资格。

## 1. 发生了什么

本批源码`ae61c29f6ed37e67a64ff29f952a45554e11096b`，PID与R-STA前两轮完整接受。第3轮原ESTA/XYZ完成90秒观察后，在降落末段被正确拒绝；结果账目与指纹见[停批报告](R03_REVISION06_STOP.md)。

| 原始仿真时间 | 事实 |
|---:|---|
| 137.524s | 已完成观察，记录land_command |
| 145.064s | vehicle_land_detected已记录landed=true |
| 145.136s | IMU0、EKF0姿态/状态仍有正常发布；原完整历史组件检查到此通过 |
| 145.160s | selector主实例0→5；console明确`primary EKF changed 0 (timeout) -> 5`；仍armed |
| 145.160s | 新位置参考高度和XY/Z/速度/heading reset计数改变 |
| 145.164s | IMU0和EKF0/3姿态恢复发布，但对应sample为145.140s，年龄24ms |
| 145.168s | EKF0状态发布，对应sample为145.144s |

失败CLI位置的timestamp=145160000、timestamp_sample=145156000，打印年龄0、宿主命令约2.269ms。前一次完整raw检查水位145.004s，年龄40ms；本次尚未执行增量读取，就在参考比较处拒绝。没有证据支持将它解释为500ms日志读取超时。

参考高度从binary32的488.4769592285156m变为488.4143371582031m，差值**−0.0626220703125m = −513/8192m = −2052个ULP**。两者按既定四位小数打印分别为488.4770和488.4143；CLI与新raw打印完全一致。这是两个估计实例参考的真实差异，不是实际飞机瞬移6.26cm，也不是float舍入应有的误差。

## 2. 为什么不能只改检查器

原检查器离线重现：包含145.160s前的最后位置记录145.136s时通过；包含切换记录立即报`Coordinate/reset changed: ref_alt`。在线CLI检查、raw heading/reference检查以及最终landing health的primary约束是独立防线，跳过第一项不会使其余项合法。

既定规则从任务yaw冻结到降落上锁都不允许primary/reference切换，见[V04原规则](V04_PROTOCOL07_RESULTS.md)及[降落EKF审计](V04_LANDING_EKF_AUDIT.md)。此时虽landed，但仍armed，不能把异步CLI状态当作已上锁，也不能删去着陆尾段、重置reference或增大容差来获得通过。

原selector默认状态超时50ms；若最近姿态发布时间距当前超过10ms，状态超时收紧为20ms。145.160s时最后记录姿态与status sample为145.136s，年龄24ms，与timeout切换的源码条件和console原因一致。原健康逻辑不应被提高超时或强制锁定EKF0绕过。

当前日志显示IMU0的vehicle_imu先发生输出延迟，EKF0/3姿态沿同一延迟链变化；IMU1/2未出现同段停顿。sensor_accel0在该窗口仍有每4ms记录且clipping=0。切换前没有已记录的新EKF0姿态可以通过发布guard恢复输出，因此**没有证据指向此前修复过的“拒绝旧sample仍污染发布状态”缺陷复发**。

进一步补查原始gyro：本轮sensor_gyro仅1Hz，三个实例在上述窄窗均无记录，最近为144.608s；FIFO未记录。已有高速日志位补充的是accel、vehicle_imu和estimator_attitude，并未补齐gyro。VehicleIMU由gyro回调驱动，输出sample取最后已消费gyro sample，pub取当前HRT。因此现在不能区分“gyro源晚”与“积分消费/工作队列晚”。原actuator_armed、vehicle_status和速度诊断均支持切换时仍解锁；没有成功disarm证据。

已读源码：`src/modules/sensors/vehicle_imu/VehicleIMU.cpp`的队列/积分与发布流程，`src/modules/ekf2/EKF2Selector.cpp`的UpdateErrorScores、Run与PublishVehicleAttitude。没有selector每次实际消费/工作队列调度追踪，单凭ULog不能锁定具体阻塞点，也不能断言是CPU不足、CLI负载、真实传感器故障或ESTA控制律造成。六个EKF近窗已记录status的filter_fault_flags为0，不夸大为每个内部时刻都无故障。

## 3. 已执行的离线检查

外部根：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_reference07`。以下脚本均实际exit0，输出是诊断、不是飞行接受；脚本/输入/输出SHA另存索引。

| 入口 | 实际范围 |
|---|---|
| offline_chain01/audit_chain.py --output .../results03 | 三轮CLI/监视器调用链；PID/RSTA各286/294个armed参考检查无拒绝，ESTA280个中最后1个拒绝；原文件及源指纹保持 |
| offline_numeric01/diagnose.py | 单次解码失败主ULog；binary32有理数/ULP及CLI比较；原raw组件截止边界通过/拒绝对照；49输入首尾指纹保持 |
| offline_timeout01/extract.py | 单次解码145.120–145.176s含前驱时序，IMU/各EKF/selector与原源码条件关联；不修改原记录 |
| offline_timeout_gyro01/extract.py | gyro/FIFO可观测性、原armed证据和VehicleIMU/日志配置源码核对；确认关键gyro窗口缺失，未填造 |

四份审计收据及其脚本/简报共12个文件的路径、字节和SHA-256见[AUDIT_INDEX.json](../regularized_sta/r03_reference07/AUDIT_INDEX.json)。主代理又实际校验四收据SHA、数值差、原组件边界通过/拒绝与非授权标志，退出0；这是收据/诊断核对，不算额外飞行或控制单元测试。

草拟索引后首次全文件核验exit1：代理同时把gyro简报中“采样比发布晚”纠正为“采样早于发布24ms”，该简报SHA变化被检查捕获。仅更新这份未冻结说明文档的索引；四份诊断收据、脚本、原始输入和原判没有改变。补充正文patch曾因待匹配文字不符未应用，按原文修正后成功；不把编辑/索引检查失败称控制测试失败。

原主ULog无dropout、无corruption不等于所有内部消费时刻均可观测。独立诊断拒绝是预期检出，不把它算作失败轮通过。更早干净qualification中的513个C++/1688个Python不冒称在此次诊断里重新执行；本轮新增C++控制测试0、飞行0，未执行MATLAB或实机。

额外只读检索猜测`audit_timeout.py`文件名返回exit1、猜测`CHAIN_AUDIT_CN.md`返回exit2；实际分别为`extract.py`和`README_CN.md`，随后用rg确认。它们是检索错误，不是控制测试失败。链审计首次误指不存在cli_clock路径、第二次因原Infinity序列化失败，已在外部README记录；最终仅诊断JSON保留原遥测非有限标记，不将其作为合格样本，也不隐藏前两次开发失败。

## 4. 下一步及当前边界

用户已授权必要有限预算调整，不需要再批准“58→61”的用量本身。但是[连续执行边界](../regularized_sta/AUTHORIZATION_CN.md)和[本版边界](../regularized_sta/AUTHORIZATION_R03_REVISION06_CN.md)明确排除上游/传感器/估计器修改，必要范围扩大时需停止说明。

当前没有经过证据支持的运行器内修复，不能原样换种子重飞赌成功。合理下一步是**扩展为上游IMU积分→EKF→selector超时/工作队列链专项**：先离线复现和确定所需观测；若旧日志不足，另冻有界SITL诊断及遥测；仅在证据支持后做最小修复，回归真实上游函数、旧PID/ESTA/R-STA、时间与安全路径。不得直接提高超时、关闭多EKF/切换、改变控制参数或放宽原验收。

上游改动可能影响既有A/B/C证据适用性，不能预先保证只需新D9。需先证明哪些路径行为保持、决定有限桥接/重验范围，再冻结准确新预算/清单/来源。若最终只需重做D9，总量候选为61=已用52+9；**现在未激活新预算、未登记新种子、未开始新飞行**。

当前52尝试/51起飞指令/46接受/6失败；完整A/X、B/Z、C/XY门各9接受保持其原历史结论。D只有本批2部分接受，仍无完整gate_pass。失败、六项未执行和全部原日志保留；阶段不push、不进入R04/R05。
