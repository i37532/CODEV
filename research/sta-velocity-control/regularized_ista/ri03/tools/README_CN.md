# RI03：X 单轴开发运行器

只执行 RI03 冻结的 PID / R-STA / R-ISTA 各三次、合计九次 Iris SITL 开发实验。
MODE 分别为 0/3/4，AXES 分别为 0/1/1；DIV=1，位置 P、Y/Z 速度 PID、姿态和角速度 PID 保持。
不是调参工具，不运行旧 ESTA、Z/XY/XYZ、正式留出或实机。

## 使用

在仓库根目录执行，Python 需要项目原有 numpy、pymavlink、pyulog 依赖：

```bash
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 -B research/sta-velocity-control/regularized_ista/ri03/tools/runner.py --gate A
```

上面只显示清单，不写参数、不创建实验目录、不启动任何仿真。
执行前必须先完成上一级 protocol/freeze/verify 流程，在干净已提交的源码上获得实际非零测试和 SITL 构建资格。
只有明确传入本次完整源码 SHA 和资格文件才进入执行：

```bash
python3 -B research/sta-velocity-control/regularized_ista/ri03/tools/runner.py \
  --gate A --execute --source-head FULL_40_CHARACTER_SHA \
  --qualification /absolute/RI03/A/qualification01/evidence.json
```

九次全部接受后，独立进程逐轮重解码并检查六个配对结果：

```bash
python3 -B research/sta-velocity-control/regularized_ista/ri03/tools/replay.py \
  --gate A --output /absolute/RI03/A/replay01 --finalize
```

路径必须属于正式协议规定的新 RI03 gate，不能把历史结果改标签后放入新矩阵。
回放不启动飞行，逐值/类型检查完整 metrics，一致性包括频谱文件指纹；不能只相信原来的 accepted 标志。

## 执行和日志边界

- 完整 BSON 参数备份；每次启动前写入明确参数并读回，每次退出后先确认进程停止再恢复全部原始字节。保留原日志配置位，再 OR 所需采样位。
- 复用最终 revision11 的项目启动器、唯一目标源、相对完整日志预热 30 秒、增量读取、双时钟白名单、同刻组、完整 reset/边界及降落尾窗。
- 私有加载按 runtime-first 顺序，明确固定 V08/protocol02 RAM 记录器，避免同名 V07 模块遮蔽；不改旧模块全局变量或文件。
- 保持既有 500 ms、新鲜度、物理、配对风险、保护和数值界限。MODE4 的 p / 理想输出 / nu 候选、限幅冻结后应用值及真正发布输出独立核对，不把 MODE4 重命名成 MODE3。
- 尝试一经登记即消耗预算。首个安全、日志有效性或预定开发风险失败立即停批，保留失败、恢复参数、列出未执行项；没有重试、补飞、换种子或追加调参入口。
- 固定九次 / 六个对 PID 的配对检查，不要求 R-ISTA 必须胜过其他算法。开发通过不等于论文统计显著。

## 离线工具回归

```bash
python3 -B research/sta-velocity-control/regularized_ista/ri03/tools/verify_tools.py \
  --output /absolute/RI03/tools_attempt_NEW
```

测试包含完整新模式数学接线负例、错模式/轴/角速度内环、时钟/缺样/未接管、CLI 元数据读回、九轮调度及失败即停。
完整参数事务用临时目录与假后端调用**实际运行器事务**；不操作真实 EEPROM，也不能代替真正的飞行日志验收。
工具测试的测试种子仅为临时 fixture，正式种子登记由上一级协议唯一管理。
