# V04 目标交接修订：离线通过，未飞行

日期：2026-09-23。范围：用户仅授权“先离线修订目标交接逻辑并补齐测试”。
状态：**offline_passed / awaiting_separate_batch_freeze**；不是V04飞行验收通过。

## 1. 结论

已将准备阶段的目标交接修订为：

`原起飞 → POSCTL与航向准入 → 读取原本地XY保持目标 → 明确经纬度/高度/yaw的单次COMMAND_INT → ACK与Navigator目标同时确认 → 原3秒高度入口 → 原60秒观察/32秒激励 → 原计划降落`

不再要求POSCTL阶段存在有效Navigator航点，也不直接跳过检查发送“XY忽略”的高度命令。原位置P、速度PID/ESTA数学、姿态/角速度PID、Takeoff/估计器、模型/默认参数都未改。

本次启动0、飞行0、种子消耗0；旧四批4次尝试/0接受、ESTA飞行0保持原判定。新入口硬性拒绝启动：没有新预算、新种子、新执行快照或新批次运行器；不是“已可以直接续跑剩余五次”。不push、不V05、不实机。

## 2. 核对与源码审计

- 开始分支`research/sta-velocity-control`，HEAD `2522940fbc0038e1dd170a7207e74190d86552ab`，主仓库及递归子模块干净。完整阅读外部速度计划、共同规则、实时进度和protocol05失败报告/前置协议。
- Gazebo子模块`822050a7ab6fd87972e59f16312f451bce217a56`、ECL`b3fed06fe822d08d19ab1d2c2f8daf7b7d21951c`。Iris限定及原项目启动器仍保留在隔离入口，但此次不调用。
- `navigator_main.cpp`：POSCTL没有活动Navigator模式，会清空triplet；高度单独修改分支复制current.lat/lon；明确有限XY走指定经纬度分支。`loiter.cpp::reposition()`复制reposition目标，而非另生成目标。
- `Commander.cpp`对DO_REPOSITION的param2位0请求切AUTO_LOITER，并负责ACK；Navigator不重复ACK。因此ACK只证明模式请求被接收，仍必须读回真实目标。
- `mavlink_receiver.cpp::handle_message_command_int()`把整数XY除以1e7保存为double，z为AMSL float，param4直接传递。本版Navigator把param4当弧度；这是固定版本语义，不推广到其他PX4/MAVLink实现。接收器未把COMMAND_INT的frame存入vehicle_command，发送端只准frame=5，并在源记录/二进制包测试证明；不能声称ULog包含未记录的frame。
- 补充上轮审计：`FlightTaskAuto.cpp`遇到NaN全局XY时可以锁定当时实际本地位置，并不必然报failsafe。但这不能证明保持之前POSCTL的目标不变，因此本次选择显式保留原目标，而非依赖这一隐式回退。
- 完整源码/投影库/消息指纹见[真实日志与编码证据](../v04/handoff06/evidence.json)。无上游源码修改，无新增目标发布者；仍由Navigator→FlightModeManager→原位置/速度链路生成目标。

## 3. 新交接契约与实现

隔离文件：`v04_handoff06.py`、`run_v04_flight06.py`、`analyze_v04_handoff06.py`、`analyze_v04_flight06.py`；旧04/05脚本、冻结协议、失败结果和原始数据不覆盖。

| 项目 | 新规则 |
|---|---|
| XY来源 | 原始ULog中最新已验证位置sample所对应的、年龄≤40ms的trajectory_setpoint.x/y；均有限。不是测量实际位置、不是旧空triplet、不是Gazebo真值 |
| 前置 | 原首次磁对齐/1秒POSCTL安静段和一次task_yaw冻结继续有效；原reference及p/v reset严格不变；armed、airborne、无接触且仍POSCTL |
| Z混合 | 源Z位置可为NaN，但z/vz/a_z至少一项有限；不错误拒绝原制动阶段的有限vz。真正高度入口仍要求原高度位置目标和低vz |
| 坐标 | 固定原NED参考，ECL等距方位投影；XY不随机头旋转，不重新冻结地面/原点。源保持目标须在原2m水平包络内 |
| 编码 | 单次COMMAND_INT，明确lat/lon整数×1e7、原2.5m高度对应AMSL float、冻结yaw float；无COMMAND_LONG全局坐标精度损失、无额外模式命令 |
| 数值误差 | 经纬度取最近1e-7度，再投影回XY；编码偏差≤0.02m。这是新接口精度门槛，不是放宽飞行跟踪误差。范围限±85°、本地10km内，实际任务仍2m包络 |
| 应答/读回 | 保留5秒壁钟预算；ACK和目标可以异步到达。待两者及AUTO_LOITER一致才准入；暂时空/旧/未匹配目标只记pending，不当成功。不重发、不延长原150秒准备预算 |
| 故障 | 拒绝/重复/未来ACK、时间倒退、超时、准入后目标/模式丢失均锁存；发送前保存尝试，发送异常不重试。原始失败数据保留 |
| 表示/原始值 | CLI与实际6位经纬度/4位float显示比较；ULog按编码后的double/float精确比较。原始微小漂移不能被CLI舍入隐藏 |
| 下游 | 3秒入口和观察段的trajectory XY及实际消费p_sp XY均有限、距离编码保持目标≤0.05m；原Z/yaw/安全/性能/激励/时间门槛保留。新的XY目标一致性检查不替代实际轨迹误差 |

