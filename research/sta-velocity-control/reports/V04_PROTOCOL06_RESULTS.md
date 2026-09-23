# V04 protocol06 / series05：任务完成，日志验收失败后停止

2026-09-23。状态：**failed / needs_revision**，不是依赖缺失。用户要求“重新冻结并授权新批次”，本次已冻结、提交、重建并实际执行；不能把启动器的PASS当成整轮验收通过。

## 1. 范围、版本与预算

- 完整阅读速度计划/共同规则、进度及handoff06前置报告；开始HEAD `5beaecfd7376178259b547e0f4d1d79156aab70a`，分支`research/sta-velocity-control`，主仓库和递归子模块干净，未回退/清理。
- 新协议/实际飞行源码：`c9030688efffce4984f39f3aa08fe270eda7206c`，12个明确研究文件。干净提交上重新通过构建和测试再飞行；生产src/msg、旧协议及handoff06草案/入口未改。
- Gazebo `822050a7ab6fd87972e59f16312f451bce217a56`，ECL `b3fed06fe822d08d19ab1d2c2f8daf7b7d21951c`；递归版本及185项资产见[冻结快照](../v04/protocol06/frozen.json)。固件SHA256 `004eb35b5bd91dd895794923a551ce2db67619ed6f9e236aeb10d23715f53448`。
- 预算9501 PID→ESTA、9502 PID→ESTA、9503 PID→ESTA，共最多6次。注册前21314份JSON无复用，注册审计21317份；飞前重扫。源文本的9502.x/9503.0为旧耗时值，不是种子。仅IMU显式播种，不主张所有随机源独立，固定PID先行偏差保留。
- 项目启动器`./sitl/run.sh --headless --backend gazebo --model iris`，实际Iris10016/quad_w、empty_grey.world、1倍速。不是DP1000、不涉及实机。
- 原位置P、Y/Z速度PID、姿态及全部rate PID不变。唯一ESTA候选λ1=1/λ2=.2/ν限.4/纠偏限.8不改；实际本轮速度0/0、rate0/0/1、RATT_TEST0、TKO_MGT0，profile147。ESTA未启动。

## 2. 实际完成与停止

| 项目 | 结果 |
|---|---|
| 计划/尝试 | 6 / 1（run01，PID，9501） |
| 完成起飞—观察—降落上锁 | 1 |
| 完整接受 / ESTA飞行 / 配对 | 0 / 0 / 0 |
| 未执行 | 5，因首轮必需日志验收失败停止，不自动续跑 |
| 起飞命令事件 / 实际命令 | 30.084s / 30.200s |
| 明确XY命令 / 实际接收 / ACK | 38.744s / 38.756s / 38.764s |
| handoff_ready | 39.064s |
| 观察窗口 | 47.576–107.736s，共60.160s |
| 降落命令事件 / 降落上锁事件 | 107.736s / 115.324s |

此前目标交接已推进：保留POSCTL的原XY目标，单次COMMAND_INT发送，在线ACK、Navigator读回、连续高度入口通过；明确XY编码偏差约.004569m。完整32秒小激励已记录，起降任务由原流程完成。完整离线交接/高度验收在下述首个异常处停止，因此**不宣称全部新增交接条件均已离线通过**。

## 3. 拒绝原因与只读诊断

最终`v04_protocol06_metrics.json`：`accepted=false`，错误`Empty/nonmonotonic vehicle_command`。冻结批次运行器退出1并停止，原结果未修改。

### 3.1 事件话题被错误套用了严格递增采样条件

原始vehicle_command共4条：起飞22与解锁400均为30.200000s，之后192和176按时序出现；ACK的22与400也共享30.208000s。它们是不同命令，不是重复重发，没有时间倒退。

`Commander.cpp`的takeoff入口顺序发送NAV_TAKEOFF和ARM_DISARM；SITL同一仿真时钟刻度能产生两个事件。新handoff分析器调用`v04_heading_stream.data()`，其通用检查要求所有相邻时间差严格大于0，因而拒绝合法的同时间戳事件。原合成测试只含单个命令，没有覆盖真实起飞/解锁前缀。这属于新增工具适配遗漏，不是已证实PID失稳或控制sample倒退。

### 3.2 同时发现接收器数值表示差异，尚未修复

独立只读审计还发现，整数经度85456078在Python`/1e7`为8.5456078，而实际vehicle_command记录为8.545607799999999，相差−1 ULP（−1.7763568394002505e−15度）。当前严格逐位检查随后也会拒绝此差异，不能仅改时间检查就宣称问题解决。

接收器源码虽写除以1e7，但真实编译命令含`-freciprocal-math`。新增**离线诊断探针**在strict和实际数值优化选项两种构建下分别计算：实际选项结果逐位等于真实ULog；strict版本等于Python参考。该探针复现相关表达式，不是完整接收器集成测试；不修改生产编译参数，也不放宽飞行门槛。

