# ROS Offboard 起飞航向检查离线修复

2026-11-02。**日志检查修复及离线回归完成；新飞行 0 次。** O001 原结果仍为失败，原八轮清单保持停止，没有补飞、调参、提交或 push。

## 修复内容

原分析器将起飞至上锁期间的一切航向 reset 都判为失败，漏接了项目已有的首次空中磁航向对齐分类。本次依据 [V04 航向审计](../../sta-velocity-control/reports/V04_HEADING_AUDIT.md) 和其 protocol04 证据条件，增加独立 [heading_check.py](heading_check.py)，仅为以下情况分类：

- 一次对齐，完整发生在 climb 准备阶段、评分开始之前；计数必须单次递增，支持合法 uint8 回绕。
- 公共航向计数、姿态四元数计数、实际主 EKF 的四元数计数及磁对齐标志相互对应。
- 主 EKF 不切换且健康；位置、速度及全局参考不 reset；无磁异常、其他 yaw 源接管、紧急事件或滤波故障。
- 实际处于 Offboard、已解锁、已离地、无接触且 takeoff state=5；沿用历史开发条件：对齐修正不超过 5°、相对高度 1–3 m、确认等待不超过 0.5 s。
- 评分前有至少 1 s 安静段，实际航向与本批原先固定的 yaw 目标相差不超过 1°。不重新捕获 yaw，不叠加 delta，不改变 ROS 指令。

第二次 reset、任务中或降落尾窗 reset、计数跳变、证据缺失、主实例变化及位置/速度 reset 仍拒绝。EKF 落地时把 `mag_aligned_in_flight` 清零是另一件事：只有实际已落地/接地、`cs_in_air=0` 时才允许清除该标志；**不因此允许任何航向或四元数计数变化**。对应源码为 `src/lib/ecl/EKF/mag_control.cpp` 的 `controlMagFusion()`。

### 时间和边界

位置日志约 10 Hz，首次记录到计数变化不等于 reset 的精确发生时刻。新版保留“上一条旧计数、第一条新计数”的观测区间，与四元数和主 EKF 证据配对；保留历史 40 ms 姿态/航向配对容差。区间不相交、跨越起飞/任务边界或同 sample 的 reset 信息矛盾均拒绝，不排序、不去重、不插值补造事件。

原 Offboard 原生日志间隔上限 **500 ms 不变**。旧 V04 高频采集的 40 ms sample-gap 要求不冒充本批 10 Hz 日志标准。selector/status_flags 使用历史 1.2 s 元数据界限，estimator_status 使用 0.5 s；event_flags 是事件型话题，以前置快照及计数连续性检查，不虚构周期心跳。边界检查包含起点之前及终点之后的相邻记录，无法确定是否跨界时拒绝。

这只是可观测日志上的分类，不证明采样间没有未记录瞬态，也不把新规则称为与 V04 完全相同的飞行协议。V04 的对齐后一次性改 yaw 不适用于本次固定 ROS yaw；本轮没有改任务生成器。

### 原版 STA2 的消息版本

跨版本原始日志核对发现，原版 STA2 的 `cs_gps_yaw` 已改名为 `cs_gnss_yaw`，`warning_event_changes` 及四个旧 warning 字段不再存在。不能把缺失字段填为 0，也不能让主仓库缺字段时自动落入另一套格式。

增加了显式版本合同：PID/RSTA/RISTA 仍必须具备旧 ECL 字段；原版 STA2 必须匹配 ULog 固件版本 `fc3720f67767c78cfab668777de13f68562fe2fd`，读取新 GNSS/EV yaw fault、mag 连续启用及导航状态，检查信息事件计数和 `yaw_aligned_to_imu_gps`。其源码 `resetYawToEKFGSF()` 每次该类 yaw reset 都置位这一信息事件，紧急路径同时设置相应故障标志。新合同不声称重建了已经移除的 warning 历史；混合格式、未知版本或所需新字段缺失仍失败。

四份历史 ULog 的对应原始字段合同均已核对，详见 [跨版本证据及来源 SHA-256](results/heading_fix01/historical_schema02.json)。这不是用旧 Navigator 飞行代替新的 Offboard 验收；旧日志仍按旧规则回放。上述两种格式另有缺字段、未知版本、GNSS/EV/导航故障和紧急 yaw 事件负例。

## 版本和历史保护

`analyze.py` 通过明确的 `job.heading_reset_policy` 选择规则：缺省仍是旧 `strict_no_reset_v1`；只有显式选择 `offboard_first_takeoff_alignment_v1` 才运行新版。运行器的清单检查同时要求批次字段和全部 job 字段一致，拒绝未知或混用版本。

旧 manifest、原 result、旧冻结源码副本及 ULog 不改写。`freeze.py` 本次未改，仍不会自动选择新规则；没有产生新的可执行批次。旧 O001 重跑入口仍拒绝，O002 仍因前轮失败拒绝；出图入口仍拒绝原清单，未生成不完整比较图。

