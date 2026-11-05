# RI02 — R-ISTA 离线保护、日志与工具接线

[阶段报告](../../reports/RI02.md) · [执行前约定](CONTRACT_CN.md) · [冻结参考](reference/README_CN.md) · [独立工具](tools/README_CN.md)

本阶段只离线。MODE4已经有配置/诊断名称，**仍不能在生产路径接管**；默认PID，原MODE0/1/2/3含义保持。只有测试文件的友元能打开离线夹具；没有参数或公共函数绕过准入。新比较仅PID/R-STA/R-ISTA，旧ESTA只做兼容回归。

最终验收通过：609项C++、348项工具Python及6项独立参考、SITL构建、36份完整历史日志回放。另审计1份旧失败ULog的两种视图，仍保留原失败。命令/退出码和6177项外部证据指纹见[归档](results/archive.json)、[C++证据](results/cpp_evidence.json)和[工具证据](results/tools_evidence.json)；不等同新MODE4飞行合格。

## 做了什么

- 隐式理想输出使用候选nu；保护冻结/限制nu后，不重算当前理想输出。所有有效轴一次原子提交，不使用rate的g，也不重复加入FF。
- Z/XYZ交接使用真实sample间隔反解seed；HTE只平移有身份的闭合应用纠偏缓存，不再次计算内核。超限或无缓存时拒绝，不裁剪成“无扰接管”。
- 重复sample、末轴失败、无效测量、reset/termination不会重复积分或部分提交；新模式失败不会冒增实际更新序号。没有增加起飞管理或修改估计器/模型。
- 扩展selection诊断，区分理想p/nu/a、保护状态/纠偏、最终发布加速度/推力，以及真实核h、seed_h、缓存和strict位。实际推力映射代理不叫实际加速度。

`ri_valid`保守表示**最终调用的完整成功事务**，不表示保护后的状态/输出仍是严格隐式解。失败第一次调用的全部中间候选并非独立持久化；同sample failsafe之后只报告最终调用。失败/调用数/模式仍可见，不能把NaN解释为“内核从未尝试”。seed-only的p由`ri_seed_h>0`识别，此时不是普通积分提交。

## 安全离线入口

```bash
cd /home/yr/Desktop/Codev-autopilot
python3 -B research/sta-velocity-control/regularized_ista/ri02/tools/run.py
python3 -B research/sta-velocity-control/regularized_ista/ri02/tools/run.py --mode 4 --axes 1
```

两条都只输出候选与预检；不写运行参数、不启动模拟器、不登记种子。`--execute`在RI02无条件拒绝，包括提供任意manifest/qualification的情况。

完整C++/SITL构建验证：

```bash
python3 -B research/sta-velocity-control/regularized_ista/ri02/verify.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI02/<新的唯一目录>'
```

该入口绑定开发基线`2f19cefc850ef4b77a8bcdc455aaec193f3da331`与本阶段明确补丁、源文件指纹。提交后原样复现应在独立检出准备基线＋补丁，或另冻验证入口；不得回退/清理当前工作区。移除继承的GTEST筛选/分片，直接执行43个目标并按XML实际用例去重，不把CTest重跑或2048步循环重复计数。保存旧固件/EEPROM副本，构建但不运行PX4或Gazebo。

工具、日志负例与历史回放：

```bash
python3 -B research/sta-velocity-control/regularized_ista/ri02/tools/verify.py \
  --with-history \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI02/<新的工具目录>'
```

大型日志/模型CSV/固件/XML只放外部；仓库results保存命令、退出码、统计和SHA索引。历史回放是只读诊断，不改变旧接受/失败，也不能抵充R-ISTA新飞行。

## 尚不具备的资格

没有新MODE4真实飞行ULog、飞行性能结论、调参、MATLAB重跑、板级耗时或实机资格。新适配层已经链接固件，因此本阶段不再沿用RI01“符号不存在”的证明；关闭准入由私有false、唯一写者及真实模块/保存重启负例共同证明。

下一阶段若启动RI03，仍需仅开放X的明确源码、完整新批次场景/参数/阈值/种子与预算、干净提交和新固件身份，以及实际运行的MODE4日志核对。不能用此处离线PASS跳过这些步骤。本阶段不push、不自动RI03或原R04/R05。
