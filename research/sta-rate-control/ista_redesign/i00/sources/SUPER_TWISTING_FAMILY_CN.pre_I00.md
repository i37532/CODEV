# Super-Twisting、ESTA 与 ISTA 算法总结

> 原始资料目录：`/home/yr/Downloads/MATLAB-ISTA`
>
> 整理目标：为后续替换 CODEV/PX4 多旋翼控制算法提供经过核对的公式和参考实现
>
> 主要论文：Brogliato, Polyakov, Efimov, *The implicit discretization of the super-twisting sliding-mode control algorithm*, IEEE TAC, 2020

## 1. 最重要的结论

这三个名字不是三套互不相关的控制理论：

1. **Super-Twisting Algorithm（STA）**是连续时间二阶滑模控制律。
2. **ESTA**是 STA 控制器的显式欧拉离散化。
3. **ISTA**是 STA 控制器的隐式离散化；论文给出了无需数值迭代的三段解析计算方法。

三者应在相同的滑模变量、对象模型、采样周期、扰动和输出限制下比较。源目录中的 `compare_all.m` 没有满足这一点，因为它调用的根目录 `ESTA.m` 并不是论文定义的显式 ESTA。

## 2. 研究对象和符号

论文考虑单位输入增益的一阶对象：

$$
\dot{x}(t)=u(t)+\phi(t),\qquad \dot{\phi}(t)=\Delta(t),
$$

其中：

- $x$：要压到零的标量状态或滑模变量。
- $u$：控制输入。
- $\phi$：匹配扰动，即与控制输入从同一通道进入系统的扰动。
- $\Delta=\dot\phi$：扰动变化率，论文假设 $|\Delta(t)|\le L$。
- $\nu$：STA 内部状态，用于逐步补偿匹配扰动。
- $\lambda_1>0,\lambda_2>0$：控制增益。
- $h>0$：数字控制器采样周期。

论文还定义不可测组合状态 $x_2=\nu+\phi$，使闭环写成：

$$
\begin{aligned}
\dot{x}_1 &=-\lambda_1\sqrt{|x_1|}\operatorname{sgn}(x_1)+x_2,\\
\dot{x}_2 &\in-\lambda_2\operatorname{sgn}(x_1)+\Delta(t).
\end{aligned}
$$

理论中的符号函数是集合值函数：

$$
\operatorname{sgn}(x)=
\begin{cases}
+1,&x>0,\\
[-1,1],&x=0,\\
-1,&x<0.
\end{cases}
$$

普通程序语言的 `sign(0)=0` 只是集合值符号函数在零点的一种选择。ISTA 的中间分支显式处理了 $[-1,1]$，这是它消除数字抖振的关键之一。

## 3. 连续时间 Super-Twisting

### 3.1 控制律

$$
\boxed{
\begin{aligned}
u(t)&=-\lambda_1\sqrt{|x(t)|}\operatorname{sgn}(x(t))+\nu(t),\\
\dot\nu(t)&\in-\lambda_2\operatorname{sgn}(x(t)).
\end{aligned}}
$$

第一项根据误差大小提供非线性校正，第二项通过内部状态补偿持续的匹配扰动。虽然 $\dot\nu$ 不连续，但 $u$ 本身通常比一阶滑模的直接开关控制更连续，因此抖振较弱。

### 3.2 参数作用

- $\lambda_1$ 增大通常会提高到达速度，也会提高瞬态控制幅值和噪声敏感度。
- $\lambda_2$ 决定 $\nu$ 的变化速率和扰动跟踪能力；过小无法覆盖扰动变化，过大会增加数字实现中的振荡趋势。
- 增益有物理量纲，取值依赖 $x$ 和 $u$ 的单位、对象输入增益及时间尺度，不能跨对象直接复制。

论文 Lemma 1 给出一个较保守的充分条件，用于保证所需的光滑 Lyapunov 函数存在：

$$
\lambda_1>\sqrt{4\sqrt{2}L},\qquad
L<\lambda_2<\frac{\lambda_1^2}{2\sqrt{2}}-L.
$$

