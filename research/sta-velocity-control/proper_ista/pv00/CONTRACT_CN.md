# PV00：Proper-ISTA 速度数学与数值接口契约

2026-10-28。此文件是后续独立速度核的设计约束，**不是生产实现或飞行资格**。PV00没有修复旧rate核，也没有注册MODE5。配套 [PV00报告](../../reports/PV00.md)、[有限诊断协议](PROTOCOL_CN.md) 和 [来源/命令指纹](results/evidence.json)。

## 1. 固定来源、命名与量纲

来源为 Seeber / Andritsch，*Proper Implicit Discretization of the Super-Twisting Controller—without and with Actuator Saturation*，**arXiv:2406.16094v1，2024-06-23**。固定[版本链接](https://arxiv.org/html/2406.16094v1)，本地PDF SHA-256为 `9aa4a20ef2a0f562cfad897e18cb8db96cf174fd332592bb2887e19ddafdd73b`；11页，404552字节。PDF第2页(1)–(4)为对象/零阶保持，第4页(11a)/(12)/(13)为本核，第4页Remark 3.3和Theorem 3.4/(15)给特殊增益与保证。PDF版式及式号已交叉核对，不能混用后续修订版。

原rate实现：`src/modules/mc_rate_control/StaRateControl/ProperIstaRateControl.{hpp,cpp}`，CPP最近提交 `3afe4fb98bf48473917da7a6c55e96ae40e82aca`，SHA-256 `e05fd08b3017efebe65689529bb92a662c9e9501a97903bf17051eec269dba45`。独立旧double参考 `research/sta-rate-control/ista_redesign/i01/audit.py` 来源提交 `547d324f6528a2fc05651574e5dd3ec5cb44e7de`，SHA-256 `61aa9d86348ffacea0e4f22e2f9997f4f3f07f28075f02c9163adadf6bd03563`。本次探针重新编译实际核，参考仍用单调求根，不复制生产解析式。

| 论文/新核 | 解释与单位 |
|---|---|
| x_k / s_k | 实测速度−实际消费速度目标，m/s；不是包内 e=v_sp−v |
| u_k / a_k | 不含FF的加速度纠偏，m/s² |
| v_k / nu_k | 调用前已提交状态，m/s²；论文v不是无人机速度 |
| v_(k+1) / nu_candidate | 本采样理想候选状态，m/s²；还未commit |
| z_(k+1) / virtual_s | 隐式预测变量，m/s；不是下次真实速度误差 |
| xi | Sgn(z)中的集合值，z=0时范围[-1,1] |
| T / h | 本次真实更新sample差，s；原PID时间语义不变 |
| k1 / lambda1 | (m/s²)/sqrt(m/s) |
| k2 / lambda2 | m/s³ |

坐标为本地NED：X北、Y东、Z下。正误差且nu=0应产生负纠偏。速度核没有rate的g，不除质量、不额外加重力；FF只在外层加一次。旧桥接g=1只是单位恒等映射，不证明真实通道无滞后。原ISTA、补偿正则化R-ISTA、Proper是不同控制律；R-ISTA的epsilon趋零也不等于本算法。保留速度0/1/2/3/4含义，与rate的数字模式分开。

## 2. 一拍的三式及解析关系

以下用z简写论文的z_(k+1)，nu_old简写nu_k；每次evaluate读取同一个旧状态：

```text
z = s + h*(a_ideal - nu_candidate)                      (11a)
a_ideal = -lambda1*sqrt(abs(z))*xi + 2*nu_candidate - nu_old  (12a)
nu_candidate = nu_old - h*lambda2*xi, xi in Sgn(z)      (12b)
```

消去输出/状态，得到单调包含关系 `z+h*lambda1*sqrt(abs(z))*xi+h²*lambda2*xi=s`。令 `q=h²*lambda2`、`alpha=h*lambda1`：

- `abs(s)<=q`（两个等号均在此）：`z=0, xi=s/q, nu_candidate=nu_old-s/h, a_ideal=nu_old-2*s/h`。
- `abs(s)>q`：`xi=sign(s), delta=abs(s)-q, r=2*delta/(sqrt(alpha²+4*delta)+alpha), z=xi*r²`；`nu_candidate=nu_old-h*lambda2*xi`，`a_ideal=nu_old-2*h*lambda2*xi-lambda1*r*xi`。
- 正/滑动/负三分支必须区分；精确边界用二进制可精确表示的h与nextafter测试，常规8/12ms边界另按实际float输入的double乘积判断。

有理化根来自 `r²+alpha*r=delta`，避免直接相减丢掉小根；不是新增平滑。旧rate核已经使用该根，不能将本次固定周期停止归因于“尚未有理化”。PV00首个研究候选沿用旧探针lambda1=2、lambda2=1，无epsilon；只用于离线，不是安全飞行参数。R对照epsilon=.02，来源为RI04共同Z候选，未加载源包高增益或搜索增益。

独立对象每拍由 `v_next=v+integral(a_applied+FF)+integral(d)` 推进。误差由新的真实v和目标重新计算，不把z赋给物理状态。两级滞后采用独立解析ZOH区间积分，并与另一套RK4微分积分核对。独立double闭环维护自己的v/nu；同输入残差比较与长期闭环差是两回事。

## 3. 保证与非保证

理想对象是单位输入增益积分器、固定h、无噪声/延迟/约束，扰动导数绝对值不超过L，满足lambda2>L、lambda1>sqrt(lambda2+L)。按论文(15)/Theorem3.4，有限步后nu_k=−w_(k−2)，s_k=h*(w_(k−1)−w_(k−2))，w为区间平均扰动：恒扰s=0，斜坡斜率r时s=r*h²。滑动z=0不要求s=0。

变化目标与左端FF形成的剩余误差必须计入等效扰动，不能直接套恒扰结论。交替/真实8/12ms、限幅、姿态/电机滞后、测量噪声、HTE/起降都不属于上述定理证明对象。论文第4节(17)/(18)是另一个conditioned算法；当前PX4保护和本次标量裁剪均不是该算法。

lambda1=2*sqrt(lambda2)时，论文Remark3.3指出外分支恰等于显式STA；滑动分支为二阶deadbeat。本次lambda1=2/lambda2=1正好在此特例。与R系列的差别还有正则化层、补偿预测和保护状态关系，不称“只比较Euler方法”。

## 4. 数值有效域与PV01修复假设

旧核限制正normal增益/时间，输入差、nu与全部输出只能是normal或精确0，binary64中间量后缩至binary32。`FLT_MIN=2^-126`不是最小非零数；`denorm_min=2^-149`到该界间的次正规数被旧representable拒绝。精确停止位模式见结果包，不用十进制显示值重新猜输入。

本次定位：固定8/10/12ms下，滑动分支 `nu_old-s/h` 消减到次正规数而首拒绝；交替周期则首先拒绝次正规输入差。允许保留舍入后次正规量时，这4个单步三式残差均可通过原尺度检查；这只是修复可行线索，**尚非完整生命周期修复**。FTZ/DAZ可能把某些输入直接变0从而“不拒绝”，但改变了问题，不能作为修复。

PV01允许研究的数值等价方向：

1. 保留binary64乘积/有理化，正常输入差精度及float舍入语义明确；真正溢出与中间float溢出分开。
2. 明确支持渐进下溢、或使用更宽内部状态并证明接口舍入合同。不能只删除一处normal检查而遗漏reset/commit/virtual_s/xi检查。
3. 对次正规舍入给绝对ULP项与相对项组合的推导，检查原三式及包含关系；不得用1e-6一类工程绝对误差直接遮蔽1e-39量级。
4. 独立80位decimal单调求根/高精度残差补充double在极端域的证据；并明确目标FTZ/DAZ环境。若不支持FTZ，显式诊断拒绝环境，不能把FTZ结果冒充同一算术模型。
5. 合法极小输入须覆盖evaluate→commit→下一步→reset，正常域、边界邻点、参数/输入/输出真实不可表示均保留拒绝测试；状态代次失败不更新。

没有授权引入epsilon、死区、强制nu冲零、滤波、预测器或conditioned律。若纯数值修复不足以满足工程条件，记录needs_revision并提出另一个具名研究范围，不暗改Proper定义。本次数值诊断不改变2e-6常规逐步残差标准，也不放宽旧飞行阈值。

## 5. 独立速度核最小接口与保护边界

候选文件 `PositionControl/ProperIstaVelocityControl.*`，C++14，无uORB/参数/Gazebo依赖。建议 `setParameters(axis, {lambda1,lambda2}) / evaluate(axis,v,v_sp,h) / commit(candidate) / reset`；不直接依赖rate类。三轴nu独立，候选只读，记录owner/轴/配置与reset代次/密封校验；重复、跨轴、跨实例、陈旧、篡改候选拒绝。evaluate不得更改nu，commit最多一次；PV02在多轴全部有效并裁决约束后原子提交，同sample二次update不得再积分。

理想诊断至少含s/z/xi/nu_before/nu_candidate/a_ideal/branch/status。应用nu、纠偏、FF后发布加速度和推力另存，候选代次与真实更新序列可追溯；不把R-ISTA的ri_p字段改名解释为Proper z。MODE5已查无占用，仅为后续预留；生产max仍4，测试确认5/所有掩码被拒绝。候选参数 `MPC_VP_L1_X/Y/Z`、`MPC_VP_L2_X/Y/Z`均未占用且≤16字符；未注册或设置默认值。

当前status格式含topic/NUL/padding为1475字节，selection为1018，队列均8，1500字节容量不能直接塞入整套新诊断。拟用独立 `proper_ista_velocity_status`（目前未占用），PV02须测实际生成格式/队列/日志吞吐、双时钟及真实解码，本次只作容量审计。

### HTE与seed的待验证恒等式，不是可直接复用的保护

固定s/h时可写 `a_ideal=nu_old+F(s,h)`、`nu_candidate=nu_old+G(s,h)`；z/xi不依赖nu_old。因此**同时平移旧状态与相应候选**delta，理想输出也平移delta。未受限的交接初值候选为 `nu_old_seed=a_target-F(s,h)`，必须区分seed发生在求解前还是已提交后；不能再补一次积分。

只改变nu_candidate而保留旧nu/z/xi时，(12a)形式重构会产生 `2*delta`，不是R-STA/R-ISTA的单倍关系；且(11a)一般同时被破坏。这说明不能照搬“冻结nu后重算输出”。保持旧a并提交裁剪nu也不再是三式严格解。PV02必须独立固定所选工程保护合同与日志strict标记，不由本审计偷偷选择一种新控制律。

HTE目标来自冻结上一拍实际应用纠偏c、FF、倾角几何的推力映射：`delta=(H_old/H_new-1)*(c+FF-g0)`。本式g0仅是外层重力常量，不是rate输入增益。若仅StateLimit改变nu而未改变当拍c，须保留闭合事务实际c/FF缓存；不能用提交后nu重算上一拍。c/nu/H、sample和配置代次、有效阶段及全部边界检查完成后才整体更新；不合格时不部分写入。映射连续不等于下一拍连续或闭环稳定。

起降、HTE、保护未在本阶段实施或验收；延续RI04_HTE_FIX的反例经验而非继承其算法证明。PV02还须覆盖合法XY、纯加速度、一次FF、Z优先/水平矢量限制、地面/ramp/假离地/取消/弹跳/超时、EKF reset、异常时间/测量、故障/termination、重新解锁及末轴失败回滚。沿用R03 revision11/position11的完整日志链，不用全话题去重修补时钟问题。

## 6. PV01可启动与后续门槛

PV00完成允许另行启动PV01离线实现：固定来源与候选、213轨迹和12精确停止可复现、数值/适用性问题已区分。**不意味着当前Proper已适合飞行。**

PV01验收至少要求：独立速度核/强候选身份、4个Proper极小数原始输入完整生命周期、122格点及边界负例、正常域不退化、独立double/decimal参考与对象、明确浮点环境、PID/R系列兼容与SITL只构建；MODE5仍不可接管。滞后/噪声结果如实保留，不要求赢，但不能因修复数值停止就宣称解决振荡。飞行候选的安全范围、保护/HTE与有界接管必须等PV02完成后单独冻结。本次没有启动这些阶段。
