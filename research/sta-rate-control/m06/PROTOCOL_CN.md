# M06 预先固定的开发协议

2026-09-16，首次 M06 ESTA 飞行前制定。起点 `7ef77081a32b9d5e42fe8167659c894f13dff524`，Iris/10016/quad_w，原灰色 world 和项目启动入口。仅 SITL，不是 DP1000 实机配置。

`calibration.json` 使用实际 SDF、电机反扭矩方向、生成 mixer 和完整 FRD 惯量矩阵计算 yaw 输入增益。工作点归一化推力 .707、pitch 指令 .004，得到 gY=34.5823263568；不同于 gR=130.5752831836、gP=112.7635334435。推力 .65/.707/.75、yaw ±.001/.005/.01 扫描用于量化局部增益变化。它是准静态模型标定，不是动态飞行辨识；电机滞后、噪声、气动误差仍存在。

重要耦合：模型雅可比 ∂αR/∂cY≈19.03918，∂αY/∂cR≈−.06705。不能假设解耦、不能只看 yaw 跟踪。逐轴检查状态、实际 mixer 正负饱和、yaw 饱和窗口内 R/P 响应及非命令轴 RMSE。

初始 yaw 候选 λ1=.65、λ2=.02、|nu|≤3，与 R/P 增益独立。三轴均 |c|≤.15；各轴使用旧 nu 输出再更新。候选不是已冻结合格参数，只有验收通过后才能升级。默认 mode/axes/gains 仍为零，不修改原 PID 参数。

验证顺序：单元测试与构建；真实两次启动的 save/restart/load；原 AXES=1/3 场景回归；trigger=3 的 yaw-only PID/ESTA 小激励；trigger=4 的 PID/ESTA 各三轮。每轮均起飞、60秒悬停、降落上锁。先完成 PID 基线再做 ESTA 对照；任何失败保留原目录和日志。三轴配置下先只激励 yaw，随后才同时激励三轴，不新增生产 AXES=4 模式。

唯一 rates-setpoint 发布者仍为 mc_att_control，推力和位置/姿态目标来自原外环。世界 z 轴 yaw 速率激励通过 q.inverse().dcm_z() 转到机体三轴，保留原姿态误差与 yaw 前馈变换。它是小角速度/姿态响应任务，不是大航向转弯任务。每阶段 12 秒，三个完整 4 秒正弦幅值 .04/.08/.12 rad/s；trigger=4 首段只 yaw，其后两段同步 R/P/Y。60秒悬停开始15秒后触发，最后留9秒以上恢复。零积分针对注入速率，不保证实际轨迹严格零转角。

沿用 15°倾角、1m高度误差、1rad/s角速度、R/P .15 指令、nu≤3、所有轴/固定窗口 RMSE≤三次 PID 中位数×1.25 的门槛。yaw 是本阶段新增受验轴：原 PID 起降已有约 .698 指令峰值，验收上限预先取物理归一化上限1，ESTA内部限幅仍.15。不根据 ESTA 结果放宽阈值或自适应噪声底。所有场景不得故障、回退、中止或 failsafe。

AXES=7 正常控制完全跳过 PID.update，用真实 pid_update_seq/pid_updated 验证，不把全轴空集合的“PID逐位比较”伪称比较通过。AXES=1/3 保留未选轴的原 PID。继续采用已测试的 SITL fault latch、禁止发布、宿主中止策略，没有自动 PID 接管；NaN 占位不是执行器指令，更不是“安全零力矩”。disarm 后重置再切换，真实 save/restart/load 不能替代空中故障验证。

原始 ULog、失败和编译日志存外部 M06 实验目录；报告区分真实状态日志250Hz和可能丢样的原始 motor_limits。未运行 MATLAB、实机或完整扰动/成本评估，不据此声称论文性能优势。

## v2 固定航向修订（2026-09-16，v2 ESTA 飞行前）

保留上述原始 v1 为 `protocol_v1.json`，不改写已飞文件。v1 yaw-only 的 PID/ESTA 均观察到 yaw_sp_move_rate=±.785398 rad/s，使实际 rate_sp 出现约±.83尖峰；这不是规划的 .12 小激励，也不是 ESTA 内核共享状态。例：c02_yaw_esta 的77.372秒，vehicle_attitude_setpoint.yaw_body 从1.585028变为1.569320，yaw_sp_move_rate=−.785398；quat_reset_counter仍为3。

来源路径：FlightTaskAuto::_set_heading_from_mode()、_limitYawRate() 自动航向/前馈，经 PositionControl 到 AttitudeControl 原世界z转机体变换。没有证据表明应修复坐标变换，未改该代码。继续盲调内环会把外层偶发参考重捕获当成指定小激励性能。

v2 使用现有参数 MPC_YAW_MODE=3（沿轨迹）；在静止悬停、距目标小于2m条件下 FlightTaskAutoLineSmoothVel::_generateHeadingAlongTraj 不生成新航向，沿用 _yaw_sp_prev。保留完整位置/姿态控制器、原发布者与 yaw 变换，结束恢复0。新增验收：整个悬停的外层 yaw_sp_move_rate 必须有限且绝对值≤.0001；若不满足场景本身失败，不剔除尖峰窗口。

所有原有阈值、.04/.08/.12激励、三轮对照规则不变；v2必须重新采集PID和ESTA，不与v1混合。v1暴露的原自动航向场景局限仍须报告，不能据v2通过声称覆盖了v1或全部导航任务。候选02参数沿用，不为掩盖尖峰继续加大yaw增益。
