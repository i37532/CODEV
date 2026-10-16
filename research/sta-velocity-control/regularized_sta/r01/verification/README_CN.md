# R01 离线验证入口

此入口由主任务统一执行，避免并行构建。同一调用串行运行历史 AX01 功能回归（其中包含 SITL 与 `DONT_RUN=1` Gazebo 构建）、AX02 任务/分析功能测试、新内核、补充 rate 内核/保护及 `VelocityAblationTask` 回归。没有任何启动仿真或实际飞行命令。

```bash
cd /home/yr/Desktop/Codev-autopilot
python3 research/sta-velocity-control/regularized_sta/r01/verification/test_verify.py
python3 research/sta-velocity-control/regularized_sta/r01/verification/verify.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R01/verification01'
```

必须使用尚不存在的外部目录；失败证据保留，修复后用新目录，不能覆盖或把不同尝试拼成一次通过。工具不自动重试、不删除数据、不修改 EEPROM。

## 证据和计数

- `evidence.json` 保存每条 argv/cwd/退出码/耗时、开工 HEAD、输入 SHA、33 递归子模块与 EEPROM 前后指纹。源包完整清单与 R00 原件匹配，旧模型/插件/研究脚本不变。
- 每个 C++ 目标真实执行并产生 XML；非零、完整执行、无 failure/error/skipped/disabled 才通过。按 classname/name/type_param/value_param 唯一身份计数，不累加 AX01/V07 嵌套汇总，不把构建中的重复 CTest 执行当不同测试。
- Python 只读取直接命令日志的独立 `Ran ... tests` 与 `OK`，不累加各层 evidence 的历史总数；AX01 的叶子日志计数须与其报告一致。工具自身单测单列，不称控制器用例。
- 严格独立 `g++ -std=c++14 -pedantic-errors` 编译新核；同时检查实际 CMake compile_commands 的 C++14 标准。
- R00 以来允许的生产改动只有独立内核 cpp/hpp/Test.cpp 和对应 CMake。原 PositionControl、selector、参数、消息、rate、传感器/估计器/land detector/模型均不得改变。源内引用仅允许新核、其测试和 CMake；生产固件符号表必须不含新类，不能仅用“默认 PID”替代不可接管证明。
- `artifacts.sha256` 包含本次输出指纹；输入验证前后再次校验，验证期间修改输入会失败。

保留 V08 `provenance_not_applicable` 明示排除：原“自 V07 生产源码完全不变”断言不适用于已合法演进的分支。AX04 源码/资产冻结资格也不适用于 R01，不能借历史功能回归宣称新源码已获旧飞行资格。未调用 AX02 整体冻结验证、旧种子登记或正式试飞。

ISTA/Proper-ISTA 只作为既有 rate 库回归，未移植新的算法、未开放任何模式。MATLAB、飞行、性能实验不在本入口执行范围。

本文件是执行说明，不预填控制器通过数；以本次主任务实际生成的 evidence/XML 为准。
