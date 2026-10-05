# AX01：全掩码离线接口与回归

只支持 **Iris SITL 研究范围，未获得新矩阵飞行资格**。本目录没有起飞命令、参数写入或 `--execute` 选项。
正式接线/完整 ULog 任务分析器与开发协议属于 AX02；旧 V08、V06、rate 的运行器保持原目标，不把它们泛化成新八组运行器。

| 名称 | MODE / AXES | 正常 ESTA / 剩余 PID 轴 |
|---|---|---|
| pid | 0 / 0 | 无 / XYZ |
| x | 1 / 1 | X / YZ |
| y | 1 / 2 | Y / XZ |
| xy | 1 / 3 | XY / Z |
| z | 1 / 4 | Z / XY |
| xz | 1 / 5 | XZ / Y |
| yz | 1 / 6 | YZ / X |
| xyz | 1 / 7 | XYZ / 无 |

这里是本地 NED 北/东/下，不是机体角速度轴。表格假设三个速度目标合法且已完成交接；含 Z 的组保留地面/ramp PID 和一帧有界 PID 交接。
MODE2 拒绝，默认 MODE0/AXES0；专项全部 DIV1。旧 PID/X/XY 的 DIV2/4 能力保留，新 Y/XZ/YZ 不开放分频。

## 离线命令

在仓库根目录：

```bash
cd /home/yr/Desktop/Codev-autopilot
python3 research/sta-velocity-control/axis_ablation/ax01/interface.py
python3 research/sta-velocity-control/axis_ablation/ax01/interface.py yz
python3 research/sta-velocity-control/axis_ablation/ax01/test_interface.py
python3 research/sta-velocity-control/axis_ablation/ax01/verify.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-AXIS-ABLATION-20261005/AX01/offline_new_unique'
```

输出目录必须不存在；验证脚本遇到失败停下并保留日志。它会编译测试、SITL、Gazebo 目标，Gazebo 命令设置 `DONT_RUN=1`，不启动仿真。
`interface.py` 只打印 AX00 审计候选的完整控制参数，八组除 MODE/AXES 外完全相同；不加载到飞控，不把候选称作已合格飞行参数。

真实模块离线轨迹解析（文件由验证器产生）：

```bash
python3 research/sta-velocity-control/axis_ablation/ax01/interface.py \
  --trace-log '/home/yr/Desktop/codev doc/experiments/VELOCITY-AXIS-ABLATION-20261005/AX01/offline03/historical/VelocityModule.log'
```

轨迹来自实际 `MulticopterPositionControl::Run`/uORB 的同步测试，传感器、inner PID 状态由夹具发布；不是本次飞行 ULog，不代表真实采样率/日志覆盖。
分析器逐组核验模式、掩码、active/committed/pid、交接、ν、sample 时间及序号，拒绝错模式/缺样/重复或倒退时间/不接管/部分提交。
未选中轴的 ν 用 `null` 表示消息中的 NaN，不能写成估算 ν 或 0；推力映射代理仍不是实测加速度。

## 独立参考与适用边界

`reference/` 的五个文件逐字来自 AX00 提交 `c5f240fb638fd94669d86c8f9e1c37d7c2efec38` 对应生产文件，仅按顺序对 `StaVelocityProtection`、`VelocityControlSelector`、`PositionControl` 加 `AX00` 前缀以隔离符号。验证器从 Git 重建并核对，不能随新实现更新参考。
它们仅编入测试。原 ESTA 内核、ControlMath、decimation 未改变，参考共享这些依赖；这不是独立推导新控制律。
旧 0/1/3/4/7 每组两条 2048 步序列比较有限值位模式、NaN 语义及输出/积分/状态。它是固定序列回归，不证明所有可能输入全等。
独立双精度对象测试另加入姿态/电机一阶滞后及约束、扰动，只验证数值有界和接线方向，不是 Gazebo、安全飞行或性能优越性证明。

`legacy_tuning.py` 明确排除**唯一**不适用于 AX 新源码的 V08“自 V07 起所有生产源码字节不变”检查。原检查和首次失败原样保留，不算通过。其余适用功能测试正常运行；V08 冻结资产不得使用 AX HEAD 冒充。
详见 [AX01 报告](../../reports/AX01.md) 和外部实时进度。未启动 AX02、未分配新种子、未 push。
