# I02：保护映射和起飞状态管理（仅离线）

本阶段只有离线实现与测试：Proper-ISTA 仍没有模式号、参数入口或执行器路径；没有飞行。

- [规格](PROTOCOL_CN.md)
- [阶段报告](../../reports/I02.md)
- [证据摘要](results/evidence.json)
- [原始文件指纹](results/artifacts.sha256)

## 重跑

从仓库根运行，输出目录必须不存在：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"

python3 research/sta-rate-control/ista_redesign/i02/verify.py \
  --output '/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I02-replay01' \
  --regression
```

这会构建并运行新增 21 个 GTest、I01 内核 16 个 GTest，并在 `--regression` 下运行既有
M09 回归和 SITL 构建/固件符号/ULog 格式检查。脚本不启动 Gazebo、不写参数、不飞行。
不加 `--regression` 不能代替完整 I02 验收。

起飞管理开关当前没有参数接线，不能在飞行中启用；I03 之前不要自行把它接入参数或使用。