这不是唯一调参方法，也不能跳过对真实飞行器输入增益、惯量和扰动界的处理。

### 3.3 源代码位置

- `/home/yr/Downloads/MATLAB-ISTA/SuperTwisting.m`
- `/home/yr/Downloads/MATLAB-ISTA/2fig4、5+supertwisting/SuperTwisting.m`

两个文件内容相同。它们用 `ode45` 在每个外部步长内同时积分 $x$ 和 $\nu$，把 $\phi$ 在该小区间内保持为常数。这适合作为数值参考，不是可以直接放进 PX4 高频回调中的实时控制器。

本目录将“控制律”和“数值积分器”分开，控制律见 `matlab/sta_continuous.m`。

## 4. ESTA：显式欧拉离散 STA

### 4.1 控制律

使用当前采样点 $x_k,\nu_k$ 直接计算：

$$
\boxed{
\begin{aligned}
u_k&=-\lambda_1\sqrt{|x_k|}\operatorname{sgn}(x_k)+\nu_k,\\
\nu_{k+1}&=\nu_k-h\lambda_2\operatorname{sgn}(x_k).
\end{aligned}}
$$

论文仿真中的对象也用显式欧拉离散：

$$
x_{k+1}=x_k+h(u_k+\phi_k),\qquad
\phi_{k+1}=\phi_k+h\Delta_k.
$$

### 4.2 特点

- 每步只需一次绝对值、平方根、符号判断和积分更新。
- 因为只使用当前量，因果性和实时实现都很直接。
- 显式离散会引入数字极限环。即使连续 STA 能有限时间收敛，ESTA 在零附近也可能保持非零振荡和控制抖动。
- 步长越大，离散误差和数字抖振通常越明显；稳定性不能仅由连续时间结果保证。

### 4.3 经过核对的源代码

论文定义对应以下文件：

- `/home/yr/Downloads/MATLAB-ISTA/email_to_author/code/ESTA.m`
- `/home/yr/Downloads/MATLAB-ISTA/1原论文fig4、5/ESTA.m`
- `/home/yr/Downloads/MATLAB-ISTA/2fig4、5+supertwisting/ESTA.m`

它们的核心都是：

```matlab
u_k = -lambda_1 * sqrt(abs(x_k)) * sign(x_k) + nu_k;
nu_k_plus_1 = nu_k - h * lambda_2 * sign(x_k);
```

本目录统一实现见 `matlab/esta_step.m` 和 `cpp/sta_algorithms.hpp`。

## 5. ISTA：隐式离散 STA

### 5.1 隐式定义

ISTA 不在未知的真实 $x_{k+1}$ 上预知扰动，而是引入不含扰动的虚拟下一状态：

$$
\tilde{x}_{k+1}=x_k+h u_k.
$$

控制器定义为：

$$
\boxed{
\begin{aligned}
u_k&=-\lambda_1\sqrt{|\tilde{x}_{k+1}|}\,\xi_{k+1}+\nu_{k+1},\\
\nu_{k+1}&=\nu_k-h\lambda_2\xi_{k+1},\\
\xi_{k+1}&\in\operatorname{sgn}(\tilde{x}_{k+1}).
\end{aligned}}
$$

看起来含有未知的 $\tilde{x}_{k+1}$，但论文证明对任意有效数据解唯一，并推导出下面的三段解析算法，不需要固定点迭代或优化求解器。

### 5.2 公共中间量

定义：

$$
b_k=-x_k-h\nu_k,\qquad a=h\lambda_1,\qquad q=h^2\lambda_2.
$$

### 5.3 Case 1：$b_k<-q$

此时 $\xi_{k+1}=+1$，$\tilde{x}_{k+1}>0$：

$$
r=\sqrt{|\tilde{x}_{k+1}|}
=\frac{-a+\sqrt{a^2-4(b_k+q)}}{2},
$$

$$
\nu_{k+1}=\nu_k-h\lambda_2,\qquad
u_k=-\lambda_1r+\nu_{k+1}.
$$

### 5.4 Case 2：$|b_k|\le q$

