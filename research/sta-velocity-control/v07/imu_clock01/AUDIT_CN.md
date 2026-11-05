# V07 IMU 双时间离线审计与 protocol02

2026-09-29。起点 `99cd43dcb4c344f471ea6bc5ccb339c3adcfcfd1`，分支research/sta-velocity-control，开始主仓库及33项递归子模块干净。用户授权先离线审计、再持续完成V07；普通相关修订和各自冻结的有限新批次无需逐次请求。没有授权通过重复抽种子、删除失败、放宽安全/性能阈值求通过；每批首个失败仍停止后续清单，先查明原因再决定范围内修订。不push、不V08、不实机、不扩大上游控制/估计器修改。

完整读取速度计划/共同规则/历史进度与V07报告；V06通过及其日志经验已核对。原V07源码c8319664a09bea74fec5d352f478bad4bcf6dc0a及结果99cd43dcb4…仍保留。旧protocol01/日志/原判不改。

## 1. 两个时间不是同一个契约

源码事实（本仓库，不外推所有PX4版本）：

- `VehicleIMU.cpp:467`将最新陀螺采样时刻赋给timestamp_sample；`:474`用hrt_absolute_time赋timestamp。两个积分时长是uint16微秒，积分值是rad与m/s。
- `VehicleIMU::Run`虽然循环消费传感器队列，但Publish成功后立即return（约209行）。因此**不能称同一次Run循环必然连续发布两条**。不同Run可处于同一HRT时刻。
- POSIX `drv_hrt.cpp:134`的锁步分支返回仿真绝对时间；lockstep_scheduler.cpp:48仅由set_absolute_time推进。一次发布不会主动给HRT加1。
- `platforms/common/uORB/uORBDeviceNode.cpp:252`每次写递增generation并复制载荷，不以timestamp作为消息唯一键。
- `EKF2.cpp:316–336`按uORB代次取消息，使用timestamp_sample与delta_angle_dt/delta_velocity_dt，不靠publication timestamp差构造IMU积分h。
- logger按订阅消息复制载荷；日志字段发布时间不是额外的宿主接收时钟。因此同刻发布不自动等于同一样本。

真实C++链离线用例 `ImuPublicationClockTest.cpp`：调用当前Simulator传感器转换→驱动→VehicleIMU::Run→uORB，仅测试内固定HRT并禁用异步调度。三个实例均得到相同发布时间、相隔4ms的sample、递增generation、不同积分值、4ms积分和零clipping。**1个实际gtest通过**，不是3次飞行，也不证明旧第11轮的精确调度过程；未重放完整EKF异步融合。

旧第11轮的两条140.508s消息，sample为140.504/140.508s，符合上述可发生语义。旧完整验收仍failed，新规则只产生另存的探索性分项诊断。

## 2. 新规则：只在vehicle_imu三个实例启用

新 `protocol02/imu_health.py` 同时接入尾段采集和最终完整分析。旧 `postland.py/landing_health.py`、旧分析器以及生产C++不改。

- 不排序、不去重、不合并、不插值、不改任何原始时间戳。publication允许相等但不许倒退；sample须正整数、严格递增且不得晚于publication。相同sample即使载荷完全相同也拒绝。
- 全日志先检查双时间结构、记录长度、顺序；健康窗口同时覆盖两个时钟的前驱/后继。取窗口边界的完整同publication组，而非只取其中一条；实际更晚发布时间才能封闭末端组。在线尾组未封闭是pending，不是成功。
- 保留原12ms publication缺口上限，并增加sample缺口及发布年龄≤12ms检查；12ms/12ms+1μs边界均有反例。这是离线证据域，不修改控制dt或保护阈值。
- 窗口内两个积分时长有限正数且≤12ms、两组三轴积分有限、clipping为0、设备ID非零稳定、calibration_count稳定；完整边界组也检查。缺字段不补零。
- sensor_accel、六EKF status和selector的原严格发布时间/窗口/缺口/截幅/切换检查保留，不给其他话题隐式豁免。
- 原15s尾段采集超时、必须已落地上锁/无failsafe等条件不变。目标交接、姿态白名单、速度/角速度模式与主指标链不改。

重要限制：旧合格日志也存在8ms采样记录间隔而delta_angle_dt为4ms，故不能新增“每条记录必须连续4ms”后再假称旧证据无损。新输出披露`recorded_gap_not_equal_integration`，保留原最大缺口门槛；**这只是有界的记录覆盖，不证明每个IMU消息都被logger/EKF完整消费**。控制诊断完整性规则独立保留。

## 3. 负例与回放

新增20个Python测试：三实例正例、同刻不同数据、输入不变、重复/倒退/未来/非整数/缺字段/长度、其他话题仍拒绝同刻、积分时长/数值/设备/标定/clipping、起止同刻组、双时间边界、12ms邻点、窗外倒退、尾组pending/超时/重新解锁及运行器/最终分析同一函数接线。既有28项初跑包含8个被import的旧测试，随后改为模块引用，最终新用例计数20，不重复累计。

`imu_clock01/replay.py`只读回放30轮主ULog：V07旧11轮、V06最终18轮和V06旧真实截幅失败1轮。28轮旧成功健康检查仍通过；V07第11轮旧publication规则拒绝、新双时间健康组件通过；真实截幅失败继续拒绝。每轮原result/job/metrics/ULog等输入前后SHA相同，**所有探索输出accepted=false，不追认旧失败，也不替代新飞行**。

外部根 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V07`：clock_chain01、clock_replay01、imu_tests01.log及verification_working01。初版C++证明退出0；最终原子时钟开关版由完整verify再次编译/实际运行通过。预提交完整回归216个不同C++、448个Python，SITL/Gazebo构建均退出0。正式仍须在最终干净协议提交复核，结果另记。

开发工具记录：批量protocol01 JSON传回和全量回放摘要传回各发生一次工具输出截断，解析/长度守卫拒绝，均未写对应文件或飞行；改为逐文件读取、紧凑摘要并apply_patch。两次只读源码搜索使用了错误旧路径，已定位真实文件；不冒称这些搜索成功。没有生产修改或飞行失败因此隐藏。

## 4. 新有限预算

protocol02与旧版本相比仅新IMU健康策略/接线、审计/回归、版本/种子/证据目录；控制律、参数、速度DIV时序、任务、数值性能/安全门槛及合格Iris接触保持。

- 新29001–29003：DIV1 PID→XY ESTA，各3轮。
- 新29004–29006：DIV2相同6轮，必须DIV1全部通过。
- 新29007–29009：DIV4相同6轮，必须DIV2全部通过。
- 合计18次；全部重新运行，不把旧10次与新样本拼接验收，不续用旧7次余量。每批首个必需失败停止，保留全部数据；没有额外调参/冒烟预算。
- 原固定yaw低速8字、约2.5m、30s预热/90–92s观察/64s两圈/降落上锁；XY ESTA+Z速度PID，全部rate PID；项目原Gazebo启动器。
- 新种子须先完整历史登记复查，先提交协议/源码→干净构建与非零回归→绑定当前授权和确切SHA/18次→执行。源资产包含IMU/时钟/uORB/EKF/logger链。

本文件是离线审计和新批飞前协议，不预写飞行验收通过。最终完整SHA、实际次数、缺失和结论写V07报告/外部进度表。
