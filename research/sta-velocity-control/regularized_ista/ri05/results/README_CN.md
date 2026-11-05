# RI05 结果与指纹复算

本目录保存结果汇总工具、测试、逐门摘要和指纹；不改变冻结协议、飞行批次、参数或阈值。完整报告见 [RI05.md](../../../reports/RI05.md)。

2026-10-24最终：A/C与B/D均9接受、9独立回放、6对风险通过，合计18/18，无飞行失败或缺失。B首次入口曾因混合dry-run stdout误存`.json`而停止，0飞行；原 [D_PRESTART_CN.md](D_PRESTART_CN.md) 与 [停批收据](D_prestart_failure.json) 保留。用户允许按原字节归档为`.log`、补接线测试后恢复原九项；不增加预算/换种子/改参数/放宽scanner，见 [恢复协议](recovery01/RECOVERY_CN.md) 和 [迁移收据](recovery01/archive_migration.json)。

A飞行源码3e633a0d2aba1326d3f79b0033f59787cc479c44，B实际飞行源码32a266f6162f1e09667ec92eeb0ad25abfee7ea7，B使用新qualification02，不能复用旧6fa资格。最终 [验收收据](final01/final_acceptance.json)、[完整XYZ配置](final01/qualified_xyz.json) 和 [核查记录](final01/FINAL_VERIFICATION_CN.md) 分别披露版本与证据。只属于固定参数Iris开发验收，不要求R-ISTA性能全胜。

## 单测

```sh
cd /home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/regularized_ista/ri05/results
python3 -B -m unittest -v test_collect_ri05
```

31 个独立结果层用例覆盖失败/缺失、指纹篡改、模式/种子/配对错配、恢复与前门收据等；实际命令及退出码见报告。全部 fixture 位于系统临时目录，不算真实飞行或 ULog 解码。测试同时核查输入不被改写。

## 停机后才运行

下面输出路径仅作示例，必须选择一个尚不存在、且在输入实验树之外的新目录。C 对应本阶段 A/XY，D 对应 B/XYZ；不能把同名旧 R03 数据混入。

```sh
python3 -B collect_ri05.py --gate C --output /tmp/RI05-C-results-NEW
python3 -B collect_ri05.py --gate D --output /tmp/RI05-D-results-NEW
```

默认只读数据根为 `/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI05`。`--data-root` 仅用于隔离的 fixture 或完整搬迁后的证据树；不导入运行器、不启动解码器、不写入任何输入数据。批次尚运行、cleanup 未最终记录或仍有 simulator 标记时拒绝读取大文件。

输出四份文件：

- `summary.json`：完整逐轮原指标、计划/尝试/实际离地证据/接受/失败/缺失、各组逐轮后均值、半窗和配对风险/描述性差异、回放与门收据。
- `ulog_index.json`：所有 `result.logs`，包括启动短日志和主日志的真实 SHA-256/字节数核验，不只收录主日志。
- `evidence_index.json`：batch/replay 全部文件、符号链接信息及外部资格收据/脚本指纹；不跨符号链接目录递归。
- `SUMMARY_CN.md`：简短表格，指向 JSON 的完整口径与局限。

仓库内 `C/summary.json`、`D/summary.json` 是明确字段选择的精简收据；完整摘要和档案索引在外部，以绝对路径/字节数/SHA-256引用。导出不重新判定试验：

```sh
python3 -B export_compact.py <外部新收集目录> <全新仓库结果目录>
```

导出会保留逐轮/半窗统计、完整组均值、配对检查、资格命令、门收据和所有 ULog 索引。不能覆盖既有目录或把 B 的来源标成 A。

退出码 `0` 仅表示收集过程与现有证据一致，不表示实验门通过。必须另看 `gate_passed`；全部九轮、原 gate receipt、独立回放/输入指纹、六个风险比较、资格及参数恢复链都一致才为 true。D 还绑定 C 既有验收收据。部分/停批结果合法保留，绝不补零。

“已离地”使用已有 `samples.jsonl` 中 `arming_state=2`、`landed=false` 且相对首次有效本地 Z 高度超过 0.5 m 的记录，仅作报告证据分类，不更改飞行安全规则。没有充分记录标 `unknown`；单独的 takeoff_command 不算完成起飞。这不是 Gazebo 真值，也不重新定义冻结验收。

位置误差保留发布目标/前驱测量配对口径；名义 2.5 m 高度误差与 V 任务 Z 速度/位置跟踪分列。各统计先逐轮再均值；缺失/失败不纳入接受组均值。p/理想 nu 峰值未预先聚合时不凭空添加。TV 不是能耗，耗时不是板级 CPU/WCET。

## 最终跨收据核对（不飞行）

在C/D真实回放、收集及导出全部完成后，使用新输出目录：

```sh
python3 -B recovery01/finalize_ri05.py \
  --d-source 32a266f6162f1e09667ec92eeb0ad25abfee7ea7 \
  --output /tmp/RI05-final-NEW
```

该工具只核对小型收据，不重新解码/哈希ULog；不能替代真实collector/replay。导出PID/RSTA/RISTA各完整127项，包含研究任务参数TEST8，不可盲目导入实机；`new_flight_authorization=false`。原18项预算已全部消费，不得重复运行flight runner。
