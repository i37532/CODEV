# RI05 最终证据与复算记录

2026-10-24，A/C与B/D均通过，18尝试/18接受/18独立回放、12对156项风险检查。仅Iris固定参数开发验收，无新飞行授权，不push，不RI06。

## B实际执行链

恢复提交/实际飞行源码 `32a266f6162f1e09667ec92eeb0ad25abfee7ea7`。新固件SHA-256 `b356efaa4f46644b26b480b54a1e8ce93bf04b8294cdb54f428cabfe3784fa0c`。全9轮同提交且工作区干净，原1085/79冻结资产不变；结果生成在完成飞行/回放后。原入口预检退出1不是飞行失败，旧记录和迁移收据保留。

以下命令均在 `/home/yr/Desktop/Codev-autopilot` 执行、实际退出0；环境为仓库`.px4-python`、研究`scripts`及M00 pymavlink路径，`PYTHONDONTWRITEBYTECODE=1`。`STAGE`表示 `research/sta-velocity-control/regularized_ista/ri05`，`DATA`表示 `/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI05`，`RESULTS`为同级`RI05_RESULTS`（说明性别名，不覆盖系统环境变量）。

1. `python3 -B $STAGE/verify.py --gate D --qualify --output "$DATA/D/qualification02"`：118子命令全0；751唯一C++/48目标、982 Python/41套、6独立参考、18历史接受回放、2失败审计、构建通过。MATLAB未重跑，历史回放不算新飞行。
2. `python3 -B $STAGE/tools/runner.py --gate D --execute --source-head 32a266f6162f1e09667ec92eeb0ad25abfee7ea7 --qualification "$DATA/D/qualification02/evidence.json"`：9尝试/9接受，6对78项，参数精确恢复、无残留模拟器。**已消费，不可再次执行。**
3. `python3 -B $STAGE/tools/replay.py --gate D --output "$DATA/D/replay01" --finalize`：9独立解码命令全0，全部指标值/类型/顺序和spectra字节一致、原输入首尾指纹一致，6对风险复算通过。
4. 将`$STAGE/results`及其`recovery01`加入PYTHONPATH后，`python3 -B -m unittest -v test_collect_ri05 test_archive_stdout test_finalize_ri05`：实际87项全通过（31既有结果层+23归档接线+33最终导出）。不是新控制器或飞行样本，56恢复用例不与飞前重复执行累加。
5. `python3 -B $STAGE/results/collect_ri05.py --gate D --output "$RESULTS/D01"`：passed、collection_ok/gate_passed=true、issues=[]；真实核验18份ULog的字节数/SHA，包含启动短日志。
6. `python3 -B $STAGE/results/export_compact.py "$RESULTS/D01" "$STAGE/results/D"`：精简摘要保留所有报告字段，引用外部4文件SHA。
7. `python3 -B $STAGE/results/recovery01/finalize_ri05.py --d-source 32a266f6162f1e09667ec92eeb0ad25abfee7ea7 --output "$STAGE/results/final01"`：passed、18接受；跨收据核对和每算法127参数导出，**不重新解码/哈希ULog，不授予飞行权限**。

首次归档测试漏配依赖退出1、0测试及原停止事件保留于recovery01证据。恢复后没有新的试飞失败、补飞、调参、种子/预算/门槛调整。

## 关键SHA-256

| 证据 | SHA-256 |
|---|---|
| D/qualification02/evidence.json | `25da01ec4ae4e6bf86d8bde62f8e4d609c3753cc60bf34a5d74195133e7cd9f3` |
| D/batch01/ledger.json | `a0c470fa2e0a4c42cef02fa9d36b45606bc07bde8ab02ad55167088c20e5c2fb` |
| D/replay01/summary.json | `58d76cb24dfe72a6b23b1714959389da8a94b0cf91c47b23efbb869b449f69f1` |
| D/gate_pass.json | `7ba76b2f5c2139f84ff3cc82052e7ff3e871e1d08b66cb17e9d905e9539aed0e` |
| RESULTS/D_RECOVERY01/closeout_tests.log | `cde7ef52a0baf6a949bf5c6a345dc0e6d49ab8592310e635fd769f685548b226` |
| final_acceptance.json | `2f308de6aebd09156e9a20562d66eb646e2c8f331806e309dc79a2677dbaebb5` |
| qualified_xyz.json | `dadfb071f8a632c8c857fdf0cee3998f609312ea7a5ee87d9cd3f55243b9dc2a` |
| 原参数BSON（最终恢复） | `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc` |

完整指标与ULog索引见`../D/summary.json`、`../D/ulog_index.json`及其中外部档案引用。A版本与结果在`../C`分列；不把A/B不同任务、源码/固件合并为同版本公平统计。三算法各n=3配对开发种子，接受不等于最优调参或显著优越。

## 提交前只读审查

1085仓库资产+79外部资产共1164项SHA核对全部通过；当前固件和最终EEPROM仍匹配上表。C/D精简摘要引用的8份外部结果文件字节数/SHA均一致，33递归子模块匹配且干净。独立审查对照原指标/导出字段、127项参数及16份小型来源收据，26个报告链接有效，未发现阻断；这些断言不是新控制器测试或新飞行。`git diff --check` 退出0。实际结果提交仅包含本次报告、结果README、D三份摘要/索引和final01三份验收/配置/说明，不改变冻结生产源码、参数或旧失败数据。
