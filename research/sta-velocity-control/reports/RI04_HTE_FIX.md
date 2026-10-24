# RI04：HTE 与状态限幅交接的离线修复

2026-10-24。**离线修复验收通过，已完成全量回归和 SITL 构建。原 RI04 仍 failed/needs_revision，Z 飞行门尚未验收。** 本次新飞行、种子和预算均为 0，没有续跑原批次、调参、push 或进入 RI05。

## 1. 问题和修复范围

入口分支 `research/ista-velocity-regularized`，HEAD `50f354678fafb3fd4d4a09530e340f0eefa60f55`；工作区干净，33 个递归子模块匹配且内部干净。已完整阅读三份专项计划/共同规则与进度、RI04 停批报告和 RI02 保护契约，并复核相关生产调用链。旧冻结快照、旧协议、旧失败判决不修改；本次规则修订单独存于 [CONTRACT_CN.md](../regularized_ista/ri04_hte_fix/CONTRACT_CN.md)。

原 RI04 第 3 轮在 Z 接管后，ν 到达 −4 的状态限幅。状态保护没有改变该拍实际加速度纠偏，但旧缓存条件把所有 StateLimit 事务一概标为不可用于 HTE。收到首个有效悬停推力估计 .7190654278、拟由 .5 更新时，HTE 因缓存无效被拒绝并锁存故障，旧值仍为 .5。这是状态限幅与 HTE 的组合处理缺口，不是由日志验收规则造成。

唯一生产行为改动位于 `PositionControl::_recordRistaDiagnostic`：**仅 StateLimit 不再单独使 HTE 缓存失效**。继续使用成功、闭合事务的真实已应用纠偏及 FF；不从限幅后的 ν 重新计算上一拍输出。

保留原有 CorrectionLimit、OutwardFreeze、下游约束、Latched、过期 sample/配置代次、失效生命周期的拒绝；`shiftZ` 的有限数、活动/闭合状态及变换前后输出、ν 边界仍全部先检查、再一起提交。不可行变换仍锁存故障，不靠扩大限幅或强制裁剪“变为可行”。

未修改隐式控制律、HTE 公式、seed、保护数值阈值、参数默认值、PID/R-STA 路径、位置/姿态/rate 环、准入轴、DIV、日志结构、估计器、land detector 或模型。默认仍 PID，SITL R-ISTA 仍只可选择 AXES1/4；“可选择 Z”仍不等于 Z 飞行合格。

## 2. 输出与状态必须分开

理想当拍输出使用候选状态，而限幅决定提交后的状态：

```text
c = −lambda1 * Psi(p) + nu_candidate
nu_applied = clip(nu_candidate)
```

只有 StateLimit 时，c 本身没有被重算，且 c 与 nu_applied 都已知。HTE 仍沿用既有有界平移：

```text
delta = (H_old / H_new − 1) * (c + FF − g)
c_new = c + delta
nu_new = nu_applied + delta
H_new * (c_new + FF − g) = H_old * (c + FF − g)
```

该等式只证明**冻结上一拍输入与倾角几何时的未限推力映射连续**。它不是完整闭环稳定性证明，不保证下一拍实际推力不变，不把保护后的 ν 与 c 称为严格隐式解。旧 `strict_axes=0` 不改，旧 p/a_ideal/nu_candidate 诊断也不追写为新候选。下一拍按新的 s/h/FF 正常求解、提交一次。

原始边界的独立 double 方程求解为：c≈−4.0714249611、nu_applied=−4，HTE .5→.7190654278，delta≈4.2279969397，c_new≈.1565719786、nu_new≈.2279969397；都在原输出 ±6 与状态 ±4 内。C++ 使用 float 重力常量，允许浮点舍入差但不放宽工程边界。

## 3. 原始失败数据与独立参考

[fixture.py](../regularized_ista/ri04_hte_fix/fixture.py) 从原失败 ULog 只读提取，审计 helper 从历史结果 Git 对象加载；不要求旧飞行使用新修复源码，不重写旧源码绑定。

