# M05 双轴对比执行入口

仅适用于已构建的本仓库 Iris SITL；是否通过以 `reports/M05.md` 和比较程序的实际结果为准。M04 使用指南仍可用于 Gazebo/PlotJuggler 基本操作，以下补充双轴配置。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH='/home/yr/Desktop/codev doc/experiments/M00-20260912/python'
export M05_DATA='/home/yr/Desktop/codev doc/experiments/M05-new-replay'
mkdir -p "$M05_DATA"
for M05_RUN in 01 02 03; do
  M05_MODE=0 python3 research/sta-rate-control/scripts/run_m05.py --output "$M05_DATA/pid$M05_RUN" || exit 1
  python3 research/sta-rate-control/scripts/analyze_m05.py "$M05_DATA/pid$M05_RUN" || exit 1
done
for M05_RUN in 01 02 03; do
  M05_MODE=1 python3 research/sta-rate-control/scripts/run_m05.py --output "$M05_DATA/esta$M05_RUN" || exit 1
  python3 research/sta-rate-control/scripts/analyze_m05.py "$M05_DATA/esta$M05_RUN" || exit 1
done
python3 research/sta-rate-control/scripts/compare_m05.py \
  --pid "$M05_DATA/pid01" "$M05_DATA/pid02" "$M05_DATA/pid03" \
  --esta "$M05_DATA/esta01" "$M05_DATA/esta02" "$M05_DATA/esta03" \
  --output "$M05_DATA/comparison.json"
```

先确认 PID 三轮都通过，再运行 ESTA；循环提前退出时应检查失败日志，保留目录。子目录必须不存在；重复运行请使用新数据根。脚本会核对模型指纹、记录参数、以 147 日志 profile 捕获、恢复参数并关闭自己的 SITL。内部共享 `m04_config.json / m04_protocol.json / m04_analysis.json` 文件名；以协议内 `milestone=M05`、`trigger=2` 及实际轴掩码识别，不能与 M04 六轮混合。

手动加载参数时，先启动 `./sitl/run.sh --backend gazebo --model iris`，确保未解锁，再逐项设置 `iris_esta_rp.json` 中的全部参数，最后设置 AXES=3、MODE=1。同时使用协议内两项 .3 降落参数；`listener sta_rate_ctrl_status -n 1` 应显示 `effective_mode=1, effective_axes=3, fault=0, config_valid=True, pending=False`。不要飞行中切换。回到 PID 设置 MODE=0、AXES=0，实验激励设置 MC_RATT_TEST=0。

稳定 AUTO_LOITER 后，`param set MC_RATT_TEST 2` 触发 36 秒组合序列：`research_elapsed` 的 `[0,12)` 为 roll，`[12,24)` 为 pitch，`[24,36)` 为同步 R/P。两轴均采用 .04/.08/.12 rad/s 正负完整正弦。yaw 与推力来自原外环。自动脚本统一等待悬停 15 秒再触发。

PlotJuggler 首选 `sta_rate_ctrl_status` 的 `rate[0/1/2]`、`rate_sp[0/1/2]`、`s[0/1/2]`，结合 `research_roll_addition`、新增 `research_pitch_addition` 和 `research_elapsed` 对齐阶段。检查两轴各自 `nu_before/nu/a_raw/c_raw/c_applied/limits`；`nu[2]` 必须保持零。有效轴应为3，mode为1，`fault/abort_requested` 为0。高度查看 local_position 的 z 与 setpoint.z，yaw 姿态误差已由分析程序按角度环绕计算。

`comparison.json` 的 `all_axis_esta_ratios` 按 R/P/Y 顺序列出完整悬停、完整跟踪及每阶段比值；`violations` 非空即失败。每个比值均需≤1.25。`all_axes_limits_fraction` 和 `all_axes_mixer_saturation_fraction` 记录冻结与实际消费的方向饱和。原始 motor_limits 仍可能丢样，图形观察不能替代上述验收。
