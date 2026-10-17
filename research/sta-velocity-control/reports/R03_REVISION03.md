# R03 revision03：已授权新 36 次开发验证

2026-10-17。**当前结论：needs_revision，A第7次尝试在解锁前日志新鲜度检查失败，已首败停批。** 新36项已尝试7、实际起飞6、完整起降/接受6、失败1、未执行29；不是R03或A门通过。下方第1–3节保留飞前记录，第4节起为实际执行结果。未改判、补飞、改参数或放宽500ms阈值。

## 1. 本轮范围与入口

用户明确授权：“开始新36轮，按修订后的44次总预算执行。”
R03 总上限为 **44＝历史8＋新36**。保留历史6接受、2失败/无效及全部原始记录；历史接受不拼入新门。仅执行这36项，不补飞、换种子、调参或扩大预算，不自动开始R04/R05。

入口仓库 `/home/yr/Desktop/Codev-autopilot`，分支 `research/sta-velocity-regularized`，完整HEAD `73c2ef5b5544a27cc8dfcaf6dfe7b2d7ceb0950d`；工作区干净，33个递归子模块版本及内部工作区正常。没有回退、清理或重建分支。

本轮建立独立 `regularized_sta/r03_revision03` 可执行版本，承接 revision02 已冻结但未尝试的36项；旧离线版本保持不变。新授权不代替每门干净源码/固件资格、实际模型/参数检查和前门验收。

| 门 | 新算法掩码 | 每门比较 | 已冻结配对种子 | 尝试上限 |
|---|---:|---|---|---:|
| A：X | 1 | PID / ESTA / R-STA | 71101–71103 | 9 |
| B：Z | 4 | PID / ESTA / R-STA | 71111–71113 | 9 |
| C：XY | 3 | PID / ESTA / R-STA | 71121–71123 | 9 |
| D：XYZ | 7 | PID / ESTA / R-STA | 71131–71133 | 9 |

只限项目启动器下的 Gazebo Classic Iris SITL。位置P、姿态和角速度PID、速度DIV1、原HTE/保护/控制器时间、参数与epsilon、模型/传感器及日志数值门槛不变。首个必需检查失败停批，不能靠重新试到成功或修改判据验收。

## 2. 飞前实际检查

- Git分支、HEAD、工作区、递归子模块和EEPROM只读检查退出0；未发现仿真进程。
- 初始可用磁盘约63.31 GiB，后续各门及各轮仍现场检查余量，不删除历史日志。
- EEPROM SHA-256：`06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`。这是持久化文件指纹，不冒称新飞行实际生效模式。
- 实际执行 `python3 -m unittest discover -s research/sta-velocity-control/regularized_sta/r03_monitor02 -p 'test_*.py' -v`，使用项目与M00依赖路径：**83项，退出0**。原500 ms新鲜度、完整历史/reset/歧义和故障检查保持；后续统一资格中的重复测试不再次累加为不同用例。
- 没有运行MATLAB、实机或新的ISTA实验。飞行/独立回放/最终统一资格尚未执行，不能把上次资格当本次通过。

## 3. 飞前接线修订与审查

新执行器仅激活本次明确授权和当前门干净资格，复用已验证的增量读取器，不改变飞行主体、数值分析、500 ms判据或控制路径。旧revision02继续硬拒绝飞行。每门只有同一个干净源码和固件，前门的原始/回放证据可在后续准入提交上复核，但不能用旧门资格启动新门。

新增迁移证明最初复制全部12个具体种子到资格/账本，飞前审查发现这会被全历史查重器误判为已消费；尚无飞行时改为严格来源文件SHA及数量，原清单中的种子逐项核验仍保留。没有增加目录白名单。实际scanner测试覆盖：资格记录不消费种子；A实际使用后不能重启A，但B未用种子仍可用；外来使用记录仍拒绝。

提交前分项测试最终为：新协议61、运行器41、分析器32、独立回放34、版本/资格审计17，加前述监视器83，合计268个不同Python用例，均退出0。独立审查重复17个审计用例退出0，不重复加数；dry-run A及diff检查退出0。完整C++/旧链/构建随后在干净提交上执行，不把这些分项当已完成完整资格。

