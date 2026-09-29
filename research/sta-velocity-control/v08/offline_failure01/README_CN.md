# V08 第13轮：跨CLI读取的时间比较审计

结论：原`Stale diagnostic`数值触发已复现，但它不是“控制器1秒不更新”的证据。
历史飞行仍失败；本目录只做离线审计，**不修补日志、不改变验收、不启动飞行、不修改旧运行器**。

## 证据链

飞行源码c2e6c0be8490c1ebe2250859f5cdc10252941f63，training01/run13。
原始主ULog SHA：`a9d352dda27f976b1ff367feaa14388d00244adf4aff360e31ddb59b9ca3340e`。
所有路径/命令/指标见相邻results01。

| 按调用顺序 | 消息timestamp（μs） | 打印时消息年龄（μs） |
|---|---:|---:|
| sample取得位置 | 112320000 | 0 |
| monitor随后取得速度诊断 | 113508000 | 8000 |
| 读取ULog之后再次取得位置 | 113788000 | 4000 |

`scripts/run_v04_protocol09.py`继承的非降落监视器，在读取中间多个话题和ULog后，
仍用最初sample位置时间减后来的速度诊断时间：绝对差1188000>1000000，于是报错。
`run_v00.py`的rate监视器也有同类比较，但本轮rate时间112324000，未触发该处。
最终一次`protocol09_monitor.jsonl`已经写入，之后抛错，与实际调用顺序吻合。

打印来源并非猜测：`msg/templates/uorb/msg.cpp.em`在print_message入口取得`hrt_absolute_time()`，
`msg/tools/px_generate_uorb_topic_helper.py`输出`(now-message.timestamp)/1e6`。
生成的`build/px4_sitl_default/msg/topics_sources/sta_velocity_ctrl_status.cpp`亦核实相同表达式。
其中无符号差对未来timestamp会回绕，本审计拒绝巨大年龄，不把它解释成合法的负时延。

全主ULog：无dropout/结构损坏，速度诊断11263条、最大12ms，rate诊断28156条、最大4ms，
publish_seq严格连续。独立位置副本11263条连续，与原话题全部逐字段位级相同；消费时间均可精确关联。
112320000到113788000μs之间148条速度诊断：MODE1/AXES3、pid_axes4、committed_axes3，
inner_mode0/axes0/divisor1，fault/sta_fault/first_fail/retry/timing/failsafe均0。

这只能证明记录区间内控制在更新。缺hover_end/land_command/landed_disarmed，不能验收完整任务。
commands.jsonl没有宿主monotonic开始/结束，**8ms打印年龄不是8ms递送延迟**，也不能证明在线保护连续及时。
不指认磁盘、CPU或OS调度为已证明的根因；未来修订需同时记录打印/递送/监视的时间。

## 复现（只读原数据，输出必须新建）

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/v08/offline_failure01/test_audit.py
python3 research/sta-velocity-control/v08/offline_failure01/audit.py \
  '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V08/training01/run13' \
  --output /tmp/v08_failure_audit_new.json
# 完整12轮重放也仅新建输出，不重写任何历史metrics：
python3 research/sta-velocity-control/v08/offline_failure01/replay.py \
  '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V08/training01' \
  --output /tmp/v08_replay_new
```

7项专项测试覆盖跨读时间反例、原1秒精确边界与±1μs、未来/无效年龄、缺失/重复字段、
错话题/错误命令、序号回绕及缺失/重复/倒退、采样未来/倒退。该解析器仅用于审计，不宣称已接入运行器。
12完整任务分别重放退出0，metrics逐字相同。失败轮审计退出0仅表示诊断证据核实完毕。

原protocol01、门槛、候选、训练种子及失败判定未改。后续任何运行需新版本修订和预算处理，
不能把这一离线结论当作自动补飞、排除候选或从hover两样本选参的许可。
