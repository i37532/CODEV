# ROS Offboard 四系统第二批：停批报告

2026-11-02。**新批次已冻结并执行，但四系统对比没有完成。** 计划 8 次，实际起飞 2 次：PID 完整通过，原版 STA2 因运行器诊断采集接线错误中止，剩余 6 次未执行。没有补飞、改增益、放宽门槛或拼接旧成功样本，没有生成四系统对比图。

## 执行清单

| 新批次编号 | 任务 | 系统 | 实际结果 |
| --- | --- | --- | --- |
| O001 | position | PID | 起飞、悬停、两个高度阶跃、降落上锁、ULog 检查及独立重读复算通过 |
| O002 | position | 原版 STA2 | 起飞并完成稳定等待；进入悬停后监视器报错，终止 SITL，未完成任务 |
| O003 | position | RSTA | 未执行：首败停批 |
| O004 | position | RISTA | 未执行：首败停批 |
| O005 | velocity | PID | 未执行：首败停批 |
| O006 | velocity | 原版 STA2 | 未执行：首败停批 |
| O007 | velocity | RSTA | 未执行：首败停批 |
| O008 | velocity | RISTA | 未执行：首败停批 |

新批次计划/尝试/起飞/完整完成/接受/无效/未执行 = **8/2/2/1/1/1/6**。包含原批失败 O001，历史实际尝试共 3 次，未超过已记录累计上限 9 次。原批 O001 仍无效，原批其余 7 项关闭；新旧编号由数据目录区分。

原版 STA2 的仿真在空中被停止，不能写成“完成降落”。两轮参数精确恢复，均无残留仿真进程。原版运行时新生成的 `parameters.bson` 与 `parameters_backup.bson` 已按备份记录移除，恢复为本轮开始前的不存在状态；没有删除原有参数或原始日志。

## 冻结和资格

- [准确协议](BATCH02_PROTOCOL_CN.md)、[冻结清单](results/batch02/manifest.json)、[批次索引与指纹](results/batch02/batch_result.json)。清单 SHA-256：`51f69ef414d51e24e29b9c6b4dbcf2d08a5b38dcac27294fbc43f4d08cc04763`。
- 分支 `research/upstream-supertwisting2`，HEAD `1f6fe1c7a46c22ea41a6a6a51c51498142ca6d62`。保留既有未提交源码、手册及图表；未声称工作区干净。本轮未提交、未 push。
- 参数、目标波形、安全阈值、两份固件和既有启动器均沿用原冻结版本；唯一预先修订的验收语义为准备阶段航向对齐白名单。它在新 PID 飞行中已接受完整证据，旧失败没有改判。
- 结束后重新校验全部 91 个清单资产、各 job 的源码资产、固件、HEAD 与两仓库递归子模块，均未改变。主固件仍为历史已登记源码构建，不冒称当前干净 HEAD 的构建。原版仓库未初始化的无关平台子模块保持原样，没有为本批更换版本。
- 实际运行 **250 个 Offboard、72 个旧工具、10 个旧航向策略测试，共 332 项**，均 exit 0、无跳过。另有真实 ROS 本机回环：25 个位置目标、20 个速度目标和转发心跳通过；使用模拟遥测，没有启动飞控，不算飞行样本。
- O001 执行 exit 0，O002 执行 exit 1。停止后只读诊断 exit 0；其中 7 项诊断断言单列，**不是另外 7 个单元测试，也不是 O002 验收通过**。

## 停批原因：采集端和检查端的默认配置不一致

这次是工具接线遗漏，不是缺少 ROS 目标，也不是已证明 STA2 算法失稳。

原版 STA2 的 job 有 `diagnostic_expectations={"attitude_sta_status": {}}`，但没有单独的 `hover_diagnostic_expectations`。

1. 冻结 `run.py` 第 116、165 行在进入悬停后查找后者，缺省回退到空字典，因此没有读取任何诊断话题。
2. `runner_contract._check_diagnostics` 缺省回退到基础诊断配置，仍要求存在 `attitude_sta_status`。
3. 首次悬停采样因此报告 `ValueError('diagnostic attitude_sta_status must be a mapping')`，运行器按冻结规则停批。

实际证据与“话题未发布”不符：停止前有 **197 次成功的 CLI 读取**；ULog 有 **12,217 个** `attitude_sta_status` 样本，12 个数值字段均有限、时间严格递增、最大间隔 **8 ms**，该日志无 dropout、无文件损坏。最后一次采样前已记录的诊断快照可通过原检查器；但采集端在阶段切换时自行漏读了它。

