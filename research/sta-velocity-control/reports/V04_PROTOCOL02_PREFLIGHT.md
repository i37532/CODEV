# V04 protocol02 飞前审计：正常降落与激励故障零值条件冲突

日期：2026-09-23。结论：**needs_revision，非依赖blocked；未启动新批次。**

用户回复“允许”，授权按已冻结设计完成接线/离线验收后执行最多6次；同一设计明确：如果需要改变任务、门槛或生产逻辑，停止并再次申请。
本轮在接线前发现冻结条件与真实生命周期冲突，先完成只读源码审计和实际C++头文件复现，未实现绕过条件的新运行器，也没有飞行。

## 1. 版本及前置

- 分支`research/sta-velocity-control`，开始HEAD `2fc381789770cdc38f82f123b1cdef3f7cacc9e6`，工作区及递归子模块干净。
- 完整读取速度TODO/共同规则、实时状态、V04/REPAIR01/protocol02报告及冻结JSON，复核原启动器/分析器和现有Run接线。
- 原protocol02设计、旧失败数据、控制源码/默认值/模型/插件全部不改。Gazebo子模块仍`822050a7ab6fd87972e59f16312f451bce217a56`。

## 2. 矛盾的准确位置

1. protocol02的`additional_log_gates`要求`excitation_fault=0`，而且明确覆盖整个armed区间。
2. `MulticopterPositionControl::Run`的`excitation_gate`明确要求实际模式为`NAVIGATION_STATE_AUTO_LOITER`，正常切入AUTO_LAND时门禁为false。
3. `VelocityDiagnosticExcitation::update`在已经启动且gate=false时执行`_fault |= Gate`，`Gate=2`；即使32秒波形早已完成，`_start`仍保留，直到disarm才清除。
4. 因此完整正常任务在降落过程中也会出现`excitation_fault=2`，与冻结全armed零值规则不相容。

这是**上一轮协议设计遗漏了正常结束语义**，不是已经发生的新飞行失稳、ESTA控制器故障或时钟故障。`Gate=2`单靠数值也不能证明正常，必须有计划降落/模式/窗口证据才能区分。
不能为了通过而改激励器清零，也不能把所有非零fault忽略，更不能先消耗一次必然不满足协议的飞行。

## 3. 实际离线复现

新增独立`ExcitationLandingAudit.cpp`直接包含**生产VelocityDiagnosticExcitation.hpp**，没有复制其算法；10ms严格递增sample，60秒合法AUTO_LOITER覆盖原12秒等待和32秒波形，再给出armed=true/gate=false模拟正常降落的模块输入。没有Gazebo或PX4飞行进程。

| 探针检查 | 实际结果 |
|---|---|
| 完整观察、波形有非零输出、降落前fault=0 | PASS |
| 冻结协议要求正常降落仍fault=0 | **FAIL：实际fault=2，输出0，excitation_time=48秒** |
| 提前丢门禁继续锁存，不能重新启动 | PASS |
| 降落同时发生真实重复时间戳 | PASS：fault=3，Clock和Gate均保留 |
| 降落同时发生真实控制失败 | PASS：fault=6，Controller和Gate均保留 |
| disarm清除锁存与计时 | PASS |

以上是6项独立C++探针检查（不是新增6个gtest），**5通过/1失败**。编译退出0，探针及审计入口退出1。失败断言按原协议保留，未改成期望2而伪称兼容。

```bash
cd /home/yr/Desktop/Codev-autopilot
python3 research/sta-velocity-control/scripts/audit_v04_protocol02_lifecycle.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/protocol02_lifecycle_audit01'
# 实际退出1；目录已存在，复现时必须另用不存在的新离线目录。
```

完整编译命令/源码及协议SHA/退出码见[evidence.json](../v04/protocol02_audit01/evidence.json)。外部4份文件含原始日志、证据及独立探针二进制，按[指纹索引](../v04/protocol02_audit01/artifacts.sha256)保留；不提交二进制。
Python工具回归实际70项通过，退出0，见[输出](../v04/protocol02_audit01/python_tests.log)。这些测试主要验证协议字段/已有工具，**不能推翻本次生命周期兼容失败**。

本轮没有运行完整104项C++回归、SITL/Gazebo构建、MATLAB或任何飞行；协议不相容时尚不满足启动条件。

## 4. 建议的最小修订（尚未生效）

保持当前生产代码、候选、9201–9203种子、顺序、6次预算、高度/稳定/性能/日志完整性门槛不变。只拆分激励退出判定：

- 完成32秒激励及60秒观察前，以及计划降落被真实模式确认前，仍要求`excitation_fault=0`；任何提前Gate均失败。
- 仅在已记录唯一计划land命令、已核实实际AUTO_LAND、窗口完整、零新增激励输出之后，到disarm之前，可把**单独的Gate=2**分类为预期结束锁存。不得允许返回LOITER重启，不得仅以宿主已发命令替代实际模式证据。
- Clock=1、Controller=4或其任何组合始终失败；首次update失败/重算、STA fault、failsafe、时间/状态异常、降落超时仍失败。
- disarm后必须清零；保留原始fault位及预期退出分类，不能把原日志改成0。

若批准，另存显式修订版本并保留protocol02原结论；补真实模式边界、未发命令/早退、组合fault、disarm等离线用例，再接线、完整回归、提交/干净重建，最后才执行授权新批次。

## 5. 预算、状态与提交

新批次计划最多6，实际启动0/飞行0/接受0/未执行6；种子未消耗。旧protocol01剩余5次仍封存，新series02目录未创建。
EEPROM字节不变，SHA`06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`。没有新增运行参数或ULog证据。
本次明确范围提交只含失败审计源/脚本/证据/报告与入口；属于可追踪的失败记录提交，不是通过验收或可飞源码提交。外部进度表更新完整SHA。
不push、不V05、不ISTA、不实机。**等待用户批准上述日志分类修订，再继续原6次上限任务；本轮没有自动改变冻结规则。**
