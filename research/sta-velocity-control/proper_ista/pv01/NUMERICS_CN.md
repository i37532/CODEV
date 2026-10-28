# PV01 数学、数值和事务接口契约

仅离线速度纠偏核，来源沿用 [PV00 契约](../pv00/CONTRACT_CN.md)：arXiv:2406.16094v1 的 (11a)、(12)、(13)，PDF SHA-256 `9aa4a20ef2a0f562cfad897e18cb8db96cf174fd332592bb2887e19ddafdd73b`。保留旧 Proper rate、原 ISTA 和 R-ISTA；本实现没有 epsilon、正则化、conditioned 或起飞管理变体。

## 1. 符号与当拍输出

- `s[k]=v[k]−v_sp[k]`，本地NED，单位 m/s；`z[k+1]`为虚拟隐式误差，不是物理对象下拍测量。
- `a[k]`、`nu[k]`、`nu_candidate[k+1]`：m/s²。只输出加速度纠偏，无质量/g/重力换算，无FF。
- `h`：s；lambda1：m^(1/2)/s^(3/2)；lambda2：m/s³；xi无量纲。

```
z = s + h (a − nu_candidate)
nu_candidate = nu_old − h lambda2 xi
a = −lambda1 sqrt(|z|) xi + 2 nu_candidate − nu_old
xi ∈ Sgn(z),  Sgn(0)=[−1,1]
```

消去a/nu得到单调包含式：

```
z + h lambda1 sqrt(|z|) xi + h² lambda2 xi = s
```

令 alpha=h lambda1、q=h²lambda2。

| 分支 | 解与当拍理想输出 |
|---|---|
| `|s|≤q`，含正负精确边界 | z=0，xi=s/q，nu_candidate=nu_old−s/h，a=nu_old−2s/h |
| `s>q` | xi=+1，delta=s−q，r²+alpha r=delta，z=r² |
| `s<−q` | xi=−1，delta=−s−q，r²+alpha r=delta，z=−r² |

外层 `r = 2 delta / (sqrt(alpha²+4delta)+alpha)`；它由根的有理化得到，与正根等价，避免“大数减大数”。外层输出 `a=nu_old−2h lambda2 xi−lambda1 r xi`。**不是R-STA的旧nu输出，也不是R-ISTA的补偿正则化关系。** FF在未来适配层只加一次；PV01没有适配层。

## 2. 数值域与修复

输入/增益/h/状态/输出为binary32，求解中间量及诊断z、xi为binary64。lambda1/lambda2/h必须正且至少FLT_MIN；输入和nu允许有限次正规数。非法dt不clamp；超出binary32有限上界的已计算输出拒绝，不饱和成MAX。

binary32有限正常输入组合的alpha、q、判别式及有理化根在binary64中有余量。保留double z/xi避免先将极小z窄化为0再开方导致的假残差。nu与a按原生最近偶数舍入变成float，允许渐进下溢；小于半个最小次正规数舍入到零是IEEE量化，**不是人工冲零或隐藏死区**。

本阶段只资格化x86 SSE Iris宿主：检查IEEE格式、x87最近舍入、MXCSR的FTZ/DAZ和SSE舍入位。非x86、fast-math、FTZ/DAZ或非最近舍入均明确拒绝，不更改宿主控制位。仅检查fegetround不足以发现SSE单独改变舍入，已专测此情况。

源目标和新测试目标局部使用 `-fno-fast-math -fno-reciprocal-math -fsigned-zeros -ffp-contract=off -frounding-math`；旧控制器/全局flags不变。目标仅在BUILD_TESTING注册，真实SITL固件不链接此核。这不是板级编译/运行资格。

### 舍入残差界

令 u32=2^-24、eta32=2^-149、B(y)=u32|y|+eta32/2；u64=2^-53，gamma64=64u64/(1−64u64)。每条式子的double操作误差预算为 gamma64×所有项绝对值之和；额外float窄化预算依次为：

1. z式：h(B(a)+B(nu_candidate))。
2. nu式：B(nu_candidate)。
3. a式：B(a)+2B(nu_candidate)。
4. 消元包含式：没有float输出窄化项。

这是按表示精度缩放的检查，不是固定1e−6工程容差。h×lambda1、h×h的两个float乘积在double精确；q增加一次舍入；邻边界delta在Sterbenz范围内相减精确，远处没有灾难性消减。正数求和/开方/有理化及少量输出运算的误差用保守gamma64预算包住；每个候选还实际检查四式。极端旧终点另用100位Decimal单调求解核对，不靠旧核自证。

范围检查对象是binary64求值结果。FLT_MAX±0.008或FLT_MAX+2可在double阶段已经舍入为FLT_MAX；这与float无穷溢出不同。参考记录高精度理想值是否超过MAX，不把这个端点舍入称限幅。不同求值顺序在端点附近可能相差一个ULP，不由有限122格点宣称全实数域证明。

## 3. evaluate / commit / reset

`evaluate(axis,v,v_sp,h)`只读，返回当拍理想z/xi/a/nu候选；`commit(candidate)`才修改选中轴nu。同轴成功提交使同代所有候选过期，再次提交拒绝。三轴参数/状态/配置代次/reset代次/state代次独立。

候选密封owner地址、单调不复用实例ID（防同地址重建ABA）、轴、分支、三代次及所有float/double有效载荷的逐位副本。跨实例、跨轴、旧配置、reset前、重复、篡改、伪造候选拒绝且不修改状态。非法setParameters/reset保持旧状态；全轴reset先检查代次空间再整体清零。实例/代次溢出fail-closed。密封用于逻辑事务检查，不宣称加密安全。

PV01只提供单轴理想commit，**没有生产保护commit，也没有三轴受约束原子提交适配器**；整体限制裁决、HTE、接管、sample去重与三轴原子提交属于PV02。对象限幅探针在外部明示先提交理想再reset导入状态，只是研究对象，不是可部署保护策略；受限输出/状态不称严格隐式解。

## 4. 验证解释边界

独立double参考在z上二分单调方程，最多1200次并检查相邻浮点终止；a由预测关系 `nu_candidate+(z−s)/h` 恢复，不复制生产有理化求根/分支输出。极值用100位Decimal独立求解。物理速度由独立ZOH积分；两级姿态/电机滞后用解析积分并由独立RK4检查，不把z当物理下一拍状态。

double参考本身不是全极端域真值：例如s=1、nu=0、h=lambda1=lambda2=FLT_MIN，double的z舍入为1会使`z−s`丢掉微小控制项；122极值格点由100位Decimal解决该消减，不把double该项错误归咎生产核。4个旧终点后各4096步是固定该终点float h的局部生命周期，交替8/12ms健壮性由另一个完整36秒对象验证，不混称原周期续跑。

固定周期、理想单位输入增益、无噪声/滞后/限幅且满足文献增益条件时，恒扰零偏差、斜坡扰动s=r h²才有理论含义。实际sample回放、变周期、噪声、滞后及限幅仅作工程诊断。数值修复不能保证稳定性、最优性、优于R-STA/R-ISTA或实机效果；PV01不进行飞行调参。MATLAB未运行。
