# E01-XYZ 完成后的路线（2026-09-27）

V05（XY已通过）+ Z03（Z-only已通过）→ **E01-XYZ（同时XYZ已通过）** → V06（尚未开始）。

- 当前完整验收：[E01_XYZ.md](../reports/E01_XYZ.md)，源码`045f642bf2bad5e532761e59b3d6810be360be58`，六轮/三对通过，三轴速度ESTA、全部角速度PID。
- `plan/`与本目录原README是飞前冻结快照，不回写其“尚未验收”历史状态。原`plan/v1`不改；外部TODO/提示词/进度为实时入口。
- 用户对E01-XYZ普通修复/有限新批次的持续授权已落实，本阶段首批六轮全部通过，没有新增批次。不会延伸为V06/实机/调参/ISTA/push授权。
- V06先明确选择已验收的XY ESTA+Z PID或XYZ ESTA，再冻结两模式三任务的准确协议预算；若两套ESTA都纳入，须重算矩阵，不能混为同组。原V08/V09的XY范围不自动扩大。
- 合格配置见`qualified_xyz.json`；三轴组合中X/Y改善、Z误差和TV退化如实保留。默认固件、恢复后的参数仍PID。
- 结果提交完整SHA见外部`VELOCITY_STA_STATUS_CN.md`；报告不预写自身SHA。
