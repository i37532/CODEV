# I02 离线保护与起飞状态管理规格

日期：2026-09-18。起点 `547d324f6528a2fc05651574e5dd3ec5cb44e7de`，I01 已通过。
本阶段不启动 Gazebo、不飞行、不增加模式，也不允许 Proper-ISTA 驱动执行器。

## 保护映射

固定 I01 的 Proper-ISTA 理想关系：

`z=s+h*(a-nu_next)`，`a=-lambda1*sqrt(|z|)*xi+2*nu_next-nu_old`。

公共保护只裁决状态候选 `nu_next` 是否因反馈无效、对应方向 mixer 饱和、输出方向饱和或
`nu_limit` 而冻结/限幅。若理想状态为 `nu*`，保护状态为 `nu_p`，在保持同一理想根与 `xi`
的诊断映射下，代数式给出：

`a_state = a_ideal + 2*(nu_p-nu*)`。

这与原 ISTA 的 `+1*(nu_p-nu*)` 不同。此时
`z_from_applied=z_ideal+h*(nu_p-nu*)`，所以只要状态被改写或输出被裁剪，最终结果就不再是
原无约束隐式方程的严格解。必须分别保存 ideal、state-mapped、preclip 和 applied 值。
本阶段不实现论文的 conditioned 控制律。

## 起飞状态机

开关默认关闭，且尚未连接参数。输入只允许控制器已有的 armed/rate/落地状态，以及机载本地
位置 NED `z/vz` 的有效估计；不接受 Gazebo 真值，不修改全局 land detector。

- `Waiting`：解锁并选中实验后清零 `nu`，捕获有效地面高度；冻结状态。
- `ConfirmingTakeoff`：两个落地标志均为假、高度增量至少 0.12 m、NED 垂速不超过
  0.20 m/s，连续 0.20 s 才释放。证据消失则返回 Waiting。
- `Released`：正常更新。空中短时 landed 只有同时接近起飞高度且速度很小才进入落地确认。
- `ConfirmingLanding`：接近基准高度、低速且存在落地标志连续 0.50 s 后才清状态；弹跳取消。
- `LandedHold`：保持冻结；仍 armed 的第二次起飞会重建基准并重新确认，避免永久冻结。
- `Fault`：估计单步超过 0.50 m 或等待超过 10 s 时中止/冻结；必须 disarm，再由公共 fault
  acknowledge 后重新解锁。不会用固定延时静默释放。

阈值是 I02 离线候选，不是飞行批准值；I03 若获授权须作为独立消融因素冻结协议。
armed 修改只暂存，disarm 后生效。默认关闭时保留旧 landed reset 与旧 PID/ESTA/ISTA 路径。

## 预定测试

1. 11 个 Proper 保护 GTest：理想候选、`2*Delta nu`、正负三轴饱和位、反馈有效期边界、
   nu/output 限制、生命周期冻结、原子失败、时间/测量 fault latch、armed 暂存、受保护提交。
2. 10 个起飞管理 GTest：默认关闭、配置边界、正常起飞、假离地/取消、估计跳变、超时、
   空中误判、落地弹跳、确认落地/二次起飞、armed 暂存/disarm 生效及公共 fault acknowledge。
3. 回归 Proper 内核 16 个、既有 M09 的 PID/ESTA/原 ISTA 90 个 C++ 与既有 Python 套件；
   构建 SITL，只检查固件符号，不启动仿真。
4. 检查 `sta_rate_ctrl_status` 生成格式仍小于 logger 1500 字节上限。本阶段不改消息，真实 ULog
   解码留待 I03/I04。
5. `nm -C` 必须确认 Proper 内核及其保护适配器均不在最终固件；参数、消息、land detector、
   模型/world 和执行器模块不改。

所有失败保留在新 attempt 目录，不因失败放宽阈值。MATLAB/Octave 不属于本阶段必需验证；未执行
必须明示。
