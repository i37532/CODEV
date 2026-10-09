# 速度环按轴消融专项

2026-10-09最终：**AX05完整320轮正式消融通过执行与日志验收**，H/V各160接受、总280配对、320独立回放、640 ULog解码/指纹通过；0失败/缺失/补飞。XY ESTA＋Z PID综合误差相对PID降低约24.0%/23.6%，XYZ增加约9.8%/9.9%，不称所有ESTA胜出。
[完整报告](../reports/AX05.md)｜[简明总结与只读复现](ax05/README_CN.md)｜[统计/区间](ax05/results/summary.json)。飞行源码794301664cc0aacee6b5c62987531ab6f0b33fdf，结果SHA见外部进度；不push，不自动下一阶段。以下保留历史时点。

2026-10-08当前：**AX05执行前系统存储阻塞**。本次81 Python/10 C++及冻结指纹检查通过；320计划、0尝试、0起飞、0接受，未消费正式种子。约38.10 GiB可用不足以容纳预计38.22 GiB完整数据/回放，且尚无运行余量。没有删除旧数据或更改协议。
[AX05报告](../reports/AX05.md)｜[简明进度](ax05/README_CN.md)｜[检查证据](ax05/preflight.json)。用户已授权原批次，阻塞不是等待逐轮许可；不push、不自动其他阶段。以下保留历史时点。

2026-10-08最新：**AX04正式协议离线冻结**，8配置×2任务×20共同种子块=320次，全部未执行。
[AX04报告](../reports/AX04.md)｜[正式包与dry-run](ax04/README_CN.md)｜[统计规范](ax04/STATISTICS_CN.md)｜[准确顺序](ax04/ORDER_CN.md)。
273 C++/710适用Python通过；不调参、不飞行、不push、不自动AX05/V09。最终源码/固件资格SHA见外部实时进度。
以下AX03及更早记录保留历史时点含义。

2026-10-08最新：**AX03固定参数开发矩阵通过**。H24/V24、48次完整起降/接受、42配对和48独立回放通过，96份ULog解码与指纹核验通过，无补飞/调参。水平误差改善，但Z误差和TV增加；不称全面胜出。

- [AX03报告](../reports/AX03.md)｜[结果与只读复现](ax03/README_CN.md)｜[逐轴摘要](ax03/results/summary.json)。实际飞行源码 `ab9df703f837a3cb2b78a9295c5d4202e4f5a3ff`；结果提交SHA见外部进度。不push、不自动AX04。

以下AX02/AX01状态保留原时点含义。

2026-10-08：**AX02 工具与48轮协议冻结通过**，干净源码复核273 C++/658适用Python通过，本专项新飞行仍为0。

- [AX02验收报告](../reports/AX02.md)：协议源码 `9f514213a2d9b0d66674367c009e0d8886fe6c39`，6份旧日志只读回放；结果SHA见外部进度。
- [AX02 入口、参数、波形、安全门与准确清单](ax02/README_CN.md)：默认dry-run；H24→V24，V首PID是预算内安全门；不自动AX03。

- [AX01报告](../reports/AX01.md)、[八配置离线接口与复现](ax01/README_CN.md)：Y/XZ/YZ实际接线，261 C++/629适用Python，旧路径20480样本对照；不等于新矩阵飞行资格。

- [AX00 报告：八配置差异、参数来源与下一阶段范围](../reports/AX00.md)
- [实际审计证据与完整参数来源](ax00/evidence.json)、[检查命令及失败记录](ax00/CHECKS_CN.md)
- [AX00 开始时新增计划快照](plan/ax00_entry/VELOCITY_AXIS_ABLATION_TODO_CN.md)，不覆盖 v1。

当前 PID/X/Y/XY/Z/XZ/YZ/XYZ 均有离线接线；MODE2拒绝、默认PID。本专项DIV1，V08水平参数与历史Z参数组成的新八配置矩阵尚未飞行验收。
混合组合必须统一未替换轴的 PID 参数，不能直接照搬 V08 ESTA 文件中的旧水平 PID 增益。

目的：固定每轴参数，比较 PID、X、Y、Z、XY、XZ、YZ、XYZ 八种速度控制配置。
位置P、姿态和全部角速度PID保持；速度DIV1。不是每组合重新调参的最优性能比赛。

- [TODO与共同规则：创建时快照](plan/v1/VELOCITY_AXIS_ABLATION_TODO_CN.md)
- [六阶段可复制提示词](plan/v1/VELOCITY_AXIS_ABLATION_PROMPTS_CN.md)
- [进度：创建时快照](plan/v1/VELOCITY_AXIS_ABLATION_STATUS_CN.md)
- [外部实时进度](</home/yr/Desktop/codev doc/plan/VELOCITY_AXIS_ABLATION_STATUS_CN.md>)

路线：AX00审计 → AX01补齐Y/XZ/YZ → AX02冻结工具/开发协议 → AX03开发验证 → AX04正式协议 → AX05正式消融。
开发候选48次（8组×2任务×3种子），正式候选320次（8组×2任务×20种子），均需对应阶段冻结；本次实际0。
完整阶段结果 SHA 见外部实时进度。本次AX02不push，不自动执行AX03。
每阶段分别启动，参数/阈值/预算不得运行中改动，不保证ESTA胜出；失败保留并停批。
V08/V09已冻结200次独立主实验保持不变，41001–41020不得挪作消融种子。
