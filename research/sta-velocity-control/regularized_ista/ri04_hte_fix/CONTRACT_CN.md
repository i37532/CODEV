# RI04 HTE／状态限幅交接：仅离线修复契约

2026-10-24；用户明确要求“离线修复这条HTE与限幅状态交接，直到完成为止”。入口分支`research/ista-velocity-regularized`、HEAD `50f354678fafb3fd4d4a09530e340f0eefa60f55`；工作区干净、33递归子模块匹配且内部干净。本目录是新修订，原RI02契约、RI04协议/资格/失败日志/报告/1880文件证据索引全部只读。

## 授权和完成条件

仅修改R-ISTA已应用输出缓存的HTE可用性，补生产路径/真实uORB离线测试、原始失败边界独立参考、全部适用PID/R-STA/旧ESTA回归、SITL构建及报告。实际新飞行、种子、调参和预算均0，不push、不RI05、不中断/重写原批次、不部署实机。默认PID、现有SITL AXES1/4、DIV1、参数值及数值安全限值、位置/姿态/rate环、上游/模型/land detector不改。

通过要求：新测试在旧生产代码上真实复现失败，修复后通过；实际运行非零既有测试与新增用例；原日志不改判；HTE不可行/保护限制仍拒绝且不部分修改状态；源码差异明确审查后提交、更新外部三文档完整SHA。离线修复完成不等于RI04飞行验收，不能据此续飞原6轮。

## 问题与最小规则修订

原RI02“任何状态保护使HTE缓存无效”在RI04遇到合法StateLimit事务后，首个有效HTE触发拒绝。区别本拍输出与下拍状态：

```text
理想候选：c = −lambda1*Psi(p) + nu_candidate
状态提交：nu_applied = clip(nu_candidate)
```

当只有StateLimit且整笔事务成功，当前实际纠偏c没有因状态裁剪重算；c和已提交nu_applied都已知。故允许保存这笔成功、未受输出/下游限幅的真实c和FF，**不要求二者再次满足原理想隐式状态等式**。不从已裁剪nu重新evaluate过去输出，不将`strict_axes=0`改成严格解。

对冻结上一拍误差/FF/XY倾角几何，原HTE变换仍为：

```text
delta = (H_old/H_new − 1) * (c + FF − g)
c_new = c + delta
nu_new = nu_applied + delta
H_new * (c_new + FF − g) = H_old * (c + FF − g)
```

右边是实际已输出纠偏的未限推力映射；不是用nu_candidate替换nu_applied，不是新算法或新起飞管理。该恒等式只描述冻结工况的映射连续性；下一拍s/h/FF及保护可变化，不保证下一拍真实推力不变、不证明闭环稳定或严格隐式轨迹。

**仅StateLimit不再单独使缓存失效。** CorrectionLimit、OutwardFreeze、下游constraint、Latched、失败/非闭合事务、无cache、错误sample/配置代次/生命周期仍拒绝。shiftZ原有有限数、nu限幅、旧/新纠偏限幅、活动/闭合状态检查全部保留；先检查再一起变更nu/缓存/hover，不裁剪HTE变换来冒充连续。PID/R-STA路径语义不改。

## 离线证据设计

- 真实原边界：run003最后有效sample43,064,000µs、ν应用−4、HTE .5→.7190654278。独立bisection复算此前414候选及实际seed；只读导出ULog小夹具，标注不是重飞或MATLAB重跑。
- 生产PositionControl自然积到正/负状态限制，非零FF/XY倾角，8/12ms及连续HTE；检查映射恒等式、无多积分/重算旧候选、nu新值与下一更新。
- 真实模块HTE发布/消费路径：StateLimit→首次有效HTE→正常下一拍；重复sample、disarm/rearm、故障/不可行HTE保持原拒绝，XY PID正常。
- 负例：输出纠偏/下游限幅、外推冻结、过期身份、reset、非有限/越域HTE、变换后状态/纠偏越界；不得为了夹具通过放宽参数范围。
- 独立参考、原PID/R-STA逐样本回归、48目标及现有Python库存，旧日志按其原源码绑定回放，不将新源码下的反事实样本当历史飞行成功。

新证据只写`/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI04_HTE_FIX/`；失败和每次命令/退出码保留，最终报告`reports/RI04_HTE_FIX.md`。本目录没有新飞行运行器、授权或gate_pass。
