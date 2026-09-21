# V03 — 前置验收审计：needs_revision

2026-09-21。本次停在 V02 前置复核，**V03 未完成**。原 V02 的 7 项测试重新编译运行后仍通过，
新增 3 项候选完整性验收探针全部失败；V02 报告对独立对象验证的表述也超过现有测试证据。
V02 当前准入状态修订为 needs_revision，保留原报告与已发布历史提交。依共同规则第 11 条，
不能将本次前置失败记为 V03 passed。不是 Gazebo、Python 或编译依赖缺失导致的 blocked。

## 分支、来源与范围

- 仓库：`/home/yr/Desktop/Codev-autopilot`，分支 `research/sta-velocity-control`。
- 起点及实际被审计内核：`3d7b5a0dfcf36be5ae678a76c9d8c1f0f52b3eba`，开始与 codev 跟踪分支同步。
  主仓库与递归子模块开始干净；增加本次审计工具后，只允许本次研究文件变化。
- 已完整阅读外部速度计划/共同规则、实时表和 V02 报告；首次 V00 已完成计划要求的旧研究资料阅读。
- 审计运行器逐字节比对 Git 中 V02 的内核、原测试、selector、PositionControl.cpp、CMake 注册；
  这些文件没有变化。审计新增的 C++ 文件未注册进默认构建，只由独立审计命令链接原内核。
- GCC 11.4.0、Gazebo Classic 11.10.2；递归版本保存在外部 submodules.log，Gazebo 子模块
  `822050a7ab6fd87972e59f16312f451bce217a56`。版本核对不代表运行了仿真。
- 生产 PositionControl/位置 P、Z 速度 PID、姿态/rate、估计器、land detector、模型、启动器、
  参数与消息没有修改。V01 selector 的 MODE=1 拒绝仍通过测试。

## 可运行复现

在仓库根执行下面命令，输出路径必须不存在。当前 V02 内核下预期进程退出 **1**，代表验收失败；
不能把这个预期失败当控制器通过。完整编译命令和退出码在 evidence.json，运行器会重新编译被测源。

```bash
python3 research/sta-velocity-control/scripts/audit_v03_preflight.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V03/reproduce-new'
```

本次实际目录为同级 `preflight01`、`preflight02`，没有覆盖原目录。

| 检查 | 实际结果 |
|---|---|
| preflight01 编译 | g++ 退出 1；与既有 gtest 静态库的 RTTI 选项不一致，0 项测试执行 |
| 修订运行器 | 与 PX4 测试依赖一致使用 `-fno-rtti -fno-exceptions`，保留首次失败日志 |
| preflight02 编译 | 退出 0，C++14、O2，从未修改的原内核/原测试源码构建 |
| preflight02 测试 | 退出 1；10 项实际测试，7 通过、3 失败、0 disabled |
| 原 7 项 V02 用例 | 全部通过；这不覆盖下面新增的接口情形 |
| 生产目录 diff、45 份证据 SHA 校验 | 退出 0 |

preflight01 的旧运行器遇到链接异常后留下 `status=in_progress`，应按其命令退出码解读为工具编译失败；
这个原始 JSON 未追改。preflight02 的实际判定为 needs_revision，不是仍在运行。

## 候选提交问题

根因在 `src/modules/mc_pos_control/PositionControl/StaVelocityControl.cpp:90` 的 commit：
它检查 status、轴范围、目标轴 revision 和 nu_next 有限性，但没有来源实例绑定，且 Candidate 全部可写。

| 探针 | 输入/触发 | 实际结果 | 验收期待 |
|---|---|---|---|
| 跨实例 | source 与 target 的同轴都配置/重置一次，但增益和 nu 不同 | target 接受 source 候选，nu 从 −0.5 变成约 +0.492 | 拒绝并保留 target 状态 |
| 改换轴 | 把 X 候选的公开 axis 改为 Y；两轴 revision 恰好相同 | Y 的 nu 从 −0.5 变成约 +0.492 | 拒绝错误轴候选 |
| 无效输出 | evaluate 成功后把公开 a_sta 改成 NaN，nu_next 仍有限 | commit 返回 Ok，nu 从 +0.5 变成约 +0.492 | 无效候选不得提交状态 |

后两项是显式构造的错误调用，不能据此声称常规 evaluate 自发产生了 NaN 或实际飞行出现串轴。
这些探针暴露的是后续保护裁决接口缺少完整性约束；可以通过不可修改候选及实例/轴/配置代次绑定，
或经过完整验证的包装器解决。任何保护后的 nu 应通过独立、明确校验的提交接口表达，不能以随意改写
“理想候选”代替保护记录。旧 ESTA 数学公式本身没有被这三项测试推翻。

V02 的 revision 能阻止**同一个候选**重复 commit，但接口没有 sensor sample 身份；同一帧重新
evaluate 后再 commit 仍可推进状态。此项是 V03 原本就应补的每采样门禁，不额外算作 V02 测试失败。
原模块 Run 中确实有失败后第二次 `_control.update(dt)` 路径，门禁必须覆盖它。

## V02 独立对象证据缺口

`StaVelocityControlTest.cpp:196` 的对象测试只保存一个 `velocity`，同时传给 float 内核和
`doubleEsta`。真正积分对象的 applied 来自 float 内核，double 参考没有自己推进的 velocity；
因此不能支持原报告“参考具有自身对象状态”的描述。现有单步/序列双精度公式核对与单条对象实验仍有价值，
但应与独立闭环对照区分。

此外，受约束部分只要求有限、发生饱和及 RMSE>0，不能证明定量跟踪门槛或稳定性；这不是一次失败飞行。
恢复前置时应分别推进 float/double 对象状态，冻结 8/12ms（含实际交替周期）的适用矩阵，区分恒定、
斜坡扰动和目标/FF 的作用，给出适用的数值残差/误差界与模型局限。不要单凭放宽原容差补足独立性。

## 参数、原始证据与未执行项

只读解码现有 `parameters_10016` 并核对生成默认值：MC_RTC_MODE=0、MC_STA_AXES=0、MC_RTC_DIV=1、
MC_RATT_TEST=0、MC_STA_TKO_MGT=0、MPC_VC_MODE/AXES=0/0；这七项在 BSON 中没有覆盖。
**这不是运行时参数或新 ULog 验证**，最近实测依据仍为 V01。未启动实例，未设置/保存参数。
原 BSON 完整指纹前后一致：`06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`。

外部数据：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V03/`。
两次编译、真实测试日志/XML、源码与外部计划快照、版本和参数都已保存；研究目录提交小型 JSON/XML/log
以及 [45 份证据索引](../v03/preflight/artifacts.sha256)。索引 SHA-256：
`bb8892c4d952fad0954ca3fdd6eed412d51f2c1421c9b086d3392266f65d1541`。

V03 所请求 1 次 PID 小速度飞行：尝试 0、完成 0、接受 0、未运行 1；尚无冻结的可执行飞行协议，未消耗预算。
未实现公共保护、sta_velocity_ctrl_status、真实 ULog 分析器或 V04 阈值；未重新构建完整 SITL、未运行
MATLAB/Octave、未飞行/部署实机、未继续旧 ISTA、未进入 V04。不能将审计编译当成完整固件构建通过。

本次只提交**失败审计**、复现工具与历史报告勘误入口；结果不是 V03 功能验收提交。完整提交 SHA
在提交后填入外部进度表。恢复顺序：修订候选提交契约并补齐 V02 独立对象证据，再完成 V03 保护/日志、
PID 等价回归和协议冻结，最后运行原请求的一次 PID 小速度任务。未 push。
