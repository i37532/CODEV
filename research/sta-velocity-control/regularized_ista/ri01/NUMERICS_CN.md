# RI01 数值域、候选事务与接线边界

本阶段实现独立 RegularizedIstaVelocityControl，不把它接到 PositionControl、公共保护、参数元数据、logger 或执行器。只在 BUILD_TESTING 中建库和测试；实际 MODE4 继续拒绝。RI00 的旧快照和来源包保持原样。

## 1. 同一个补偿隐式关系

沿用 RI00：s=v−v_sp，p+h*lambda1*Psi(p)+h²*lambda2*rho(p)=s；
nu_next=nu_before−h*lambda2*rho(p)，a_sta=−lambda1*Psi(p)+nu_next。

纯核输出只有 m/s² 加速度纠偏，nu单位相同；epsilon为m/s；没有FF、质量、重力、rate的g、推力或PWM。包内e=−s，nu物理符号不变。输入补偿已代数消元，不实际执行先加再减h*nu，避免大状态消掉小误差。正s/零nu产生负纠偏，NED各轴同一符号约定。

内层求根保留 RI00 线性分支；外层改用等价有理化/缩放式：

~~~text
A=h*lambda1, B=h*(h*lambda2), C=abs(s)−B
r = C / (hypot(A/2, sqrt(C)) + A/2)
p = sign(s)*r²
~~~

它等于2C/(sqrt(A²+4C)+A)，但避免A²、4C、2C和相近根相减。不是新的控制算法。极端仍可能在A/B、内层分母、最终r²/输出等处超出float域，因此明确拒绝，不承诺全有限输入可计算。

一个实际审查修复：float b与根的独立舍入可能使内层算出的p略大于epsilon。不能直接令rho=p/epsilon而产生|rho|>1；求根后按实际p重新形成rho=sat(p/epsilon)、Psi(p)，并增加典型8/12ms在内的360个有符号边界邻点检查。branch记录选择的求根分支，不冒充无限精度p的层归属。

## 2. 明确数值域，不静默冲零

- lambda1/lambda2须finite positive normal；epsilon∈[.001,1]，无epsilon=0回退；未配置仍拒绝。
- 纯核dt须finite positive normal，不做clamp。物理sample窗[.002,.04]s仍属于未来适配器；单测中的更大dt是算术反例，不是飞行资格。
- 非零误差、根、形状、增量、相关中间乘积和最终非零输出/状态不得为subnormal或消失为零；溢出/NaN/Inf拒绝为NumericalError，evaluate不改状态。错误候选不能提交。
- s精确为0时不计算无用h*gain，p/形状/增量精确0，保留非零旧nu作为本步输出。显式保持零例外不等于把小误差设死区。
- 正常delta加到很大nu后因float加法舍入无变化，是普通有效位舍入；不混称乘法下溢。

这一可用域比来源包宽松接受subnormal的策略窄。零扰理想对象可能在误差极小后耗尽正常量域；按执行前规格记录提前拒绝和状态保持，不把它写成完整60秒成功、不悄悄加死区。RI02要验证该状态如何进入公共故障处理，RI01不因此开放任何安全接管路径。

double参考使用单调二分和直接重算的隐式残差，不调用生产根函数或复制解析根式。独立对象分别推进float核和double参考的状态；保存CSV只作来源fixture核对，不是本次MATLAB重跑。

## 3. 三轴、身份与提交

每轴有独立参数、nu以及config/reset/state三种64位代次。成功设置同值参数、reset回同值也使旧候选失效。配置变更不偷偷清nu；是否需要清状态由调用方明确reset，未来模式交接由RI02处理。

候选绑定owner地址和每实例唯一ID；实例ID以饱和原子计数生成，使同一内存地址析构重建后旧候选仍无效。禁止拷贝/移动控制器。公开诊断浮点载荷、轴、branch及三种代次均与私有密封副本逐位核验。此为防意外篡改/误用的类型接口，不是对任意内存破坏的密码学防护。

evaluate只产生候选，commit改变nu；同一候选或同代次兄弟候选一旦提交便全部失效。另一轴提交不影响本轴候选。

commitProtected只导入调用方明确裁决的finite normal-or-zero状态；**不回算当前理想输出**。commitBatch对mask、各轴身份和所有应用状态先整体校验，末轴不合格不改变前轴。它没有限幅、HTE或接管决策，因此不是提前执行RI02。状态被外部冻结/限制后，不能称applied值满足原隐式关系。

代次不允许回绕。全局void reset若无法增代次，则永久锁定该实例，不能再次configure复活未清状态；实例ID耗尽时不能配置。计数饱和路径仅代码审查，未冒称动态跑完2^64。单轴bool reset失败返回false且不变。

本核没有真实timestamp或armed状态：事务防重复提交不等于独立阻止“同一sample重新evaluate再提交”。真实sample生命周期、armed参数、HTE、Z/XYZ seed、故障/termination须在RI02适配/回归后才可接入。

## 4. 构建、性能和回归边界

只有新类三文件及PositionControl/CMakeLists的测试条件块进入本阶段控制源码改动。原PID/ESTA/R-STA/Proper算法、选择器、模块、参数、消息、模型不变。验证包括旧算法/PositionControl/ControlMath/Takeoff/Rate及参数/模块测试，实际固件重建、生产编译数据库和符号表无新核。

C++14严格独立编译之外，还使用项目真实CMake编译选项。项目-Wfloat-equal/-Wdouble-promotion以显式转换和fabs精确零检查适配，不关闭告警、不加误差阈值。

实例ID原子64位计数、hypot和诊断字段的未来板级代价未测试；这里是宿主离线实现。不能以SITL编译或主机测试时长宣称硬件实时性、WCET或飞行稳定性。
