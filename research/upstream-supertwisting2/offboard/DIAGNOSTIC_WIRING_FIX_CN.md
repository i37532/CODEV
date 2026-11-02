# Offboard 诊断接线离线修复与回归

2026-11-02。**已修复原版 STA2 进入悬停时漏读诊断话题的问题，离线回归通过。** 本次零飞行，没有改控制律、固件、参数、任务波形、数值安全阈值或 ULog 验收器；B02 仍为 1 次接受、1 次中止、6 次未执行，历史失败不改判。

当前分支 `research/upstream-supertwisting2`，HEAD `1f6fe1c7a46c22ea41a6a6a51c51498142ca6d62`。本次未提交、未 push，既有未提交文件保留。

## 修复内容

原故障见 [B02 停批报告](BATCH02_RESULT_CN.md)：采集端缺少专用悬停配置时使用空字典，而检查端仍要求基础诊断，导致没有读取原本正常发布的 `attitude_sta_status`。

现在清单准入、参数核验、实时采集与状态检查使用同一套诊断配置选择规则：

| 配置情况 | 行为 |
| --- | --- |
| 没有 `hover_diagnostic_expectations` 键 | 继承基础诊断配置，原版 STA2 各阶段仍读取 `attitude_sta_status` |
| 存在合法专用配置 | 按既有专用配置读取，保留 PID/RSTA/RISTA 的 active_axes、内环和 fault 检查 |
| 显式空字典、null、错误类型或非法值 | 准入时拒绝，不当成缺省继承，不允许禁用诊断 |
| `attitude_sta_status: {}` | 合法：空的是字段条件，不是话题；仍必须实际读取话题和有效时间戳 |

- `runner_contract.py`：集中选择与快照检查，预先验证两种阶段配置，同一系统跨任务的诊断条件不能悄悄变化。
- `run.py`：两处实际采集入口共用 `collect_diagnostics`，每次重新读取，缺失时不沿用缓存。计分阶段集合直接使用检查器的同一定义。
- 原有模式、轴掩码、时间戳有效性和状态检查保留；不会因原版缺少专用配置而跳过检查。没有给未知算法增加默认映射。

## 实际回归结果

| 检查 | 实际数量 | 退出码与结果 |
| --- | ---: | --- |
| 全部 Offboard 单元测试 | 271 | 0，通过，无跳过 |
| 其中新增诊断接线测试 | 21 | 已包含在 271 中，不重复计数 |
| 既有四系统工具测试 | 72 | 0，通过，无跳过 |
| 既有航向策略测试 | 10 | 0，通过，无跳过 |
| 合计单元测试 | **353** | 全部通过 |
| 旧航向检查及 Navigator 日志回放 | 5 份 ULog、17 个内存负例 | 0，旧判定保持，负例全部拒绝 |
| B02 日志回放 | 2 份 ULog | 0，PID 指标完全相同；STA2 部分任务仍拒绝 |
| 四系统真实 CLI 记录核对 | 4 套记录 | 原始文本及来源 SHA 核验，两种配置选择路径通过 |

新增测试从实际 `run.execute` 抽取原样的 `topic/diagnostics/verify_configuration/sample` 函数体，在隔离闭包中执行；仅替换进程和 CLI 边界，不启动 PX4、Gazebo、ROS 或网络。测试使用已冻结八项 job 和四系统真实 listener 文本，不再只给检查器手工填入完整诊断字典。

覆盖两任务、四系统的预热→预发送→起飞→稳定→悬停→任务→恢复→下降→落地采集路径；阶段状态变化及负例为明确的离线合成输入，不是未执行飞行的回放。验证两处入口都真正读取话题、阶段切换不漏读、无缓存补缺，并覆盖缺专用键、显式空值、每个必需话题缺失、模式/轴/内环/fault 不符、时间戳缺失/NaN/Inf/负值/非整数。

