# V04 protocol02：高度任务与验证协议重新冻结

日期：2026-09-23。**本轮完成设计冻结；执行包未完成，未获新飞行授权，V04仍failed / needs_revision。**

## 范围与版本

用户要求“重新冻结高度任务与验证协议，再申请新批次飞行”。完整读取速度计划/共同规则、实时状态、V04与REPAIR01报告，复核历史协议、运行器、分析器及实际导航/命令链。
起点为`research/sta-velocity-control`、HEAD `65d1b5c4e2177547e369ba2a750581f1bb894c56`，工作区和递归子模块干净；没有回退、清理或重建分支。
本轮只增加协议、只读审计/协议测试和记录；不修改生产源码、旧运行入口、旧分析器、旧报告/冻结结果或plan/v1。

## 冻结内容

详见[新协议](../v04/protocol02/README_CN.md)和[JSON](../v04/protocol02/protocol.json)。

- 保留原Takeoff及导航参数，等待原起飞完成；以一次明确DO_REPOSITION高度请求替代原当前位置Hold，不新增轨迹发布者。
- 起飞前冻结估计地面/坐标参考，`z*=z_ground−2.5`、`alt*=ref_alt−z*`；全局命令与本地目标回读交叉检查，armed参考/reset变化拒绝。
- 高度2.0–3.0m且|vz|<0.2m/s等条件连续3秒，再写hover_start；60秒观察及原起降验收不省略。
- 激励仍为12秒等待+32秒原X波形；必须在激励门禁起点后10秒内完成高度准备，否则停止，不延迟/重启激励凑窗口。
- 保持同一ESTA X候选、Y/Z及全部rate PID；旧安全/性能/日志门槛按旧JSON哈希继承，不放宽。补first_fail/retry_result/excitation_fault及命令/目标/高度连续性的必需证据。
- 新种子9201–9203，每对PID→ESTA，最多6次独立预算，0次额外冒烟/调参；旧剩余5次不复用。第一PID轮就是同批首轮任务验证，不另加预飞。
- 固定PID先行是开发风险控制，不是顺序随机化；仅IMU显式seed，其他源不独立，不声称全部随机源或六个独立种子。

高度转换和命令语义来自本地源码：MavlinkReceiver直接复制param4，Navigator DO_REPOSITION直接写yaw与alt，FlightTaskAuto使用弧度yaw及`z=−(alt−ref_alt)`。本冻结版本专用发送器需使用原始弧度并实际回读；不能套用其他版本/通用工具的角度转换。

## 实际检查与数量

| 检查 | 实际结果 | 退出码 |
|---|---|---:|
| `python3 -m unittest discover -s research/sta-velocity-control/scripts -p test_v04_protocol02.py -v` | 12个新协议/高度转换检查通过 | 0 |
| 项目依赖PYTHONPATH下同目录`-p 'test_*.py' -v` | 共70个Python通过，原58+新增12；重复复跑不累计 | 0 |
| `python3 research/sta-velocity-control/scripts/check_v04_protocol02.py --audit-seeds` | 21,068份历史JSON，种子匹配0、无未解释无效JSON | 0 |
| 源码/文档seed关键字文本补查 | 仅本次新注册命中，没有旧任务命中 | 0 |
| 120项设计时文件指纹、递归子模块、EEPROM核对 | 快照记录当前文件，不伪装旧未修复源码 | 0 |

测试原始输出：[python_tests.log](../v04/protocol02/python_tests.log)。种子证据：[seed_audit.json](../v04/protocol02/seed_audit.json)。
历史空文件`M06-20260916/c02_regression_roll_diagnostic.json`仍按已审计0字节诊断例外明列，未删除/改写；本次仅排除新protocol02登记目录，旧V04数据未排除。
JSON审计不能证明每个未登记外部实验均不存在，实际飞前必须再审计种子使用历史。

新增12项仅验证协议不被误作授权、预算与配对顺序、旧参数/门槛继承、坐标float32转换/非法值、旧1.9669m仍拒绝、窗口关系、一次命令/回读需求和首次失败规范。
**没有声称已测试真实ACK接线、高度门禁状态机或新分析器**；这些尚未实现，已列飞前必需条件。Python已有合成ULog测试也不是本次飞行ULog。

本轮C++测试0、SITL/Gazebo构建0、Gazebo运行0、飞行0、MATLAB0。
REPAIR01的104个C++/58个Python是此前证据，不累计成本轮；本轮未改生产控制，没有必要仅为文档重编，但真正飞前必须在最终执行提交重建/回归。

## 指纹与保留

[design_snapshot.json](../v04/protocol02/design_snapshot.json)包含120个现有资产/新增协议工具指纹、原control_parameters及完整递归子模块；它是设计时快照，**不是尚不存在的最终运行器/固件执行清单**。
旧资产相对protocol01的6个变化均对应已经提交的REPAIR01控制/消息修复。Takeoff、导航链、world、模型和插件在本轮没有变化。
Gazebo子模块仍`822050a7ab6fd87972e59f16312f451bce217a56`。
EEPROM SHA仍`06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`；没有写入参数或新运行参数证据。
新预算仅预留`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series02`路径，本轮未创建该飞行目录，也未消耗种子飞行。

## 停止点与申请

审查明确范围后提交设计/工具/证据；提交完整SHA写外部进度表。未push、不V05、不实机、不旧ISTA。
旧`run_v04.py`/`analyze_v04.py`仍为protocol01，不能用它们冒充新协议执行。

申请用户允许以下**有条件的新批次**：先按冻结设计补齐隔离运行器/分析器，离线测试和完整回归通过并明确提交，干净源码重建和固定执行清单后，按顺序执行最多6次Iris SITL；任何必需失败立即停止，保留失败，不重试、不补飞、不增候选、不扩大XY。
若实现需改变任务/门槛/控制逻辑或预算，再停下申请；用户同意本设计不等于豁免飞前检查。只有所有六次和三对均通过才能更新V04验收状态。
