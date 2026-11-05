# R03 四门开发结果包

验收结论与解释见 [最终中文报告](../../reports/R03_ACCEPTANCE_CN.md)。A/B/C 是 revision09，D 是 revision11；每门三算法各三个配对种子，不能混成同固件正式实验。此目录只保存结果，不含执行飞行的入口。

- `summary.json`：36 轮的逐轴均值/方差/RMSE、J、nu、限制、TV、位置/yaw、时序、实际模式/输出、宿主耗时及 276 项输入路径/SHA；包含各组均值和逐种子差。
- `gate_A.json` 至 `gate_D.json`：外部真实签发收据的逐字节副本；包含资格、原始来源、历史账本索引。不是本目录脚本自行判定或手写的通过标志。
- `summary.py`：检查既有四门收据及完整接受数、读取原始指标、复核日志指纹，再做描述性汇总。不改原始工件、不飞行、不签发新 gate；只允许写全新输出。
- `test_summary.py`：9 项结果一致性检查，不替代飞前 C++/Python、完整 ULog 回放或安全门。

大型 ULog、每轮完整参数/目标/metrics/spectra/result、原始测试日志和失败在 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016`，未打包进 Git。单独 clone 仓库不等于取得原始日志；输入缺失必须补齐外部证据，不能跳过指纹检查。当前汇总路径按本机冻结位置记录。

在仓库根目录运行以下只读复核（只生成一个新临时 JSON，不飞行）：

```bash
python3 -B research/sta-velocity-control/regularized_sta/r03_results11/test_summary.py
r03_result_tmp=$(mktemp -d)
python3 -B research/sta-velocity-control/regularized_sta/r03_results11/summary.py --output "$r03_result_tmp/summary.json"
cmp "$r03_result_tmp/summary.json" research/sta-velocity-control/regularized_sta/r03_results11/summary.json
```

当前 `summary.json` SHA-256：`5bcf8a9c2963e54a0ada5eb49c77d0c1ae24a277667814236113cb1b3c41f455`。两次生成已逐字节一致。重算只读原工件的数值和指纹；完整独立解码证据另在各门 `replay01/summary.json`，不能把重算汇总称又飞了 36 轮。

覆盖率并非所有层级均 100%：旧 A/run001 输出匹配 11699/11700，位置原 raw 与镜像数量有 2 条差；D/run036 原 raw 数量差 1 条。连续镜像、完整重叠载荷和实际输出匹配按各自冻结合同检查，不插值/去重/补造数据。新结果测试最初两次误加全覆盖断言失败，纠正后 9 项通过；未改原门槛或历史结论。
