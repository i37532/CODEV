# V06 protocol03 结果索引

源码64cd58b6c8fe112ffb2086b7ddff483489acd624；合格弹性接触Iris。18/18轮、9/9配对，三个任务各3对。主结论和限制见 ../../reports/V06.md。

- ledger.json：顺序、配对、源码/固件、参数恢复和预算。
- run01–run18：原始小记录、真实模式/参数、模型/world、指标；不含大型ULog。
- raw_artifacts.sha256：外部series03内940工件指纹，含36份ULog及失败审计所需全部原始流。
- summary.json：逐轮实际模式与36份ULog健康状态。
- complete.json：全18轮独立回放等价、验证196 C++/467 Python、每任务/半窗/全窗速度RMSE、位置/yaw、请求/推力TV及外部证据SHA。

外部根：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260928/V06；series03、replay03、verification_committed03。重新分析可用soft_landing/replay.py --protocol protocol03，指定全新输出目录；不重飞已耗尽的本批预算。

所有算法使用同一接触参数、相同已冻结增益和任务门槛；新组不与旧硬接触失败批次或专项悬停六轮混合统计。ESTA速度误差和TV更大，验收通过不是性能胜出或实机安全结论。
