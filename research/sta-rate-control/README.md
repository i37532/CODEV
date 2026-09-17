# PX4 STA 研究目录

日常操作入口：[sim_scripts 中文说明](../../sim_scripts/README_CN.md)。三个入口：`start.sh` 启动Gazebo，`switch.sh pid|esta|ista` 选择算法，`fly.sh hover|figure8|yaw` 自动完成10秒悬停、8字轨迹或定点yaw激励及起降，保留当前仿真窗口供下一轮对比。

已完成 M00～M08 的各阶段限定范围验收。M08开放Iris SITL的MODE=2，按roll→R/P→三轴通过后，同固件PID/ESTA/ISTA各三轮，90项比值均≤1.25；ESTA最大1.233325、ISTA最大1.178393。重启/重载和armed暂存/取消回归通过，80个C++/45个Python用例通过，见 [M08报告](reports/M08.md)、[运行说明](m08/RUN_CN.md)及 [冻结配置](m08/FROZEN_BASELINE.json)。默认仍PID；未执行M09。原始motor_limits仍丢样，不是完整全速TV/频谱数据集。

ISTA初始R/P候选因非命令pitch比值1.315543失败，完整保留。合格候选02仅把ISTA pitch lambda1改成2.0，ESTA仍为M06的2.4，因此不是同增益、纯离散化效应的论文实验。M08之后追加的日常 `sim_scripts/switch.sh ista` 自动加载候选02；M08报告中“日常脚本只支持PID/ESTA”是完成当时的历史状态。日常10秒悬停/8字/yaw任务不等于M08原验收场景，验证记录见 `sim_scripts/_internal/VERIFY_TASKS_CN.md`。

M04 已按用户授权修复 IMU 切换时间戳发布契约；协议 v3 下 PID/ESTA 同固件各三轮通过，最终注释修订构建另各一轮复核。M04 最终独立配置 `m04/iris_esta_roll.json`（lambda1=2.5、lambda2=0.05）达到该小幅场景门槛，五组候选和所有失败均保留。详见 [M04 报告](reports/M04.md)，历史暂停报告另存 `reports/M04_BLOCKED_20260914.md`。

M05 独立标定 g_P=112.763533，开放 AXES=3，组合场景 PID/ESTA 各三次及原 roll 回归各一次通过。45项各轴/窗口RMSE比值全部≤1.25，最大1.246256，接近门槛；起降方向冻结与原始日志丢样均保留。见 [M05 报告](reports/M05.md)、[双轴运行说明](m05/RUN_CN.md)。这是 Iris 仿真结果，不是 DP1000 实机或正式论文验证。

M06独立标定gY=34.582326，开放AXES=7且正常运行不计算闲置PID；1/3/7、重启重载与disarm切换回归通过。冻结 [三轴参数基准](m06/FROZEN_BASELINE.json)，复现见 [三轴运行说明](m06/RUN_CN.md)。三组候选、v1/v2场景与全部失败均保留；不覆盖旧v1自动航向重捕获、强yaw饱和或实机任务。

M07历史阶段新增当时未链接至飞行控制路径的 `IstaRateControl`，采用有理化求根、double中间运算、float可表示范围及隐式方程校验。73个C++、39个Python用例，6011个独立参考样本、36组独立对象闭环通过；理想/扰动/噪声/饱和结果分开记录，MATLAB未运行。M08已经链接该内核；当前总回归请用 `python3 research/sta-rate-control/scripts/verify_m08.py --output <新的绝对路径>`。M07旧入口保留历史“不得链接ISTA”断言，只适用于M07提交。

- `plan/`：M00 开始时三份外部计划的历史快照。
- `environment.md`：环境、模型、参数与启动约定。
- `baseline/`：版本指纹、参数和指标摘要；不存大型日志。
- `reports/M00.md`：验收、失败记录、限制及下一步边界。
- `reports/M01.md`、`m01/`：选择框架、逐样本等价回归和 SITL 证据。
- `reports/M02.md`、`m02/`：ESTA 公式/单位、11 个内核单测、27 组独立对象闭环及 PID 回归证据；MATLAB 未执行。
- `reports/M03.md`、`m03/`：公共保护、真实更新序号/实际 PID 消费的 mixer 反馈、高频诊断与原始话题丢样统计；30 个 C++、8 个 Python 用例和最终 PID 60.440 s 悬停证据。
- `reports/M04.md`、`m04/`：roll 标定、协议修订、五组候选、上游 IMU 修复、44 个 C++/17 个 Python 用例、六轮比较和最终构建复核；复现使用 `run_m04.py`、`analyze_m04.py`、`compare_m04.py`。
- `reports/M05.md`、`m05/`：pitch 标定、独立参数、R/P 激励及交叉轴验收；51 个 C++/21 个 Python 用例、六轮组合对照与两个 roll 回归；使用 `run_m05.py`、`analyze_m05.py`、`compare_m05.py`。
- `reports/M06.md`、`m06/`：三轴ESTA与参数冻结，yaw标定及坐标变换/耦合/重启验证。
- `reports/M07.md`、`m07/`：ISTA纯内核、数值域及独立对象验证的历史证据。
- `reports/M08.md`、`m08/`：ISTA共用保护/日志接入、逐轴门槛、同固件九轮比较、失败候选、三模式配置与生命周期验证。
- `M04_RUN_PLOTJUGGLER_CN.md`：Gazebo/PX4 启动、PID/roll ESTA 切换、三轮自动对比及 PlotJuggler 曲线选择快速指南。
- `scripts/`：SITL 捕获、ULog 分析及证据索引生成器。

