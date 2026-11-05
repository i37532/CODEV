# IMU 切换时间戳契约修复（M04 扩展范围）

2026-09-14 用户明确授权：修复上游 IMU 切换时间戳处理，完成回归后继续 M04。先前失败场景和报告保留在 reports/M04_BLOCKED_20260914.md、blocked_evidence.json、blocked_artifacts.sha256 及外部 pid01 目录。

## 问题与最小修复

VehicleAngularVelocity 的 _last_publish 是允许落后的频率调度标记，不等于上次真正发布的 timestamp_sample。IMU 切换时新实例可提供与上次同时间但测量值不同的样本。不能给它伪造一个较大的时间戳；也不能让角速度积分状态在 dt=0 时多推进一步。

新增 GyroPublicationGuard 只负责实际消息发布契约：维护跨 IMU/FIFO 切换保留的最后实际发布 sample 时间。候选为零、等于或早于该时间时不发布新的 vehicle_angular_velocity/acceleration；较新的候选仍按原频率门槛发布。被频率门槛跳过的样本不占用“最后实际发布时间”。未来样本的时间不重写，因此真正长间断仍会交给 STA raw_dt 检查并锁存故障。

此修复在 CalibrateAndPublish 的发布判断处接入。已有选择器、偏置校正、滤波计算、滤波 reset 及校准逻辑均保留；同时间新实例测量仍经过原有内部计算，只是不再作为第二个时间步发送给控制环。名义无重复序列的发布时刻和数据计算顺序不变。异常路径有意改变：原 PID 不再对同一 sample 时间多执行一次夹紧为 125 us 的更新。

## 可观测性

新增事件型 gyro_sample_status，默认日志注册、队列 8；包含候选/前次实际 sample 时间、device_id、switch 标志、事件序号、重复/倒退/零时间/切换累计计数和是否发布。reason：0=accepted，1=duplicate，2=backward，3=zero，4=cadence not due。首次设备选择和每次切换/拒绝都会产生记录；原 sensor_selection/estimator_selector_status 继续保留。没有关闭冗余、隐藏异常、取消 STA 的重复/倒退/长间断保护或自动切 PID。

## 验证边界

新增 C++ 自动测试：启动零时间、不同限频下名义序列一致、切换时等时/过旧候选、频率跳过不推进时间、真实长间断/时间回退，以及先前两次实测异常时间的重放。另有源发布契约到 STA 保护的组合测试：被拒绝的等时样本不推进 nu，下一有效样本正常，真实 100 ms 间断仍触发 LongGap latch。

实际 PID/ESTA SITL 每轮解码时必须检查控制 sample 严格递增、armed raw_dt 正常、gyro_sample_status 的拒绝记录自洽，并记录自然发生的 IMU 切换及重复抑制次数。不能凭“画面正常”判断修复通过。没有在实机注入故障，板级性能/传感器驱动组合也未验证；共用源码修复不等于实机验收。

## 已取得的实际回归证据

resume/pid01 的 5 次自然 IMU 切换中，抑制了 4 个重复样本和 3 个已发布过的旧 FIFO 样本；所有 28,393 个控制更新的相邻 sample 差均为 4,000 us。例：106944000 us 切回 IMU 1310988 时，FIFO 候选 106932000/106936000/106940000/106944000 先后到达，前次实际输出已是 106944000，因此全部不重复发布；下一正常控制样本继续按 4 ms 到达。完整诊断见 resume/pid01_limits.json，不靠删日志行获得单调性。

该轮 28,393 个 PID 更新样本三轴浮点位独立重算一致，26,348 个匹配 actuator 样本逐位一致。它仍因另一个降落输出边界问题未通过 M04；时间戳回归成功不等同整个 M04 成功。原异常路径中 PID 额外执行一次 125 us clamp 的行为被有意消除，名义 PID 数学和参数语义不变。
