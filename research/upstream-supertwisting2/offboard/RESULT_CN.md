# ROS／Offboard 四系统对比：首批停止报告

2026-11-02。**四系统对比尚未完成。PID 首轮完成实际任务，但未通过冻结日志验收；其余七轮未执行。** 没有补飞、调参、改判或 push。

## 1. 已经跑通的部分

已安装隔离 ROS 2 环境，并完成真实双进程 DDS 往返和真实 ROS→MAVLink 本机链路验证。随后沿用项目 Gazebo Iris 启动器，实际执行 O001（PID）：

持续位置目标 → Offboard/解锁 → 平滑升至约 2.5 m → 稳定后悬停 10 秒 → 2.8 m/2.5 m 小高度阶跃 → 恢复 → 平滑下降 → AUTO_LAND → 落地上锁。

运行器记录 `task_completed=true`，没有飞行 failsafe；参数逐字节恢复，退出后无残留仿真进程。原有控制算法、增益、固件、模型和估计器未修改。

| 本批计数 | 数量 |
| --- | ---: |
| 计划上限 | 8 |
| 启动／起飞／完整任务 | 1／1／1 |
| 按冻结规则接受 | 0 |
| 未执行 | 7 |
| 原版 STA2、RSTA、RISTA 新飞行 | 各 0 |

O002–O008 不执行，不使用历史飞行补齐。此次绘图入口对不完整且首轮未验收的清单返回 1，未创建四系统图，不能声称已经比较出响应快慢。

## 2. 为什么停止：航向对齐被新检查器一并禁止

原始错误为 `Native estimator reset: heading_reset_counter`。这不是虚构计数，也不是 ROS 目标没有发到 PX4。

| 原生证据 | 观察 |
| --- | --- |
| 主 EKF 实例 0，49.680000 s | `reset_count_quat` 2→3，同时 `cs_mag_aligned_in_flight` 0→1 |
| local_position，49.688000 s | `heading_reset_counter` 2→3，`delta_heading=-0.0038480782 rad`，约 −0.220479° |
| 所处阶段 | climb 开始后 11.480 s、悬停评分开始前 7.832 s |
| 状态 | Offboard、armed、takeoff state=5，无接地、failsafe 或 EKF fault；主实例始终为 0 |

源码 [mag_control.cpp](../../../src/lib/ecl/EKF/mag_control.cpp) 的 `checkHaglYawResetReq()` 在尚未完成空中磁对齐、内部离地高度超过 1.5 m 等条件下请求 yaw reset，`runInAirYawReset()` 成功后置位对齐标志。本次数据与**正常首次空中磁航向对齐**一致，不是失控或主估计器切换。

项目其实已经在 [V04_HEADING_AUDIT.md](../../sta-velocity-control/reports/V04_HEADING_AUDIT.md) 处理过此类情形。本次新分析器把航向计数也加入了“从 climb 到落地全程不许 reset”的列表，**没有复用既有的正常起飞对齐分类，是这次工具接线的遗漏**。不应由此去改 PID、STA、ISTA 增益，也不应关闭 EKF 对齐。

尽管原因已确认，原冻结规则确实被违反，因此本轮仍保留 `success=false`。离线诊断不是对原失败的改判。

## 3. 其余独立诊断

在不改原日志、计数数组和冻结结果的前提下，独立检查未发现第二个失败项：

- 128 个预期参数一致；1339 条 ROS 发布与实际发送记录一一对应。
- 七个非预发送阶段的真实轨迹目标匹配；三个评分阶段的模式、PID 状态和实际速度目标检查通过各自检查。
- 最大倾角约 4.530°；最大水平偏移 0.1583 m；最大水平速度 0.2570 m/s。
- 相对起点高度范围约 −0.0723～2.7602 m；最大 |vz| 0.6608 m/s。
- 最大原生位置日志间隔 0.108 s；四个位置／速度 reset 计数不变。
- 落地和上锁有原生日志依据，最终参数恢复一致。

以上只定位拒绝原因，不是新的四算法成绩，也不能把“其他检查分别通过”写成“本轮总验收通过”。

## 4. 测试、版本和指纹

- 飞行前：170 项新离线测试通过、无跳过；72 项原有工具回归通过，退出码均为 0。
- 后续绘图工具：28 项测试通过；纯合成渲染仅用于工具 QA，不是飞行图。
- 最终新工具全套复跑 198 项全部通过、无跳过，退出码 0，见外部 `offline_tests04.log`；该计数包含前述 170＋28，不重复累计。
- 真实 DDS 往返通过，退出码 0；本机回环收到 25 个位置目标、20 个速度目标，并验证禁止发送及已知 GCS 转发心跳处理。
- O001 执行退出码 1；第一轮实际日志验收失败后停止，没有执行第二轮。
- 未重新编译生产固件、未执行 MATLAB/C++ 控制律测试、未实机、未提交和 push。

分支 `research/upstream-supertwisting2`，HEAD `1f6fe1c7a46c22ea41a6a6a51c51498142ca6d62`，原有未提交改动保留。

| 对象 | SHA-256 |
| --- | --- |
| 冻结 manifest | `f8be458bf753b66c204ce0176220681e6753ff14a2364718cedac10d6ffbb24c` |
| O001 原始 ULog | `6b710e4c35aa52765f880dff00fa6085abfe3300216694ba326e21bee80dd813` |
| 主固件，运行前后相同 | `a1ebc57f178c07713f14e2ed423c8b1d27dad251bc70e6047411bfa7877695d8` |
| 恢复后的 parameters_10016 | `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc` |

仓库快照：[清单](results/attempt01/manifest.json)、[O001 结果](results/attempt01/O001.json)、[ROS 本机回环](results/attempt01/ros_loopback.json)、[只读诊断](results/attempt01/diagnosis01.json)、[拒绝不完整绘图](results/attempt01/plot_rejection_check01.json)。

`diagnose_reset.py` 实际执行退出码 0，明确标记 `diagnostic_only=true`、`not_acceptance=true`。21 条诊断中 19 条独立检查通过，两条失败分别是完整审计及其航向重置原因；不是两个不同故障。ULog/result 前后 SHA 完全相同。复现时须使用新的输出路径，脚本拒绝覆盖：

```bash
cd /home/yr/Desktop/Codev-autopilot
PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python" \
python3 -B research/upstream-supertwisting2/offboard/diagnose_reset.py \
  --attempt '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102/runs/O001' \
  --output '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102/diagnosis02.json'
```

原始证据目录：`/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102/`。O001 ULog 约 8.2 MB；ROS 隔离环境约 1.01 GiB，没有更改系统 ROS 或用户旧工作区。

## 5. 下一步应修什么

先把既有“准备阶段、证据齐全、仅一次的正常空中航向对齐”分类接入新的 ROS 运行器和分析器，补齐正负例与任务目标交接回归。必须区分正常对齐、主 EKF 切换及位置／速度 reset；不能简单删掉所有 reset 检查，不能把本轮数据用来调控制参数或放宽性能阈值。

修订后保留本轮失败与旧清单，重新冻结准确的有限批次。由于首个 PID 已占用一次且原结果不改判，若重新完成两任务×四系统，则需要新的完整八轮，总历史尝试上限为九轮；本报告**不授权或自动执行**该新批次。