开始及结束分支均为 `research/upstream-supertwisting2`，HEAD 为 `1f6fe1c7a46c22ea41a6a6a51c51498142ca6d62`。既有脏工作区和递归子模块保留。开始时保存 215 个文件指纹，结束除本轮有意修改的 3 个既有 Python 文件外，其余 212 个均相同，包括已有用户源码、固件、参数及 O001 原始记录。新增文件不计入该开始快照分母。

## 真实日志回放

O001 同一原始 ULog 分别通过冻结旧分析器、当前分析器旧规则、新版规则只读回放：

| 检查 | 结果 |
| --- | --- |
| 原冻结分析器和当前旧规则 | 均保留原 `Native estimator reset: heading_reset_counter` 拒绝，错误文本一致 |
| 新版完整离线分析链 | 检查通过；仅作规则开发回放，不将 O001 改为接受样本 |
| 新版第二次独立读取 | 输出一致；不是独立飞行或另一套算法验证 |
| O001 内存副本 17 种故障注入 | 全部拒绝；不写回 ULog |
| 原四系统 Navigator 日志 S101/S202/S203/S304 | 按其自己的旧规则重算，4 份指标逐字段相等，原结论不变 |

O001 对齐观测：位置计数变化区间 49.588–49.688 s，姿态区间 49.660–49.716 s，主 EKF 区间 49.480–49.680 s；对齐标志在 49.680 s 置位，最后配对确认记录为 49.716 s。航向修正 −0.220479°，首次位置记录相对高度约 1.734607 m。56.520–57.520 s 安静段最大 yaw 误差约 0.0004884 rad。105.888 s 的对齐标志清零有落地证据，不是第二次航向 reset。

本次是 **5 份不同真实 ULog** 的回放；重复读取及 17 个内存负例不算新增飞行样本。最终证据见 [replay02.json](results/heading_fix01/replay02.json) 和 [验证汇总](results/heading_fix01/validation02.json)。早期 replay01 作为修订过程记录保留。

## 实际测试与命令

最终共 **325 项不同 Python 测试**，全部通过、无跳过，三条命令退出码均为 0：

- [Offboard 工具 243 项](results/heading_fix01/offboard_tests03.log)：包括本轮新增 44 项分类/完整链回归及 1 项清单版本回归；覆盖四系统两任务的合成输入、精确边界/邻点、计数回绕、缺字段、时间歧义、跨版本和负例。
- [旧四系统工具 72 项](results/heading_fix01/legacy_tests01.log)。
- [原 V04 航向策略 10 项](results/heading_fix01/v04_policy_tests01.log)。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python:/home/yr/Desktop/codev doc/experiments/M10-20260917/plot_dependencies01/python"
export PYTHONDONTWRITEBYTECODE=1
python3 -B -m unittest discover -s research/upstream-supertwisting2/offboard -p 'test_*.py' -v
python3 -B -m unittest discover -s research/upstream-supertwisting2/tools -p 'test_*.py' -v
python3 -B -m unittest discover -s research/sta-velocity-control/scripts -p test_v04_heading_policy.py -v
```

真实回放命令退出 0，最终输出为 `replay02.json`。复跑应使用未存在的新输出名，例如：

```bash
python3 -B research/upstream-supertwisting2/offboard/replay_heading_fix.py \
  --attempt '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102/runs/O001' \
  --frozen-analyzer research/upstream-supertwisting2/offboard/results/heading_fix01/analyze_frozen_O001.py \
  --output '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-ROS-OFFBOARD-20261102/heading_fix_wlvzH7/replay03.json'
```

未运行示例中的 `replay03.json`；实际运行的是 `replay01.json` 和 `replay02.json`。脚本拒绝覆盖和写入原尝试目录。绘图拒绝检查退出 1 是预期负例：O001 仍不是成功样本。

开发过程中确实出现过：初始参考经纬度 NaN 被误纳入全局有效性检查、正常落地标志清零被误判，以及起点恰好发生 reset 时漏读前一条记录。均已修复并有回归覆盖；早期合成测试有失败，不将其写成从未失败。最终计数不累计多次重跑。没有重新编译或运行 C++ 控制律测试，因为本轮没有改 C++；没有 MATLAB、ROS 在线重跑、Gazebo 或实机。

## 下一批之前

当前完成的是检查器离线修复，不是四系统实验完成。新飞行前还需明确选用新版日志规则、将其和源码指纹写入所有 job，冻结新的独立数据目录、准确顺序及有限预算，并复核运行环境/模型/参数。旧批次保持关闭。若仍完成两任务 × 四系统，新的完整清单是 8 次，连同保留的 O001 历史尝试为 9 次；本轮未冻结或执行该预算。

文件范围：新增分类器、对应测试、离线回放器、本报告及证据快照；修改分析器的显式选择接线、清单一致性检查/测试及 README 入口。原控制律、控制器 dt、增益、模型、起降逻辑、ROS 目标及数值安全阈值不变。未提交、未 push。
