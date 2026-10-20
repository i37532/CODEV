# R03 revision06：保留前三门，完整验证XYZ

2026-10-20。最新：干净资格通过后，D前2轮接受、第3轮ESTA降落期真实EKF切换被拒绝，批次已停止，余6未执行，**R03尚未验收**。完整账目见[停批报告](R03_REVISION06_STOP.md)。下方飞前准备段落为历史检查点，保留不覆盖。

## 范围、历史和预算

用户明确授权后续必要预算调整无需再次确认，直到R03验收。本次有限上限58＝已用历史49＋新D/XYZ9。历史48起飞、44接受、5失败/无效完整保留。保留的完整门为revision04 A/X、revision05 B/Z和C/XY，每门9接受、6配对检查和9独立回放，共27个有效门运行；累计44接受不能全并入本次矩阵。

入口分支research/sta-velocity-regularized，HEAD ddb4c2f803e4a79af2bfb2c1ad9a1731688ec660，开工工作区干净，33递归子模块无偏移。revision05 D首轮物理起降完成但原完整分析失败，原判保留；其余八项不续跑。新D使用独立revision06、三算法各3轮、三个全新配对种子，准确顺序与指纹以本版manifest为准。

本次只将已离线验证的handoff06完整height→handoff→AX02三维目标参考接入新运行器、完整分析、资格和独立回放。numeric05候选精确核对、prearm04增量预热和原500ms规则保持；控制律、dt、127项参数、epsilon、波形/窗口、模型/world/插件和全部数值门槛不改。只限项目Gazebo Classic Iris SITL，位置P/姿态/rate PID、速度DIV1，默认PID。

每批首个安全、必需有效性、配对风险或清理失败立即停批。若需再修订，先离线修复并公开准确新增预算，再冻结新有限版本，不补飞旧清单、不调参或放宽门槛。此次只到R03，不自动R04/R05、ISTA或实机。

## 飞前检查记录

已完整阅读当前三份专项计划、共同规则、revision05报告及handoff06离线报告和说明。新增AUTHORIZATION_R03_REVISION06_CN.md与plan/r03_revision06_entry三份快照；旧快照和原失败不覆盖。

现场只读检查：正确分支、完整HEAD、干净工作区；无PX4/Gazebo或旧批运行器进程。磁盘约59GiB可用、tmpfs约7.3GiB可用，仍须按每轮预检核验。不删除历史日志。

历史证据审计、新工具接线、种子查重/冻结、真实非零回归、源码提交和干净资格仍在准备；本次新尝试/起飞/接受均0。此处不把旧513 C++/1430 Python或337项handoff06定向测试算成本次新资格。

大型证据根：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision06。

后续记录包括真实命令、退出码、不同测试数、准确源码/固件SHA、九轮账本、日志指纹、六配对和九独立回放、逐轴指标及未执行项。未重新运行MATLAB；本阶段不实机。

### 历史输入与保留门重新核验

独立只读审计 `R03_revision06/offline_evidence01/audit.py` 实际exit0（24.53s），确认49尝试/48起飞/44接受/5失败。98份原ULog共5,205,201,909字节逐文件SHA符合；2414个不同输入前后指纹保持。A04/B05/C05各用原版本 `verify_complete` 重新核验九接受、六配对、九独立回放，返回与原gate_pass精确一致。

handoff06原索引1337文件/10符号链接保持；A660/B724/C724/D724源资产分别核对。A/B/C各五个后来准入改动从对应原飞行提交的Git对象验证，不假称当前源码与旧飞行源码相同。EEPROM仍为06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，33子模块工作区/版本正常、无仿真残留。此审计只读指纹/既有回放收据，不冒称重新解码98份ULog或新增飞行。

审计脚本SHA：894b8bef3e89b02e7e16ee26345dd9df97869a2c58312359dfd102a0f0aff84e；evidence.json SHA：015af812ee7bacfd7b2d14a5f1e5febd959a164be53ce13e604f0e8e875a7c70。

### 新清单与定向离线测试

新种子71431–71433完成全历史结构化查重，首次实际解析61,391份JSON，无冲突/非法JSON；scan_manifest_sha256为ce5e55fa02a1be0556cf64644315b1870347cde49b913e58aa594103dbe39132。仅新四份准确SHA登记豁免，旧预留未飞种子不复用，起飞前仍重新现场查重。

准确顺序：run028–030为PID/RSTA/ESTA，run031–033为PID/ESTA/RSTA，run034–036为PID/RSTA/ESTA；分别使用上述三个种子。所有九项同TEST8、64s主窗、90s观察与127参数，科学字段/顺序逐字段对照旧D，仅版本与种子改变。新execution SHA为a36942e674cdedfb5e2cbb52848a8d6b670f04dea1c709a7d8a4aea33938973c。默认 `runner.py --gate D` 主代理实际exit0，只输出清单，无参数/文件/进程/飞行变化。

分项真实测试（均使用项目`.px4-python`、研究scripts及M00 Python依赖；后续统一资格会重跑，不重复累加）：