这是隐式算法的离散滑动区：

$$
\xi_{k+1}=-\frac{b_k}{q}\in[-1,1],\qquad
\tilde{x}_{k+1}=0,
$$

$$
\nu_{k+1}=-\frac{x_k}{h},\qquad
u_k=\nu_{k+1}.
$$

因此 $x_k+h u_k=0$。在无扰动条件下，论文证明到达离散滑动面后能保持零输入、零数字振荡。

### 5.5 Case 3：$b_k>q$

此时 $\xi_{k+1}=-1$，$\tilde{x}_{k+1}<0$：

$$
r=\sqrt{|\tilde{x}_{k+1}|}
=\frac{-a+\sqrt{a^2+4(b_k-q)}}{2},
$$

$$
\nu_{k+1}=\nu_k+h\lambda_2,\qquad
u_k=\lambda_1r+\nu_{k+1}.
$$

### 5.6 理论结论应如何准确表述

- 无扰动时，论文证明该隐式离散闭环全局渐近稳定，并在有限步内到达不变的离散滑动面。
- 有扰动时，论文给出了滑动面内 $x$ 的 $h^2$ 量级精度描述和仿真优势，但明确说明没有证明受扰情况下的有限步到达性质。
- 因此不应写成“ISTA 在所有扰动和任意步长下必然有限时间精确收敛”。

### 5.7 源代码位置

解析三段式实现位于：

- `/home/yr/Downloads/MATLAB-ISTA/email_to_author/code/ISTA.m`
- `/home/yr/Downloads/MATLAB-ISTA/1原论文fig4、5/ISTA.m`
- `/home/yr/Downloads/MATLAB-ISTA/3原论文fig6、7/ISTA.m`
- `/home/yr/Downloads/MATLAB-ISTA/ISTA.m`（增加了判别式数值保护和 `xi` 输出）

本目录的统一实现为 `matlab/ista_step.m` 和 `cpp/sta_algorithms.hpp`。

## 6. 三种方法对比

| 项目 | 连续 STA | ESTA | ISTA |
|---|---|---|---|
| 本质 | 连续控制律 | 显式欧拉离散 | 隐式离散 |
| 当前步使用 | 连续 $x(t),\nu(t)$ | $x_k,\nu_k$ | $x_k,\nu_k$ 解析求虚拟下一状态 |
| 单步计算 | 连续求解；仿真需积分器 | 最低 | 稍高：分支 + 最多一次平方根 |
| 是否需要迭代求解 | 理论控制律不需要 | 不需要 | **论文解析实现不需要** |
| 零点符号处理 | 集合值微分包含 | 程序通常取 `sign(0)=0` | 中间分支显式选 $\xi\in[-1,1]$ |
| 数字抖振 | 取决于实现/执行器 | 通常最明显 | 论文中显著更小 |
| 大步长表现 | 取决于数值积分 | 容易退化 | 通常优于 ESTA |
| PX4 可直接实时运行 | 不能使用 `ode45` | 可以 | 可以 |

`ode45` 结果只是连续系统的数值基准，不能笼统称作“数值稳定性最好且无步长限制”。任何数值积分都有容差和步长，真实飞控也必然是采样系统。

## 7. 原 MATLAB 文件夹代码审计

### 7.1 根目录 `ESTA.m` 名称与实现不一致

文件 `/home/yr/Downloads/MATLAB-ISTA/ESTA.m` 的注释称其为隐式方法，并用最多 20 次固定点迭代预测 `sign(x_next)`。它：

- 不是论文的显式 ESTA；
- 也不是论文给出的解析三段式 ISTA；
- 预测时忽略了 $\phi$；
- 在符号函数切换附近可能来回跳变，且达到 `max_iter` 后没有报告未收敛。

所以根目录 `compare_all.m` 调用这个文件时，“ESTA”曲线不能代表论文的 ESTA。

### 7.2 `SuperTwisting.m` 的比较口径

