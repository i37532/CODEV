# M08 预先固定的开发验收协议

2026-09-17，开始 HEAD d1f43ff63f211d3c95b2bf8fafba27e8c1a0fdb1。仅 Iris SITL，默认仍 PID。无分频、无实机、无自动 PID 接管。M07 的 379 份证据已复核。

## 范围和顺序

1. 先用 C++ 自动测试验证 ISTA 公共保护、状态隔离/切换、全轴跳过 PID、故障锁存和耦合/电机滞后对象；使用原 M06 冻结参数作为 ESTA/ISTA 的同增益起点。
2. ISTA AXES=1，完整复跑 M04 协议v3起飞、60秒悬停、原小幅roll激励和降落。先与历史 M04 三个固定 PID 的全部三轴 hover/tracking RMSE 对照，≤1.25，且原15°、1m、1rad/s与输出/nu边界通过。历史参考不是同固件三模式正式比较。
3. 上一步通过后才飞 AXES=3，复跑 M05 的独立R、独立P及同步激励。对照历史 M05 固定PID三轮，每轴每窗口≤1.25，无故障或中止。不能只检查命令轴。
4. 双轴通过后才飞 AXES=7。沿用 M06 协议v2、固定悬停航向及 yaw-only→三轴激励、起降。最终同一固件同场景 PID/ESTA/ISTA 各3次；每个实验模式各三次的R/P/Y在hover、tracking及三个阶段均不超过三次PID中位数的1.25倍。两算法g/限值相同；初始同lambda候选01失败后，候选02仅ISTA pitch lambda1改为2.0，ESTA仍2.4（见TUNING_CN.md），其余不变。这不是纯离散化效应对比，不能有选择地缩短窗口或放宽门槛。
5. 独立的生命周期运行不纳入性能九轮：地面1/3/7与三模式切换、重启保存/参数重载、armed修改暂存与取消、disarm清零。故障注入主要在离线自动测试，不主动在真实飞行器上制造故障。

单一 `mc_att_control` rates发布者、原姿态坐标变换、位置/姿态/推力来源保持。M04/M05历史场景保留原yaw设置，三轴场景使用M06的MPC_YAW_MODE=3。不改变原PID参数或电机/传感器模型。所有失败原始文件保留；当前数据不是论文独立留出集，也不保证Gazebo的配对随机种子。

## ISTA 理想/受保护输出的定义

每步只计算当前有效算法。ISTA先从旧nu求理想候选，记录 `a_raw,c_raw,nu_candidate,xi,virtual_state,ista_branch`。随后共用原饱和方向、反馈有效性、nu限制、落地/疑似落地冻结。

如果保护将候选状态改成 `nu_applied`，使用：

```text
a_protected = a_raw + (nu_applied - nu_candidate)
c_protected = a_protected / g
c_applied   = clamp(c_protected, -0.15, 0.15) * battery_scale
```

nu未改变时直接保留原候选a/c，避免不必要的再次舍入。最终提交nu_applied，日志 `nu` 即真实提交状态。改变后的输出不再保证理想三个隐式方程成立；日志保留理想预测与实际输出的差别。ESTA继续用旧nu输出，原float运算顺序不变。三轴输出/状态原子提交；故障锁存、抑制本步输出，宿主SITL中止，不零力矩冒充安全，也不继承旧PID/其他算法状态。

## 参数和门槛

三轴g=130.575283/112.763533/34.582326；lambda1=2.2/2.4/1.5；lambda2=.05/.08/.02；nu限值均3；实验力矩限值均.15。参数来自M06已冻结Iris专用配置，ISTA尚须本阶段实际验收。候选失败必须记录后单独修订配置并重跑，不得静默覆盖。

HIGH_RATE 保留原 SDLOG_PROFILE 位，131|16=147；按真实序号核查250Hz与丢样，原motor_limits历史存在丢样，不将ULog dropout=0等同全速无损。验收必须实际解码ULog，核对有效模式、候选/保护后状态、未选轴PID逐位等价及真实PID执行计数。
