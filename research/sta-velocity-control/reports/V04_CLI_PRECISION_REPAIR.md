# V04：CLI / 原始参考精度修复（仅离线）

日期：2026-09-23。开始于 `e9e3d233d5a4aad1289aad1e84412296e5b0f721`，分支 `research/sta-velocity-control`；主仓库和递归子模块干净。完整读取速度计划/共同规则/进度及 protocol04 失败报告。

用户批准“仅修复检查器精度问题、补齐离线测试，通过后再申请新批次”。本次新启动/飞行/种子消耗均为0；**离线修复通过，V04飞行仍未验收**。旧三批失败全部保留，不push、不V05、不实机。

## 1. 修了什么，没有改什么

旧运行器将原始 ULog 纬度47.3977508与CLI的47.397751比较，差2e-7大于错误采用的1e-7门槛。此次没有扩大原始坐标变化容差，而是区分两类证据：

- 新 `v04_task04.check_cli_reference`：按固定版本真实uORB打印格式，double经纬度六位、float参考高度四位小数，先格式化**参考的副本值**再与CLI解析值精确相等比较。ref_timestamp及reset计数仍精确相等；缺失/非有限值拒绝。原始参考不修改、不重置。
- `run_v04_protocol04.Checks.monitor`和高度入口`entry_ok`均接入新函数，避免只修首次监控、后续入口仍同类误报。
- `v04_heading_stream.replay`和最终ULog分析完全未改，原始坐标/参考高度/reset计数仍逐样本严格不变；即使一个double ULP变化被CLI舍入隐藏，原始检查也会拒绝。原时间间隔、消费样本关联、对齐、元数据、传输年龄等门槛不变。
- 原有`check_reference`保留为历史错误复现入口，原失败审计仍能重现原错误。已有协议JSON、冻结资产快照、旧日志及原判定不追改。新代码不与旧协议04资产指纹匹配，且旧批次目录已存在/种子已消耗，因此不能复用旧入口直接续跑。

没有改 `src/`、`msg/`、`Tools/`、`sitl/`：PID/ESTA控制律、EKF、Takeoff、模型、参数默认值、日志话题和打印器均不改。CLI表示检查不是新的测量或飞行安全认证，仍需原始日志全链准入。

## 2. 离线测试和真实历史复核

新增10个Python用例：实际生成打印格式契约；归档CLI/ULog同采样复现并修复；真实libc `snprintf`对正负/零/舍入边界及相邻浮点值对照；一显示单位变化拒绝；两端缺失/非有限拒绝；reset/时间戳精确检查；隐藏于打印的微小原始变化拒绝；原始缺样/缺字段拒绝；实际monitor方法继续调用原始回放且不提前冻结yaw；高度入口接线。

真实monitor测试只替换无关的宿主基础监控/外部I/O，使用归档ULog和实际回放逻辑；不启动PX4、Gazebo或MAVLink。独立C打印参考来自系统libc，并检查生成打印器确实使用相同格式，未修改打印器来迎合测试。每个用例内的参数组合不另算独立用例。

| 命令/证据 | 实际结果 | 退出码 |
|---|---|---:|
| `python3 -m unittest -v test_v04_cli_reference` | 新增10/10通过 | 0 |
| `verify_v04_protocol04.py --output .../cli_precision_verify01` | 109个不同C++、141个Python通过；两组2048步PID等价；SITL及DONT_RUN Gazebo仅构建通过 | 0 |
| 验证器内旧series02整轮重分析 | 仍拒绝，未完成观察窗口，预期退出1 | 1（预期） |
| `audit_v04_protocol04_failure.py` → `cli_precision_old_audit01` | 原series03的8项诊断通过、旧错误仍可复现，accepted=false | 0 |
| `analyze_v04_protocol04.py` → `cli_precision_reanalysis01` | series03仍accepted=false，缺hover_start；不因工具修复补造飞行窗口 | 1（预期） |

本轮没有测试失败或新的试飞，重复调用不累加不同用例数量。109个C++包括106个控制相关及3个姿态测试；141个Python包括既有131和新增10。完整命令/退出码见本轮外部证据；验证发生于上述起始HEAD加本次脚本修改的工作区，不冒称已经在未来可飞干净协议提交上完成验证。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/research/sta-velocity-control/scripts:$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest -v test_v04_cli_reference
# 重跑请另取全新输出目录：
python3 research/sta-velocity-control/scripts/verify_v04_protocol04.py --output <全新的离线验证目录>
```

外部根：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04`。本轮 cli_precision_* 目录/日志保留，仓库仅存[修复证据快照](../v04/cli_precision_repair01/)。原series03的32项原始指纹重新核验通过；EEPROM仍为 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，没有新仿真进程。MATLAB、实机和新ESTA飞行均未执行。

## 3. 新批次申请，不是当前可执行协议

[proposal.json](../v04/cli_precision_repair01/proposal.json)明确 `flight_authorized=false`、`execution_ready=false`。申请 **9401、9402、9403各先PID后ESTA X，共最多6次**；新目录拟为 `.../V04/series04`，目前未创建，旧余5次不复用，不加冒烟/调参或补飞。

保持原候选λ1=1、λ2=.2、ν限.4、纠偏限.8，Y/Z速度和全rate PID。任务沿用原起飞、证据完整的首次航向对齐、POSCTL稳定1秒、一次yaw冻结/一次高度任务、3秒入口、60秒观察含32秒X激励、降落上锁；原安全/性能/非命令轴/日志/配对门槛不变。任一必需检查失败即停。

种子结构化历史扫描21203份JSON无复用、无未解释无效文件，旧M06空诊断例外保持；该扫描在本次注册前完成。仅IMU显式种子，其余随机源不独立，固定PID先行顺序偏差仍披露；飞前必须再次扫描。当前注册不是种子实际消耗。

获新预算授权后，还须单独创建protocol05可执行冻结配置/入口，固定实际源码/资产、提交并干净重建/回归后才允许飞行；任何额外规则变化需再次申请。本次不宣称现有protocol04可以直接使用新种子执行。修复提交只包含明确研究文件，提交后完整SHA更新外部进度表。
