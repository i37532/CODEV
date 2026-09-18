# I03 工具入口

正式运行前须处于包含本目录 `FROZEN.json` 的干净提交，并重新构建 SITL。批处理会核对冻结文件、M10 参数快照和插件清单的 SHA-256，再按固定顺序进行 12 次且不重试：

```bash
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-rate-control/scripts:$PWD/research/sta-rate-control/ista_redesign/i03:/home/yr/Desktop/codev doc/experiments/M00-20260912/python"
export PATH="$PWD/.px4-python/bin:$PATH"
python3 research/sta-rate-control/ista_redesign/i03/batch.py \
  --output "/home/yr/Desktop/codev doc/experiments/I03-20260918/formal01"
```

输出目录已存在时只允许按 immutable manifest 续读已完成轮次；任何未裁决的中断目录都会拒绝覆盖。`analyze.py` 使用 Gazebo 真值只做飞后诊断。

结果完成后，`package_evidence.py --root <formal01>` 会重新核对 12 个 job、24 份 ULog、源码/固件唯一性、同种子前 5000 个 IMU 增量和所有外部文件指纹，并生成仓库内的小型证据快照。

最终结论见 [I03 报告](../../reports/I03.md)：新增管理 4/6 通过，但 seed 6101 两种算法均提前释放，因此后续共同保护基准仍为既有保护。