根任务提交前再次真实扫描57,064份JSON：无新增冲突或非法JSON，退出0，扫描清单SHA `09d9fe45a0bbe0862fbd6fdaaf33e8a713ade223fcbe7b9a104f3dc08c0230f6`。A门冻结635个仓库资产，旧所有协议/监视器及生产路径无修改；新三计划快照随本次源码提交绑定，不覆盖旧快照。飞前仍由运行器重新核验当时本门种子。

协议测试最初60项中两个保护种子subtest因更早的迁移检查拒绝而未被旧异常包络捕获；仅修正测试预期，最终61项通过。分析器初轮沿用旧版“永久拒绝执行”的断言出现3个失败；新版已获授权，改为明确撤销授权的负例后通过。均为离线测试记录，不消耗飞行预算，不更改历史判定。

## 4. 干净源码资格与实际执行

本版协议/源码提交 **7f0f174f9d44b98190e7927713cbdf891ab63cf9**，23个明确新增文件；A生产控制实现保持入口版本，只有MODE3/AXES1开放。该提交工作区干净、33递归子模块一致。实际固件SHA-256为 `c0a5101cc97d1c123081168c952d6141f64170215b3e238f62ff6d4b05e61ca5`。

外部根：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision03`，后文相对此根；所有大型原始日志外置。

以下为已执行的历史命令，**停批后不可直接再次启动runner**。命令共同环境（仓库根下）：

```bash
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python"
```

| 实际命令/检查 | 结果 |
|---|---|
| `python3 research/sta-velocity-control/regularized_sta/r03_revision03/verify.py --gate A --qualify --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision03/A/qualification01'` | 退出0；43条顶层命令全部退出0，475不同C++、1143 Python；32768旧路径主样本对及256同sample重算；SITL/Gazebo仅构建通过；参数与依赖保持 |
| `python3 research/sta-velocity-control/regularized_sta/r03_revision03/runner.py --gate A --execute --source-head 7f0f174f9d44b98190e7927713cbdf891ab63cf9 --qualification '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision03/A/qualification01/evidence.json'` | 会话92928，退出1；按冻结顺序接受6次，run007首败停止，未执行run008 |
| Git工作区/递归子模块、容量、参数恢复、原始指纹 | 只读核验；未回退、删日志或改子模块。停批时磁盘约63GiB可用，不是容量不足 |

资格的`new_flights=0`描述飞前验证时，不覆盖之后实际7次尝试。先前268分项及重复审查不能再加到1143上。资格通过不等于飞行验收通过。MATLAB、实机、ISTA、B/C/D及R04/R05均未执行。

## 5. 逐轮账本、首败与预算

| 新轮次 | 门/算法 | 种子 | 起飞/完整起降 | 原验收 |
|---|---|---:|---|---|
| run001 | A / PID | 71101 | 是/是 | accepted |
| run002 | A / ESTA | 71101 | 是/是 | accepted |
| run003 | A / RSTA | 71101 | 是/是 | accepted |
| run004 | A / PID | 71102 | 是/是 | accepted |
| run005 | A / RSTA | 71102 | 是/是 | accepted |
| run006 | A / ESTA | 71102 | 是/是 | accepted |
| run007 | A / PID | 71103 | 否/否 | failed：Stale prearm ULog |
| run008–009 | A / ESTA、RSTA | 71103 | 未执行 | unattempted |
| run010–018 | B / Z三算法 | 71111–71113 | 未执行 | unattempted |
| run019–027 | C / XY三算法 | 71121–71123 | 未执行 | unattempted |
| run028–036 | D / XYZ三算法 | 71131–71133 | 未执行 | unattempted |

两完整种子块仅产生4个STA对PID开发风险配对检查，全部通过；门需要9接受、6配对及9独立回放，本次未达到，不生成`gate_pass.json`。

首败result时间 `2026-10-17T01:44:42Z`，仅有ready事件；运行器抛出`RuntimeError('Stale prearm ULog')`，外层ledger记`SystemExit(1)`。没有`commander takeoff`，不能称起飞失败、空中控制失稳或RSTA失败。该轮仍消耗1次尝试预算。

