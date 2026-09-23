# V04 protocol05 / series04：CLI精度修复后的独立六次协议

2026-09-23。用户已明确批准：单独冻结新协议、提交并完成干净源码验证后，执行最多六次Iris SITL；首个必需单轮/配对失败即停止。不补飞、不加调参/冒烟、不push、不V05/XY/实机。修复前置为85b8647644c5d316d41005ce0ddd26f250fa5a81，开始主仓库/递归子模块干净。

准确清单：9401 PID→ESTA X、9402 PID→ESTA X、9403 PID→ESTA X；目录 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series04`，必须不存在。任何启动失败也计入预算，旧三批剩余预算不用。

## 规则和版本

- `execution.json`记录新身份/授权/六条任务；`v04_protocol05.load_protocol`按SHA固定继承protocol04设计与execution及protocol03数值规范，只允许批次身份、授权与CLI表示说明变化。参数、阈值、任务窗、保护、日志标准不变。
- 原位置P、Y/Z速度PID、姿态及全rate PID。ESTA X候选λ1=1、λ2=.2、ν限.4m/s²、纠偏限.8m/s²；MODE0/AXES0与MODE1/AXES1比较。
- 每轮独立重启预热，原起飞→证据完整首次空中磁对齐→POSCTL连续稳定1秒→只固定一次yaw→一次DO_REPOSITION至2.5m→连续3秒高度入口→60秒观察内完整32秒X速度正弦→计划降落/上锁。唯一navigator→FMM目标链，原起飞/EKF不改。
- CLI参考仅按真实打印表示比较，raw参考始终精确不变；样本/对齐/元数据/传输/缺样/失败重算/故障门槛全保留。正常计划降落仅允许既定Gate2分类，不能豁免其他错误。
- 沿用项目启动器、Iris10016/quad_w/empty_grey.world、原插件/模型。仅IMU显式播种；同种子初始5000创新比较及跨种子区别检查仍必需，非所有噪声独立；PID固定先行的顺序偏差保留。
- `frozen.json`固定170项资产、控制参数和递归子模块；`seed_audit.json`初次扫描21210份JSON，仅排除本次和前置提案的明确登记文件，无历史复用/未解释坏JSON。飞前再次核查，不忽略真实运行路径。

## 实现和离线验证

新run_v04_protocol05/analyze_v04_protocol05只是修复后的04版本隔离副本，单测强制核对除了模块导入/配置目录/输出文件名之外字节一致，复用原run_v04_flight04及raw回放。旧入口/分析器/冻结文件不覆盖。新增6项测试核对准确继承、授权/dry-run、种子历史过滤、隔离副本一致性、六轮/三对上限及首失败停止/参数恢复。

最初在frozen.json尚未生成时提前运行六项测试，dry-run1项因缺配置失败，其余5项通过，退出1；原日志protocol05_targeted01.log保留，不是飞行失败。随后完成快照，无代码/门槛修订，完整verify_v04_protocol04.py在protocol05_verify01目录通过：109个不同C++、147个Python、SITL及DONT_RUN Gazebo仅构建，退出0。旧失败整轮分析继续预期拒绝。此为提交前证据，提交后还要在干净源码重复验证再执行。

## 执行与停止

新入口默认dry-run；已获准执行时仍需精确授权令牌、干净HEAD、版本头/固件、170项资产、插件、无冲突进程、参数、端口、磁盘和新目录全部通过。原参数完整备份并逐轮还原。结果另提交，报告记录协议/源码与结果两次SHA。

```bash
python3 research/sta-velocity-control/scripts/run_v04_protocol05.py \
  --execute --authorization V04-protocol05-series04-six-attempts \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series04' \
  --source-head <实际协议提交的完整SHA>
```

禁止照抄占位SHA、复用已存在目录、把失败改通过或改门槛续跑。仅六轮及三对全部通过才可验收V04；目前协议提交时尚未飞行。大型证据留外部，提交结果时纳入指纹/摘要。
