# R03 A：飞行前准备记录

本文件记录冻结前证据，不是 R03 或 A 门飞行验收报告。R03 起点为
`080528bd30f4a8b7816f5097d789fc71e56ecefe`，分支为
`research/sta-velocity-regularized`；旧研究分支及历史数据保留。

## 范围与门控

生产行为仅在 SITL 的 `PositionControl::configureVelocityControl()` 开放
MODE3/AXES1/DIV1；原 PID 默认值及 MODE1 全掩码不变。
MODE3 其余掩码仍拒绝。新增/更新测试覆盖实际模块输出、参数重启、
armed 暂存/取消、disarm/reset、无效配置、同 sample failsafe 和时钟。
位置 P、姿态、rate PID、传感器、估计器、land detector、原模型默认值不改。

`execution.json` 固定 36 次、四门各 9 次，`manifest.json` 为准确顺序，
`outcomes_unattempted.json` 是注册时快照，不能用来表示后续真实结果。
12 个种子初查 56433 份 JSON，无冲突；运行前再次查当前门历史。
协议、参数、运行器、分析器及模型依赖由每门 `frozen.json` 固定；
实际源码/二进制由提交后的干净资格绑定，不用旧资格冒充新源码。

## 已实际完成的离线检查

外部根目录：
`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03/A/`。

- `verification01/evidence.json`：32 条顶层命令全部退出 0；475 个不同
  C++、820 个 Python 测试；旧 PID/ESTA 路径 32768 对主样本和 256 对
  同 sample 重算一致；571 个输入指纹首尾一致。
- 实际执行 `make px4_sitl_default -j4` 和
  `DONT_RUN=1 make px4_sitl_default gazebo_iris -j4`，均退出 0。
  这是构建，不是飞行；当时工作区有本阶段改动，不能作为干净源码资格。
- 33 个递归子模块版本及工作区保持；持久参数 BSON 原样保持。
- verification01 后补强独立回放配对门槛复算，`test_replay.py` 25 项、
  `test_protocol.py` 34 项退出 0。新增 5 项未计入上述 820；
  提交后仍须对最终全部文件重新统一验证，实际计数以 qualification 为准。
- 之后补强运行器严格 JSON 类型绑定，`test_runner.py` 27 项退出 0，
  防止程序调用把 bool/浮点当成整数协议而晚到飞行后才拒绝；该修订同样
  在 verification01 之后，最终干净资格统一复验，不冒称首轮已覆盖。
- `target_replay02/summary.json`：六份旧日志目标组件回放通过，覆盖
  H PID/XYZ、V PID/XYZ、旧 X/Z 任务。原日志和输入指纹未变。
  仅验证目标、位置 P、FF 和时钟/下游匹配组件，**不是新控制器准入或
  新飞行通过**；旧 X/Z 只验证其原 60 秒观察中的 32 秒激励。

统一离线命令（首轮不含 `--qualify`）：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/regularized_sta/r03/verify.py --gate A --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03/A/verification01'
```

该目录已存在，不能重跑覆盖；后续干净资格使用新的 qualification01 目录。

## 保留的开发错误及未执行项

首轮旧目标组件回放 `target_replay01` 的 H/V 四例通过、X/Z 两例失败：
旧 job 仅存部分参数，新核对需要实际运行参数。第二轮显式读取并指纹绑定
旧 `runtime_parameters_start.json` 后，六例通过；未放宽门槛、未改旧判。
准备期间出现 Python 路径/平铺模块导入及测试夹具问题，修复后才统一回归；
这些不是飞行尝试，不能当作重飞。首轮失败目录保留。

独立回放拒绝仅靠 true 标记/计数证明通过，须核对原始 ULog、文件指纹，
逐值比较重新解码结果，并从实际指标重新计算每门六对、每对 13 项风险门槛。
真实试验仍可能暴露问题；一轮必需失败即停批，不补飞、不放宽阈值。

截至本准备记录：新飞行 0、MATLAB 未执行、没有实机测试，B/C/D 未开放。
先提交准确协议，再完成干净资格、A 门 9 次与独立回放，才允许进入 B。
