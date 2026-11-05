# ISTA 专项优化运行说明

先读 [冻结协议](PROTOCOL_CN.md)。这是新增 ISTA 调参预算、固定 ESTA 的后续研究，不改写 M10、不改变日常飞行默认参数。最多342次尝试，训练或验证未达目标会提前结束。

在本机没有其他仿真/实机链路时：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python"
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONDONTWRITEBYTECODE=1
python3 -m unittest discover -s research/sta-rate-control/scripts -p test_ista_opt01.py -v
```

先提交干净的协议/工具源码，再构建并回归（输出目录须全新）：

```bash
python3 research/sta-rate-control/scripts/verify_m09.py --output '/home/yr/Desktop/codev doc/experiments/ISTA-OPT01-20260918/verification01'
python3 research/sta-rate-control/scripts/ista_opt01.py \
  --output '/home/yr/Desktop/codev doc/experiments/ISTA-OPT01-20260918/search01' \
  --plugins '/home/yr/Desktop/codev doc/experiments/M10-20260917/plugins03'
```

入口依次运行代理筛选、训练、验证和（门槛通过时）新留出。每轮独立启动/结束 Gazebo，无需另开 `start.sh`。不要同时运行手动切换或任务脚本。参数、原始 ULog、失败和不可变清单留在外部目录；完成状态见 `conclusion.json`。

暂停后只能在相同干净源码、固件和配置下重复原命令；已有完整记录不重飞。基础设施/数据质量问题会阻塞，不可删除失败目录绕过。原 M10 日志无效轮次的特批不适用这里。结果提交后若需恢复历史实验，必须先检出其冻结源码并重建，不能在新 HEAD 上续写旧证据。
