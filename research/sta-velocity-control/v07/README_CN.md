# V07：速度纠偏分频与宿主耗时

当前阶段只比较 **原速度 PID** 与 **XY ESTA + Z 速度 PID**。原位置 P、姿态环、全部角速度 PID 不变。
V06 的 XYZ ESTA 不自动成为本阶段 Z 授权；DIV>1 明确拒绝 Z/XYZ ESTA。默认 DIV=1/PID，参数切换只能落地上锁后生效。

## 实现口径

- `MPC_VC_DIV=1/2/4` 与角速度 `MC_RTC_DIV=1` 独立。V06 实测回调约100Hz；本阶段按日志实测频率命名，不预称250Hz。
- DIV1 保留原 PID 数学及更新时序；两个2048步冻结参考回归仍是验收项目。
- DIV2/4 只保持不含加速度FF的纠偏，积分/ν只在真实更新推进。位置P、新目标/FF、倾角、推力转换、Z优先/XY余量仍每有效回调处理。
- HTE 引起的 Z PID 积分增量同步加入纠偏缓存。它不是一次速度积分，不把旧总推力直接缓存。
- 每回调 sample 原始时间差仍限2–40ms；积分h是上次真实更新到本次的sample差，上限N×40ms。逐回调检查不能用放宽h替代，也不夹限h掩盖停顿。
- 区间汇总实际观察到的NED映射约束方向。PID受影响轴保守冻结积分；ESTA仅冻结向外ν增量。不是mixer符号，也不声称恢复未观察到的反馈。
- 同帧第二次调用不重复积分；异常锁存，不声称停止发布等于安全悬停或自动PID接管。起降/NaN使能切换使旧缓存失效，重新进入建立新时段。

## 日志与分析

`sta_velocity_ctrl_status` 旧调用计数含义不变。扩展既有 `velocity_ctrl_selection`，队列8，用相同 `publish_seq` 精确关联：

- `div_req/div_eff/div_pending/div_reject`：请求、生效、暂存、拒绝。
- `control_seq/control_updated/control_held/h/control_fault`：真实反馈更新、保持、真实h及故障。
- `correction[0..2]`：未加FF的速度纠偏；`integral[0..2]`：本次调用后PID积分状态。
- `interval_pos/interval_neg`：当前观察后、供下一更新使用的区间方向位；不是实际加速度。
- `path_ns/module_ns/clock`：Linux CLOCK_MONOTONIC宿主墙钟。path包含速度分配、映射、保护及诊断；module从Run入口到选择状态发布前。分更新/保持统计，不称纯算法CPU、板级耗时或WCET。
- ν理想候选在保持周期为NaN，没有运行内核就不伪造理想更新；应用状态仍记录。

TV只按真实更新序列。频谱重采样仅用于分析，不用于补齐验收日志：原生按实测更新频率ZOH；共同带宽先100Hz回调网格ZOH，再513阶长度的Blackman FIR（8Hz截止）、降至25Hz，比较0–7Hz，首尾各裁2.56s。独立测试验证通带和混叠抑制。

## 固定预算与运行

协议 `protocol01/execution.json`：同一低幅固定yaw8字任务，DIV1→2→4；每档3个新配对种子，各PID后ESTA，共18次。每一档6次及3对通过才进入下一档。沿用V06已通过的软接触模型、起降/交接/末尾真实日志采集；原始Iris/world不改。

默认只打印清单：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/v07/protocol01/run.py --source-head "$(git rev-parse HEAD)" --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260928/V07/series01'
```

实际执行还需`--execute --authorization <绑定干净源码与协议SHA的记录>`；用户已给V07持续授权，不需每轮再问。脚本仍强制18次有限预算和失败停止，不能复用已耗种子或重跑失败批次。仅可在完整通过一档之后按原清单恢复。

本文件为实现说明，不代表已完成飞行验收；最终以 `reports/V07.md` 和原始证据为准。不push，不进入V08。
