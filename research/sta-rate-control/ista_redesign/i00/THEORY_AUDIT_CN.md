# I00：公式、代码与理论边界审计

2026-09-18。对象是已有 ESTA/原 ISTA；Proper-ISTA 仅固定下一阶段的数学规格，本阶段未实现它。

## 1. 资料与版本

| 资料 | 固定版本与定位 |
|---|---|
| 原论文，本地 `BBSTA.pdf` | HAL `hal-02336599v1`，2019-10-29 提交；首页列 IEEE TAC 2020, 65(8), 3707–3713，DOI `10.1109/TAC.2019.2953091`。本机 PDF 含高亮/注释，依据该确切文件，不假称最终出版 PDF |
| 原论文文件 SHA-256 | `373f1b7ad7d745935d08230f21407ce62f517370d28301f428552d20620446f1` |
| 原 MATLAB | 仓库 `/home/yr/Downloads/MATLAB-ISTA`，HEAD `ac400f89ab1455dd0ef5121532c0af87ff9d0ae7`，工作区干净；`email_to_author/code/ISTA.m`、`ESTA.m` |
| 本地算法总结 | `SUPER_TWISTING_FAMILY_CN.md`，勘误前全文另存 `sources/SUPER_TWISTING_FAMILY_CN.pre_I00.md`；历史内容保留 |
| 新论文 | Seeber & Andritsch，[arXiv:2406.16094v1 PDF](https://arxiv.org/pdf/2406.16094v1)，封面标 2024-06-23，页脚标 2024-06-25；本审计固定 PDF，不使用网页动态编号 |
| 新论文 PDF SHA-256 | `9aa4a20ef2a0f562cfad897e18cb8db96cf174fd332592bb2887e19ddafdd73b` |

新论文在线 HTML 与所下载 PDF 的定理编号展示不同：本计划以后采用 **PDF Theorem 3.1/3.4、公式 (11)–(13)/(15)**，不得混称 HTML 的 Theorem 3/6。没有核对最终出版全文与该预印本逐字相同，后续如果换文献版本应单独说明差异。

两份 PDF 的相关完整页面已渲染目视核对；文本抽取仅用于检索。PDF 原件/渲染放外部证据目录，不将第三方论文整篇纳入 Git。原 MATLAB 源码小型快照只作来源审计，未用 MATLAB/Octave 执行。

## 2. 统一物理量和下标

在固定参考、单轴、近工作点的理想模型中，`s_dot = g*c + d = a+d`。跟踪任务实际有效扰动还含 `-rate_sp_dot`、模型失配和耦合；量纲和假设必须随之核验。

| 数学量 | 本仓库量 | 单位/含义 |
|---|---|---|
| x 或 x1,k | s=rate-rate_sp | rad/s；与原 PID 的误差符号相反 |
| u_k | a_k | rad/s²，虚拟角加速度，不是直接的归一化指令 |
| v_k 或 nu_k | 更新前内部状态 nu_before | rad/s² |
| v_(k+1) | nu_candidate；无保护时提交 nu | rad/s²；下一步旧状态 |
| T 或 h | 本次真正更新的 dt | s；非 callback 次数或夹限前后含糊值 |
| k1/k2 | lambda1/lambda2 | (rad/s²)/sqrt(rad/s)、rad/s³ |
| g | 已标定输入增益 | rad/s²/单位归一化力矩；g>0 |
| c | a/g | 归一化力矩；并非电机实际力矩 |
| dbar_k | 一段的扰动平均值 | rad/s²；精确 ZOH 对象不能随意以段末值代替 |

`a` 在本项目表示角加速度；原 MATLAB 的局部变量 `a=h*lambda1` 只是求根中间量，应在移植说明中叫 alpha，避免重名误解。

## 3. 原 ISTA 数学—源码对照

以下源码路径相对仓库，均为审计起点 d45383a419… 的版本。

| 规则 | 来源 | 实现位置 |
|---|---|---|
| virtual_s=s+h*a | 原 PDF 公式 (7)，物理第5页/印刷第4页 | `src/modules/mc_rate_control/StaRateControl/IstaRateControl.cpp:72` 起；舍入后校验在 :129 |
| a=-lambda1*sqrt(abs(virtual_s))*xi+nu_next；nu_next=nu-h*lambda2*xi | 原 PDF (8)/(10) | `IstaRateControl.cpp:93` 起；原 MATLAB ISTA.m 三分支 |
| b=-s-h*nu，q=h²*lambda2 | 原 PDF (11) 后定义 | `IstaRateControl.cpp:83` |
| abs(b)≤q：virtual_s=0，nu_next=a=-s/h | 原 PDF 算法 case 2，物理第6页/印刷第5页 | `IstaRateControl.cpp:93–99`；MATLAB `elseif` |
| 外分支求根与 xi=±1 | 原 PDF 算法 case 1/3 | `IstaRateControl.cpp:101–113`；C++ 使用等价有理化根 |
| 映射 c=a/g，验证全部结果后一次提交 | 项目量纲与原子性约定 | `IstaRateControl.cpp:116–145` |
| ESTA 旧 nu 输出，随后推进 nu | 原 MATLAB ESTA.m | `StaRateControl.cpp:71–94` |
| 保护后改变 nu 与输出 | 非原论文控制律 | `StaProtection.cpp:153–200`：MODE2 替换候选的加性 nu，再限幅 |

原 PDF case 3 的 else-if 印作 `b>-h²lambda2`，但它位于 case1、case2 之后，剩余域实际是 `b>+h²lambda2`；MATLAB 使用 else，C++ 先判断中间区后选正负，三分支域一致。本轮没有因该排印文字改变程序。

已核对的差异是数值工程处理，不是数学算法替换：C++ 有理化消减、double 中间量、float 状态/结果、有界表示与方程残差检查；MATLAB 直接根号相减。不能把独立 Python/C++ 对照写成 MATLAB 已运行。

## 4. 恒定扰动的平衡点：本项目的直接推导

控制器理想预测 `z=s+h*a`，真实对象 `s_next=s+h*(a+d)`。设 d 为恒定非零量，取

`s*=h*d, nu*=-d, a*=-d, xi*=0, z*=0`。

逐项代入可得：`b=-s*-h*nu*=0`，进入中间区；`nu_next=-s*/h=-d`，`a=-d`；真实对象 `s_next=h*d`。所以这是原控制器—对象的精确平衡点，任意正 lambda1/lambda2 都不改变它。量纲 `h*d` 正确为 rad/s。

这证明**原实现存在 O(h) 的受扰实际误差平衡点**，不是证明任意受约束飞行都会到达它。有限案例中的到达由本次测试给证据，不以测试代替全局证明。改变 lambda 仍会影响过渡、噪声和稳定性，但不能从这个平衡公式中消去偏差。

对线性扰动采用精确平均 `dbar_k=d0+m*(t_k+h/2)`。可核对的不变轨迹为

`s_k=h*dbar_(k-1), a_k=-dbar_(k-1), nu_k=-dbar_(k-2)`。

此时 `xi=m/lambda2`，当 `|m|≤lambda2` 可留在中间分支，真实 `s_next=h*dbar_k`。这个构造解释为什么“扰动变化率有界”不等于原形式可消除不断增长的扰动误差。实际有限运行仍按自身初值独立积分，未强制赋值为该轨迹。

## 5. §5.6 勘误及与旧论文关系

旧总结把有扰动时 h² 的表述概括过宽，须补全条件。原 PDF Definition 1 的离散滑动面是 **(virtual_s,nu)=(0,0)**，不只是 virtual_s=0。Lemma 4 以状态此前持续属于该集合为条件；紧随段落明确没有证明受扰时该集合的不变性、渐近可达性或有限步可达性。

上面的恒定扰动平衡点在 d≠0 时有 nu=-d≠0，**不满足该集合条件**，因此不能引用 Lemma 4 把真实 s 称为一般 O(h²)。也不能把“扰动导数 Δ=0”混同“扰动本身 phi=0”。无扰动结论要明确 phi=0 及相应增益/模型条件。

勘误还限定旧总结对“大步长通常更好”的概括：特定理论/仿真中的数字抖振优势，不等于 PID/ESTA/ISTA 的真实 RMSE、起降安全或全部工程指标排序。M10、OPT01/OPT02 的历史数据与排名不变。

## 6. I01 固定的数学规格（本阶段未实现）

下一阶段只考虑上述固定 PDF 的**无执行器约束 Proper Implicit**，不是其 conditioned 饱和变体。式 (11a)/(12)：

`z_next=s+h*(a-nu_next)`

`a=-lambda1*sqrt(abs(z_next))*xi+2*nu_next-nu`

`nu_next=nu-h*lambda2*xi, xi in Sgn(z_next)`。

Theorem 3.1 的式 (13) 可解析实现；Theorem 3.4 的充分条件为 `lambda2>L`、`lambda1>sqrt(lambda2+L)`，固定 h、单位虚拟输入通道、精确 ZOH、Lipschitz 匹配扰动。其受扰误差界不能自动扩展到滤波噪声、模型 g 失配、电机滞后、接触、变步长或项目裁剪/冻结。[固定 PDF](https://arxiv.org/pdf/2406.16094v1)

I01 应重新推导解析式与数值稳定实现、验证隐式残差和独立对象；本报告不提供未经测试的飞控替换文件。I02 需另核对新形式中的 `2*nu_next-nu` 与旧保护输出重算的关系，不能机械复用。论文执行器饱和处理不等于触地状态检测，两者也不是本阶段已修复。

## 7. 不支持的结论

- 没有证明偏差是 M10 所有失败或全部误差的唯一原因。
- 没有证明 Proper-ISTA 在项目上已消除偏差或优于 ESTA；新算法一次也未运行。
- 没有通过更换主指标、去均值或选日志改写原论文实验。
- 没有新 SITL/实机/MATLAB 测试，没有更换原 MODE=2 的含义。
