# Proper-ISTA 速度对象离线试验

本工具比较 R-STA、R-ISTA、Proper-ISTA 的纯数学核；**不是速度模式切换脚本，不会启动 Gazebo、写参数或驱动执行器**。当前速度 MODE4 仍是 R-ISTA。

结论见 [离线报告](../reports/PROPER_ISTA_PROBE.md)：Proper 的理想抗扰关系复现，但当前共同增益下加入滞后后误差、输出TV明显增加，不能直接作为速度飞行合格配置。保留原 R-ISTA、生产默认值和旧验收结果。

## 使用

仓库根目录执行。默认仅打印清单：

```bash
cd /home/yr/Desktop/Codev-autopilot
python3 -B research/sta-velocity-control/proper_ista_probe/probe.py
```

显式运行144条独立标量对象轨迹；每次输出目录必须不存在，不能覆盖历史：

```bash
python3 -B research/sta-velocity-control/proper_ista_probe/probe.py \
  --execute \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-PROPER-20261024/PROBE/my_new_attempt'
```

需要系统 `g++`、Python3标准库及既有 `build/px4_sitl_test` 测试目录。不需要 MATLAB、Gazebo 或额外Python包。新桥接与三个纯核用C++14重新编译；既有 CTest 目标只是重新执行，不重建整机。

独立重算逐步数据的指标和指纹：

```bash
python3 -B research/sta-velocity-control/proper_ista_probe/analyze.py \
  --summary '/home/yr/Desktop/codev doc/experiments/VELOCITY-PROPER-20261024/PROBE/my_new_attempt/summary.json' \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-PROPER-20261024/PROBE/my_new_replay'
python3 -B research/sta-velocity-control/proper_ista_probe/test_analysis.py -v
```

只核验本次保存的173文件档案、源码指纹、摘要、文档链接和分析器测试，不重跑模型或飞行：

```bash
python3 -B research/sta-velocity-control/proper_ista_probe/verify_results.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-PROPER-20261024/PROBE/my_new_checks'
```

此命令需要原外部档案仍在记录的路径，输出目录同样必须是新目录。

## 文件和解释

- [冻结协议](PROTOCOL_CN.md)：算法、单位、144条清单、36秒及12–36秒窗口、参考和门槛。参数未搜索；不是公平调参后的最终比较。
- `kernel_bridge.cpp`：链接未修改的实际C++核。Proper仅在离线使用g=1作恒等映射，不代表实机输入增益。
- `probe.py`：默认dry-run；独立double参考及独立ZOH/滞后对象。Proper无边界层，不能与R系列同ε表述。
- `test_probe.py`、`kernel_bridge_test.cpp`：单步、边界、残差、状态和接口检查。
- `analyze.py`、`test_analysis.py`：逐轨迹指纹和独立指标复算。
- [结果摘要](results/summary.json)、[原始证据入口](results/archive_reference.json)、[工具修订记录](PREPARATION_CN.md)。

`success=true`表示预定诊断和机制检查完成，**不表示144条均收敛**：最终132条运行36秒，12条零扰极小数触发原核拒绝并停止；完整轨迹中另有12条预定控制能力不足的反例。`status`、`seconds`、`stop`必须同时查看，不能把部分尾窗当完整窗口。TV/s按各窗口内实际相邻更新计算，不包含人为初始零指令，不代表能耗。

本轮停止在离线筛选。若继续，先研究当前增益的滞后/噪声适用范围、极小数处理及保护/HTE映射，再另行冻结接入与SITL协议；没有自动飞行入口。
