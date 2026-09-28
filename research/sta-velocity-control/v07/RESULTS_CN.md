# V07 结果入口

本批状态为 **failed / needs_revision**，不是V07完成：DIV1共6轮/3对通过；DIV2尝试5轮，前4接受，第11轮PID因降落期IMU日志发布时间同刻被冻结规则拒绝；剩余7轮不执行，DIV4无飞行数据。

见 `../reports/V07.md`。`results01/archive.json` 记录10接受、1失败、7取消和证据副本来源；`summary.json`保留5个完整配对及部分描述性结果，不能把缺失轮次记作通过。

`package_results.py`仅校验并打包已有结果，不启动飞行，不修改原始result/ULog。1311工件及22个ULog保留于：

`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260928/V07`

校验归档（只读）：

```bash
cd /home/yr/Desktop/Codev-autopilot
sha256sum --check --quiet research/sta-velocity-control/v07/results01/raw_artifacts.sha256
```

`results01/tools_snapshot`是外部ROOT中实际运行脚本的逐字快照；依赖其所在目录为原实验ROOT，不能从仓库快照位置直接运行。已有输出目录会阻止覆盖。完整分析重放使用报告中的 `protocol01/analyze.py`，指定新的输出目录；若重新打包，必须在所有日志写入结束后指定新的`--output`。

不要再次执行已耗种子的`protocol01/run.py --execute`，不要将失败单轮分项审计当作完整验收，也不要运行V08。本阶段未push。