| 测试入口 | 已实际通过数 | 退出码/说明 |
|---|---:|---|
| r03_handoff06/test_adapter.py | 46 | 主代理复跑exit0，旧组件测试不是新飞行 |
| r03_revision06/test_protocol.py | 35 | exit0 |
| r03_revision06/test_revision_audit.py | 21 | exit0；与上项interface_tests01收据 |
| r03_revision06/test_replay.py | 44 | offline_replay_tests02，exit0 |
| test_r03_revision06_result_summary.py | 44 | offline_summary_tests01，exit0 |
| r03_revision06/test_qualification_diagnostics.py | 11 | 主代理exit0，完整诊断的非授权/来源/绑定/类型负例 |

开发错误原样保留：首次回放单测启动漏项目PYTHONPATH，44项中39项依赖导入报错，exit1；补齐既定环境后重跑通过，不改逻辑或阈值。版本迁移的retained字段前缀误替换在飞前审查发现并修复，严格字段/计数负例补齐；分析/运行器旧测试夹具编号正在单独修正，统一回归尚未宣布通过。

新统一验证将使用正常执行与诊断共用的完整科学函数：新D旧失败日志两种独立CLI导入顺序，以及A/B/C每门三算法各一份，共10原运行/11次新链诊断。旧首批A与数值失败B另用冻结revision05诊断入口回归，不能冒充新D接线证明。所有历史诊断必须accepted=false、flight_accepted=false、0新飞行且原判/输入指纹保持；任何失败阻断资格。

### 统一离线验证通过（提交前，尚非飞行资格）

`env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<.px4-python:研究scripts:M00依赖> python3 -B research/sta-velocity-control/regularized_sta/r03_revision06/verify.py --gate D --output '<外部根>/R03_revision06/D/verification01'` 实际exit0。72条顶层命令全部退出0，**513个不同C++、1688个Python测试**，原PID/ESTA固定序列32768对主样本和256对同sample重算通过。SITL及DONT_RUN Gazebo构建通过；输入指纹、33子模块和原EEPROM保持。

新链10个旧运行/11次完整诊断全部结束，D两种真实加载顺序metrics值/类型完全一致、频谱SHA一致；ABC九个代表日志全部通过完整检查。所有诊断输出非授权、不改原判。另执行冻结revision05的两类旧失败各两序诊断，明确不是新链证明。未执行MATLAB、飞行或实机。

本次evidence SHA为9c11c186b996cea5e5aa03955b79815e45adcebfd9474e71418fca9251d38dd5；success=true、clean=false、新飞行0，因此不可拿本次收据起飞。仍须明确源码提交后重构建并生成干净资格。

开发夹具修订最终为numeric16、analysis56、runner50及replay44项定向通过；上述1688已包含对应实际执行，不再加计166项。offline_analysis01保留四个旧D-only/历史范围/运行编号夹具失败；修正后offline_analysis02三命令全0。最终独立审查核对flight_main/shutdown_owned/prearm/restore与原实现除私有版本名外AST一致，numeric适配仅私有模块名改变；没有删安全谓词、改变数值门槛或生产文件。

注册后全历史再次扫描61,398份JSON通过，scan SHA d437430b1bb6bdc7f86935704b5687dd54f915a85dc72b4992f770686b51fc3a；仅四份精确登记文件例外。新版默认dry-run与源码范围审查退出0。后续冻结/干净资格/飞行结果在实际完成后追加。

飞前冻结实际exit0：759项仓库资产、79项外部资产，严格绑定原A/B/C证明及58＝49＋9预算。明确范围暂存32文件，生产文件/旧冻结目录零改。暂存diff检查唯一提示为授权文档末尾一个空行（exit2），人工审查为无功能影响的格式提示并保留；不把该检查写成exit0，也不修改已绑定授权或科学门槛。其余差异由两个独立审查及主代理检查无阻断；最终源码SHA待真实提交后在外部进度记录。

### 干净资格、实际三次尝试及停止

真实源码提交为`ae61c29f6ed37e67a64ff29f952a45554e11096b`。在该干净提交上`verify.py --gate D --output '<外部根>/R03_revision06/D/qualification01' --qualify`实际exit0，72命令全0、513不同C++/1688 Python、32768对主样本及256对同sample重算、完整诊断/构建通过；clean=true、approved=true。资格SHA `af5095d811551aa817a155ae8cafd0243f478e867d22b40bf7e82a8a224c23c0`，固件SHA `9e2d15d95c0bc53a2a427d33b1e21a5cd90ddb31c067d1aae80cecf853ce1a55`。

随后实际调用`runner.py --gate D --execute --source-head ae61c29f6ed37e67a64ff29f952a45554e11096b --qualification '<上述资格目录>/evidence.json'`，会话48010在第3次失败后exit1。新D实际3尝试/3起飞指令/2接受/1失败，剩6未执行；原PID和RSTA完成起降上锁，ESTA在降落期拒绝，没有完整上锁事件。累计52/51/46/6，不能称D或R03通过。

两接受按原版独立CLI解码、指标逐值与频谱SHA核验、一个配对重算均通过，原失败不分析改判。参数精确恢复、无仿真残留。详见[停批记录](R03_REVISION06_STOP.md)和[EKF超时离线审计](R03_EKF_TIMEOUT_AUDIT.md)。

当前是上游时间链原因/范围待解决，不是预算待批准。已有原始证据确认真实EKF超时切换及参考变化，正确检查不能删除或放宽；gyro/调度证据不足以确定因果修复。用户允许后续有限预算调整，但现有明确上游边界仍在。新有限预算尚未激活，不续旧run031，不以重飞碰运气，不push或进入R04/R05。