7轮参数恢复收据保留，批次`parameter_restore_exact=true`、`remaining_simulators=[]`，最终EEPROM与原备份SHA相同。失败轮`logger stop`退出0、`shutdown`CLI退出255，但拥有的启动器最终退出0，无残留进程；不隐瞒单条CLI退出码，也不将它误判为起飞执行。

累计：旧8+新7=**15尝试**；旧8次起飞+新6=14次起飞；旧6+新6=12接受、3失败/无效。历史成功不拼入当前矩阵。上限44尚余29，而本版36接受还缺30；即便余下全接受也只有35。算术至少多1次并不授权补飞或跨源码混合。若修复后遵守同门同源码并重做A9，再B/C/D27，需新36次、累计上限51（较44增加7）；本报告只列缺口，未批准、冻结或执行新批。

## 6. 预解锁时间链诊断（只读，不改判）

触发点为继承的`axis_ablation/ax04/run.py::Checks.start_heading`：首次构造日志reader、读取历史、选取有封口姿态证据的position reference，然后读未解锁状态及当前local_position，最后检查`0 <= CLI.timestamp - reference.timestamp <= 500000`。原规则未变。

`r03_monitor02/integration.py`只替换reader构造器，保留该顺序。warmup阶段尚无reference，reader尚未开始增量读取；因此首个start_heading仍从offset0冷解析预热历史。最终归档约20MB，只说明数据规模，在线首读的实际字节数未保存。真实命令记录中，最后warmup诊断CLI结束到prearm状态CLI开始间隔约505.502ms，随后两次prearm CLI合计约4.395ms，最终position发布时间30.740s。

失败发生在`live_log.json`/`height_reference.json`写入之前，未保存该次在线read的精确字节截断、reference、水位和read/decode/snapshot计时。**因此不能从最终归档日志反推一个精确在线age，也不能声称505ms全是解码耗时。** 这是首次全量读取/延后取CLI的冷启动路径问题线索，不是已证明的传感器断流或固件时间倒退；最终日志回放仅作诊断，不改历史失败。

前6轮在线暖读取通过与本次冷启动拒绝可同时成立；上一版离线暖轮询优化及测试未覆盖这次实际冷启动最坏耗时。后续应优先离线验证预热期持续解析、封口前新鲜增量读取和完整时间收据，保持原500ms、reset/边界/歧义规则；未经新修订不在当前冻结脚本中现场修补或重飞。

失败轮一次最终归档解码核实：29次warmup的reader计时记录全部为空，使用的确为新incremental reader，不是误接旧版；ULog始终arming_state=1、armed_time/takeoff_time=0、landed/contact=1。最终20651447字节日志的position序列无缺口、sample间隔8/12ms，姿态sample最大间隔8ms，dropout0、corruption=false。该最终归档含停批前后尾数据，不能冒充失败瞬间的快照。一次离线冷读458.637ms（解码444.751ms）仅支持冷启动开销线索，未当在线age或已修复证据。

诊断脚本首次在解码前因私有loader未注册类模块导致`inspect.getsourcefile(reader_cls)`失败（退出1、完整解码0次），保留`stop_diagnostic01/failure/attempt01.json`；改为检查类的read函数源码后，诊断退出0、完整归档解码恰1次。没有修改仓库loader或原日志。

## 7. 部分回放、指标及结果指纹

部分独立回放脚本 `partial_replay01/partial_replay.py`（实际入口以该目录脚本/收据为准）退出0；六次独立`analyzer.py <run目录> --output <新目录>`进程均退出0。6份metrics所有值、类型与列表顺序精确一致，仅JSON表示/字典键序不同；频谱文件SHA一致。独立重算4对、每对13个预定风险条件全true，与原账本一致。整个batch的427个文件前后SHA不变，回放12份ULog；没有生成gate_pass。

