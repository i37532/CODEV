# Offboard 事件语义离线修复与整链回放

2026-11-02。**旧事件重发误判已修复，离线回归通过；原版 STA2 的完整分析链仍因落地末帧时效失败而不能验收。** 本次没有飞行、改控制器或调参数，也没有改判 B01/B02/B03 的历史结果。

当前分支 `research/upstream-supertwisting2`，HEAD `1f6fe1c7a46c22ea41a6a6a51c51498142ca6d62`。保留既有未提交代码、手册和图表；本次未提交、未 push。

## 修复规则

原版固定提交 `fc3720f67767c78cfab668777de13f68562fe2fd` 的 `EKF2::PublishEventFlags` 有两条路径：新事件增加 `information_event_changes` 并更新采样时间；无新事件时，每秒重发缓存，只改发布时间。原检查器把后者也当作新事件，导致 B03 O002 被误报 `reset_vel_to_gps`。

新增显式策略 `upstream_fc3720_event_republication_v1`，只在已核实的原版版本与完整航向证据路径下采用新处理。默认 `publication_events_v1` 保持旧规则；主仓库的旧 event-only 发布机制仍保持原检查，不要求它发送周期心跳。

| 情况 | 新检查行为 |
| --- | --- |
| 计数相同，采样时间及全部 17 个布尔字段完全相同 | 合法重发，保留每条发布记录，不去重 |
| 计数相同，但采样时间或任何载荷字段变化 | 拒绝，不能借缓存掩盖新事件 |
| 计数增加 1，包括 uint32 单次回绕 | 必须采样时间前进、载荷非空；按新事件检查 |
| 计数跳跃、倒退、非法值；NaN、非二值字段、未知或缺失字段 | 拒绝 |
| 新禁止事件与检查窗口起点、终点或延迟采样边界重叠 | 拒绝，即使事件标志与旧缓存相同 |
| 只剩窗口中间数据、缺前驱/严格后继、丢失周期记录 | 拒绝 |

事件话题的周期覆盖单独按源码的 **1 秒重发周期＋原有 500 ms 间隔余量**检查，最大 1.5 秒。此话题过去没有心跳检查；这是新增的版本化约束，不是把位置、目标或终止状态的 500 ms 规则放宽为 1.5 秒。所有其他数值限制保持不变。

每条记录仍校验严格递增的发布时间、有效采样时间、完整载荷与计数。检查包含起点前记录和终点后的严格后继，并核验到后继为止的已记录计数历史。现有位置/速度 reset、姿态/航向配对、主实例、故障、目标、模式、参数和安全边界检查保留。

## 修改范围

- `heading_check.py`：加入版本化事件历史校验，返回重发数量、边界及新事件证据。
- `analyze.py`：显式读取 `event_semantics_policy`；无完整航向证据时不能启用新规则。
- `runner_contract.py`：清单与各 job 必须统一显式声明策略，未知或混用策略拒绝。没有改实时采样或落地循环。
- 新增 [27 项事件语义测试](test_event_semantics.py)、[真实事件夹具](results/event_fix01/sta2_event_fixture.json) 与[整链回放入口](replay_event_fix.py)。

没有改 `run.py`、原任务、控制律、默认参数、固件、模型、估计器、land detector 或历史冻结快照。没有创建可飞的新清单；旧清单既不能改判，也不能直接续飞。

## 实际测试

| 检查 | 数量 | 结果 |
| --- | ---: | --- |
| Offboard 单元测试 | 306，含新增 27 项 | exit 0，无跳过 |
| 既有四系统工具测试 | 72 | exit 0，无跳过 |
| 既有航向策略测试 | 10 | exit 0，无跳过 |
| 合计 | **388** | 全部通过 |
| 真实 ULog 回放 | **9 份，8 份完整动作日志＋1 份部分任务** | 按下表分别报告，不称 9 份均验收通过 |
| 真实原版 ULog 的内存负例 | 4 | 全部在预期事件检查处拒绝；不计入 388 |
| 四系统真实 CLI 接线记录 | 4 套、两种配置选择路径 | 保持上一轮修复，通过 |

新增测试包含四系统×位置/速度两任务的完整合成链、所有禁止事件、相同标志再次触发、全部缓存字段篡改、精确边界/延迟后继、计数回绕/跳变、无效时钟/载荷、字段与周期记录缺失、版本/策略错误、模式准入及真实 reset 不得豁免。主仓库 PID/RSTA/RISTA 新旧完整输出精确一致。合成任务测试不是实际飞行。

首次新增测试 27 项中有 1 个边界负例失败：终点恰有记录时，初版只检查到了终点，漏掉了终点后的延迟事件。改为强制包含严格后继后，完整 388 项通过。失败输出保留，没有降低边界要求。

## 真实日志回放

所有原始 ULog、事件、job、参数、结果均只读。回放在独立输出中使用显式新策略；旧策略和 B03 冻结分析器的判定/输出逐项一致。全部原 Offboard 批次的 **209 个证据文件**前后 SHA 保持一致。