该函数用 `ode45` 返回区间末端的 $x_{k+1},\nu_{k+1}$，而 `compare_all.m` 记录的是区间起点计算的 $u_k$。这不一定错误，但必须解释为零阶保持扰动下的连续参考轨迹，不能与固定周期数字控制器的每步 CPU 成本直接比较。

### 7.3 指标索引不统一

不同脚本有时用：

$$
e_k=|x_{k+1}|+\nu_k^2,
$$

有时用：

$$
e_k=|x_{k+1}|+\nu_{k+1}^2.
$$

这会改变图线细节。论文定义图示指标为 $e_k=|x_{1,k}|+\nu_k^2$；对比时必须统一状态时间索引。

另外，$e_k$ 在论文中称为 homogeneous norm/regulation error。它不是文中稳定性证明所构造的严格 Lyapunov 函数，不应直接把它称为“论文的李雅普诺夫函数”。

### 7.4 收敛时间指标需要“保持条件”

根目录 `compare_all.m` 用首次满足 $|x|<0.01$ 的样本作为收敛时间。振荡轨迹可能进入阈值后又离开。更合理的指标是首次进入阈值且之后连续保持，或者要求至少保持固定窗口。

## 8. 示例参数与含义

论文 Fig. 4～7 和源脚本主要使用：

| 参数 | 数值 | 含义 |
|---|---:|---|
| $\lambda_1$ | 10 | 根号误差项增益 |
| $\lambda_2$ | 6 | 内部状态变化率增益 |
| $x_0$ | 10 | 初始状态 |
| $\nu_0$ | 10 | 内部状态初值 |
| $\phi_0$ | 0 | 匹配扰动初值 |
| $T$ | 5 s | 仿真时长 |
| $h$ | 0.001 s、0.1 s | 无扰动步长对比 |
| $\Delta(t)$ | $2(1+\sin(2t^2))$ | 受扰仿真的扰动变化率 |

注意 $\Delta(t)=2(1+\sin(2t^2))$ 虽然幅值在 $[0,4]$，频率随时间提高；在论文有限的 5 秒仿真区间内可用 $L=4$ 作为幅值界。此处 $\phi$ 是对 $\Delta$ 的积分，不应把 $\Delta$ 直接加到对象状态更新中。

## 9. 为 PX4 移植做准备

### 9.1 最合适的第一接入点

第一阶段建议替换多旋翼**角速度内环**，而不是位置环。当前 CODEV/PX4 位置是：

```text
/home/yr/Desktop/Codev-autopilot/
src/modules/mc_rate_control/RateControl/RateControl.cpp
RateControl::update()
```

这里已有：

- 角速度设定值 `rate_sp`；
- 实际角速度 `rate`；
- 角加速度 `angular_accel`；
- 实际采样间隔 `dt`；
- mixer saturation 反馈；
- 解锁、落地时积分状态重置机制。

### 9.2 论文对象和无人机角速度对象不是同一个量纲

单轴旋转动力学近似为：

$$
J\dot\omega=\tau+d.
$$

若定义 $x=\omega-\omega_{sp}$，则忽略设定值快速变化时：

$$
\dot x=\frac{\tau}{J}+\frac dJ-\dot\omega_{sp}.
$$

STA 计算的 $u$ 更接近角加速度指令，而不是 legacy PX4 的归一化力矩输出。合理映射至少需要考虑惯量 $J$、电机/桨推力模型、陀螺耦合项、设定值前馈和输出饱和。

PX4 源码中的 `rate_error = rate_sp - rate` 与上面建议的 $x=rate-rate_{sp}$ 符号相反。直接把 `rate_error` 代入论文公式会把负反馈变成正反馈；必须统一误差和输出符号。

仓库中的可选模块：

```text
src/modules/angular_velocity_controller/AngularVelocityControl/
src/modules/control_allocator/
```

已经包含惯量矩阵和 $\omega\times J\omega$ 刚体耦合补偿，从物理量角度可能比 legacy `actuator_controls_0` 路径更适合作为后续 STA 力矩控制实验的基础，但 CODEV 默认固件目前没有启用这条路径。

### 9.3 实时实现必须增加的工程处理

