# ROS Offboard 四系统 B03：执行与停批报告

2026-11-02。**四系统比较尚未完成。** 新冻结 8 次，已执行 2 次：PID 接受；原版 STA2 完成所有飞行动作并落地上锁，但完整日志检查失败。按首败停批规则，剩余 6 次没有启动。未补飞、未调参、未修改阈值，未生成四系统对比图。

这次失败已定位为分析器未正确处理原版 PX4 的**旧事件周期重发**，不是已证明的 STA2 控制算法失稳。上一轮修复的诊断采集接线正常通过了悬停与后续阶段；本次暴露的是另一处跨版本日志语义遗漏。

## 1. 实际清单与预算

| 编号 | 任务 | 系统 | 结果 |
| --- | --- | --- | --- |
| O001 | position | PID | 完整任务、降落上锁、ULog 检查及重新读取复算通过 |
| O002 | position | 原版 STA2 | 完整任务、降落上锁；日志验收拒绝，未接受 |
| O003 | position | RSTA | 未执行：首败停批 |
| O004 | position | RISTA | 未执行：首败停批 |
| O005 | velocity | PID | 未执行：首败停批 |
| O006 | velocity | 原版 STA2 | 未执行：首败停批 |
| O007 | velocity | RSTA | 未执行：首败停批 |
| O008 | velocity | RISTA | 未执行：首败停批 |

本批计划/尝试/起飞/动作完成/接受/拒绝/未执行 = **8/2/2/2/1/1/6**。此前 B01/B02 共 3 次，本轮后历史实际 5 次，未超过冻结累计上限 11 次。剩余 6 项关闭，不能改工具后直接沿用该清单续跑。

两轮参数均精确恢复，无残留仿真进程。原版本轮创建的 `parameters.bson` 和 `parameters_backup.bson` 按快照恢复为不存在；没有删除原有参数或原始日志。

## 2. 冻结与离线资格

- [冻结协议](BATCH03_PROTOCOL_CN.md)、[准确清单](results/batch03/manifest.json)、[结果与指纹索引](results/batch03/batch_result.json)。清单 SHA-256：`da6402a35e09bea071e81df26eaab817fad6f1f88b7d54a0b80c40b872b11cf6`。
- 分支 `research/upstream-supertwisting2`，HEAD `1f6fe1c7a46c22ea41a6a6a51c51498142ca6d62`。现有未提交源码、手册和图表均保留；不声称工作区干净，也不声称历史主固件由当前 HEAD 重建。
- **279 个 Offboard＋72 个旧工具＋10 个旧航向策略测试 = 361 个**，全部 exit 0、无跳过。包括新增 8 个批次历史/预算测试。没有修改 C++ 或重建固件。
- 新真实 ROS→MAVLink 本机回环通过：25 个位置目标、20 个速度目标、转发心跳及停止发送检查；模拟遥测，不算飞行。
- 执行后重新核验全部 **108 项冻结资产**、每个 job 的源码/固件/HEAD、两仓库递归子模块，均与冻结一致。两份固件 SHA 见协议。原版未初始化的无关平台子模块保持原样。
- 旧 B01/B02 的 3 个原始 ULog SHA 全部重新验证，不改判或挪入 B03。

## 3. 停批原因及原始证据

O002 的原始错误为：

```text
ValueError('Heading evidence: unexpected reset_vel_to_gps')
```

原版 `EKF2::PublishEventFlags` 的实际语义：有新信息事件时，增加 `information_event_changes`，记录事件和 `timestamp_sample`；没有新事件时，每秒重发上次缓存，只更新发布 `timestamp`。源码已与原版固定提交 `fc3720f67767c78cfab668777de13f68562fe2fd` 的 Git 内容逐字核对。

实际 ULog 显示：

| 证据 | 实际值 |
| --- | --- |
| 起飞任务检查窗口 | 原生时间 34.800～103.560 s |
| 最后一次新信息事件发布 | 2.744 s，早于起飞任务 |
| 该事件采样时间 | 2.592 s |
| 事件计数 | 5，整个飞行窗口没有增加 |
| 飞行窗口内重发 | 68 条，每秒一次；除发布时间外载荷完全相同 |
| `xy/z/vxy/vz_reset_counter` | 包含两侧边界，分别恒定 4/2/3/2 |
| ULog dropout / corruption | 0 / false |

