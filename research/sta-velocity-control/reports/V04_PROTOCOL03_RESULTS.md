# V04 protocol03 / series02：起飞航向重置门槛失败

日期：2026-09-23。状态：**failed / needs_revision，不是依赖blocked；V04未通过。**

本次已完成用户批准的日志分类修订、隔离运行器/分析器、测试和源码提交，随后在干净源码上实际启动新批次。第一轮原PID起飞时触发冻结的reset计数门槛，立即停止，未重试/补飞/改阈值。

## 1. 源码与实际范围

- 协议/飞行源码：`965052446cf0d52c32e1e5641d90db0f96e9a5b4`，分支`research/sta-velocity-control`；开始HEAD `a367c7afa561e5f3829f39ad6092b51e63afd2bf`。
- 固件SHA-256：`43f48198934c483c1ef9cf5798b61b870098c54d7c4baa0010219b05c6cdfd54`，提交后重建版本头等于源码SHA；运行器核对启动前后固件未改变。
- protocol03 SHA-256：`bcc85869426017b4fa36b3c03eae40474f9acdb878788b06fccf72c1de3ceb0a`。
- 冻结142项资产、完整递归子模块及原模型/world/插件；Gazebo仍`822050a7ab6fd87972e59f16312f451bce217a56`。沿用`./sitl/run.sh --headless --backend gazebo --model iris`，仅Iris SITL，不是DP1000。
- 生产变更仅logger增加两个话题注册；控制律、Takeoff、导航、估计器和参数默认值均未改。原protocol01/02、原失败数据及分析器保留。

计划6次；实际启动/起飞1次、完整任务0、接受0、配对0；未执行5次。实际仅seed9201 PID，**ESTA飞行0次**。不得重用series02目录或把未执行五轮视为可直接续跑授权。

## 2. 实测失败时间线

| PX4时间 | 事件 |
|---|---|
| 30.008 s | 冻结地面位置/heading/reset计数，发送原起飞命令 |
| 30.028 s | 解锁，AUTO_TAKEOFF |
| 31.048 s | commander记录起飞检测 |
| **36.860 s** | local_position的heading_reset_counter从2变3；delta_heading=0.006559979 rad，约**0.375859°**；相对冻结地面高度约**1.599521m** |
| 36.976–36.988 s | 六个estimator_status实例先后记录mag_aligned_in_flight从0变1；主估计器实例保持1 |
| 37.036 s | 原起飞完成进入POSCTL |
| 37.120 s | 宿主轮询发现reset计数改变，抛出`Coordinate/reset changed: heading_reset_counter`，关闭本次自有SITL实例 |

此时尚未发送DO_REPOSITION，未进入三秒高度准入、32秒激励或60秒观察，更未执行正常降落。SITL关闭不是一次正常降落验收。

### 原因与可作出的结论

固定源码`src/lib/ecl/EKF/mag_control.cpp::checkHaglYawResetReq()`明确：离地后首次高于约1.5m时可请求航向重置，以摆脱近地磁干扰；`runInAirYawReset()`在成功对齐后置`mag_aligned_in_flight`。`EKF2.cpp`把四元数reset计数和delta_heading发布到local_position。
本轮小角度重置、首次爬升及空中磁对齐标志，与该机制一致；未观测到主估计器切换。日志未直接记录私有函数调用栈，不能把这一机制推断冒称逐函数跟踪。

**失败的是协议“从解锁前冻结后所有reset计数绝对不变”的条件，不是已经证实PID或ESTA失稳。** 该条件把原EKF允许的起飞对齐也列为中止；不能在看见本轮结果后直接豁免，再继续同一批次。

## 3. 日志检查与未完成项

已实际解码两份ULog，SHA逐份核验，dropout均0。主日志起飞后记录：

