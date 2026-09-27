# Z03 protocol03：三对PID / Z ESTA

前置：[PID02准入与离线非零ν筛选](../../reports/Z03_PID02.md) 已通过。
用户已持续授权；新19001/19002/19003，每个先PID后Z ESTA，准确6次。
固定PID先行顺序的偏差披露；IMU显式种子，其他随机源及宿主调度不独立。
任何必需/配对失败停止本批并保留全部数据，不自动补飞、不放宽门槛、不飞危险小参数。

唯一新ESTA候选：λ1=2、λ2=1、ν绝对限4m/s²、纠偏限6m/s²；默认参数仍为0，不改变PID增益。
依据PID起飞所需非零初态与4条离线对象轨迹选择，不声称完整飞行证明或公平正式调参。
MODE1/AXES4只选Z；起飞地面/ramp和1个交接样本原PID，空中正常只算Z ESTA。
X/Y速度、原位置P、姿态、全rate PID不变；HTE保持开启。

任务与PID02一致：原启动器Iris10016/quad_w/empty_grey，预热→起飞→2.5m明确高度交接，
12s settle、3s稳定入口、60s观察包含32s Z小正弦（0.1m/s，周期8s，sin²包络），固定yaw，降落上锁。
共同land_speed=.6/down_cap=.55、profile1171，完整EEPROM每次恢复。
唯一目标源Navigator→FlightTask→位置模块；不使用Gazebo真值进入控制。

安全/日志规则逐项沿用PID02，数值不变。主32s窗按真实sensor dt加权算XYZ速度RMSE，
配对开发非劣界：ESTA≤1.25×PID+[.02,.02,.01]m/s，位置逐轴≤1.25×PID+.05m，
yaw≤1.25×PID+.02rad。约束≤5%且最长≤.5s；无首次失败、回退、中止、异常reset、dropout。
三对都满足才验收，不要求ESTA所有指标胜出，报告TV、非命令轴及全部失败。

日志核实实际z_phase/active/pid/committed掩码、同帧PID交接seed、已提交ν的HTE补偿、
old-ν输出和受约束应用状态。理想候选≠保护后严格解，a_proxy≠真实加速度。
外部数据 `VELOCITY-STA-20260927/Z03/paired01`，原PID01失败与PID02准入另存、不混入配对。
冻结源码/资产/精确收据后才启动；默认dry-run；完成报告/结果提交后停止，不push、不实机、不进入XY。