缓存仍含 `reset_vel_to_gps=1`、`reset_pos_to_gps=1`、`starting_gps_fusion=1`。现有 `heading_check.py` 虽检查计数未跳变，却将**所有起飞后发布的记录**当成新事件来检查字段，因而误拒绝了起飞前事件的重发。这处拒绝不代表飞行中发生了新的 GPS 速度重置。

[只读复现脚本](results/batch03/diagnose_stop.py) 重跑原分析器，精确复现原错误；核对双时钟、完整载荷、事件计数、位置/速度 reset 计数及固定版本源码，同时确认 O003 被首败逻辑阻止。[诊断输出](results/batch03/stop_diagnosis02.json) 保存原始文件和代码 SHA。**没有修改 ULog、数组、结果或验收函数，也没有绕过拒绝继续计算完整验收。** 此错误之后的全部检查尚未被认证，O002 不能改称通过。

首次只读诊断脚本假定 `EKF2.cpp` 在冻结资产表内，报 KeyError、exit 1；随后改为核对实际固定 Git blob，exit 0。两次都没有启动仿真或改变验收。该复现不计入 361 个单元测试。

## 4. 已有结果与未完成项

PID 悬停窗口 10.088 s，X/Y/Z 速度跟踪 RMSE 为 **0.007326 / 0.006853 / 0.002657 m/s**；相对初始高度均值 2.4770 m，全程最大倾角 4.787°。实际位置日志中位频率约 10 Hz。这是单次 PID 描述，不能据此排名四系统。

RSTA/RISTA 本批没有飞行；速度任务四轮均未执行。因此没有完整四系统实际速度/位移图、响应速度对比或统计结论。原版仍是 rate STA＋XY 归一化误差 PID＋Z PID，不能和本项目速度 RSTA/RISTA 混称同一控制环消融。

大日志和参数/目标记录外置于：

`/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102-B03/`

| ULog | SHA-256 |
| --- | --- |
| O001 PID | `7b87d1caa935f1427b4c0884132e317f5e739dcdb1175c270c3ee0f6d2ec332e` |
| O002 STA2 | `313aa66b75e244a8cd1f1082f0ac3361e76148d8acdfb763fbaed0d1c64ee998` |

仓库保存小型结果、测试、指纹、冻结工具及诊断，原始大日志不纳入仓库。本轮未提交、未 push。

## 5. 下一批前必须补齐

先离线修订固定上游版本的事件语义：区分新事件、相同代次的合法重发和可疑载荷变化，严格检查 counter 跳变/回绕、sample 时间、首尾边界、丢样及真实飞行中 reset；不能简单删除 `reset_vel_to_gps` 检查，也不能靠发布时间去重。

对主仓库旧事件流保持原规则，新增原版真实重发夹具及负例；用已有完整原版日志跑完整分析链，而不只验证本次第一个错误。再审查四系统/两任务的跨版本接口覆盖，避免只修一个报错就消耗新飞行预算。修订验收后另冻有限批次，历史失败保持不变。

## 6. 本次命令与退出码

以下是已经执行的记录，不可重新运行已占用编号：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python:/home/yr/Desktop/codev doc/experiments/M10-20260917/plot_dependencies01/python"
export PYTHONDONTWRITEBYTECODE=1
python3 -B -m unittest discover -s research/upstream-supertwisting2/offboard -p 'test_*.py' -v
# 279 tests, exit 0
python3 -B -m unittest discover -s research/upstream-supertwisting2/tools -p 'test_*.py' -v
# 72 tests, exit 0
python3 -B -m unittest discover -s research/sta-velocity-control/scripts -p test_v04_heading_policy.py -v
# 10 tests, exit 0
python3 -B research/upstream-supertwisting2/offboard/verify_live_bridge.py \
  --output '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102-B03/live_bridge02' --execute-local-loopback
# exit 0; no flight
# freeze.py --data-root <B03> --offline-log <B03>/offline_tests01.log
#   --output <B03>/manifest.json --heading-reset-policy offboard_first_takeoff_alignment_v1
#   --previous-manifest <B02>/manifest.json --revision diagnostic_wiring_v1 --freeze: exit 0
# run.py --manifest <B03>/manifest.json --job O001 (dry-run): exit 0
# run.py --manifest <B03>/manifest.json --job O001 --execute: exit 0
# run.py --manifest <B03>/manifest.json --job O002 --execute: exit 1, STOP
python3 -B research/upstream-supertwisting2/offboard/results/batch03/diagnose_stop.py
# first diagnostic lookup exit 1, corrected pinned-source lookup exit 0; no acceptance override
git diff --check
# exit 0
```
