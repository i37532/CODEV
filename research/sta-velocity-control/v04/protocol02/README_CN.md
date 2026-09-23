# V04 protocol02：明确高度目标的新批次协议

日期：2026-09-23。**设计冻结、飞行待授权；运行器/分析器适配尚未完成，不能直接运行旧入口。**
本次用户仅要求重新冻结高度任务与验证协议、随后申请新批次；实际新增飞行0。

## 1. 修订理由和范围

旧protocol01首轮PID失败及其原始日志全部保留：高度1.9669m未满足2.0–3.0m入口，且起飞同帧重算锁止激励。
修复提交`65d1b5c4e2177547e369ba2a750581f1bb894c56`解决目标缓存/同帧失败处理，但**没有解决任务层转Hold后高度目标降低的问题**。
不能把“导航认为起飞完成”当作“实验已达到2.5m”，也不能把旧失败PID与新源码ESTA配对。

本协议不改Takeoff、NAV_MC_ALT_RAD、位置P、Y/Z速度PID、姿态/rate PID、HTE、滤波、模型或ESTA候选。
保留MIS_TAKEOFF_ALT=2.5、MC_RTC_MODE=0、MC_STA_AXES=0、MC_RTC_DIV=1、MC_RATT_TEST=0、MC_STA_TKO_MGT=0。
PID为速度MODE0/AXES0，ESTA只为MODE1/AXES1；X是本地NED北向，不是roll；3/7仍拒绝。
四个X候选值仍为lambda1=1、lambda2=0.2、nu限0.4、纠偏限0.8；不增加候选或调参次数。

唯一数据源为[protocol.json](protocol.json)：按其中`inherit.sha256`核对旧JSON，只继承列出的明确字段；未列出的旧sequence/jobs/authorization等不能混用。
旧安全、性能和日志数值条件不放宽。旧文本中“未来授权/原failsafe不变”仅是历史描述，以本次协议和REPAIR01的明确差异为准。

## 2. 每轮高度任务

1. 全新启动Iris和原项目启动器，1倍仿真，预热至少30秒。确认估计器、global/local reference有效、参数和实际内环PID正确，备份完整EEPROM。
2. 起飞前最后一份有效local_position冻结地面z、heading、ref_alt/ref_timestamp及reset计数。定义实验高度`H=z_ground−z`，目标`z*=z_ground−2.5`，全局高度`alt*=ref_alt−z*`。这是估计相对高度，不是Gazebo真值/地形测距。
3. 沿用`commander takeoff`。等待原起飞流程完成并进入armed、airborne POSCTL；**不发送旧的当前位置Hold命令**。
4. 在已有本地MAVLink连接发送**一次**DO_REPOSITION：param2=1请求AUTO_LOITER，param5/6=NaN保留原有效起飞XY目标，param7为上述明确alt*；固定yaw，其他字段见JSON。不新增Offboard/trajectory/姿态/角速度发布者。
5. 核对新鲜ACK、实际模式、navigator目标回读；ACK成功本身不等于导航目标已接受。检查XY未改、alt误差≤0.02m、yaw差≤0.001rad。任何错误/超时均停止，不能自动重发。
6. 连续3秒满足：高度2.0–3.0m、|vz|<0.2m/s、最终轨迹z接近z*（≤0.05m）、轨迹|vz_sp|≤0.05m/s；armed/AUTO_LOITER、非landed/ground_contact、估计与诊断有效。禁止用“高度>1m”作为另一套稳定门槛。
7. **通过后才写hover_start**，观察60秒（允许60–62秒采样边界），随后原auto:land，核实落地且自动上锁。稳定候选窗口也保存，实际ULog必须独立复核连续3秒。

起飞到入口墙钟总超时150秒；启动/预热各180秒、观察240秒、降落150秒。期限不由失败数据延长。
地面参考、原点或EKF reset计数在armed期间改变，本批拒绝；不通过重定参考“消除”高度误差。正常模块reset功能仍保留，这只是小幅配对实验的拒绝规则。

### 本仓库命令单位的特殊处理

已静态核对当前源码链：`mavlink_receiver.cpp::handle_message_command_long`直接复制param4，Navigator DO_REPOSITION直接存入yaw，FlightTaskAuto按弧度消费。
因此本地专用入口必须发送**冻结heading的弧度原值**，并核对下游yaw；不能照通用外部工具习惯再转成度，也不把此行为推广为其他PX4版本的接口约定。
该适配仅针对冻结CODEV源码；飞前必须补±pi/2、非零yaw、NaN XY、float32高度编码/回读测试。无需修改上游MAVLink或Navigator。

## 3. 与既有激励时钟的关系

不改控制器激励：第一次有效空中AUTO_LOITER开始12秒等待，然后32秒X速度波形：
`0.2*sin(2*pi*t/8)*sin(pi*t/32)^2`。原位置P继续作用；波形积分为零不保证实际净位移为零。

