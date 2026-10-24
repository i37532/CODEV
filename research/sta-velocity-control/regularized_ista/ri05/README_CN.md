# RI05 工具：先 XY，再 XYZ

这是有限18次开发验证，非一键无限重飞。内部 C 对应本阶段 A/XY（H/TEST6）；D 对应 B/XYZ（V/TEST8）。先看 PROTOCOL_CN.md 与 AUTHORIZATION_CN.md。

在仓库根设置项目Python依赖后：

```bash
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python"
python3 -B research/sta-velocity-control/regularized_ista/ri05/tools/runner.py --gate C
```

默认只显示准确九轮清单，不写参数、不起进程、不飞行。执行需已经冻结提交、干净本门固件和verify.py生成的实际资格，再显式传 --execute --source-head 完整SHA --qualification 证据路径。D额外核验本专项C真实9接受/9回放/6配对，不能用旧XYZ成功替代。

独立回放：tools/replay.py --gate C --output 新外部目录；--finalize仅在全部核验通过后首次生成gate_pass。原始日志/参数/目标/失败不覆盖，已存在batch拒绝重跑。每门首败停批。

生产改动仅准入及回归；算法/参数/模型/数值规则不变。不加载仅离线Z增益候选或Proper-ISTA，不push、不进入RI06。
