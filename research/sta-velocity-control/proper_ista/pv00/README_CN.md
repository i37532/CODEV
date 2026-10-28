# PV00离线证据与复现

此目录只做来源审计、原144轨迹复现和有限69条诊断，无Gazebo/PX4启动、飞行或参数写入入口。

先读 [协议](PROTOCOL_CN.md)、[数学/数值契约](CONTRACT_CN.md)、[报告](../../reports/PV00.md)。原始根目录 `/home/yr/Desktop/codev doc/experiments/VELOCITY-PROPER-20261028/PV00/`；`results/`为紧凑结果及原始SHA索引。

在仓库根设置已有依赖路径（不安装新包）：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python:$PWD/research/sta-velocity-control/proper_ista/pv00${PYTHONPATH:+:$PYTHONPATH}"
python3 -B research/sta-velocity-control/proper_ista/pv00/diagnostic.py
python3 -B research/sta-velocity-control/proper_ista/pv00/numerical.py
python3 -B research/sta-velocity-control/proper_ista/pv00/test_pv00.py -v
```

前两条默认仅打印有限清单，不生成数据；最后一条实际执行22个单元测试。需要新离线重算时才加`--execute --output <新的外部目录>`；不能覆写已存目录。

- 原144：`proper_ista_probe/probe.py --execute --output <新目录>`，会重新编译三核和桥接，并执行既有ctest筛选；不会构建/启动PX4。
- 新69：`proper_ista/pv00/diagnostic.py --execute --library <原144新目录>/kernels.so --output <新目录>`；需原R03 ULog和RI00 cadence，缺失即失败，不用摘要冒充回放。
- 原12停止/122格点：`proper_ista/pv00/numerical.py --execute --output <新目录>`；固定旧原始停止来源，临时插桩副本在外部目录，生产源码不改。
- 独立轨迹指标复算的实际命令在results/evidence.json中（old_replay/new_replay）；原始完整JSONL均保留。

`run_checks.py`、`collect.py`、`export.py`是**本轮入口/收尾工具**，绑定入口HEAD和上述原始根/来源，不是跨提交通用飞行资格。收尾产物为audit02/closeout02/publication01；首次audit01/closeout01保留并在报告披露审计漏项修正。导出需要显式新的外部`--output`及pv00下新`--repo-output`，不会覆盖现有结果。

551个C++与46个Python为本轮实际执行数；213离线轨迹不是飞行或独立随机样本。12个极小数拒绝、12个完整但不可行限幅反例未被删去。既有ctest二进制未重建，生产固件仍RI07版本；MATLAB未运行。PV00通过不等于Proper具备速度飞行资格。
