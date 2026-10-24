# RI04 revision01 入口

本目录是已提交 HTE 修复后的独立九轮协议；不是旧失败批的续跑。详见 [协议](PROTOCOL_CN.md) 和 [明确授权](AUTHORIZATION_CN.md)。新9次＋历史3次＝总上限12次；原批剩余6次作废。

顺序：协议 prepare 仅一次登记新种子 → 审查源码/工具 → freeze --write 生成唯一清单 → 提交明确文件 → 在该干净提交 verify --qualify → 默认 dry-run 复核 → 显式执行最多9轮 → 全部接受才 replay --finalize。首次必需失败立即停批，无自动补飞。

以下命令在仓库根执行。运行环境见 [工具 README](tools/README_CN.md)。

```bash
python3 -B research/sta-velocity-control/regularized_ista/ri04_revision01/freeze.py --write
python3 -B research/sta-velocity-control/regularized_ista/ri04_revision01/verify.py --qualify --gate B --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI04_REVISION01/B/qualification01'
python3 -B research/sta-velocity-control/regularized_ista/ri04_revision01/tools/runner.py --gate B
```

freeze 清单已存在时只用 --check，不覆盖；上述 qualification 目录必须新建。本阶段不更改任何生产文件，旧固件资格不能授权新构建。明确执行需要工具 README 中的完整源码 SHA 和真实资格文件，不能复制占位符起飞。

新分析层逐样本检查 HTE 缓存：StateLimit-only 可以保留真实应用纠偏；CorrectionLimit、OutwardFreeze、Latched、下游约束仍不能冒充有效缓存。仅将新语义用于本批，不重判旧失败；全部旧数学、时钟、日志数值门槛保持。

历史准备记录见 [离线准备记录](PREPARATION_CN.md)。结果报告另存 reports/RI04_REVISION01.md；协议和初始 unattempted 清单不覆盖为结果。
