# M08：PID / ESTA / ISTA 仿真复现

仅限本仓库 Iris Gazebo SITL，不能直接用于 DP1000 实机。开发验收结果及限制以 [M08 报告](../reports/M08.md) 为准。默认固件仍 PID；实验配置显式加载。

## 1. 准备

关闭其他 PX4/Gazebo 实例及 QGC/实机链路。以下自动实验自己启动并关闭 Gazebo，**不要先手动启动第二个实例**。输出目录必须是新的绝对路径。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
make px4_sitl_default
```

环境沿用既有本地 Python 依赖；第一条设置 Python 模块搜索路径，第二条优先使用该目录的构建工具。大型 ULog 不在 Git 中，旧基线/阶段门槛数据需要独立复制并验证指纹。

## 2. 三种模式各独立运行一轮

每轮均执行起飞 → 60 秒悬停（含先 yaw、后三轴小幅激励）→ 降落上锁 → 地面切换/复位检查。不是日常脚本的 10 秒悬停或 8 字任务。原位置/姿态环和推力来源保留，只有已有 `mc_att_control` 发布角速度设定值。

PID：

```bash
M08_MODE=0 M08_SCENE=rpy \
M08_CONFIG="$PWD/research/sta-rate-control/m08/iris_pid.json" \
python3 research/sta-rate-control/scripts/run_m08.py \
  --output '/home/yr/Desktop/codev doc/experiments/M08-replay-pid01'
python3 research/sta-rate-control/scripts/analyze_m08.py \
  '/home/yr/Desktop/codev doc/experiments/M08-replay-pid01'
```

ESTA，沿用 M06 冻结增益：

```bash
M08_MODE=1 M08_SCENE=rpy \
M08_CONFIG="$PWD/research/sta-rate-control/m08/iris_esta_rpy.json" \
python3 research/sta-rate-control/scripts/run_m08.py \
  --output '/home/yr/Desktop/codev doc/experiments/M08-replay-esta01'
python3 research/sta-rate-control/scripts/analyze_m08.py \
  '/home/yr/Desktop/codev doc/experiments/M08-replay-esta01'
```

ISTA，候选 02（不要误用保留的初始失败候选）：

```bash
M08_MODE=2 M08_SCENE=rpy \
M08_CONFIG="$PWD/research/sta-rate-control/m08/iris_ista_rpy_candidate02.json" \
python3 research/sta-rate-control/scripts/run_m08.py \
  --output '/home/yr/Desktop/codev doc/experiments/M08-replay-ista01'
python3 research/sta-rate-control/scripts/analyze_m08.py \
  '/home/yr/Desktop/codev doc/experiments/M08-replay-ista01'
```

**必须显式提供 `M08_CONFIG`。** 为保留最初实验来源，运行器原默认文件仍是候选 01。候选 02 仅 ISTA 的 pitch lambda1=2.0，ESTA 仍是 2.4；不是同增益、只比较离散化效应的论文实验。

逐轴复跑配置：roll 使用 `M08_SCENE=roll` 和 `iris_ista_roll.json`；R/P 使用 `M08_SCENE=rp` 和 `iris_ista_rp_candidate02.json`。MODE 都为 2。它们分别复用 M04/M05 场景，不能把不同场景的 RMSE 直接混作三轴对照。

需要观察图形时，在自动运行期间的另一个终端执行 `GAZEBO_MASTER_URI=http://127.0.0.1:11345 gzclient`，不要启动第二个 PX4 或 gzserver。下一轮前关闭 gzclient，否则启动器会因发现现有 Gazebo 进程而拒绝继续。GUI 不决定是否通过，验收以日志为准。

## 3. 完整开发回归

离线构建、80 个 C++ / 45 个 Python 用例及独立参考：

```bash
python3 research/sta-rate-control/scripts/verify_m08.py \
  --output '/home/yr/Desktop/codev doc/experiments/M08-replay-offline01'
```

三模式各三轮（需要本机已通过的逐轴门槛文件和其引用的原始数据）：

```bash
python3 research/sta-rate-control/scripts/run_m08_batch.py \
  --output '/home/yr/Desktop/codev doc/experiments/M08-replay-nine01' \
  --roll-gate '/home/yr/Desktop/codev doc/experiments/M08-20260917/gate_roll.json' \
  --rp-gate '/home/yr/Desktop/codev doc/experiments/M08-20260917/gate_rp_c02.json'
```

批次固定源码/固件指纹，任意失败停止并保留数据，不自动挑选重试。最后生成 `comparison.json`，逐轮/轴/窗口对照三次 PID 中位数，阈值为 1.25。不能只挑总体平均值。

实际重启/保存/重载及 disarm 切换（全程不解锁）：

```bash
python3 research/sta-rate-control/scripts/verify_m08_restart.py \
  --output '/home/yr/Desktop/codev doc/experiments/M08-replay-restart01'
```

独立 armed 暂存/取消飞行（不计入恒定请求性能九轮）：

```bash
M08_CONFIG="$PWD/research/sta-rate-control/m08/iris_ista_rpy_candidate02.json" \
python3 research/sta-rate-control/scripts/run_m08_lifecycle.py \
  --output '/home/yr/Desktop/codev doc/experiments/M08-replay-lifecycle01'
python3 research/sta-rate-control/scripts/analyze_m08_lifecycle.py \
  '/home/yr/Desktop/codev doc/experiments/M08-replay-lifecycle01'
```

运行结束检查 `result.json` 的 success 和参数恢复记录，不把退出/零力矩视为安全降落。故障中止只处理自有 SITL 实例；禁止用于实机。M07 的旧总验证脚本包含“ISTA 不得链接”的历史断言，在 M08 请用上述新入口。

## 4. 查看哪些日志

PlotJuggler 打开每轮 `result.json` 中 SHA 对应的 research ULog，优先查看 `sta_rate_ctrl_status`：

- 模式：`requested_mode/effective_mode`、`effective_axes`、`pending/config_pending/config_seq`；armed 修改不能改变有效算法/增益。
- 跟踪：三轴 `rate/rate_sp/s`，同时看 `research_*_addition` 和 `research_elapsed`，区分命令轴与非命令轴。
- 理想 ISTA：`nu_before/nu_candidate`、`a_raw/c_raw`、`xi/virtual_state/ista_branch`。分支 1/2/3 为正/滑动/负；255 为不适用。
- 真实保护：`nu/a_protected/c_applied/limits`。`nu` 是已提交状态；`c_applied` 是归一化发出指令，**不是物理电机力矩**。不能用受保护输出证明理想三个隐式方程。
- 生命周期：`reset_reason/fault/abort_requested/output_valid`、`landed/maybe_landed/armed`，以及 `pid_updated/pid_update_seq`（全轴 ESTA/ISTA 正常 armed 时不应更新 PID）。
- 时间/采样：`timestamp_sample/raw_dt/update_seq/motor_update_seq`；配合 `gyro_sample_status`、姿态/高度数据。原始 `motor_limits` 可能丢样，ULog dropout=0 不等于每个话题全速。

各限制/故障位定义见源码 `StaProtection.hpp` 和 [M04 查看指南](../M04_RUN_PLOTJUGGLER_CN.md)。定量比较以分析器固定窗口为准，不以画面稳定或平滑曲线替代验收。
