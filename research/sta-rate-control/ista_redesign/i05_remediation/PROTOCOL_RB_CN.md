# I05R-B：AXES=7 准入

前置 R-A 10/10 单轮有效、五配对全部通过，pitch 主比值中位数 1.014743。现在才开放 MODE3/AXES7。
参数沿用 R-A 和 M06 的独立 yaw 标定 `g_Y=34.582326`，旧保护、DIV1、模型/滤波/外环均不变。

trigger4 先 12秒 yaw-only，再两个 12秒 R/P/Y 同步零净转角窗口；世界 z yaw 激励继续由原四元数律
映射到 body rates，只有现有 mc_att_control 发布 setpoint。种子 6701–6703，ESTA/Proper 各3次，
每项只尝试一次。单轮沿用安全/日志/公式/执行器门槛；全轴正常路径不得计算闲置 PID。

每个窗口/轴逐 seed 要求 Proper RMSE ≤ `max(1.25*同seed ESTA, ESTA+.001)`；每一对的三个窗口×三轴
RMSE 几何/算术总比值取算术平均，三配对中位数≤1.10。3/3 配对和6/6单轮有效才进入 R-C。