保留的 B02 旧运行器在同一离线闭包内精确复现原错误；修复后的实际函数体通过同一输入。PID/RSTA/RISTA 新旧快照一致，未使用的 NaN 诊断项按项目既有 `diagnostic_json` 表示比较，没有冲零或把 NaN 当有效必需状态。

### 历史结果不变

- B02 PID：重新完整解码 ULog，指标与原 `metrics.json`、`independent_replay.json` 完全一致。
- B02 STA2：原 ULog 仍有 12,217 个诊断样本，但缺少完成的悬停/后续任务，完整分析仍因 `Unpaired phase event: hover` 拒绝，`success=false` 保持。
- 原首批 O001：严格旧规则仍拒绝；修订航向规则的离线诊断不转换历史结果。
- 四个更早的 Navigator 日志：按各自原合同回放，指标和判定不变，不与 Offboard 样本合并。
- B02 后续 O003 仍被首败规则拒绝；修改工具后旧资产指纹也不再匹配，不能直接执行旧清单。

### 开发中遇到的失败

第一次运行新增 21 项测试有 2 项失败：一项直接比较已序列化的 `"NaN"` 与原始 float NaN，另一项直接比较两份含 NaN 的字典。改为项目既有诊断序列化表示后重跑全部测试通过；没有改变生产数值有效性检查。保留了第一次失败输出。

另一次只读参数探针未设置项目依赖路径，因缺少 numpy 退出 1；设置已有 `PYTHONPATH` 后四系统参数核对通过，没有新安装依赖。一次补丁因同一文件重复操作被工具原子拒绝，未产生文件改动，重新合并补丁后应用。

## 文件和证据

核心修改仅为 `run.py`、`runner_contract.py`；新增 [接线测试](test_diagnostic_wiring.py)、[离线回放入口](replay_diagnostic_fix.py)、真实 CLI fixture 和本报告/README 入口。旧 B02 运行器与合同快照仍在 `results/batch02/frozen_tools/`，原结果、协议及日志未覆盖。

证据：[测试及指纹汇总](results/diagnostic_fix01/validation.json)、[B02 回放](results/diagnostic_fix01/b02_replay02.json)、[历史回放](results/diagnostic_fix01/historical_replay02.json)、[真实 CLI fixture](results/diagnostic_fix01/cli_fixture.json)。测试完整输出同在 `results/diagnostic_fix01/`。

外部工作目录：`/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-DIAGNOSTIC-FIX-20261102-xvn129`。本次开始时记录 379 个已有文件指纹，结束时除两个目标脚本及 README 入口外均不变，包含历史实验、固件、参数文件和已有用户改动。没有启动仿真，因此未进行 C++ 重构建或新的飞行验收。

## 复现命令

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python:/home/yr/Desktop/codev doc/experiments/M10-20260917/plot_dependencies01/python"
export PYTHONDONTWRITEBYTECODE=1
python3 -B -m unittest discover -s research/upstream-supertwisting2/offboard -p 'test_*.py' -v
python3 -B -m unittest discover -s research/upstream-supertwisting2/tools -p 'test_*.py' -v
python3 -B -m unittest discover -s research/sta-velocity-control/scripts -p test_v04_heading_policy.py -v
```

已执行的回放命令（输出路径已占用；复查应另选新输出，不覆盖证据）：

```bash
python3 -B research/upstream-supertwisting2/offboard/replay_diagnostic_fix.py \
  --output '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-DIAGNOSTIC-FIX-20261102-xvn129/b02_replay02.json'
python3 -B research/upstream-supertwisting2/offboard/replay_heading_fix.py \
  --attempt '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102/runs/O001' \
  --frozen-analyzer research/upstream-supertwisting2/offboard/results/heading_fix01/analyze_frozen_O001.py \
  --output '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-DIAGNOSTIC-FIX-20261102-xvn129/historical_replay02.json'
```

## 下一步

离线修复完成，但未创建新飞行清单。下一步是重新明确有限续跑预算、历史样本处理方式和顺序，冻结修复后的工具及全部资产后再起飞；不能重写 B02 指纹、重跑其 O002 或称当前四系统实验已完成。
