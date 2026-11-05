# RI01 最终小证据

`evidence.json` 是外部 verification03 原样副本，记录57条实际子命令及退出码、输入SHA、517个唯一C++测试身份和隔离证据；38份XML来自实际测试。`submodules.log`/`submodule_status.log`保存入口33个递归子模块版本与内部干净检查。

`artifacts.json` 路径相对于外部 `verification03/`，包含该次完整输出指纹。`external_artifacts.json` 路径相对于其 `root`，覆盖当时RI01全部8个尝试目录及失败。大文件不纳入Git，不能用仓库小证据替代原始数据。

只读重核全部497个外部文件（不运行实验）：

```bash
python3 -B research/sta-velocity-control/regularized_ista/ri01/archive.py \
  --evidence-dir '/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI01' \
  --output research/sta-velocity-control/regularized_ista/ri01/results --verify
```

对象摘要另见 [最终对象证据](../model/results/verification03/summary.json)。84条完整60秒、18条数值域停止，以及6条不可行限幅反例不得合称102条跟踪通过。
