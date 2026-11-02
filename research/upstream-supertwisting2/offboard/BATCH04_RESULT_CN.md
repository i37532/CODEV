# ROS Offboard 四系统 B04 执行结果

2026-11-02。新冻结资格及工具指纹已更新，B04 已实际执行后按首败规则停止。**计划 8 次，尝试 2 次，PID 接受，原版 STA2 在降落期触发估计高度下限，剩余 6 次未执行。四系统比较未完成。**

没有补飞、调参、放宽规则或改判旧失败。当前分支 `research/upstream-supertwisting2`，HEAD `1f6fe1c7a46c22ea41a6a6a51c51498142ca6d62`；既有未提交源码、手册和图表保留。本次未提交、未 push。

## 冻结与资格

[执行前协议](BATCH04_PROTOCOL_CN.md)、[准确清单](results/batch04/manifest.json)、[资格验证](results/batch04/qualification01.json)、[结果及指纹索引](results/batch04/batch_result.json)。清单 SHA-256：

`20e22f5c81f30d520b7b87a51e84c855df37686a06320b45f971680a47db9045`

本次新增 `event_landing_capture_v1` 冻结资格：统一启用固定上游版本的事件重发语义及新鲜落地确认，覆盖当前完整工具集、三套测试、真实历史 ULog 和落地尾段回放。新冻结器拒绝缺失/失败测试、过期源码、历史指纹变化、放宽尾段阈值或篡改历史接受状态。旧冻结快照保留。

- **343 项 Offboard＋72 项旧工具＋10 项航向策略＝425 项测试**，全部 exit 0、无跳过。其中新增 14 项冻结资格/历史预算测试，不重复加到总数中。
- 9 份历史 ULog 再回放，原始结果不改判；旧 STA2 尾段只作离线接线验证，不计新样本。
- 新真实 ROS→本机 MAVLink 回环通过：25 个位置目标、20 个速度目标、转发 GCS 心跳及停止发送检查。使用模拟遥测，不算飞行。
- 执行前核对源码/资产，执行后再次核对全部 **314 项冻结资产**、各 job 的实际源码、固件/HEAD 和两仓库递归子模块，保持一致。
- 主仓库及原版固件、完整参数、原模型/world、任务、控制器和安全数值阈值均不变；没有重建固件。实际脏工作区与历史固件来源仍按协议披露，不称当前干净 HEAD 构建。

## 实际清单

| 编号 | 任务 | 系统 | 结果 |
| --- | --- | --- | --- |
| O001 | position | PID | 接受，完整起降、日志检查及独立复算通过 |
| O002 | position | 原版 STA2 | 起飞、悬停、两段阶跃和平滑下降完成；AUTO_LAND 期间安全中止 |
| O003 | position | RSTA | 未执行，首败停批 |
| O004 | position | RISTA | 未执行，首败停批 |
| O005 | velocity | PID | 未执行，前门未通过 |
| O006 | velocity | 原版 STA2 | 未执行，前门未通过 |
| O007 | velocity | RSTA | 未执行，前门未通过 |
| O008 | velocity | RISTA | 未执行，前门未通过 |

计划/尝试/实际离地/完整任务/接受/失败/未执行＝**8/2/2/1/1/1/6**。历史实际由 5 次增至 **7 次**，没有超过本批冻结的累计上限 13 次；剩余 6 项关闭，不可改工具后继续这份清单。

两轮参数均精确恢复，无残留仿真进程。原版本轮临时生成的 `parameters.bson`、`parameters_backup.bson` 按快照恢复为不存在，所有飞行日志和失败证据保留。

## 新落地确认的实际验证

PID 完整通过了新的等待路径：结束事件位置时间为 106.744 s，status 为 106.744 s，land 为 106.736 s；差值为 **0 ms、8 ms**，均满足原 500 ms 限制。随后参数核验、ULog 解码、重新读取复算和指纹一致性通过。