在线准备/观察均接入目标检查；完整原始日志再核对命令唯一性、来源、目标、时间和连续性。线上轮询仍不是每个飞控sample即时中止保证。准备段允许异步pending不豁免原控制fault或错误参数。

`handoff_ready`事件在读回成功后重新读取位置时间，避免把应答/目标成立前的旧时间戳记成准入时间；tail快照先于CLI当前时间读取，避免把正常新日志误判成未来。观察窗按原半开区间处理，恰在hover_end开始的计划降落不混入悬停目标。

## 4. 真实证据与测试

真实只读回放series04主日志，SHA `88b9cd401f5e410dac6b50f6ee07073597b01a7a7e910646fe89d321f429e086`：

- 位置sample38.096s，对应目标38.084s，年龄12ms；原保持XY≈(−0.0130653, 0.0329855)m。
- 编码为lat=47.3977507、lon=8.5456077，回投影XY≈(−0.0111195, 0.0301074)m，误差**0.003474m**。
- 同坐标若使用COMMAND_LONG float32 XY，此例误差约0.023069m；这是该样本的数值演示，不是飞行数据或对所有经纬度的统一误差断言。
- 真实pymavlink生成/解码二进制包，确认COMMAND_INT、frame5、system/component255/190、整数坐标、弧度yaw和高度；记录packet hex。未向网络或飞控发送。

新增**25项Python测试**覆盖：真实失败ULog、CLI旧异常可复现、命令包编解码、NED方向/符号/投影范围、无效/半组XY、合法混合Z、坐标/primary/航向和状态前置、目标时效、一次发送、发送不确定异常、应答先后/错源/旧/重复/拒绝/未来/超时、时钟倒退、准入后目标丢失、CLI与原始精度、伪造来源/错命令、下游缺样/NaN/错XY、正常半开观察与降落边界、后续reset拒绝、旧记录仍拒绝、无授权入口零副作用。

其中一项实际编译C++14探针，链接当前真实`libecl_geo.a`并调用生成的MAVLink C编解码，24组南北/东西/零/高纬及经度跨界向量，与Python路径对照。它是**1个独立探针/24向量，计在Python测试内，不冒称新增24个gtest**。完整目标—高度—观察—降落用合成后续数据测试；不是完整PX4进程或飞行。

| 实际命令/输出 | 结果 | 退出码 |
|---|---|---:|
| `python3 -m unittest -v test_v04_handoff06`，targeted01 | 初始16项通过 | 0 |
| 同上targeted02 | 23项中22过1错误：新分析器把hover_end的计划降落计入悬停 | 1 |
| 同上targeted03/04 | 修正半开窗口后24/25项通过；旧失败日志保留 | 0 |
| `verify_v04_protocol04.py --output .../handoff06_verify01` | 实际109个不同C++、171个Python、SITL及DONT_RUN Gazebo构建通过 | 0 |
| 同上verify02及最终verify03 | 实际109个不同C++、172个Python（含新增25项）、构建通过；重复不累加独立数量 | 0 |
| `audit_v04_handoff06.py --output .../handoff06_audit02` | 原始SHA/目标/二进制包/源码审计证据生成成功；audit01字段命名优化前版本亦保留 | 0 |
| `analyze_v04_flight06.py series04/run01 --output .../handoff06_reanalysis01` | 旧失败仍accepted=false、缺hover_start；预期拒绝 | 1 |

继承原PID两组各2048步逐样本等价、速度/ESTA/保护/生命周期及rate/姿态回归。ULog格式仍1403字节、无消息/队列/注册变化。开发期生成克隆文件时JS API拼写错误在写文件前终止，修正后继续；无仿真副作用。不能把合成通过当作真实Navigator/Commander/FlightTask异步调度已通过。

复现环境：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/research/sta-velocity-control/scripts:$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest -v test_v04_handoff06
python3 research/sta-velocity-control/scripts/verify_v04_protocol04.py --output <全新离线目录>
python3 research/sta-velocity-control/scripts/audit_v04_handoff06.py --output <另一全新离线目录>
```

## 5. 归档、限制与停止

- 外部`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/handoff06_*`保留所有验证/失败/审计；仓库只提交[小证据和索引](../v04/handoff06/)，不提交大型ULog或探针二进制。原series04的34份指纹全部复核一致。
- EEPROM完整字节不变，SHA `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`；没有新模拟器、飞行、ULog或种子。
- 单独新设计文件`handoff06/protocol.json`明确flight_authorized=false、execution_ready=false、maximum_attempts=0、jobs/seeds为空。旧protocol05授权不会被新分析器/入口继承。
- 未测试真实COMMAND_INT经接收器→Commander/Navigator→FlightTask的整进程调度；当前历史数据只支持命令前真实回放，后半链是离线合成。未运行MATLAB/实机，无ESTA性能结论。
- 先审查并明确范围提交本次离线修订，提交后在外部进度表写完整SHA。以后如获准飞行，仍需单独冻结新批次、清单/种子/预算/新资产及分析版本，在干净源码重建和复核后运行；不能现在直接执行或复用旧五轮。
