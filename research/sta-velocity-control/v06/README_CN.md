# V06：可重复任务与开发回归

当前状态：needs_revision，未通过。protocol02实际9轮：8接受、1失败、9取消；hover3对通过，figure8仅1对通过，heading未飞。降落冲击造成真实IMU截幅→EKF切换→参考变化，不能放宽日志检查或继续抽种子。见 [V06报告](../reports/V06.md)。新批未启动，等待明确共同起降专项范围。

比较原速度PID与已验收XYZ速度ESTA（不是XY+Z PID），原位置P/姿态/全部角速度PID不变，固件默认PID。

- [三个便捷脚本和PlotJuggler说明](scripts/README_CN.md)
- [当前冻结协议02](protocol02/execution.json)：新18轮、新24001–24009，三任务依次通过。首批1接受/1失败/16取消，见reports/V06_PROTOCOL01_FAILURE.md；旧协议/结果均保留。
- plan01 是外部三文档的本阶段冻结快照，旧计划与旧结果不改。
- 协议源码提交后完整重新编译、实际非零测试，再允许飞行；仅本项目 Iris 启动器。
- 首个必需失败立即停批。按用户本次持续授权，仅允许离线修复后另冻新源码/新种子/新有限批次，不复用失败预算，不放宽阈值，不push或自动进入下一阶段。

任务是新增默认关闭SITL目标适配，不更改控制器dt、PID/ESTA律或全局估计/起降规则。VCT_TEST5/6/7保留真实目标、一次FF、任务时钟；旧TEST0..4保持。源码增量和日常脚本与旧sim_scripts隔离。自动清单以唯一命令来源完成起降，每轮实际读回速度/角速度模式和完整恢复EEPROM。

离线开发记录：verification_dev01 因测试入口漏设历史脚本PYTHONPATH退出1（未飞行）；修复后的 verification_dev02：196个不同C++、432个Python测试，全部命令退出0，SITL/Gazebo构建通过。初期Python负例夹具复用timestamp数组使单条修改同步污染期望，已改独立数组并通过；没有改变日志验收数值。最终以协议提交后的 verification_committed 证据为准。

外部根目录：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260928/V06。结果报告待实际完成后写 reports/V06.md，不把准备工作称验收通过。
