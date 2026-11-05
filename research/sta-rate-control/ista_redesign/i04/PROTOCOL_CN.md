# I04 冻结协议：Proper-ISTA 只接 roll

本文件与 `FROZEN.json` 在任何 I04 飞行前提交。I03 已选择 `established` 为共同保护基准，故全部 I04
运行固定 `MC_STA_TKO_MGT=0`；新增起飞管理不参与，不把保护因素混入算法比较。

## 模式、模型和信号来源

- `MODE=0/1/2` 继续表示 PID/ESTA/原 ISTA；Proper-ISTA 独立使用 `MODE=3`。
- I04 的 `MODE=3` 只接受 `AXES=1`。`AXES=3/7` 必须报告 unsupported；pitch/yaw 使用原 PID。
- 仅 Iris 10016、Gazebo Classic、`empty_grey.world`，启动链仍为
  `./sitl/run.sh --headless --backend gazebo --model iris`；不是 DP1000 或实机结论。
- 唯一 rates setpoint 发布者是既有 `mc_att_control`。它通过 `ResearchPulse trigger=1` 在 roll 加入
  0.04/0.08/0.12 rad/s、周期 4 s 的正负对称零净转角激励；pitch/yaw setpoint、姿态环坐标变换和
  `mc_pos_control -> mc_att_control` 推力链不变，没有第二个发布者争抢话题。

## 固定参数和任务

ESTA 与 Proper-ISTA 都使用 roll `lambda1=2.2`、`lambda2=.05`、`g_R=130.575283`、`nu_limit=3`，
`c_limit=.15`、`DIV=1`。`g_R` 沿用 M04 模型标定，运行前核对标定源指纹；模型、质量、惯量和
电机插件未变。任务是起飞、60 s 悬停（15 s 后开始 24 s 激励）、降落并上锁。

新种子 6201/6202/6203 在运行前用精确 seed 字段和文件名审计，未出现在 M10、OPT01、OPT02、I03
清单中。固定顺序共 8 次：PID 冒烟 1 次、原 ISTA roll 回归 1 次、ESTA/Proper-ISTA 配对各 3 次。
每项仅尝试一次；失败保留且不自动补飞、重排或扩大预算。

## 预设门槛

每轮必须完成起飞—任务—降落上锁，无 NaN、fault、abort、fallback、failsafe、ULog dropout 或诊断
序号缺失；全 armed 倾角不超过 15°，悬停高度误差不超过 1 m，三轴 rate 不超过 1 rad/s，roll 指令
不超过 .15，`|nu_R|` 不超过 3。日志必须显示真实 requested/effective mode、AXES=1、更新序列、
理想 `a/c/nu_candidate`、保护后的 `a_protected/c_applied/nu`、xi/branch/virtual_state 和实际执行器输出。

性能验收以三次固定 ESTA 的中位数为开发参考：每次 Proper-ISTA 的 roll 全悬停和 24 s 激励 RMSE
均不超过 1.25 倍 ESTA 中位数。pitch/yaw 非命令轴分别不得超过
`max(1.25*ESTA中位数, ESTA中位数+0.005 rad/s)`；安全边界仍逐轮判断。该门槛只决定 I04 是否能
进入 I05，不证明 Proper-ISTA 全面优于 ESTA，也不是正式论文统计结论。