后续应单独修订事件流顺序/唯一性检查及接收器编码参考，覆盖同刻不同命令、重复192、反序/错源/拒绝ACK，以及真实编译选项和边界数值。仍需保留原始来源、目标连续性与控制sample严格检查，不能全局把时间或坐标检查放松。本次**只诊断，不实施验收修订、不改判本轮、不续飞**。

## 4. 记录到的性能（未接受运行的描述性数据）

32秒激励3200条实际消费速度样本，X/Y/Z RMSE分别为**0.046067 / 0.008181 / 0.002172m/s**。没有ESTA或成对改善率，不能拿本轮替代合格基线。

- 60.16秒观察6016条速度诊断约100.003Hz、最大12ms；整飞行8524条，内环证据年龄0–4ms，无first_fail或重算。
- 高度相对2.5m目标RMSE .029205m、最大误差 .066740m；yaw RMSE .0001603rad；最大倾角1.0591°。
- 原基线49项检查通过、局部输出/姿态目标匹配覆盖100%且误差0；actuator覆盖91.503%、匹配误差0、最大8ms，不称下游无损。
- 正确饱和位解析为0%，有效反馈100%；旧通用v00指标中的raw非零1.0包含valid位，不能解释成100%饱和。已完成计划降落后的Gate2原始704条被既有规范分类为预期退出，不清零隐藏。
- 两份ULog均dropout0、无文件损坏；在线171次回放年龄28–220ms。序列/模式检查通过不等于新增命令来源及完整交接验收通过。
- 旧v00_metrics内部分V00限制文字和原饱和字段为继承工具历史产物；本轮消费状态、显式IMU种子及新诊断以本报告和06指标为准，不追改原文件。

## 5. 测试、命令与退出码

环境沿用[新批次说明](../v04/protocol06/README_CN.md)。完整命令/XML/log在外部目录和小型证据中。

| 命令/阶段 | 实际结果 | 退出码 |
|---|---|---:|
| verify_v04_protocol04.py --output .../protocol06_verify01 | 提交前109个不同C++、180个Python；SITL/Gazebo仅构建 | 0 |
| 同上 .../protocol06_committed01 | 干净c9030688ef重建，109C++/180Python全部通过 | 0 |
| run_v04_protocol06.py --execute --authorization V04-protocol06-series05-six-attempts --output .../series05 --source-head c9030688efffce4984f39f3aa08fe270eda7206c | 1任务完成，必需ULog验收拒绝，余5停 | 1 |
| audit_v04_protocol06_failure.py .../series05/run01 --output .../protocol06_audit01 | 13项只读诊断检查通过，两种C++表达式探针编译/运行均0 | 0 |
| analyze_v04_protocol06.py .../series05/run01 --output .../protocol06_reanalysis01 | 隔离目录重现同一拒绝，不写原日志/指标 | 1（预期） |
| python3 -m unittest discover -s research/sta-velocity-control/scripts -p 'test_*.py' | 结果阶段180项仍通过，不累计重复用例 | 0 |

109个C++包含原速度PID两组各2048步、保护/内核/生命周期/旧rate/姿态回归；180Python含新增8项批次接线测试。13项诊断和两种表达式探针不冒称新增gtest或飞行验收。ULog消息仍1403字节，无日志配置/生产接口改动。

开发/诊断错误如实保留：一次临时只读解码漏了M00的pyulog搜索路径，ModuleNotFoundError退出1，补全既有环境后成功；一次复制证据的JS JSON解析器不支持原始NaN，在文件写入前失败，随后按原文本复制，无数据清洗。均非新增飞行。未运行MATLAB、硬件、V05或ISTA。

## 6. 证据、提交与下一步

外部根`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04`：series05及protocol06_verify01/committed01/audit01/reanalysis01全部保留。仓库[results06](../v04/results06/)只保存小证据、诊断探针、指纹索引，不提交ULog/二进制。

- 主ULog36005502字节，SHA `d8d97dfd7b54fb512c42669e1b874ea49911abe332495b893a269f0ce5e82f16`。
- 启动ULog205136字节，SHA `b1c0bcb78b6b9180c1047db4a6bc402d6325e771c68347efd452d86b123ce340`。
- 50份原始工件索引SHA `20fb1b88f85f457acf3637d361fc0361f8913f44110d92db873dbb30fc22686e`；其余173份证据索引SHA `0587642a4dd1a172320841ee10896b5c96c5d55d42c010d615f20b09a721d5d6`。
- EEPROM全字节恢复，SHA `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`；自有模拟器正常退出无残留，旧日志未删除。

结果另行明确范围提交，完整结果SHA写外部实时进度表，不预填自身SHA。此次结果提交只包含报告/入口、只读审计、探针和小证据，冻结执行资产不变。五批累计5尝试、1次完整任务、0接受，ESTA总飞行0，V04仍未验收。下一步须先单独获准修订上述两类工具检查并离线验证，再决定新的飞行授权；不能直接续跑剩余5轮。不push。
