# 速度环按轴消融专项

2026-10-08：**AX02 工具与48轮协议已实现，正在完成干净提交复核**，本专项新飞行仍为0。

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