- 旧飞行源码 `74327418e18eafd421e18b48fe3964fdad63cfb5`，旧结果 `50f354678fafb3fd4d4a09530e340f0eefa60f55`。
- `06_07_48.ulg` SHA-256：`04bee85bf9fa20aaf42e29b0bcf9f0c4c5315caa4c7e89ceace9e63d860fdc0f`。
- `log001.ulg` SHA-256：`5fcc91abb13ed790995d6d2a05e9f8044c0fd22fb0401636c2f0dff9d086c378`。
- 414 个真实有效 Z 候选以独立 double 单调二分隐式求根核对，另核对真实 seed；最后有效 sample 43,064,000µs、h=8ms，首故障 sample 43,076,000µs。第一条有效 HTE 前有 22 条无效估计。
- C++ 使用小型 [recorded_hte_fixture.hpp](../regularized_ista/ri04_hte_fix/recorded_hte_fixture.hpp)，与由原始 ULog 数值重新生成的头文件逐字节一致；先自然积分到限幅，再重建最后有效控制边界与 HTE 更新。不是完整飞行轨迹重演，更不是新的接受飞行。模块测试的下一拍速度目标由已记录的轨迹 Z 与当前位置 Z 重建为代表输入，不是直接记录的首次调用 v_sp。
- 原故障帧的目标已被 failsafe 二次调用覆盖，不冒充第一次输入；原内部 abort 顺序仍是日志与源码共同支持的推断，不宣称存在未记录的调用栈。

ν 在真实起飞中为何较早到达限制，仍未完成系统因果验证。本次只解决可复现的 HTE 交接拒绝，不能由离线通过推断下一次起降必定通过。

## 4. 新增组合回归与真实红绿过程

新增 **13 个 C++ 用例**：PositionControl 7 个、真实 uORB 模块路径 6 个；旧测试保留。覆盖首次进入正负状态限幅、非零 FF/倾斜、8/12ms、重复 HTE、旧候选不重算、下一拍独立隐式参考、真实首个有效 HTE、XY PID、重复 sample、接触/重新起飞、disarm、termination 和拒绝锁存。

负例包括：仅 ν 越界、仅纠偏越界、两者同时越界、非有限/无效 HTE、错误 sample/配置代次、reset、StateLimit 与输出限幅/下游约束/外推冻结共现。拒绝后旧 ν/c/H 不部分更新，下一次 update 不允许发布。

所有尝试保存在新的外部根目录 `.../VELOCITY-RISTA-20261024/RI04_HTE_FIX`，不覆盖旧证据：

| 尝试 | 实际结果及退出码 |
|---|---|
| fixture01 | 缺 pyulog 依赖路径，exit1；没有称为解码成功 |
| fixture02 | 补齐既有 M00 依赖路径，实际解码及独立参考 exit0 |
| red01 | 新测试 double-promotion 编译告警视为错误，build exit1，未运行测试；修复显式类型转换 |
| red02（旧生产代码） | build0；Position 7 项全失败，Module 6 项中 5 失败，两个测试命令均 exit1；其中新负例过早检查尚未由 update 刷新的发布诊断，已修正测试检查时刻，不改生产时序 |
| red03（旧生产代码） | build0；Position 7 项中 3 个正常交接失败、4 个拒绝负例通过；Module 6 项中 5 失败/1 通过，两个测试命令 exit1，真实复现组合缺口 |
| green01（最小生产修复） | build0；Module 全 65 项通过/exit0；Position 22 项中 1 失败/exit1：新测试由加速度近似重建倾角漏掉 limitTilt 的小角度 float 舍入。改为冻结真实输出方向，不放宽误差容限、不改 ControlMath |
| green02 | build0；Position 全 22 项、Module 全 65 项通过，两个命令均 exit0；包含全部 13 新用例 |

旧代码红测与新代码绿测不是新飞行；不累计多次运行作为独立测试数量。原输出映射测试保留严格容限，下一拍更新另用独立求根核对。

## 5. 全量验证与复现

全量入口是 [verify.py](../regularized_ista/ri04_hte_fix/verify.py)，只生成离线证据：`approved=false`、`flight_authorized=false`、`new_flights=0`。从旧库存继承适用测试/回放，绑定当前修复文件与原模型/工具指纹；不调用旧飞行资格、freeze.capture、运行器或 gate_pass。

在仓库根运行（输出须为新的不存在目录）：

