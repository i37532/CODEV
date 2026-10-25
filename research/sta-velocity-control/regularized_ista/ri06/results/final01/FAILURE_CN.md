# 首次结果导出失败（保留）

54次飞行/独立回放与36配对风险检查已经通过后，原冻结`final_package.py`在严格JSON序列化时退出1：`ValueError: Out of range float values are not JSON compliant: inf`。

原20183字节不完整输出仅原样改名为`package.partial.log`，SHA-256 `3cefa7324fbb37176d8961b5043e2990d68e68075023e29a9ef4c9bca3053d96`；没有覆盖或删除，不作为有效JSON/成功结果。

54份原指标检查发现12个固定诊断路径各出现54次正无穷：`height_task`中heading.latest_position、handoff.source.reference、reference.position三个位置快照的vxy_max/vz_max/hagl_min/hagl_max。冻结EKF2.cpp 841–857明确将这些非有限可选估计器约束发布为INFINITY；msg注释写0，与当前实现不一致，未修改两者。它们不是误差、实际速度/高度、控制输出或本实验安全阈值；所有科学指标均有限。

`../final02/export.py`只在这12个精确路径将正无穷编码为可逆的显式标记并保存648条位置清单；其他非有限值、NaN/负无穷及科学指标中的非有限值仍拒绝，不用0/null填补。新导出层另补14项负例/可逆性测试。原生产、冻结导出器、运行器、分析器、阈值、选参、原指标和54次验收结论均不改；零新飞行。该异常是结果归档错误，不是新的飞行失败或补飞理由。
