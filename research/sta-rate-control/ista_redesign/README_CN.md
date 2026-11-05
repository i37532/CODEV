# ISTA 后续研究（I 系列）

本目录与历史 M00–M10、ISTA-OPT01/02 并列，不替换它们。原 `MODE=2` 算法含义不变。

- [新计划快照](plan/ISTA_REDESIGN_TODO_CN.md)、[逐阶段提示词](plan/ISTA_REDESIGN_PROMPTS_CN.md)：保留 I00 开始时原始内容的快照，状态不随外部进度表更新。
- [I00 报告](../reports/I00.md)：原 ISTA 受扰偏差的离线审计与生产内核回归。
- [理论与代码审计](i00/THEORY_AUDIT_CN.md)、[离线规格](i00/PROTOCOL_CN.md)、[证据摘要](i00/results/evidence.json)。

- [I01 报告](../reports/I01.md)、[Proper-ISTA 离线内核与复跑入口](i01/README_CN.md)：新内核已实现并离线验证，未连接执行器。
- [I02 报告](../reports/I02.md)、[保护/起飞状态离线复跑入口](i02/README_CN.md)：保护映射和默认关闭的起飞状态管理已离线验证。
- [I03 冻结协议与运行入口](i03/README_CN.md)：ESTA/原 ISTA × 旧/新起飞保护的 2×2 隔离消融；Proper-ISTA 仍不接执行器。
- [I03 报告](../reports/I03.md)：12/12 飞行完成、10/12 通过；新增管理存在机载高度漂移导致的提前释放，后续共同基准保留既有保护。

当前原 MODE=0/1/2 不变；Proper-ISTA 仍无执行器路径。I03 新增默认关闭且仅限 Iris SITL 研究的
`MC_STA_TKO_MGT` 参数，只有冻结协议中的正式消融可将其设为 1。

## 重复离线检查（不启动 Gazebo）

在仓库根目录执行。每个输出目录必须不存在；示例 `replay01` 若已存在，请另取新名字，不能删除重用。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"

python3 research/sta-rate-control/ista_redesign/i00/verify.py \
  --output '/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I00/replay01/scalar_verification'

python3 research/sta-rate-control/scripts/verify_m09.py \
  --output '/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I00/replay01/regression'

python3 research/sta-rate-control/ista_redesign/i00/analyze_logs.py \
  --root '/home/yr/Desktop/codev doc/experiments/ISTA-OPT02-20260918/run01' \
  --output '/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I00/replay01/historical'

sha256sum --check --quiet research/sta-rate-control/ista_redesign/i00/results/artifacts.sha256
```

第一次命令构建离线共享库，真实调用原 C++，执行 13 项工具测试和 138 组对象；第二次回归既有控制器/保护/时序并构建 SITL，不飞行；第三次需要外部旧日志，缺失时不能称解码通过。

`package_evidence.py` 是本机 run01 布局的归档入口，明确读取 attempt01/regression/historical02，不是任意实验的自动选优器。它输出新目录，不覆盖已提交证据。原始 NPZ、PDF 与构建产物位于外部索引中，不随 Git 克隆下载。
