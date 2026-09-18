# ISTA-OPT02 运行

先阅读[协议](PROTOCOL_CN.md)。本轮只诊断和搜索参数，不修改land detector或冻结规则。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python"
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONDONTWRITEBYTECODE=1
python3 -m unittest discover -s research/sta-rate-control/scripts -p 'test_ista_opt*.py' -v
# 在已提交的干净协议/工具源码上构建（输出目录全新）
python3 research/sta-rate-control/scripts/verify_m09.py --output '/home/yr/Desktop/codev doc/experiments/ISTA-OPT02-20260918/verification01'
python3 research/sta-rate-control/scripts/ista_opt02.py diagnosis \
 --output '/home/yr/Desktop/codev doc/experiments/ISTA-OPT02-20260918/run01' \
 --plugins '/home/yr/Desktop/codev doc/experiments/M10-20260917/plugins03'
```

检查 `diagnosis_audit.json`、`diagnosis_gate.json` 和全部失败，不得跳过基础设施/日志异常。证据门槛通过后才运行：

```bash
python3 research/sta-rate-control/scripts/ista_opt02.py search \
 --output '/home/yr/Desktop/codev doc/experiments/ISTA-OPT02-20260918/run01' \
 --plugins '/home/yr/Desktop/codev doc/experiments/M10-20260917/plugins03'
```

每轮自行启动/结束Gazebo，不能并行开日常start/switch/fly脚本。最多100次尝试，阶段失败按协议停止。不要删除失败目录、修改已冻结清单或在结果提交后的新HEAD续写旧数据。原始日志在仓库外，默认参数结束后恢复，研究参数不自动应用到日常飞行。
