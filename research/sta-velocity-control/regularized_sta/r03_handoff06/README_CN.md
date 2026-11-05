# Handoff06：D 任务目标检查的离线依赖修复

本目录只提供离线诊断组件；不接入旧运行器，不更改控制律、波形、参数、容差、旧文件或旧判定，不签发飞行资格。原 revision05 的总预算 57 不在此修改。本目录没有新种子或新飞行清单。

## 问题与限定修改

revision05 D/run028 在线完整分析报 `Downstream XY target differs`。实际 runner-first 导入链为：AX02 `height_evidence` → V08 `check_handoff` → 函数内部泛名 `from task import offsets`，最后命中 V07 的二维参考。该参考只实现任务 6/7，对任务 8 返回零位移，因而把合法的水平 8 字当成目标漂移。C 使用任务 6，其 XY 公式相同，不能覆盖这个缺陷。原版 analyzer-first 独立回放能通过，说明原验收存在导入顺序依赖；这不改变在线的原失败判定。

`adapter.py` 仅做以下依赖修复：

- 固定 AX02 `height.py`、AX02 `task.py`、V08 `handoff.py` 和 `handoff_capture.py` 的路径及 SHA-256。
- 保留两个完整函数体，分别将唯一的局部 `from task import offsets` 替换成 `pass`；将该节点恢复后，整个 AST 必须逐节点等于原函数。
- 在各自独立 globals 中绑定 `height → check_handoff → AX02 offsets`，height 内的高度偏移也用同一个三维参考。不会替换 `sys.modules` 或修改原函数 globals。
- 所有直接项目符号按显式路径载入并检查来源；`task`、`handoff`、`handoff_capture` 不由泛名缓存解析。唯一命名的旧 v04 辅助函数保持原实现，未宣称重写或审计整个历史工具依赖树。

任务 1/2 的位置/加速度前馈偏移为零（它们在另一条速度激励路径工作）；任务 6 是固定 yaw 的水平 8 字；任务 8 在相同 XY 上叠加平滑 Z 位移。四模式参考都必须返回完整有限 N×3 的 p/v/a，不能把二维结果补零冒充三维。

原检查不变：下游窗口 `[hover_start−3s, hover_end)`、各话题首尾及内部最大缺口 40 ms、补偿后的 XY 与编码目标绝对差不超过 0.05 m；原始 Navigator、命令/ACK、航向、时间、重置、起降、保护和实际输出检查仍完整执行。新组件不会因错误捕获而跳过这些检查。

## 测试

从仓库根目录执行：

```bash
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python"
PYTHONDONTWRITEBYTECODE=1 python3 -B research/sta-velocity-control/regularized_sta/r03_handoff06/test_adapter.py
```

合成测试包括：两种真实导入顺序、泛名模块污染、固定源指纹、逆 AST 等价、四模式三维语义、独立位置公式/数值微分、旧零参考复现失败，以及真实目标漂移、相位错误、NaN、缺样、原始目标丢失、ACK/模式异常等负例。完整 handoff 函数体测试用合成上游来源夹具，不能代替原日志的完整 CLI 回放。

## 真实日志诊断（由主任务执行）

两个命令必须分别在全新进程运行，输出目录必须不存在；以下路径保留原 batch 输入：

```bash
python3 -B research/sta-velocity-control/regularized_sta/r03_handoff06/adapter.py \
  '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision05/D/batch01/run028' \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision05/D/handoff06_diagnostic_runner01/run028' \
  --import-order runner-first

python3 -B research/sta-velocity-control/regularized_sta/r03_handoff06/adapter.py \
  '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision05/D/batch01/run028' \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision05/D/handoff06_diagnostic_analyzer01/run028' \
  --import-order analyzer-first
```

诊断沿用 revision05 的原来源/参数恢复、预热收据、候选数值及完整科学分析链，所有读取的原文件和两份 ULog 在前后核对 SHA；输出引用原 ULog，不重写或复制原日志。旧授权侧车仅在原归档中由完整原 `provenance` 读取，不复制到诊断目录。分析前逐文件核对其他副本与原侧车的 SHA；旧 `r03_metrics.json` 也不复制，防止早期异常遗留原接受判定。不会签发新资格。

同一 CLI 还支持已保留的 revision04 A 原始归档：严格核对 `retained_a()` 固定证明和原 A/batch01 路径，使用原 revision04 的 `replay_protocol`、来源及预热检查，原 job/revision 不变。A 仅作修复回归，不计为新试验。其他旧版本/旧 B 门不在此入口范围。用 A、B、C 每个算法一轮和 D 失败 PID 的真实回放覆盖模式 1/2/6/8；每份输出仍为非授权诊断。

所有新保存的诊断 `r03_metrics.json` 和摘要均强制 `accepted=false`、`flight_accepted=false`、`new_flights=0`。`diagnostic_checks_complete=true` 只表示修复后的完整离线检查结束，不等于旧运行改判、更不等于 D 门通过。退出 0 还要求输入/源码指纹与原判均未改变。工具不生成 `gate_pass.json` 或 `authorization.json`，不提供运行器，也不执行 PX4/Gazebo。

首轮合成测试实际为 39 项、退出 0。补齐 retained-A 来源、异常前不得遗留接受副本、原授权读取接线及输出范围负例后，第二轮实际为 46 项、退出 0（1.090 秒）。其中原授权接线夹具执行冻结的真实 `provenance` 函数体，仅替换上游协议查询为临时数据；不是实际正式日志验收。真实全链诊断结果由主任务另存收据，本说明不预填结果。
