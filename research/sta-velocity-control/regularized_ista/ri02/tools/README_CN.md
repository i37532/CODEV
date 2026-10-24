# RI02 离线工具

本目录只服务 RI02：**零飞行、零新种子、MODE4 生产准入关闭**。
默认只打印来源明确的完整127参数档案；即使提供源码、资格或manifest，`--execute`也硬拒绝。
不调用 Gazebo，不写真实 EEPROM，不启动旧 R04/R05，不建立旧 ESTA 新统计组。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python"
python3 -B research/sta-velocity-control/regularized_ista/ri02/tools/run.py
python3 -B research/sta-velocity-control/regularized_ista/ri02/tools/run.py --mode 4 --axes 1
```

PID=0/AXES0；R-STA=3、R-ISTA=4的离线候选掩码为1/4/3/7。MODE1/2不进入本专项清单，未知轴不映射成X。参数来源是RI00已冻结的R03完整档案，不是来源MATLAB高增益；保留原位置P、姿态/rate PID和DIV1。候选不代表准入或飞行合格。

## 参数事务

`parameters.py`复用原`run_v00`的BSON编码/完整参数读回与内环检查。显式注入存储与“自有会话已停止”函数，并先创建不可覆盖的完整持久备份。保留未知无关参数和原logger配置位；异常退出也精确恢复原始字节。若会话尚运行，保留备份并明确拒绝危险的在线还原。

提供的`FileStore`只允许显式离线沙箱内的现有文件，拒绝真实`build/rootfs`。测试使用新临时目录和fake CLI，没有使用真实运行后端。MODE4读回验收要求requested=4且实际effective≠4、unimplemented位存在、无新候选/提交；不能以请求成功冒充接管。

读回还核验effective variant、轴掩码、完整requested/effective epsilon、配置代次与pending/reject；PID允许未使用STA配置的reject标志，但已生效R-STA不可拒绝配置。拒绝MODE4后若仍为R-STA，必须显式提供此前已核实的保留配置，不能把被拒请求的参数当作实际生效参数。

## 日志合同

新数学诊断在`velocity_ctrl_selection`里，`ri_version=1`；与`sta_velocity_ctrl_status`按完整`publish_seq + timestamp_sample`关联，输入publication也精确一致。`ri_h`才是内核sample步长；原`h`/used_dt仍是原PID语义。

- 隐式候选：`ri_p`、`ri_nu_candidate`、`ri_a_ideal`，使用候选nu计算当步理想输出。
- 工程应用：`ri_nu_applied`、`ri_a_applied`，后者仅FF之前的纠偏；冻结nu不重构理想a。
- 实际发布：`ri_acc_published`和`ri_thrust_published`；a_proxy仍只是推力映射代理。
- `ri_strict_axes`仅标记未被状态/纠偏/下游保护改变的已提交候选。保护后的输出不被当作严格隐式解。
- 起降seed使用`ri_seed_h`和单独保留的p反解：nu_seed=PID纠偏+lambda1*Psi(p)+h*lambda2*rho(p)。seed不是正常积分，ri_valid=false。

`analyzer.check`检查新MODE4的离线组件及完整边界，包含理想三式、保护状态、FF一次、发布值、实际内环、参数代次、缺样/未接管/同刻歧义与seed。它只返回component_valid，**永远不签发飞行accepted或gate_pass**。RI02没有新MODE4飞行ULog；夹具通过不冒充真实飞行全链证据。

共同DIV1规则保持原要求：h与原used_dt相符、宿主耗时为正、无held/虚构饱和区间位、完整且非零的参数代次、未选轴epsilon/STA载荷为NaN。ri_valid必须对应完整成功提交；无候选时不可残留理想载荷，seed仅例外保留p。HTE连续性逐轴验证，只允许Z状态使用Z平移，XY不继承它。

nu候选使用已冻结numeric05的独立整数/Fraction逐步舍入原语，但输入明确为新隐式根p；隐式根残差和候选nu输出仍独立核对。不把算法4改标3，也不用旧显式Psi(s)关系。`full_chain.py`把此新组件与最终完整科学链私有组合，保留旧预热/完整位置和姿态/目标/落地尾窗/内环/输出/谱/耗时检查；只扩展私有任务模式域。调用仍只产离线诊断，不能继承旧批次资格。没有完整MODE4真实ULog，因此只报告真实绑定和负例测试，不报告新飞行全链验收。

`dependencies.py`固定最终revision11/position11/相对预热依赖SHA，直接复用完整白名单、同刻组、reset、增量解码及降落尾窗规则；不是全话题去重。`replay.py`在新外部目录调用同一个最终完整分析函数，并保留原job/版本/模式/来源与参数恢复证据。原ESTA只允许作为历史日志防退化输入。

## 离线复现

```bash
python3 -B research/sta-velocity-control/regularized_ista/ri02/tools/test_tools.py
python3 -B research/sta-velocity-control/regularized_ista/ri02/tools/verify.py \
  --with-history --output '/一个全新的外部目录'
```

完整验证包含本目录工具用例、旧position11/warmup10/monitor02/prearm04组件，最终A/B/C/D各9份共36份历史完整日志回放，以及revision10/run033的真实失败ULog和确切67333572字节增量前缀。成功旧日志要求科学数值/类型和谱一致；输入逐文件SHA首尾一致。失败前缀只作诊断，旧失败不改判、不补成新样本。所有新回放结果固定diagnostic_only=true、accepted=false、flight_accepted=false。

revision09相比最终position11有一处已知描述文字变化：`task_targets.attitude.association`从旧“唯一发布时间交集”改为“完整同刻组/载荷/身份对应”。只允许这一个字段、这一对精确文字和这一旧版本，其他字段（包括数值类型）逐项不变；同时记录未排除此说明时的原始逐值比较结果。不是删除整个任务目标检查或放宽数值规则。

每个输出目录不可覆盖。`verify.py`记录实际argv、cwd、退出码、耗时、测试数和日志SHA；失败尝试保留。大型旧ULog不复制入Git，新sidecar/解码摘要只写独立外部目录。实际测试数量和通过范围以最终报告/收据为准，不在本说明预填未完成结果。
