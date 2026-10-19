# R03 numeric05：仅离线的理想 nu 候选数值核验

此组件针对 revision04 B/run015 的浮点验收拒绝，不是新运行器、飞行资格或完整验收分析器。
不导入/覆盖原 R02/R03 分析器，不更改旧 accepted=false，不改控制律、控制器 dt、参数、模型或安全阈值。
未接入运行器；本目录通过不意味着可以续跑旧批或开放 XY/XYZ。

## 为什么需要它

原核按单精度分步计算 rho、h×lambda2、增量及旧 nu 减增量；旧分析器用含 double 的表达式再以固定 2e-7 比较。
当理想候选刚超过 nu 上限4时，正常最终减法舍入已可能大于2e-7。限幅发生在候选计算之后，不能把 applied nu 当理想候选。
真实拒绝帧及独立 C++ 复算见 [revision04报告](../../reports/R03_REVISION04.md)。

## 实际检查范围

`checker.check_candidate(...)` 接收已记录的 s、h、实际 lambda2/epsilon、旧 nu、理想 nu，以及冻结配置值。
记录字段必须精确为 binary32；参数与冻结配置量化值单独核对。h/epsilon 仍限定既有域，不 clamp 或补修输入。

1. 用明确的 NumPy float32 除、乘、减重建每个舍入点。
2. 用输入位型构造精确有理数，以整数商/余数实现 round-to-nearest、ties-to-even，独立核对每步位型。
3. 对日志候选做严格位比较；另以未舍入有理数方程分解各次舍入误差，不用统一放宽容限换通过。

测试包括实际拒绝帧与正负镜像、边界/邻点、状态上限前后、参数量化、零/非零状态、异常时间、NaN/Inf、下溢/溢出。
漏掉/重复 h、错符号/旧状态、候选改一个 ULP、以 applied 代 ideal 必须拒绝。

它不核验 s 的来源、sample 时间链、旧 nu 生命周期/HTE 来源、Psi/原始纠偏、限幅/冻结后的状态、完整核有效性或飞行安全。
即使候选一致，返回值也明确 `flight_accepted=false`、`execution_authority_granted=false`。
还需原始各层检查及将来新版本的完整接线回归；不能将一帧数值一致冒称整轮通过。

## 算术假设与执行

假设逐操作 binary32 最近偶数舍入，无 FMA/重结合/倒数近似/FTZ。现有 SITL 编译包含不同优化选项，
已有两份日志21976样本在实际库和严格重编核之间逐位一致，只是这些样本的证据，不是所有平台的保证。
若新平台或编译选项不能满足假设，应明确停止审计，不能隐式放宽位比较。

在仓库根目录运行离线测试：

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/.px4-python" \
  python3 -m unittest discover \
  -s research/sta-velocity-control/regularized_sta/r03_numeric05 \
  -p 'test_*.py' -v
```

实际用例数量、退出码和证据指纹在 revision04 报告记录；网格内子样本不得重复算成独立测试。
未运行 MATLAB、PX4 新飞行或新预算。旧 R03 协议、资产、判定及日志保持。
