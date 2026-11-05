# I04 复现入口

I04 只允许在协议/源码提交的干净工作区运行：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
python3 research/sta-rate-control/ista_redesign/i04/batch.py \
  --output '/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I04/formal01'
```

批次按 `FROZEN.json` 精确执行 8 次，不自动补飞。`run.py` 复用项目 `sitl/run.sh`、M10 已固定的
显式种子 IMU 插件及原起降/清理器；`analyze.py` 逐份解码 ULog，并用独立 binary64 二分解核对
Proper-ISTA 理想候选及 `2*Delta nu` 保护映射。大型日志只放外部目录。

正式批次前的两次地面启动/参数保存回归使用：

```bash
python3 research/sta-rate-control/ista_redesign/i04/restart.py \
  --output '/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I04/restart01'
```

批次完成后核对源码、二进制和全部 ULog 指纹，并把小型证据快照复制回仓库：

```bash
python3 research/sta-rate-control/ista_redesign/i04/package_evidence.py \
  --root '/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I04/formal01'
```
