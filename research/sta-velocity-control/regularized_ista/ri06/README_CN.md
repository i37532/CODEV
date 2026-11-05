# RI06：XYZ 公平调参与正式协议

仅 PID/R-STA/R-ISTA，训练36+独立验证18；正式 A80+B120 只冻结。原模型、保护与生产源码不变。
详细规则：[PROTOCOL_CN.md](PROTOCOL_CN.md)。入口默认 dry-run；任务按 TH→TV→一次选择→VH→VV。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python"
export PATH="$PWD/.px4-python/bin:$PATH"
python3 -B research/sta-velocity-control/regularized_ista/ri06/tools/runner.py --gate TH
```

明确执行还必须提供同门干净源码资格的完整 SHA 和 evidence.json；没有资格不会启动。每门先冻结、提交、验证；失败即停止，不自动重试。训练全部回放后 `choose_candidate.py --write` 只能创建一次 selection.json，先提交再验证。
新数据目录 `/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261025/RI06`，每轮原始ULog、参数及恢复凭据外置；小摘要/指纹在本目录 results。
没有 formal 执行选项，不运行 RI07/旧R04/旧R05；不得在训练中读取新正式留出。
