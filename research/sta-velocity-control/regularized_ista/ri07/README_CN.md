# RI07 当前状态

## 2026-10-26 恢复准备（最新）

用户已另行授权清理历史 ULog，原容量阻塞已解除；清理清单保存在外部 `HISTORY-CLEANUP-20261026`，不改判旧结果。原 RI06 图表暂存外部并在收尾原样恢复。

新执行清单严格复制 RI06 final02：A80+B120=200，原种子/次序/参数/任务/规则不变。A001 是 STA，A 组没有 PID，不另增先导。每轮独立解码回放后才前进，首个必需有效性或安全失败停批。没有飞行前不预填通过。

用户批准仅更新 Git 版本并重新冻结固件：先提交本目录工具，再在同一干净源码完成 `qualify.py`，把新固件 SHA 写入资格收据；全部200次使用该版本。保留原 RI06 固件指纹，不修改生产源码或统计方案。

```bash
# 默认只显示准确清单，不启动仿真或写参数
python3 -B research/sta-velocity-control/regularized_ista/ri07/tools/runner.py
# 仅在干净已提交工具源码进行零飞行资格验证
python3 -B research/sta-velocity-control/regularized_ista/ri07/qualify.py --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261026/RI07/FORMAL/qualification01'
# 资格通过后才显式执行；SOURCE_SHA 必须为该资格的完整40位源码 SHA
python3 -B research/sta-velocity-control/regularized_ista/ri07/tools/runner.py --execute --source-head "$SOURCE_SHA" --qualification '/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261026/RI07/FORMAL/qualification01/evidence.json'
```

正式统计仍调用未改动的 `ri06/statistical_plan.py`：8主比较、组内共同完整块、20预注册块、200000次配对重采样；缺失不填0，不为显著性追加样本。最终以报告及外部 ledger 为准。不 push，不执行其他阶段。

## 以下为原启动阻塞记录（历史保留）

2026-10-26：**启动前容量阻塞，0/200 尝试，未起飞。**

按冻结预检需要 51.0625 GiB 可用，实测约 35.05 GiB，缺约 16.02 GiB。没有降低容量规则、删除历史数据、调参或消费种子。全部正式任务仍未执行。

- [详细报告](../../reports/RI07.md)
- [只读入口证据](results/prestart01/evidence.json)
- `prestart_audit.py` 只是只读审计，不是飞行运行器；退出码 2 表示 blocked。
- `test_prestart_audit.py` 有 8 项辅助程序测试，不能替代控制器/SITL 资格。

先解决存储与已有图表未提交状态，再完成正式执行适配和干净资格。当前没有正式性能结论，不 push、不运行其他阶段。
