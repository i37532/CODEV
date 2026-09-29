# V07 第七批：按真实消费目标关联，不猜测源消息

2026-09-29，起点abcb8d99d7695cd9a8c085eda0f6e2477e8846c4。

第六批首轮已完成实际起降但旧任务目标验证失败，剩17取消、0接受，历史不改判。
唯一错误样本：位置输入49264000、诊断及消费目标49268000μs；旧分析选49244000目标。
真实p_sp.z=-1.97243332862854与消费新目标相同，而误选旧值=-1.9723647832870483。
无EKF reset、无dropout、无位置缺样；RAM日志源与归档一致。

## 代码依据与修订范围

MulticopterPositionControl::Run先获取local_pos，再_trajectory_setpoint_sub.update(&_setpoint)。
末尾diagnostic.setpoint_timestamp=_setpoint.timestamp，diagnostic.timestamp=hrt_absolute_time()。
因此位置采集与读取目标之间可能已有新发布，input_timestamp之前的最近目标并非实际消费身份。

仅新protocol07/task.py用明确记录的setpoint_timestamp精确匹配trajectory_setpoint。
严格正整数时钟、原始源严格递增且唯一、消费时间非倒退；source不能晚于diagnostic发布时间，publication-source仍至多40ms。
不按输出挑候选、不最近邻补缺、不去重；缺失、同刻歧义、倒退、未来、陈旧、非有限源全部拒绝。
XY目标/速度及加速度FF一次性、Z不变和yaw/rate原2e-6容差不改。其他时间/topic规则不变。
这没有取消EKF补偿审计；仍按原数值验证全部目标，不能用此关联豁免reset引起的不一致。
生产源码、控制律、参数/模型、运行器、tmpfs保护/归档与第六批字节相同；仅协议身份/种子/分析器和测试变更。

## 测试与预算

12新增Python用例覆盖精确消费、同源重复消费、40ms精确边界/邻点、未来输入/目标、缺失/歧义/倒退/非整数/非法时钟，以及完整9000样本task和错误Z/XY/FF/yaw拒绝。
前六批所有完整任务窗口共41份原始ULog只读组件回放通过，原result/metrics及ULog指纹保持，见replay_evidence.json。
仅任务组件结果，不宣称旧失败飞行验收通过；未完成任务的旧轮没有强行补齐。
audit_snapshot.py是外部V07-TARGET实际脚本快照，依赖原ROOT，不能在仓库快照目录直接执行覆盖新输出。
首次机械复制替换命令分隔符错误退出255，没有写入；修正后完成新副本，不动旧快照。

持续授权内全新35001–35009，DIV1→2→4各3组PID/XY ESTA+Z PID，18次准确清单见protocol07/execution.json。
同任务/数值门槛/参数/噪声插件/模型，rate PID。先源码提交、干净构建复核再飞；首失败停批，不补飞、不追加机会，不拼历史。
外部根/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V07-TARGET。
不push、不V08/ISTA、不实机。