独立账本审计 `A/stop_diagnostic01/accounting/`退出0：14份原ULog（含未起飞失败轮的2份）共677157090 bytes与result登记的字节/SHA全部匹配；7次恢复和现场EEPROM一致，无仿真残留，33子模块版本及工作区未变。重新读取43份XML得到475个唯一实际运行testcase，41个直接Python测试日志合计1143项；293资格输出指纹匹配。这里是核验已执行证据，**不是重新运行475/1143测试**。

以下仅为X任务32秒主窗内两个完整配对种子的描述性均值（每算法n=2），不拼旧批次。每轴RMSE按sample间隔加权，单位m/s；J为每轮三轴RMSE算术平均再对两轮取均值。TV/T为主窗口内实际更新序列的加速度纠偏变化总量/时长（m/s³），不是能耗。

| 算法 | X RMSE | Y RMSE | Z RMSE | J | X纠偏TV/T |
|---|---:|---:|---:|---:|---:|
| PID | 0.036043 | 0.007464 | 0.002698 | 0.015401 | 0.119163 |
| ESTA | 0.008636 | 0.007082 | 0.002336 | 0.006018 | 0.197184 |
| RSTA | 0.007599 | 0.007378 | 0.002688 | 0.005888 | 0.141296 |

这两个种子中，RSTA的X误差和X输出变化量均小于硬sign ESTA，但Y/Z误差并未都更小，X输出变化量也仍高于PID。不能据n=2宣布统计显著、全轴优势或R03验收；含Z、XY和XYZ的主要问题仍未验证。完整逐轮误差/位置/yaw/约束/宿主耗时及指纹入口在 `regularized_sta/results/r03_revision03_stop.json`，完整指标与共同带宽/原生频谱在各轮外部`r03_metrics.json`/`spectra.json`。宿主墙钟不等于板级CPU。

| 关键证据（相对外部根） | SHA-256 |
|---|---|
| A/qualification01/evidence.json | eb0d3932a5b26f52bb8c4e878322918f78bb51679e1abf5697facb4fa0cf5ac0 |
| A/qualification01/authorization.json | cf0fa71494ed8172917ed6d234b1242666f72ac08e23f46b65f5ef20c54f8cc1 |
| A/batch01/ledger.json | 7a1661e09418341803272f1b156cc9d75aeaca41cfbb59353d674c6772dca8dd |
| A/batch01/journal.jsonl | 8c4597667a6335f36dca8b08d73c0137060bc5b73cd474e71f70b640df011a44 |
| partial_replay01/evidence.json | a35a660f49d192bba7988cbea8fcf5b72a0c4ab67b8a2d95946ca19059a3cf77 |
| A/stop_diagnostic01/accounting/accounting.json | ecc60c0e8687b63a5891191ab1a698ed1afe206248ae42c816a6617d13e77bc5 |
| stop_diagnostic01/failure/evidence.json | 0e9c8a925a633269115f3310b79740c10ba814b8da5f0d5d5a6965ff509f0810 |
| A/batch01/run007/result.json | f7979242d6946a680010222f6ae18e5da61ecab23a5f5e026f24f12e96922cca |
| A/batch01/run007/commands.jsonl | 0c3fbfaa2386784b71ea7e686e85ce7a13592076968786843eb044e873aa827a |

本结果提交只包含报告/结果索引，不修改冻结协议、原始日志、控制实现、参数或旧计划快照。完整结果提交SHA在提交后写外部实时进度，不预写自身SHA。自动续办已PAUSED，未push，未开始B/R04/R05。单张额度重置请求已在本轮观察到额度恢复且卡数3→2时记为兑现，未再调用重置或消耗下一张；它不构成飞行扩预算许可。

结果提交前：`freeze.py --gate A --check`退出0（635仓库资产、49外部资产保持）；结果JSON解析/59处路径SHA/7轮身份和计数/三组描述统计校验退出0，`git diff --check`退出0，独立只读事实审查无阻断项。结果阶段未改C++/Python执行路径，因此未把已完成的资格测试冒称再次执行。一次自动任务配置读取因系统Python无`tomllib`失败，改用已知单行字段只读解析后通过，自动任务API确认PAUSED；一次文档patch上下文不匹配被工具拒绝，修正上下文后应用，均无飞行或原始数据影响。
