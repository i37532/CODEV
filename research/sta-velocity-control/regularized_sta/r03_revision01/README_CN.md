# R03 revision01 运行与核验

用户已授权旧失败1＋新36，总R03最多37。原失败不改判；控制参数/任务/风险门全部沿用 [协议](PROTOCOL_CN.md)。本目录为新版运行/分析入口，旧r03目录和旧batch不再执行。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
python3 research/sta-velocity-control/regularized_sta/r03_revision01/runner.py --gate A
```

默认只列清单，不飞。以下命令由本任务在对应前置满足后顺序执行，不能复用旧资格、覆盖已存在输出目录或直接启动后门：

1. `verify.py --gate A --output <全新外部验证目录>`：统一非零离线回归、双真实导入顺序完整旧日志诊断、构建；诊断不改历史判定。
2. `freeze.py --gate A`：冻结资产，明确范围审查提交，工作区必须干净。
3. `verify.py --gate A --output <本门qualification01目录> --qualify`：干净提交重建、完整测试，自动收据绑定已有有限授权，不扩大权限。
4. `runner.py --gate A --execute --source-head <该干净提交完整SHA> --qualification <本门evidence.json>`：仅新A9，任一必需失败立即停止，精确恢复原参数。
5. `replay.py --gate A --output <本门全新replay01目录> --finalize`：完整九轮独立回放与六配对复算后才生成gate_pass；旧数据指纹保持。

B/C/D依次开放生产掩码、回归、冻结新的本门源码后才重复对应门流程。每门必须九轮同一源码/固件。前门通过凭原始证据重算，不信任单个布尔标志。

真实日志在 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision01/`。仓库只保存小型清单/指纹/摘要和报告，ULog外置。结果记录在 `reports/R03.md` 后续修订部分；旧报告检查点不可改写成当时通过。

新三文档快照在 `plan/r03_revision01_entry`。资格还包含旧失败ledger/journal指纹、旧源码不可修改检查；R04/R05仍为54/200且当前未开始。
