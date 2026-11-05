# AX03 结果包：固定参数八配置开发验证

本目录只做结果汇总/审计，不启动 PX4/Gazebo、不改参数、不修改 AX02 验收规则。
报告：[AX03.md](../../reports/AX03.md)。当前结果提交 SHA 见外部实时进度，不能把结果提交当作飞行源码。

## 已执行的冻结清单

- 协议/源码提交：`9f514213a2d9b0d66674367c009e0d8886fe6c39`。
- 实际干净飞行 HEAD：`ab9df703f837a3cb2b78a9295c5d4202e4f5a3ff`；相对协议提交仅五个报告/证据文件变化，固件已重建并核验。
- 原清单：[AX02 execution.json](../ax02/execution.json)，H24→V24；每任务 PID/X/Y/Z/XY/XZ/YZ/XYZ × 3 个配对种子。
- H：51001–51003；V：51011–51013。它们已经使用，不能再称新种子。
- 原数据：`/home/yr/Desktop/codev doc/experiments/VELOCITY-AXIS-ABLATION-20261008/AX03/batch01`。
- 原执行命令、退出码及指纹入口见报告和 `results/references.json`。本批预算已用完，不续跑，不以重建新输出目录绕过限制。

## 只读复现

依赖沿用项目已有 `.px4-python` 和 M00 Python 目录；不需要安装或升级。
以下输出目录必须不存在；选择新的独立目录，不覆盖 `batch01`、`replay01` 或 `audit01`。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"

python3 research/sta-velocity-control/axis_ablation/ax03/test_collect.py

python3 research/sta-velocity-control/v08/evidence_tools/replay_batch.py \
  '/home/yr/Desktop/codev doc/experiments/VELOCITY-AXIS-ABLATION-20261008/AX03/batch01' \
  --protocol research/sta-velocity-control/axis_ablation/ax02 \
  --output /tmp/AX03-replay-new

python3 research/sta-velocity-control/axis_ablation/ax03/collect.py \
  --batch '/home/yr/Desktop/codev doc/experiments/VELOCITY-AXIS-ABLATION-20261008/AX03/batch01' \
  --replay /tmp/AX03-replay-new \
  --output /tmp/AX03-audit-new
```

原分析器完整解码每轮飞行 ULog，检查模式/轴/内环、时钟、消费目标、理想/受保护状态、接管和起降。
独立目录回放必须与原 `xyz_metrics.json` 数值完全一致。已知唯一字节差异允许项是 `cli_receipts.counts` 的字典键顺序；不归一化任何数值或重写原文件。
`collect.py` 再解码每份启动/飞行 ULog，校验前后 SHA、无 corruption/dropout、真实离地和主窗轴配置，汇总完整48项及42组配对。
它只接收完整矩阵；缺轮/失败不能生成“完整通过”。若未来批次失败，应保留原记录另写失败报告，不能修改此脚本把缺失填零。

## 指标解释

- 速度：64秒激励窗内**实际被消费**的 `v-v_sp` 时间加权逐轴 RMSE（m/s）；另保留两个32秒半窗、均值、标准差及 IAE。
- 位置/yaw：原90秒观察口径；保留原位置P，因此不同算法最终合成的速度目标不必逐样本相同。
- TV：只按真实更新计算，分别报告未加FF的纠偏、加速度需求和归一化推力的 TV/T。不是电机能耗。
- 频谱：保留原生频谱文件；共同带宽使用原冻结的513 tap/8Hz Blackman FIR→25Hz、0–7Hz口径，不用重采样修补缺样。
- 耗时：宿主墙钟。原 `host_cost.path_ns/module_ns` 键沿用输入字段名，但其中统计已换算为 **µs**；不是板级CPU/WCET。
- 每配置每任务只有3个开发配对种子，仅IMU播种，其他传感器/宿主调度不完全可控；PID固定先行及既有历史开发预算均是局限。

通过开发风险门不等于性能胜出，更不等于实机安全认证；不运行AX04、正式留出或ISTA。
