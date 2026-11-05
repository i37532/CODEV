# Z03 protocol02：一次 PID 垂直任务

前置 Z02 `9bf317ea5a975908e63506a2acdd0c252af3acfb` 离线通过。用户持续授权内的新批次，
最多 **1 次**，IMU 种子 **18002**，只 PID，不飞 ESTA、不补飞。失败停止，旧失败保留。

重启/预热 → 原起飞 → 对齐后唯一 Navigator 高度目标 2.5m → 3s 稳定入口 →
60s 观察（其中32s Z速度平滑激励，0.1m/s峰值上界、8s周期、sin²包络）→ 原降落上锁。
12s settle、入口10s截止、准备150s超时不变。X/Y位置保持、固定yaw。
仅IMU显式播种，其他噪声与宿主调度不独立；这是开发准入，不是正式统计样本。

沿用 `sitl/run.sh --headless --backend gazebo --model iris`，Iris10016/quad_w、empty_grey.world，
原 IMU 方程的播种插件；HTE 开启，MC_RTC_MODE0/AXES0/DIV1，RATT_TEST/TKO_MGT0。
共同 land_speed=.6、down_cap=.55；日志 profile保留原位并含bit10=1171。
启动前/后完整参数备份恢复，不写实机。

原 V04 数值门槛全部保留：全程高度[-.5,4]m、XY偏移≤2m、XY速度≤1m/s、
Z速度全程≤3.5m/s/观察≤.6m/s、倾角≤15°、yaw误差≤20°、观察高度距2.5m≤1m；
约束占比≤5%、最长连续≤.5s。至少60s完整观察/32s激励，故障/回退/重算/异常reset0，
raw_dt2–40ms，严格序号/时钟及原话题特定时序策略；ULog dropout0。
下游仍为已实现的发布边匹配，不能称未记录的实际消费；actuator精确匹配≥80%、最大gap≤.25s。

`flight.py` 与已接受 V04 protocol17 字节一致，仅本目录 common 绑定新协议。
运行器复用已回归的 prearm17/entry14/landing10/attitude09/handoff16；独立 Z 分析器
检查 MODE/AXES、Z波形、ν候选/应用和HTE/起飞阶段，旧冻结文件不修改。

本次 PID 通过后，依据此 PID 证据确认候选1/.2/2/3（λ1/λ2/ν限/纠偏限）及原开发配对门槛：
ESTA逐轴RMSE≤1.25×PID+[.02,.02,.01]m/s，位置逐轴≤1.25×PID+.05m，yaw≤1.25×PID+.02rad。
这些是预先提出的非劣界，不要求 ESTA 必须胜出；不根据 ESTA 数据放宽。三对新种子另冻源码/预算。

入口默认 dry-run。实际执行须干净源码、固件HEAD、资产指纹和本次持续授权收据一致。
外部目录 `VELOCITY-STA-20260927/Z03/pid02`，准确清单/路径见 execution.json。

修复前 PID01/18001 已失败并保留；本批基于 inactive-pending 修复 0d06ff47389e6cf2cf7046f20c6c855ecfd9d4d2，任务、参数、数值门槛与预算1不变。
