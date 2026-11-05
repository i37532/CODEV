# R00 数学与来源包独立审计

2026-10-16。范围仅离线数学、来源包构建/测试；未改生产控制、参数、模型，未启动 Gazebo 或飞行。
本文件是 R00 的子证据，不单独代替主报告、实际日志周期审计或完整阶段验收。

## 1. 公式、量纲与时序

来源为 `/home/yr/Desktop/STA-ISTA-MATLAB-PX4/matlab/sta/sta_velocity_ff_conditional.m`、
`height_sta_acceleration.m` 和 `cpp/velocity_sta_ista.hpp` 的 STA 分支。
源码包使用 `e=v_sp-v`；当前 PX4 新/旧 STA 接口使用 `s=v-v_sp=-e`。
改变误差符号时不反转物理加速度状态 nu：

```text
rho(s,epsilon) = s/epsilon                       if |s|<epsilon
                 sign(s)                        otherwise
Psi(s,epsilon) = s/sqrt(epsilon)                 if |s|<=epsilon
                 sqrt(|s|)*sign(s)              otherwise
a_sta[k]      = -lambda1*Psi(s[k],epsilon)+nu[k]
nu_candidate  = nu[k]-h*lambda2*rho(s[k],epsilon)
```

零点 `rho=Psi=0`，非零初始 nu 在零误差时仍生成相应加速度；不是每周期清零状态。
`+epsilon/-epsilon` 两侧连续，导数在边界可改变；层外与硬 sign ESTA 相同，层内为线性反馈。
上述分段式与包内 `sqrt(max(abs(s),epsilon))*sat(s/epsilon)` 实数等价，避免层外巨大 `s/epsilon`
不必要的中间溢出。R01 仍须对实际 float、subnormal、状态增量舍入和溢出做独立测试。

| 量 | 单位 |
|---|---|
| s、epsilon | m/s |
| a_sta、nu、一次有效 a_ff | m/s² |
| lambda1 | sqrt(m)/s^(3/2) |
| lambda2 | m/s³ |
| h | s |

旧 nu 生成当步输出，保护裁决后才提交新 nu。这里是正则化显式算法，不能叫 Proper Implicit，
不能把边界层线性系统的渐近性质写成硬 sign STA 的精确有限时间结论。
保持 PX4 的“纠偏限幅 → 一次 FF → 下游推力/倾角/Z 优先约束”；不移植包内 `-lambda*v`、
FF 后总量裁剪、`[-22,+8]` 总加速度界、质量/PWM/油门或 rate 的 g。

来源包独立探针给出反例：纠偏 3、FF 3、限幅 ±1 时，包内总量裁剪为 1，
PX4 保留的纠偏裁剪后加 FF 为 4；这不是相同限幅接口。

## 2. 理想局部离散模型与 Jury 条件

仅在恒定速度目标、无 FF、无噪声/滞后/限幅、单位增益精确 ZOH 加速度对象且状态位于层内时：

```text
alpha = lambda1/sqrt(epsilon), beta=lambda2/epsilon
s_next = s+h*(-alpha*s+nu)
nu_next = nu-h*beta*s
A(h) = [[1-h*alpha, h], [-h*beta, 1]]
trace=2-h*alpha; det=1-h*alpha+h²*beta
```

特征多项式 `z²-trace*z+det` 的单位圆内条件可写为三个严格不等式：

```text
1-trace+det = h²*beta > 0
1+trace+det = 4-2*h*alpha+h²*beta > 0
1-det       = h*alpha-h²*beta > 0
```

正增益下，首个小步长稳定边界为 `h_det=alpha/beta`；当 `alpha²>=4*beta` 时还需取
`h_minus_one=4/(alpha+sqrt(alpha²-4*beta))` 与之的最小值。边界等号不算渐近稳定。
探针以直接矩阵特征值与独立 ZOH 对象推进交叉检查，不仅重复同一个布尔判据。

来源高 Z 参数 `(lambda1,lambda2,epsilon)=(20,12,.01)` 对应 `alpha=200,beta=1200`，
首边界 **10.31947467255235 ms**：

| 固定 h | 局部谱半径 | 理想局部 Schur |
|---|---:|---|
| 5 ms | 0.969041576 | 是 |
| 10 ms | 0.938083152 | 是 |
| 12 ms | 1.325699782 | 否 |
| 16 ms | 2.100933043 | 否 |

这说明不能把 5ms 包参数直接照搬到当前约 100Hz 速度回路，不等于预测真实 PX4 必然失稳。
尤其实际采样可为 **8/12ms 交替而非固定10ms**：理想层内两步矩阵
`A(.012)A(.008)=[[.7248,.0008],[-.96,.8848]]` 的谱半径约 **0.8798466522**，仍小于1。
因此“某一个12ms矩阵非Schur”也不能直接当作该周期交替系统失败证明。
R01 必须按实测时间序列、姿态/电机滞后、噪声和约束独立验证；本节不扩展为变步长或飞机稳定性定理。

## 3. 原增益下的 epsilon 数值域与离线候选

参数来源为既有 `axis_ablation/ax04/parameters/*.json`，不是源包的高增益：

| 轴 | lambda1/lambda2 | nu/纠偏限制 | h≤40ms 的理想层内严格下界 |
|---|---|---|---|
| X/Y | .5/.1 | .4/.8 | epsilon > .000064 m/s |
| Z | 2/1 | 4/6 | epsilon > .0004 m/s |