M02 算法验证入口：`python3 research/sta-rate-control/scripts/verify_m02.py --output <新的绝对路径>`。它构建 SITL 固件、执行并核对共 20 个相关 GTest，不启动 Gazebo、不驱动执行器。双精度期望值生成器及可选 MATLAB 对照入口见 M02 报告。原始数据独立保存在 `/home/yr/Desktop/codev doc/experiments/M02-20260912`，由 `m02/artifacts.sha256` 索引。

上述 M02 入口包含 M02 历史提交的“算法未链接”约束；M03 已链接保护观察器，应使用 M03 报告的 CTest 命令回归内核。M03 飞行入口为 `run_m03.py --output <新的绝对路径>`，之后执行 `analyze_m03.py <该目录>`；原始数据在 `/home/yr/Desktop/codev doc/experiments/M03-20260913`，91 份指纹见 `m03/artifacts.sha256`。脚本暂时添加 HIGH_RATE 日志位，并在悬停时修改未启用的实验参数验证 pending，结束恢复；全程仍是 PID。中止机制只关闭自有 SITL，不适用于实机安全处置。

## 复跑一轮（仅本机 Gazebo SITL）

先阅读 environment.md，检查没有其他仿真、QGC 或实机链路。沿用当前冻结的 Iris 参数；不要导入 DP1000 参数，也不要使用全局 param reset。原始 EEPROM/导出 BSON 和 ULog 参数快照保存在每次运行目录，复跑前应核对与基线参数是否一致；若参数不同，输出不能直接当同配置对照。

```bash
cd /home/yr/Desktop/Codev-autopilot
python3 -m pip install --target '/home/yr/Desktop/codev doc/experiments/M00-20260912/python' -r research/sta-rate-control/requirements-m00.txt
export PYTHONPATH='/home/yr/Desktop/codev doc/experiments/M00-20260912/python'
python3 research/sta-rate-control/scripts/run_m00.py --output '/home/yr/Desktop/codev doc/experiments/M00-replay-01'
python3 research/sta-rate-control/scripts/analyze_m00.py '/home/yr/Desktop/codev doc/experiments/M00-replay-01'
```

已安装上述固定依赖时跳过安装。输出目录必须不存在；每一轮单独启动/退出，不覆盖历史。先按 environment.md 编译固件。脚本失败退出非零并保留日志；只限仿真，失败清理可能终止空中的模拟实例，不具备实机安全降落保障。

运行器保存本次子进程 PID、源码 SHA、二进制 SHA、运行器 SHA、跟踪文件补丁、CLI 返回码、阶段时间、参数和仅本次新增的 ULog。分析器独立核查 ULog 哈希和状态。指标时间窗为记录的 hover_start 至 hover_end，设定值使用最后已发布值对齐；不同话题频率不同，不能视为同步全速测量。

## 数据归档与版本规则

本次原始数据根目录为 `/home/yr/Desktop/codev doc/experiments/M00-20260912`。`build/` 是构建/单测原始输出；`runNN/` 是成功或失败试验的控制台、命令、ULog、参数、指标。所有失败都保留，报告同时说明调试尝试总数和冻结场景的重复次数。Python 依赖缓存不作为实验数据提交。

M01 数据独立保存在 `/home/yr/Desktop/codev doc/experiments/M01-20260912`。`run_m01.py --output <新目录>` 复用 M00 启动器，并增加起飞前、悬停中及 disarm 后的实际参数检查；随后运行 `analyze_m01.py <该目录>`。它会暂时设置两个新选择参数，验证拒绝/等待/取消行为，最后恢复 `MODE=0、AXES=0`，全程实际仍为 PID。默认无检查回调时 `run_m00.py` 保持原场景；其历史版本及指纹保留在 M00 提交中。

M00 提交包含研究目录的小型文本和 JSON；M01 另包含选择框架与单测源码。`baseline/artifacts.sha256`、`m01/artifacts.sha256` 分别索引各阶段外部证据。Git 克隆本身不含大型 ULog，迁移/共享论文数据时必须另行复制并校验原始数据；原始数据没有上传。脚本 `capture_m00_provenance.py` 是一次性现场采集工具，不要在新 HEAD 上覆盖历史 provenance。外部状态表后续变化不会改变历史计划快照的含义。
