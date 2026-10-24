# RI04：Z 单轴开发门

仅执行本轮已冻结的9次PID/R-STA/R-ISTA开发尝试。新R-ISTA只新增AXES4，保留已验收AXES1，不执行XY/XYZ。范围、波形、参数、阈值和首败停批规则见 [协议](PROTOCOL_CN.md) 与 [授权记录](AUTHORIZATION_CN.md)。

在 `/home/yr/Desktop/Codev-autopilot` 执行；Python依赖沿用项目环境：

```bash
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python"
python3 -B research/sta-velocity-control/regularized_ista/ri04/tools/runner.py
```

不带执行选项仅列清单/预检，不起飞。真实飞行必须先在干净本阶段源码上完成 `verify.py --gate B --qualify --output <新的本门qualification目录>`；路径和固件SHA与本门冻结协议一致。runner 的显式执行入口只消费原9次清单，存在旧批、未通过资格或首败即拒绝继续，不得把此README当追加飞行权限。

本阶段先离线验证、提交源码/协议，然后干净资格、有限批次、独立完整回放、结果提交。数据仅写新的 `/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI04`，仓库留协议/参数/摘要/指纹；旧结果只读，不能借作新样本。

比较目标为真实消费的Z轴速度 `v[2]` 与 `v_sp[2]`（m/s），不是高度。另报告对原位置目标的Z位置误差和相对名义2.5m高度偏离；水平位置/速度及yaw也须满足既有风险门。

没有验收前不能宣称R-ISTA Z可用；通过也仅适用于Iris SITL开发门，不代表实机资格或统计显著性。不push，不自动运行RI05或旧R04/R05。