STA2 本轮尚未达到落地上锁条件，原安全检查就已拒绝，因此没有记录 `landed_disarmed`。不是用新鲜度问题再次拒绝一个已完成的末帧，也不能声称该系统本轮完整验证了新结束路径。

## 原版 STA2 停止证据

原始错误：

```text
ValueError('Full-flight height/vertical speed envelope')
```

| 原生证据 | 值 |
| --- | ---: |
| AUTO_LAND 命令事件 | 99.524 s |
| ULog 首次记录高度下限越界 | 101.380 s，相对估计高度约 −0.501681 m |
| 触发运行器的采集时刻 | 101.420 s |
| 本轮起始估计 z | −0.01047 m |
| 触发时估计 z | +0.50882 m，NED 向下为正 |
| 相对估计高度 `origin.z − z` | **−0.51929 m** |
| 冻结高度下限 | **−0.5 m**，低于下限约 0.01929 m |
| 垂直速度 | +0.786 m/s，未超过绝对值 3.5 m/s 限制 |
| 实际状态 | `nav_state=18`、`arming_state=2`、`landed=false`、`ground_contact=false` |
| ULog corruption / dropout | false / 0 |

只读诊断用原 CLI 原文重建同一次采集，再调用未修改的安全检查，精确复现同一错误；原 ULog 同时刻 XYZ/速度数值与 CLI 显示精度一致。飞行窗口内 XY/Z/速度 reset 计数未变化，主估计器实例保持 0。

这证明是**被检查的估计状态确实越界**，不是旧事件重发误报，也不是采样器把该时刻的 z 读错。但相对估计高度不等同于真实离地高度，不能直接断言物理穿地、碰撞损坏或控制器必然失稳。日志中的仿真 ground-truth 字段与估计量在降落尾段存在差异；只读诊断已分别记录并使用各自起始零点，完整来源、接地及估计动态仍待离线审计，未用真值覆盖安全判据。

[诊断脚本](results/batch04/diagnose_stop.py)、[原始数值与复现证据](results/batch04/stop_diagnosis01.json)。完整任务分析仍拒绝缺失的结束事件；O003 首败门和四系统出图入口也实际拒绝，没有越过失败继续跑。

## 已有指标与未完成项

PID 悬停窗口 10.04 s，XYZ 速度跟踪 RMSE 为 **0.007312 / 0.006946 / 0.002690 m/s**；相对起始高度均值 2.47823 m。这只是本轮 PID 描述，不是四系统排序。

RSTA/RISTA 本批未飞，velocity 四项均未开始，STA2 也未完成起降验收，因此**没有完整四系统实际速度/位移图或响应速度排名**。未使用旧成功日志补样本，未以 STA2 的部分阶段冒充一轮完整接受。

原始日志保留在 `/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102-B04/`：

| 系统 | 原始 ULog SHA-256 |
| --- | --- |
| PID | `5547621aff1c2e0dffb0bb0bc24a27a801c0ce36c98cc3ac2658af3350ed308f` |
| 原版 STA2 | `6a54d350710f0108ccafa563b0f65bae5586303a7dd4a3a5d42a6411b483c73b` |

## 命令与后续边界

已执行命令及退出码：`prepare_evidence.py` 0；`replay_landing_fix.py --tests` 0；`verify_live_bridge.py --execute-local-loopback` 0；`freeze.py --revision event_landing_capture_v1 --freeze` 0；O001 dry-run 0；O001 `run.py --execute` 0；O002 `run.py --execute` **1**，串行批次立即停止；`archive_results.py` 0；`diagnose_stop.py` 0；`git diff --check` 0。诊断 exit 0 表示成功复现拒绝，不是飞行通过。

重现离线诊断需另选输出，不能覆盖现有证据；更不能重跑已占用的 O001/O002。完整工具源码快照在 `results/batch04/frozen_tools/`。

下一步应仅离线核对原版 STA2 的 AUTO_LAND 接地过程、估计高度/速度与仿真真值的差异，再决定是否需要修复或另立验证协议。**不建议为通过而放宽 −0.5 m 下限，也不能把当前失败自动变成追加飞行授权。**