下界来自上节全部条件，不是只检查 `h*alpha`；40ms来自现有 DIV1 保护允许区间上沿，
并非实际常用周期。不能将此下界当成真实飞机可飞参数的证明。

提出新参数工程数值域 **[.001,1] m/s**：有限、正、正常 float；下沿高于上述旧增益/40ms 理想下界，
避免把极端小 epsilon 导致的高局部增益当正常配置；上沿是本低速研究的工程范围，不是理论最优上界。
R01 可采用该域并进一步检查计算有限性，R04 改增益时必须重新核验而非沿用旧增益稳定声明。

本次只进行 **12 个解析筛查点**：两组旧增益各遍历 epsilon
`[.0025,.005,.01,.02,.04,.08]`，全部在固定40ms理想局部筛查通过；没有基于新飞行优化。
提出下一阶段第一组离线候选 `epsilon_X/Y/Z=.01/.01/.02 m/s`，对应首稳定边界约
`.5/.5/.282843 s`。它保持旧增益和限幅不变，Z使用略宽层；**不是已验收飞行参数**。
R01 须报告有限候选/对象矩阵的准确预算，并在含滞后/噪声/变周期验证后冻结唯一 R03 参数。

一个必须披露的平滑代价：理想恒定扰动 d 的平衡可为 `s=0,nu=-d`；
若层内扰动斜坡每步增加 `r*h`，稳态特解为 `s=r/beta=epsilon*r/lambda2`。
增大 epsilon 降低局部输出/积分响应，也可能增加变化扰动下跟踪偏差；不能预设全面胜出。
探针验证正/负/零扰动平衡及斜坡特解，而非把同一 nu 公式当实际飞机收敛证据。

## 4. 来源包安全接口差异

实跑来源 C++ 表明：

- reset 回到同一 nu 数值后，旧候选仍能提交。
- X 对象生成的候选可以提交到 nu 相同的 Y 对象。
- 原包只检查 nu 值和候选 committed 标记，不能代替现有 PX4 的 owner/axis/revision/密封载荷验证。

`source_probe.cpp` 对这些已知缺口做显式再现；结果中的 true 是“缺口被复现”，不是安全通过。
R01/R02 必须保留强事务、三轴原子提交和配置代次；epsilon-only 变更也必须使旧候选失效。
当前源包允许 k1/k2=0，而现有 PX4 STA 要求严格正正常增益；本专项不借移植悄悄放宽该语义。

## 5. 本次执行、数量与复现

在仓库根执行，输出文件必须不存在：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 research/sta-velocity-control/regularized_sta/r00/math/run_audit.py \
  --package /home/yr/Desktop/STA-ISTA-MATLAB-PX4 \
  --output /tmp/r00-math-new-result.json
```

实际最终结果为 `results02.json`，源码包未写入，构建在 `/tmp/r00-source-audit-pp7r2m91`。
JSON 记录完整 argv/cwd/stdout/stderr/退出码、来源 SHA、数值和测试明细。

| 检查 | 本次结果 |
|---|---|
| 原包 SHA256SUMS | 29/29，退出0 |
| CMake3.22.1 + GCC11.4.0 原包 Release 构建 | 退出0 |
| 原包 CTest | 2/2，退出0；包含共享文件原有ISTA测试，不表示本专项移植ISTA |
| 历史 MATLAB CSV 一步 fixture | 7980行，STA/ISTA各3990，每行float/double；不是7980个闭环实验 |
| 新 C++14 映射/符号/旧nu/边界/FF探针 | 4320个输入-精度组合，17284断言，0失败，退出0 |
| 独立 Python 数学/理想对象测试 | 15个唯一unittest，0失败/错误；由入口实跑 |
| MATLAB/Octave | PATH均无可执行程序，本次未执行 |

`results01.json` 是初次14测试的通过记录，保留不覆盖；补充实际8/12ms两步语义和精确重根的
代数化简后执行 `results02.json`，最终15个唯一测试。不将两次重复运行相加宣称29个不同测试。
同样，源包CTest、fixture和4320映射组合重复执行不重复计唯一数。
没有生产固件编译、PX4 GTest、SITL、新飞行、整机Simulink闭环或板级性能结果；由后续阶段分别验收。

## 6. 阅读范围与继承教训

本子审计完整阅读：新专项 TODO/PROMPTS/STATUS（三份初版全文及连续执行授权增补）；
源包 README、VALIDATION、cpp/README、三份 docs、STA两函数、common高度映射、参数及来源JSON、
C++头/测试/CMake、MATLAB导出/参数检查/测试说明；当前 StaVelocityControl/Protection 相关实现。
另完整阅读原率环 I00/I01/M09/M10/I05_LOGGING_AUDIT/I05_RC_CONTINUATION_IMPLEMENTATION，
以及旧 STA_MILESTONES 共同规则和技术约定（§2–3）。其余速度阶段/实际周期由R00主审计整合。

继承内容：先复现机制再宣称改进；固定周期定理与工程保护分开；真实更新算TV、宿主墙钟不作板级CPU；
ULog dropout=0不等于所有话题完整；下游部分覆盖只能证明匹配部分，不插值补造；
历史修订须保留原判、源码资格和数据；旧报告的历史“未push/需再授权”不覆盖本次明确新授权。
没有重新审阅/下载外部论文，不将包内名称或旧 Proper-ISTA 论文保证移植到本正则化显式内核。
