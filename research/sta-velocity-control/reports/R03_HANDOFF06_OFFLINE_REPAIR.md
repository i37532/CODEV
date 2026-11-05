# R03 handoff06：完整任务参考依赖的离线修复

2026-10-19。本次不新增飞行、不改控制律或参数、不重判历史失败。R03仍未验收：保留A/X、新B/Z、新C/XY完整通过，D首轮因分析依赖冲突停批。原批次计数、指纹与完整定位见[R03 revision05](R03_REVISION05.md)及[失败索引](../regularized_sta/results/R03_revision05_D_failed.json)。

## 为什么会再次报目标不匹配

生产任务8的真实目标包含XY八字和小幅Z变化。旧修复只固定了高度函数自己的波形参考，没有固定其内嵌交接函数的参考。在运行器先加载的顺序下，后者取到不支持任务8的旧模块，把XY参考错误地当成零；独立分析器先加载时却取到正确模块。同一日志因此出现相反结论，是分析工具的完整依赖接线缺陷，不是这次PID飞行失稳的证据。

实际旧参考产生5274个轴样本超限。正确参考下，原0.05m门槛内最大残差只有X=0.000306741m、Y=0.000188746m。旧在线失败仍为失败；新的离线诊断不计接受样本，不填补预算。

## 改了什么、没有改什么

新增独立[r03_handoff06](../regularized_sta/r03_handoff06/README_CN.md)，旧冻结目录均未编辑。

- 明确固定 `height → check_handoff → AX02 offsets` 三层来源、路径和SHA；两函数的波形参考同源，支持1/2/6/8完整三维结构，未知模式拒绝。
- 各函数只替换唯一的泛名导入节点，逆AST恢复后逐节点等于原函数。原5cm、40ms、Navigator/ACK、航向/reset、起降及保护检查不变；不全局修改模块缓存或比较函数。
- 实际来源/授权/参数恢复在原归档只读检查；分析副本每个侧车文件先逐SHA绑定。输出不复制旧授权或旧接受metrics，避免早期异常留下可误读的接受副本。
- 新诊断结果固定 `accepted=false / flight_accepted=false / new_flights=0`。`diagnostic_checks_complete=true`仅表示离线检查全部结束；没有运行器、资格生成或gate_pass入口。
- 保留A仍使用原revision04的job、来源与预热检查，不改成revision05，也不拿历史日志冒充新样本。

控制实现、固件默认值、dt、保护、127项参数、epsilon、模型/world/插件、波形、实验窗口和全部安全/性能数值阈值未改。当前源码中的三轴准入仍是未经D门飞行验收的实验路径。

## 实际非零测试与开发错误

主代理命令环境（仓库根）：

```bash
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python"
python3 -B research/sta-velocity-control/regularized_sta/r03_handoff06/test_adapter.py
```

最终46项真实测试exit0，主代理会话11685，独立审查重复执行也exit0；重复执行不算新增不同用例。首轮39项是同套测试的早期子集，不累加为85项。覆盖两种真实加载顺序、泛名污染、完整函数AST、三维波形/导数、5cm精确边界与邻点、真实XY漂移、NaN、相位、缺样、目标/ACK/模式错误、原授权拒绝与副本来源。

另主代理会话84068串行执行下列八个原测试文件，实际全部exit0，共291项；加本次46项，**本轮定向Python回归337项**，不是重新执行全资格1430项。

| 原测试文件（相对regularized_sta） | 实际用例 |
|---|---:|
| r03/repair01/test_adapter.py | 25 |
| r03_numeric05/test_checker.py | 41 |
| r03_revision05/test_numeric_adapter.py | 16 |
| r03_revision05/test_analysis.py | 53 |
| r03_revision05/test_runner.py | 49 |
| r03_revision05/test_replay.py | 42 |
| r03_revision05/test_revision_audit.py | 33 |
| r03_revision05/test_protocol.py | 32 |

审查保留的开发缺口：早期实现排除authorization副本，但原来源函数仍读取诊断目录，会在真实链上缺文件；交叉审查在真实回放前发现。改为核验全部副本SHA并只读原归档的真实provenance，新增真实冻结来源函数体的正反测试。另排除旧accepted metrics副本。没有改数值门槛或飞行逻辑来绕过失败。

