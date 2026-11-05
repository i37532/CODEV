# V03 protocol02：修复后单次 PID 准入

用户在原一次尝试失败、诊断订阅修复后明确回复“运行”，授权本次新预算 **1 次**。
旧 protocol01、series01 和失败证据保留，不覆盖、不计作通过。

修复源：`970adacafb850002820c8ff5f2522b2ff1944096`。
改变仅为读取角速度诊断队列的最新消息并记录其时间/序号；本协议不修改控制律。
原场景、参数、阈值、默认随机源及失败停止规则全部保持。无独立随机种子主张。
本次：全 PID、Iris、原启动器，预热至少 30 秒，原起飞/Hold，60 秒观察
（12 秒 settle 后 32 秒 X 速度小激励），降落上锁。其余目标发布者与旧协议相同。

先在此协议的干净提交编译测试，再运行（SOURCE_SHA 必须填现场完整提交 SHA）：

```bash
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/scripts/run_v03_resume02.py --output "/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260922/V03/series02" --source-head SOURCE_SHA --execute
```

省略 --execute 仅检查/打印计划；真实运行入口拒绝现有输出目录，预算在启动前消耗。
失败必须停止，不自动补飞，不放宽阈值。原 EEPROM 完整备份恢复。
实际固件 SHA 由运行 ledger 记录；frozen.json 冻结源文件、模型、world、插件及参数。
不 push，不 V04，不启用 ESTA，不实机。

使用本协议重新分析已有单轮数据（不飞行）：

```bash
PYTHONPATH="research/sta-velocity-control/scripts:$PYTHONPATH" python3 -c 'from pathlib import Path; import json; import run_v03_resume02 as r; r.configure(); print(r.analysis.analyze(Path("/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260922/V03/series02/run01"), json.loads((r.CONFIG/"protocol.json").read_text())))'
```
