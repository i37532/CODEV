# R01：独立正则化显式 STA 内核

本阶段只实现数学内核和离线验证，不修改原 PID/硬 sign ESTA、不接 PositionControl 输出、不飞行。
阶段总报告为 [R01](../../reports/R01.md)；在该报告完成前，本目录不代表验收通过。

## 接口与隔离

新类 `RegularizedStaVelocityControl` 位于 `src/modules/mc_pos_control/PositionControl/`。
独立 C++14 库只由本阶段测试使用；现有 PositionControl 和飞行模块不链接/调用该类。
参数为各轴 lambda1、lambda2、epsilon，纯核输出加速度纠偏，不含 FF、质量、角速度输入增益或电机映射。

~~~text
s = v - v_sp
rho = sat(s / epsilon)
Psi = s/sqrt(epsilon)        (abs(s) <= epsilon)
      sqrt(abs(s))*sign(s)   (otherwise)
a_sta = -lambda1*Psi + nu_old
nu_candidate = nu_old - h*lambda2*rho
~~~

epsilon 工程域为 `[.001, 1] m/s`，不是任意增益/采样率下的稳定保证。
层外分支不计算 `s/epsilon`，避免无必要的中间溢出；极小误差的真正数值下溢与正常浮点相加舍入应分开处理。
静态 `nonlinear()` 提供统一 Psi/rho，供后续阶段审计 HTE/交接时使用；本阶段不改那些路径。

evaluate 不改变 nu；commit/commitProtected 在 owner、轴、revision、密封载荷校验通过后最多提交一次。
保护后状态不回写理想候选，也不重算已经用旧 nu 生成的当步纠偏。重置到相同数值、epsilon-only 配置变化仍使旧候选失效。

## 验证组织

- 新 C++ GTest：数学分支/边界/数值、三轴隔离、强事务和独立 double 一步参考。
- `model/`：实际 float C++ 内核与独立对象/双精度参考；分别报告理想 ZOH、约束/噪声/滞后和实测变周期。
- `verification/`：统一离线验收入口，运行适用旧速度/角速度及日志回归、构建并验证未接执行器。

首个离线候选 epsilon 为 X/Y/Z `.01/.01/.02`，保留 R00 固定旧增益和限制。
有限对象矩阵和判据必须在执行前明确；性能无需胜过旧算法，且离线对象通过不等于 Iris 飞行通过。
大构建日志/XML及原始验证输出外置，仓库保存脚本、小型摘要和 SHA 索引。不运行 MATLAB 时明确记录。
