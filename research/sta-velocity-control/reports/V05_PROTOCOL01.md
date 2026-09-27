# V05 protocol01：飞行前冻结

日期：2026-09-27。基线 `5cfc2ac088ad458522311659eefff465a219d46d`，分支 `research/sta-velocity-control`，进入时工作区与递归子模块干净；不删除重建分支。
前置 V04 protocol17：6/6、3/3 配对通过；Z03 的独立 Z 路径保留但本阶段不用。
完整读取外部速度计划/共同规则/进度表，原共同规则和指定旧研究报告、日志审计；三份速度计划另存 `v05/plan_snapshot`，不覆盖 v1。

## 本次授权及范围

用户新增指令：“不用要求我授权实验起飞，一直到xy双轴实现为止”。
据此 V05 的常规离线修复、冻结及新 Iris SITL 批次无需逐次询问；仍严格每批六次、首个必需检查失败即停止，不自动补飞、改判失败或放宽数值门槛。
不包含实机、XYZ、V06、ISTA、push 或新的上游控制改造。

## 实现及审查

- 仅新增独立 `_velocityControlEstaXY`；既有 X-only、Z-only 路径保留。默认 PID 数学、位置 P、原加速度映射、Takeoff、HTE/Z PID、姿态与 rate 控制未改。
- selector 接受已配置的 1/3/4，7 和 MODE2 仍拒绝；Y 独立参数默认 0。完整选中轴集合参与 armed 暂存/取消、disarm 生效和 reset。
- XY 无闲置 PID 输出，Z 保留 PID；Z 优先后水平矢量限幅；公共保护预验证两轴后原子提交，逐轴残差冻结不混用 ν。
- 新默认关闭 TEST3 为 X32s/Y16s/XY16s 顺序激励，每窗口正负且零积分；统一时钟/退出 latch。X 保留原波形。
- 新增 `excitation_y`，其余话题和日志规则继承。90s 观测容纳64s激励，旧60s运行器/分析器未修改。
- 新分析链逐轴复算候选/应用状态/FF，逐窗口安全/误差和配对门槛；原定高交接、航向白名单、落地时间匹配仍接入。
- 全轴率 PID 与 XY ESTA + Z PID 是不同环，不能称三轴 ESTA。

## 离线验证（尚非飞行结果）

命令（仓库根目录、原本地 Python 环境）：

```bash
python3 research/sta-velocity-control/v05/protocol01/capture.py
python3 research/sta-velocity-control/v05/protocol01/verify.py --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260927/V05/offline01'
```

两条命令退出码均 0。`offline01/evidence.json`：174 个实际 C++、399 个 Python 用例通过，无禁用测试；SITL 和 Gazebo 构建成功。
C++ 包含旧 PID 逐样本参考、X/Z 回归、独立 XY/原子性/倾角和 Z 推力优先、非单位对象增益/内环及电机滞后/耦合、模式1/3/PID/拒绝7、BSON保存重载、重入和真实模块调参/失败重算/完整波形接线。
Python 386 个旧工具测试 + 13 个新协议测试；新测试包含坏 Y 波形、坏 Y 状态、共享 ν、错误内环、缺样/边界、每窗口非命令轴、预算失败即停和参数恢复。
此前开发中的一次编译失败（double-promotion）、一次非法 shell TESTFILTER 写法和两处测试预期失败均保留日志；修正 C++ 显式类型、命令写法、半NaN退出/reset预期和原倾角 slew 稳定前 ν 冻结预期，没有放宽生产保护。
无 MATLAB、无实机、此时新飞行数为0。提交后必须重建并重复此验收，确认固件版本对应干净源码再飞。

## 准确飞行清单

`v05/protocol01/execution.json` 固定种子 20001/20002/20003，每种子先 PID 后 XY ESTA，共6次，无额外调参。
新外部目录：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260927/V05/paired01`。
候选 X/Y 分别 λ1=1、λ2=0.2、ν界0.4、纠偏界0.8；Z参数0、Z PID，全rate0/0/DIV1，旧起飞管理关闭。
保持灰色空 world、项目 Iris 启动器、原种子插件、2.5m定高固定yaw、共同0.6/0.55降落参数。
种子结构扫描无历史使用；仅自身协议注册排除。噪声前5000行配对相同、跨种子不同方可通过；仅IMU随机源受控。
每窗口原数值门槛与配对规则见 README/execution；若未完成六轮、三对则 V05 不验收。

协议/源码 SHA 由提交后外部进度和最终 V05 报告记录，避免自引用哈希。正式结果另提交。