- 速度诊断712条，发布/更新序号连续，最大间隔12ms；速度实际MODE0/AXES0，角速度实际MODE0/AXES0/DIV1。
- first_fail=0、retry_result=0、pid_calls=1，最终输出valid=1；fault/sta_fault/excitation_fault/timing/failsafe均0。输入有效位按NaN通道语义独立核对通过。
- 角速度诊断1781条，序号连续，最大间隔4ms；未观察到旧同帧重算问题重现，但这里只覆盖本轮短起飞段，**不等于完整修复起降验收**。
- 激励尚未启动：excitation_peak=0，excitation_time=-1；PID轴ν为NaN。主日志navigator triplet4条、command_ack2条，新增注册可被真实解码，但尚无高度命令ACK或正常降落Gate2实测验收。
- 未获得完整主指标窗口，不计算/填补32秒RMSE，也不报告ESTA改善率。三对性能/非命令轴准入、正常降落分类和完整高度任务均未完成。

所有失败保留。seed9201已经消耗一次PID尝试；9202/9203未启动。没有加入新的种子或额外冒烟。

## 4. 测试、命令和退出码

| 实际验证 | 数量/结果 | 退出码 |
|---|---|---|
| 提交前最终`verify_v04_repair.py`（protocol03_verify02） | 104个不同C++、89项Python通过；两组2048步PID参考回归包含其中 | 0 |
| 提交后干净`verify_v04_repair.py`（protocol03_verify_committed01） | 同上104/89通过，SITL与DONT_RUN=1 Gazebo构建、1403字节消息格式和diff检查通过 | 全部0 |
| 新协议专属工具测试 | 19项，包含实际生产C++头文件轨迹、离线高度链、六轮预算及失败停/参数恢复模拟；计入89，不重复算独立飞行 | 0 |
| run_v04_protocol03.py --execute，确切源码965052446c… | 新批第一轮起飞reset检查失败，后续未启动 | **1** |
| audit_v04_protocol03_failure.py（两个独立输出目录） | 实际ULog只读诊断；第二次另加首次调用有效位核对，未改判原失败 | 0、0 |

初期尚未生成frozen.json时一次dry-run测试失败已在协议报告披露，随后修复配置文件并通过；不把这个工具开发失败算飞行。旧protocol02探针5通过/1协议失败仍保留。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
# 下列飞行命令已经执行并失败；只用于记录，不可直接续跑或复用目录。
python3 research/sta-velocity-control/scripts/run_v04_protocol03.py --execute \
  --source-head 965052446cf0d52c32e1e5641d90db0f96e9a5b4 \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series02'
# 可只读复核失败；输出目录必须另取不存在的唯一目录。
python3 research/sta-velocity-control/scripts/audit_v04_protocol03_failure.py \
  '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series02/run01' \
  --output <新的离线审计目录>
```

MATLAB、ESTA飞行、V05、旧ISTA及实机测试均未执行。

## 5. 数据、恢复与后续范围

外部目录：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series02`；验证目录protocol03_verify01/02/committed01、诊断目录protocol03_flight_audit01/02同级。
两份ULog均保留：启动日志`06_58_18.ulg`183,932字节、主日志`06_58_19.ulg`11,181,921字节，完整SHA见[run01索引](../v04/results03/run01.json)。共149份外部工件指纹见[artifacts.sha256](../v04/results03/artifacts.sha256)。仓库只纳入小JSON证据/索引，不提交ULog或二进制。

EEPROM全字节恢复为`06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`；自有PX4/Gazebo已退出，无残留实例。未动其他进程或删除日志。运行时SDLOG_PROFILE=147（原131 OR 16），原其他配置位保留。

建议的下一步**尚未执行/获准**：先离线审计起飞阶段首次正常航向对齐及delta_heading目标补偿，区分“坐标原点/位置速度reset”和“预期起飞航向对齐”；若修订准入，须重新明确适用阶段、次数/幅值/状态证据、观察段严格规则和新批次预算，先提交再申请飞行。不关闭EKF、不篡改计数或静默重冻heading，也不把本轮重分类为通过。

结果提交明确限制在只读审计、证据/报告和入口；完整结果SHA在提交后更新外部进度表。本阶段不push、不V05。