```bash
cd /home/yr/Desktop/Codev-autopilot
python3 -B research/sta-velocity-control/regularized_ista/ri04_hte_fix/verify.py \
  --output "/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI04_HTE_FIX/verification03"
```

脚本自行设置已有 Python 依赖路径，逐命令保存 argv/退出码/日志 SHA、gtest XML 和 Python 叶收据。包含 SITL 与 `DONT_RUN=1` Gazebo **仅构建**，不会起飞。未设置 PYTHONPATH 的入口 `--help` 另实际检查 exit0。

最终 `verification02/evidence.json`：**106 条真实命令全部 exit0**，独立收据再次读取实际 XML/叶日志，非零计数如下：

- **711 个唯一 C++ 用例／48 目标**：原 698＋新增 13。包含 PositionControl、ControlMath、Takeoff、RateControl、模块/参数与 PID/R-STA/旧 ESTA 等适用回归。
- **904 个 Python 用例／38 套**：原 872＋新夹具 22＋新验证器 10；另 **6 项独立 double 参考**通过。
- 独立对象仍为 102 轨迹、559827 有效更新：84 条完整 60s（含 6 条不可行限幅反例），18 条极小 float 数值域停止，不称全部收敛。3990 行来源 MATLAB R-ISTA fixture 只是已有数据比较，MATLAB 未重跑。
- 9 份历史接受日志完整回放一致；旧失败精确前缀与本 RI04 失败边界两项审计通过，**旧失败判决不变**。
- 严格 C++14、SITL、Gazebo 仅构建通过；selection/status 实际 ULog 格式为 1018/1475B（含 topic 名/NUL）、队列均 8，默认 PID 未变。
- 1082 项源码/资产输入及 33 子模块首尾一致。EEPROM 仍为 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，未产生新模拟飞行进程。

首轮 `verification01` 同样 106 命令全 exit0。最终审查仅把模块测试中的“原始首次输入”注释改为“根据日志重建的代表输入”，数值/控制代码未改；之后完整重新运行 `verification02`，精确绑定最终源码，**两轮不累加为独立样本数**。

最终证据 SHA-256：`12dc58701362cb96e9f7eced821d85679efbb8e0060c5570a38c848a63956f1b`。

修复固件 SHA-256：`061e2a374defd80a32476710b6d6dd78b71950b2532d051ba7e598e944a0c402`。它由入口 HEAD＋本次已核验补丁构建，**不是新干净提交上的飞行资格**。

原 RI04 完整归档独立核验 1880 文件/3 链接全部未变（审计 7 条检查命令全 exit0）；其新审计摘要 SHA 为 `946e42a9920e0d809441686e9e06a9c1500bf801e5d3125ffd6dc52f405ad9b9`。本次新证据 1609 文件索引另存 `RI04_HTE_FIX/archive_index.json`，SHA 为 `5e7e1dd566235fb679eed0d749572bbce5e340152057fa1c7e2921ef6e52da8c`。所有开发失败和红/绿尝试保留，未删除大日志。

仓库 [verification_summary.json](../regularized_ista/ri04_hte_fix/verification_summary.json) 保存上述路径、指纹、实际计数及三个生产/测试文件的新旧 SHA。独立只读审查未发现阻断；没有把审查者阅读叶证据描述为另一次独立测试运行。

## 6. 提交和后续条件

本次提交限定为 1 个生产缓存条件、2 个 C++ 测试文件、新离线契约/夹具/验证工具/结果摘要和本报告。旧 RI04 计划/manifest/资格/失败结果不改；外部三份实时文档另记本修复提交完整 SHA。报告不自嵌自身提交号，可用 `git log -1 --format=%H -- research/sta-velocity-control/reports/RI04_HTE_FIX.md` 查询。

下一批飞行前仍须另获用户对新有限批次的明确授权，并修订冻结：新干净源码/固件资格、准确清单/顺序/新种子与历史查重、参数/模型/分析器绑定及首败停止规则。不能直接续跑旧 6 轮、拼接不同源码结果或把原失败改为成功。本次不建立或执行该批次；RI04 总体仍未验收，RI05 前置未满足。

未执行：任何新飞行、MATLAB/Simulink 重跑、调参、新预算/种子登记、板级 CPU/实机验证、RI05、旧 R04/R05 或 push。