| 原记录 | 本次离线回放 | 历史结果 |
| --- | --- | --- |
| B01 O001 PID | 默认旧规则仍拒绝航向 reset；显式既有航向策略＋新事件策略的诊断回放通过 | 仍失败，不转换为新样本 |
| B02 O001 PID | 完整指标与原 metrics、independent_replay 精确相同 | 接受不变 |
| B02 O002 STA2 | 仍拒绝 `Unpaired phase event: hover` | 部分任务仍失败 |
| B03 O001 PID | 完整指标与原记录精确相同 | 接受不变 |
| B03 O002 STA2 | 事件与航向检查通过，完整调用到落地时效检查后拒绝 | 仍失败 |
| 旧 Navigator S101/S202/S203/S304 | 按各自原 Navigator 合同回放，指标、接受状态及指纹精确相同 | 不混入 Offboard 样本 |

原版真实事件夹具与 B03 原 ULog 的全部字段逐项相同，并核对原日志及原结果 SHA。固定版本的 `EKF2.cpp`、`EstimatorEventFlags.msg` 与该 Git 提交内容一致。没有把未验证的其他 PX4 版本自动归入新规则。

## 整条分析链发现的剩余问题

B03 O002 使用新策略后，已经通过原调用链中位于终止检查之前的完整航向/reset、参数、模式、安全边界、计分窗诊断和速度指标计算。随后仍触发：

```text
ValueError('Stale final state receipts')
```

| 末帧证据 | 原生时间 |
| --- | ---: |
| 记录的 `landed_disarmed` 位置时间 | 103.560 s |
| 该事件所引用的 status 发布时间 | 103.528 s，差 32 ms |
| 该事件所引用的 land 发布时间 | 102.656 s，差 **904 ms** |
| 冻结时效上限 | **500 ms** |
| 日志中的下一条 land 发布 | 103.656 s，仍为 landed/ground_contact |

运行器看到 `landed=true` 和 `arming_state=1` 就结束，没有同时确保记录的两种状态足够新鲜。现有完整 ULog 中确实有之后的 land 消息，但不能用它回填或改写原末帧事件。该问题属于终止状态采集与验收的时序不一致，不能通过放宽 500 ms 或修改历史时间戳解决。

为避免只检查到首个错误，回放脚本还**单独执行了原分析器之后的剩余组件**：原始落地/上锁值检查、ROS 发布—实际发送身份核对、全部实际目标匹配、话题时钟统计均通过。1342 个 ROS 发布、1341 个实际发送的既有身份/顺序/目标规则通过。这些分项不绕过终止检查，不合成为一次“完整通过”。

旧 B03 O003 仍被首败逻辑拒绝；四系统出图入口仍因 O002 未接受而拒绝，未生成误导性比较图。RSTA/RISTA 的新 Offboard 飞行及四系统速度任务仍未执行，现阶段只能依赖合成接线测试，不能声称有对应真实任务覆盖。

## 证据与复现

[验证汇总](results/event_fix01/validation.json)、[整链回放](results/event_fix01/replay02.json)、[既有诊断接线回归](results/event_fix01/diagnostic_regression02.json)。大日志仍在原批次目录，未复制或删除；本次工作目录为：

`/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-EVENT-FIX-20261102-XS6m34`

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python:/home/yr/Desktop/codev doc/experiments/M10-20260917/plot_dependencies01/python"
export PYTHONDONTWRITEBYTECODE=1
python3 -B -m unittest discover -s research/upstream-supertwisting2/offboard -p 'test_*.py' -v
python3 -B -m unittest discover -s research/upstream-supertwisting2/tools -p 'test_*.py' -v
python3 -B -m unittest discover -s research/sta-velocity-control/scripts -p test_v04_heading_policy.py -v
# 分别 exit 0，306 / 72 / 10 项
python3 -B research/upstream-supertwisting2/offboard/replay_event_fix.py \
  --output '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-EVENT-FIX-20261102-XS6m34/replay02.json'
# 已执行 exit 0；含预期拒绝的诊断回放，不代表所有飞行通过；复查须另选未占用输出
python3 -B research/upstream-supertwisting2/offboard/replay_diagnostic_fix.py \
  --output '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-EVENT-FIX-20261102-XS6m34/diagnostic_regression02.json'
# 已执行 exit 0；保持历史结果
git diff --check
# exit 0
```

首次真实 STA2 整链探针因上述落地时效退出 1，故如实记为尚未全链通过；后续诊断入口 exit 0 只表示成功复现并核对各项证据。本次不需要 C++ 构建、ROS 启动或新增试飞。

## 下一步

先离线修复落地确认采样：在现有有界等待内，只有落地、上锁及状态时间差同时满足冻结条件才记录最终事件；补齐四系统接线、旧缓存/新发布、超时、状态反跳等回归。保持 500 ms 阈值，不改 land detector 或控制律。然后才重新冻结新策略、完整工具指纹及有限批次；不能直接继续旧 B03。