- 每个轴维护独立的 $\nu_x,\nu_y,\nu_z$。
- disarm、落地、控制模式退出、传感器异常和长时间 `dt` 中断时重置内部状态。
- 对 `dt` 做有效范围检查。论文证明基于固定 $h$；用逐步变化的 `dt` 虽能计算，但理论保证不能直接照搬。
- 把执行器饱和反馈作用到 $\nu$，避免类似积分 windup。
- 限制 $u$、$\nu$ 和每周期输出变化率。
- 评估角速度和角加速度滤波延迟；`sign` 与噪声结合会引发高频切换。
- 若给 ESTA 加 `sat(x/epsilon)` 边界层，要明确它已变成近似算法，不能再引用原 ISTA 的精确离散滑动结论。
- 绝不能将论文示例 `lambda1=10, lambda2=6` 不经量纲变换直接用于真机。

## 10. 后续 PID/STA/ESTA/ISTA 公平对比方案

后续在 Gazebo 中至少应保持以下条件一致：

- 同一机体、质量、惯量、电机模型和电池模型；
- 同一角速度设定值与轨迹整形；
- 同一输出上下限、slew rate 和 mixer；
- 同一传感器噪声、滤波和控制频率；
- 同一初始条件和扰动注入；
- 每种控制器单独保存内部状态并正确 reset。

建议记录：

| 指标 | 说明 |
|---|---|
| RMSE / MAE | 角速度或姿态跟踪精度 |
| IAE | $\sum |e_k|h$ |
| 超调与稳态误差 | 阶跃响应质量 |
| 2% settling time | 进入后保持在误差带内 |
| RMS/峰值控制量 | 执行器负担 |
| Total Variation | $\sum|u_k-u_{k-1}|$，衡量数字抖振 |
| 饱和占空比 | 输出到达限制的时间比例 |
| 最坏执行时间 | 飞控实时性 |
| 抗扰恢复时间 | 阵风/力矩扰动后的恢复能力 |

第一轮建议四组控制器：PX4 原 PID、连续 STA 数值基准、ESTA、ISTA。连续 STA 只作为离线/SITL 高精度参考，不作为飞控上的 `ode45` 实现。

## 11. 本目录参考代码设计

### MATLAB

- `sta_continuous.m`：只给连续控制律和 $\dot\nu$，不隐藏积分器。
- `esta_step.m`：严格按显式公式单步更新。
- `ista_step.m`：严格按论文三分支解析更新，并输出分支和虚拟状态便于测试。
- `compare_three.m`：统一索引与评价指标；连续 STA 用更细 RK4 子步作为数值基准。

### C++

`cpp/sta_algorithms.hpp` 与当前 CODEV/PX4 的 C++14 标准兼容，并使用：

- 固定大小标量结构；
- 无动态内存；
- 无异常；
- 输入合法性标志；
- ISTA 分支和虚拟状态诊断输出。

它仍是“算法参考代码”，不是已经完成 PX4 安全机制、参数系统、日志和 mixer 反馈集成的飞行代码。

## 12. 核对资料与版本快照

本总结按以下优先级解决公式或代码冲突：论文原文、论文对应子目录的复现代码、根目录的便捷脚本。主要核对资料为：

- `/home/yr/Downloads/MATLAB-ISTA/BBSTA.pdf`：论文正文，是算法定义和理论结论的首要依据。
- `/home/yr/Downloads/MATLAB-ISTA/email_to_author/README.pdf`：复现文件说明。
- `/home/yr/Downloads/MATLAB-ISTA/email_to_author/Questions_on_Reproducing_Figures_4_to_7.pdf`：复现论文图 4～7 时整理的问题。
- `/home/yr/Downloads/MATLAB-ISTA/email_to_author/code/`：与论文公式一致的 ESTA/ISTA 基准代码。

检查时源仓库位于 `main` 分支，Git 提交为 `ac400f89ab1455dd0ef5121532c0af87ff9d0ae7`（`ac400f8 english version`）。以后若源目录更新，应先比较提交差异，再决定是否更新本文和参考实现。
