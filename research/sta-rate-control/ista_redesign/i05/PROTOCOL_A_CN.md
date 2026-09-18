# I05-A 冻结协议：Proper-ISTA roll/pitch

本协议在任何 I05-A 飞行前提交。只开放 MODE=3/AXES=3，MODE=3/AXES=7 仍必须拒绝。采用 I03
选定的 established 保护、DIV1，以及已验收的 `g_R=130.575283`、`g_P=112.763533`。参数与固定
ESTA 相同：R `2.2/.05`，P `2.4/.08`；yaw 保持 PID。

唯一 rates setpoint 发布者为现有 `mc_att_control`。trigger 2 的 36 秒序列依次是 12 秒 roll、12 秒
pitch、12 秒同步 R/P；每段含 .04/.08/.12 rad/s 三个完整 4 秒正弦周期，净转角为零。推力和姿态/位置
外环不变，不增加第二发布者。

新配对种子为 6301/6302/6303，顺序见 `FROZEN_A.json`。ESTA 与 Proper-ISTA 各三次，每项只尝试
一次；失败保留，不自动补飞、重排或放宽阈值。

每轮须完成起飞、60 秒悬停、激励、降落并上锁；无 fault、abort、fallback、failsafe、ULog dropout
或诊断缺样。倾角≤15°、高度误差≤1 m、三轴 rate≤1 rad/s、选中轴指令≤.15、|nu|≤3。
Proper 的 roll/pitch 在 hover、tracking 和三个固定阶段相对三次 ESTA 中位数不超过 1.25；阶段中未
激励轴及 yaw 使用 `max(1.25*中位数, 中位数+0.005 rad/s)`。这只是开发准入，不是正式统计结论。
