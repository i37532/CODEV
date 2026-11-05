# V04：selector时间交接修复与削顶故障定位

2026-09-26，起点 `01c70ee6f78459f3166500cc01e885426f9b6a91`，research/sta-velocity-control；起始主仓库/递归子模块干净。

**结论：完成一项真实上游缺陷修复及离线回归；没有新飞行，V04仍未通过，Z仍未接实际输出。** 本轮遵循用户持续修复授权，处理X/Z共同试飞前置问题。不push、不实机、不V05、不修改旧失败判定或数值验收门槛。

## 1. 为什么发生切换

重新读取series09原始ULog中的变化触发话题 `estimator_status_flags`：

| EKF实例 | bad_acc_clipping置位 | 恢复 |
|---|---:|---:|
| 0、5 | 113.444s | 113.456s |
| 1 | 113.448s | 113.456s |
| 2 | 113.448s | 113.460s |
| 3 | 113.452s | 113.460s |
| 4 | 113.452s | 113.464s |

这些记录只有 `fs_bad_acc_clipping` 故障位，与控制台三次“filter fault”切换相符。低频estimator_status未记录到非零值不能反证没有故障。ECL的covariance.cpp在延迟IMU的任一轴clipping位为真时置该标志；selector原有健康规则拒绝非零filter_fault_flags。本轮**没有修改这两项规则或屏蔽削顶**。

采样倒退也确实存在：vehicle_local_position在113.448s发布sample113.440s，前一个已发布sample113.444s。原ULog SHA仍为 `96db142fdfc5449c74ab0c86e46cae39d380caee51df31690280207b285a3403`。

补充只读观察：113.344s估计az约−36.84m/s²，113.384s及之后100ms采样的真值vz为0；发生时处在降落末段。触地冲击是有依据的下一步诊断方向，**但低频数据不足以给出削顶瞬时峰值或证明全部物理因果**。真值仅用于离线诊断，不能接保护/控制。

## 2. 独立复现并修复的代码问题

旧EKF2Selector在判断消息过期后，仍更新 `_..._last`、实例记录及reset累计状态。例：已发布sample=10000，收到4000后拒绝但覆盖基准，后续8000因此被发布，形成时间倒退；一个因status下界被拒绝的较新样本也可能错误压制后续合法样本。被拒绝实例还能污染下次reset差值。

修复对attitude/local_position/global_position/odometry/wind五条具有相同缺陷的发布路径统一做**前置时间检查**：不合法即返回，不触碰发布基准、实例或reset状态。合法路径继续原有计算与发布。没有更改健康评分/选源、EKF滤波、原reset数学、控制器dt、PID/ESTA律、起飞/降落参数、ULog验收器或world。

测试调用真正的生产函数，通过真实uORB发布/订阅；不是用Python另写一份selector来“自证”。测试访问friend不构成生产执行路径。

## 3. 实际测试与证据

| 批次 | 结果 |
|---|---|
| selector11_old02：旧生产实现 | 6项测试均失败，gtest退出1（预期负对照），验证脚本退出0 |
| selector11_fixed01：修复初版 | 同6项全部通过，控制回归通过 |
| selector11_fixed02：最终 | 10项selector通过，0失败/错误/禁用；控制回归与构建通过 |

10项覆盖五话题过期/同刻/倒退与status下界、被拒绝实例不污染本地位置5类reset、瞬时换源后回原实例不产生伪reset、四元数reset差值、全局高度reset传递、2048条正常消息及计数器回卷。没有宣称完整异步多EKF/传感器实时仿真已通过。

最终另有原控制106项C++、Z原型16项C++、347项Python通过，合计**132项不同C++、347项Python**；重复执行不累加。原PID两组各2048步回归、SITL/测试/Gazebo DONT_RUN构建均通过。新飞行/新种子/新ULog=0；未跑MATLAB、11项IMU专项、3项姿态专项或七/八批完整旧日志重分析，不借用历史通过数。

外部目录：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04/`。

- 旧负对照：[negative.json](../v04/selector11/negative.json)，完整日志/XML在selector11_old02；manifest SHA `0a99ae4ac44374cc57ab36a0328accf2d55de823941bf4b18f9e4a90bcd4cd09`。
- 最终：[verified.json](../v04/selector11/verified.json)，完整构建/测试/XML/控制证据在selector11_fixed02；manifest SHA `cc4eec89e7c61fefa044c3f7349b7e5ed7264a5944f20237cffe07524208c798`。
- 两份索引全量SHA核验通过。EEPROM前后仍为 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，未启动模拟器。

复现修复后测试（已存在测试构建配置；首次先执行 `make tests TESTFILTER=RateControl -j4` 配置）：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/scripts/verify_v04_selector11.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04/selector11_reproduce_new'
```

输出目录须不存在。`--expect-old-failure`仅供旧实现负对照，不能在修复版上用来宣称通过；old02的生产cpp指纹对应起点提交，测试源码指纹单独记录。所有运行都是起点提交加明确工作区补丁的离线测试，不称干净源码飞行。

开发失败保留：首次测试编译缺MODULE_NAME退出2；首次运行漏启工作队列，随后old01漏HRT初始化导致析构等待，分别终止本任务测试子进程（未杀模拟器/其他任务）。old01保存退出−15及失败日志，脚本退出1；补齐夹具初始化后old02完整6/6负对照。修复的是夹具初始化而非放宽断言。调试器附加受ptrace限制未成功；没有修改系统权限。

## 4. 还没有解决什么

修复保证过期候选不污染发布状态，**不保证没有真实削顶、没有合法EKF切换/reset或V04下一轮必过**。旧日志各实例local_position/attitude约2Hz，不能完整重放113.44s附近所有输入并证明修复后会选到同一轨迹。

下一步需为触地/削顶定位冻结一个有准确预算的PID诊断，保留原控制/安全门槛，补齐各实例状态与IMU裁剪证据；先验证修复后的实际采样/切换链，再决定接触阶段的最小处理。不得仅换种子赌通过、屏蔽clipping、允许负dt，或悄悄放松reset拒绝。若考虑减小降落速度，须先检查项目MPC_LAND_SPEED元数据最小值0.6m/s及实际实现，不能直接套用其他PX4版本或静默设到0.3m/s。

后续Z02模块接线仍按Z计划推进；正式V04目标仍是PID/ESTA三组配对、完整起降与原门槛通过。当前累计9次尝试/0接受/ESTA0，历史数据保留。普通相关步骤沿用持续授权，不重复向用户索要同类批准。