高度入口必须在**该门禁起点后10秒内**通过，给12秒激励起点留出余量。门禁起点由`timestamp_sample`和`excitation_time`回算，不能拿宿主收到消息时间代替。
若到期仍未准备好，则停止本轮；不能推迟/重启激励、先激励再挑后面的窗口或边爬升边计算主指标。60秒观察必须完整包含[0,32)激励窗口。
在线轮询只检查所见样本（最大间隔1秒），实际ULog稳定/主窗按≤40ms间隔复核，不把稀疏CLI当作高频连续证明。

## 4. 新预算与验收

申请独立新预算最多6次，不复用旧剩余5次，无额外冒烟、补飞或调参。

| 顺序 | 开发种子 | 速度算法 |
|---|---:|---|
| run01 | 9201 | PID |
| run02 | 9201 | ESTA X |
| run03 | 9202 | PID |
| run04 | 9202 | ESTA X |
| run05 | 9203 | PID |
| run06 | 9203 | ESTA X |

每对先PID确认修复后任务，再ESTA；整对通过才进入下一对。此顺序不是随机化，报告披露顺序偏差。
沿用隔离IMU显式seed插件和相同噪声方程；GPS/mag/baro默认随机源与宿主调度不独立播种。
种子需历史登记审计，飞前再查期间是否被其他任务消耗。同seed前5000条创新差<1e-10、不同seed差>1e-6，不将六次称六个全随机独立样本。

主指标仍为完整32秒内实际消费`v−v_sp`的X速度时间加权RMSE，Y/Z同窗单列；每对逐轴ESTA≤1.25×PID+固定容差（X/Y0.02、Z0.01m/s）。
60秒位置各轴≤1.25×PID+0.05m、yaw RMSE≤1.25×PID+0.02rad。倾角≤15°、XY偏移≤2m、水平速度≤1m/s、观察高度误差≤1m、|vz|≤0.6m/s；起降垂速≤3.5m/s。
限制比例≤5%、连续≤0.5秒；无fault/failsafe/termination。日志序号/时间完整，dropout0，下游精确匹配≥80%、差0、最大间隔≤0.25秒，完整继承旧JSON的其他检查。

新增REPAIR01字段为必需证据：`first_fail=0`、`retry_result=0`、`excitation_fault=0`；缺字段不能补零。`first_input`按目标使能语义解码，不要求所有NaN关闭通道有限。
即使第二次update成功，也因第一次失败拒绝本比较轮，不能用最终valid=1掩盖。真实短帧可能在线轮询未见，但离线检查失败后不得开始下一轮。

每轮启动自有项目启动器前即消费一个attempt；启动/日志失败也保留且停止后续。仅分析工具纯离线失败不算飞行，但修复分析器必须记录版本和原结论，不能变更门槛。
不补齐、不插值、不填零；不足六轮/三完整配对不能验收V04。通过是开发准入，不是显著优于PID或实机安全证明。

## 5. 飞前尚需完成的接线与授权

**本次是协议设计冻结，不是可执行飞行包验收。** 当前`run_v04.py`硬编码protocol01并调用旧起飞转Hold；当前`analyze_v04.py`不检查新增first_*字段。禁止把两者直接用于本批。

下一执行任务须在本设计内新增隔离入口`run_v04_protocol02.py`和分析器`analyze_v04_protocol02.py`：

- 复用项目启动/进程归属/参数恢复，接上一次明确高度命令、ACK/回读、稳定门禁、事件顺序和超时；同一MAVLink连接串行发命令，禁止额外目标发布者。
- 真实日志检查命令→triplet→trajectory→消费目标；若必需话题未记录，在不覆盖profile位的前提下显式注册，先检查格式与订阅容量，不用CLI证据冒充完整ULog。
- 测试错ACK/错目标/弧度与度、边界/缺测/reset/时钟/超时、激励未准备、首次失败/重算、失败停止、预算和原字节参数恢复。
- 复跑REPAIR01全部C++/Python和新用例，SITL/Gazebo只构建。离线失败时不得启动Gazebo“探一下”。
- 明确文件列表提交源码/协议引用/展开配置，干净提交重建并固定source/firmware/model/world/plugin/参数及分析器SHA；记录递归子模块。设计提交不能冒称最终飞行源码。

任何实现发现需要改控制器/Takeoff/导航逻辑、改变本协议任务/门槛/候选/预算，停止并再次申请，不在本授权中夹带。

拟用新目录：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series02`，若已存在必须拒绝，不能覆盖或断点续跑。
旧protocol01/results01/repair01和外部失败原始日志不改；新结果单独提交，外部进度表记录协议、执行源码和结果三个完整SHA。不push、不V05、不ISTA、不实机。

**待用户确认：是否允许在上述新入口/分析器离线验收并提交后，执行该6次上限的新Iris SITL批次，任何必需检查失败立即停止？**