此前D干净资格的513不同C++/1430 Python、32768对主样本+256对同sample重算及SITL/Gazebo构建，属于源码d0401534528b906d18836f28daabb769532da84a的飞前记录，不冒算为本次Python修复后的新资格。本次没有生产源码变化，因此未再编译/运行C++或MATLAB、仿真、实机。

## D失败日志：两种顺序均走完整链，但不改原判

真实执行命令见新组件README。`D/handoff06_diagnostic_runner01/run028`（会话96063）和`D/handoff06_diagnostic_analyzer01/run028`（会话26082的首命令）均exit0。两次均完整检查结束、诊断accepted=false、0新飞行，原文件/源码指纹及原失败判定保持。

后半链真实执行而非仅目标组件：高度进入窗301点、进入高度2.38502–2.40870m；降落检查10134行；三IMU clipping均0、六估计器fault均0；尾部等待清空，CLI最大打印年龄12ms，mixer有效反馈22550条、方向饱和0。IMU仍仅是有界记录覆盖，不宣称内部全量无丢样；这些是旧日志的离线诊断，不是D门接受。

保留A run001/002/003、新B run010/011/012、新C run019/020/021，各门PID/ESTA/RSTA各一例，均在独立新进程以runner-first执行；会话26082实际exit0（set -e、pipefail，任何CLI失败都会停止），九例全部完整检查结束、输入/源码/原判保持。

合计**10个不同原运行、11次完整诊断CLI**：D同一日志两种顺序不是两个飞行样本；共绑定20份原ULog（各运行启动/主日志），不等于20次新飞行或20份全部消费链解码。每份输出均非授权。D两metrics的原始字节cmp退出1，diff仅为两个counts对象的键顺序；不能写成字节相同。两份频谱SHA同为 `0e9d0ee98dbd18b3313d577f4d14bccff822a5c759c06169f82755ba258e9437`。

最终独立审计逐路径保留全部差异：D两顺序的完整JSON值/类型精确一致（只忽略对象键序）；ABC九例的所有原科学值和频谱均保持。除accepted由true变为诊断false及新增诊断来源字段外，A新增候选审计元数据，A003还增加flight/observation两处candidate_numeric证明；没有删除科学值或使用数值容差归一。1337文件及10符号链接实际复核，原数据、三个新组件文件保持不变。

可复现审计器位于外部 `R03_revision05/D/handoff06_result_audit01/audit_results.py`，SHA `77bc84f7499a647a5e0d560032cad1a473d69226c8c6b1782739a56f974f9725`。独立审计exit0，主代理再次执行 `python3 -B <该脚本> | cmp - research/sta-velocity-control/regularized_sta/r03_handoff06/RESULT_INDEX.json`，pipefail下实际exit0，索引字节一致。审计只重读JSON/指纹，没有新增ULog解码或飞行。

最终[结果索引](../regularized_sta/r03_handoff06/RESULT_INDEX.json) SHA为 `3fd772dd7df3e2cf3af368a07cb5cb854c9a73b4aa7af7cbc8bb8a52a84c08a5`。各CLI退出码来自主代理实际工具会话，索引明确标记无另存磁盘进程收据，不伪造收据。主代理也再次独立复核D失败索引的81项输入SHA全通过；此处不代替未来新批的干净资格。

## 下一批前仍缺的条件

1. 当前总57已用49、剩8。完整同源码D9至少需总58（增加1），此处仅提案，未激活预算或登记新种子。不能直接续旧八项。
2. 若有限新D9得到授权，须将已验证的新绑定接入**独立新版**运行器/完整分析/资格/回放链，回归真实两加载顺序和四任务，保留原版本和失败。
3. 冻结准确九项新清单、三配对种子、顺序、参数和完整资产指纹；明确源码提交后，在干净提交实际构建/资格。旧D资格不可用于新分析链。
4. 按原首败停止规则运行新D9，再九份独立回放及六配对风险检查；全部完成才验收R03、提交结果并按原授权push。不能凭本次离线诊断直接验收或开始R04/R05。

当前未push，无新增飞行或预算消耗。最终修复/报告提交SHA由提交后外部进度表记录，不预写报告自身SHA。