[只读复现脚本](results/batch02/diagnose_stop.py) 从实际冻结 `run.py` 的 AST 提取两个配置选择表达式，再对真实 job 和记录快照调用原检查器，精确复现同一错误。完整证据见 [stop_diagnosis02.json](results/batch02/stop_diagnosis02.json)。同时核实 O003 被首败停批逻辑拒绝，没有启动新的仿真。

之前的单元测试覆盖了“给检查器一个含诊断的状态”，却没有覆盖“原版 STA2 无专用悬停配置时，实际采集端是否仍读取基础诊断”的完整接线。332 项通过不能替代这个缺失场景。

本次停止后未修改已冻结运行器、验收器或算法。离线复现仅解释故障，不补造悬停、阶跃或降落证据，不将 O002 改判为通过。

## 已获得的数据及未完成项

PID 的 10.008 s 悬停窗口，相对初始位置高度均值约 2.478 m；实际速度目标跟踪 RMSE 为 X/Y/Z = 0.00817/0.00775/0.00301 m/s。全程最大倾角约 4.105°，位置日志原生中位频率约 10 Hz。这些仅是单轮 PID 描述，不是四系统排名，不能据此判断 STA2、RSTA 或 RISTA 响应快慢。

未执行：剩余六轮、完整原版 STA2 位置任务、四系统曲线及响应速度比较。原始日志、失败命令、ROS 发送记录、参数快照均保存于：

`/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102-B02/`

| 记录 | ULog SHA-256 |
| --- | --- |
| B02 O001 PID | `2d17de0c4d632f90a5c9130edd91ddf4545becf0f7cbc1c5f471a60ea9817b79` |
| B02 O002 STA2 | `1f2e8c364ec4308f527fc191b0d0fbe3002bd38a6ac178538e9c5b71b6097b96` |

仓库仅保留小型结果/测试/配置/指纹和冻结工具快照，大日志外置。

## 下一批之前需要完成

1. 离线统一运行器采集、参数核验及检查器的诊断配置选择语义：缺少专用配置时必须继承基础配置，不是删除必需检查或允许空诊断。
2. 补齐四系统从预热→起飞→稳定→悬停→任务→降落的采集接线回归，覆盖缺少专用键、显式空值、缺话题、错模式和阶段切换；使用真实冻结 job 与实际 listener 记录，不只手造已完整状态。
3. 审查修复后，明确下一批有限预算、准确顺序与源码版本，重新冻结再飞。不能直接改写 B02 清单、重跑 O002 或把部分飞行当接受样本；本轮没有自行扩大预算。

## 命令与退出码

以下为已执行记录，不是让用户重跑已占用编号：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python:/home/yr/Desktop/codev doc/experiments/M10-20260917/plot_dependencies01/python"
export PYTHONDONTWRITEBYTECODE=1
python3 -B -m unittest discover -s research/upstream-supertwisting2/offboard -p 'test_*.py' -v
# 250 tests, exit 0
python3 -B -m unittest discover -s research/upstream-supertwisting2/tools -p 'test_*.py' -v
# 72 tests, exit 0
python3 -B -m unittest discover -s research/sta-velocity-control/scripts -p test_v04_heading_policy.py -v
# 10 tests, exit 0
python3 -B research/upstream-supertwisting2/offboard/verify_live_bridge.py \
  --output '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102-B02/live_bridge02' --execute-local-loopback
# exit 0; no flight
python3 -B research/upstream-supertwisting2/offboard/freeze.py \
  --data-root '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102-B02' \
  --offline-log '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102-B02/offline_tests01.log' \
  --output '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102-B02/manifest.json' \
  --heading-reset-policy offboard_first_takeoff_alignment_v1 \
  --previous-manifest '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102/manifest.json' --freeze
# exit 0
# run.py --manifest <above manifest> --job O001 (dry-run): exit 0
# run.py --manifest <above manifest> --job O001 --execute: exit 0
# run.py --manifest <above manifest> --job O002 --execute: exit 1, then STOP
python3 -B research/upstream-supertwisting2/offboard/results/batch02/diagnose_stop.py
# exit 0; read-only reproduction, not acceptance
git diff --check
# exit 0
```
