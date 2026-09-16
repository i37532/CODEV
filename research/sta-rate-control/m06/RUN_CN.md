# M06 三轴 ESTA 的复现入口

只限本仓库 Iris SITL。候选03已通过协议v2开发验收，`iris_esta_rpy.json` 为冻结三轴配置，指纹见 `FROZEN_BASELINE.json`；其他候选保留用于追溯。验收范围见 `../reports/M06.md`。禁止用作 DP1000 实机参数。

## 构建与显示 Gazebo

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
make px4_sitl_default
./sitl/run.sh --backend gazebo --model iris
```

自动实验自行启动并关闭 headless Gazebo，开始前关闭手动仿真和 QGroundControl，不能同时开两台实例。图形界面启动、基础起降及 PlotJuggler 打开 ULog 的说明仍见 `../M04_RUN_PLOTJUGGLER_CN.md`，控制配置以本阶段为准。

## 顺序运行

选择新的输出目录，不要覆盖任何失败数据。先通过测试、原 AXES=1/3 回归和重启检查，再做 yaw 小激励，最后做三轴六轮。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH='/home/yr/Desktop/codev doc/experiments/M00-20260912/python'
export M06_DATA='/home/yr/Desktop/codev doc/experiments/M06-new-replay'
mkdir -p "$M06_DATA"
python3 research/sta-rate-control/scripts/verify_m06_restart.py --output "$M06_DATA/restart" || exit 1

for M06_MODE_VALUE in 0 1; do
  M06_MODE="$M06_MODE_VALUE" M06_YAW_ONLY=1 python3 research/sta-rate-control/scripts/run_m06.py --output "$M06_DATA/yaw$M06_MODE_VALUE" || exit 1
  python3 research/sta-rate-control/scripts/analyze_m06.py "$M06_DATA/yaw$M06_MODE_VALUE" || exit 1
done
for M06_RUN in 01 02 03; do
  M06_MODE=0 python3 research/sta-rate-control/scripts/run_m06.py --output "$M06_DATA/pid$M06_RUN" || exit 1
  python3 research/sta-rate-control/scripts/analyze_m06.py "$M06_DATA/pid$M06_RUN" || exit 1
done
for M06_RUN in 01 02 03; do
  M06_MODE=1 python3 research/sta-rate-control/scripts/run_m06.py --output "$M06_DATA/esta$M06_RUN" || exit 1
  python3 research/sta-rate-control/scripts/analyze_m06.py "$M06_DATA/esta$M06_RUN" || exit 1
done
python3 research/sta-rate-control/scripts/compare_m06.py \
  --pid "$M06_DATA/pid01" "$M06_DATA/pid02" "$M06_DATA/pid03" \
  --esta "$M06_DATA/esta01" "$M06_DATA/esta02" "$M06_DATA/esta03" \
  --output "$M06_DATA/comparison.json"
```

AXES=1 回归：`M04_MODE=0/1` 分别调用 `research/sta-rate-control/scripts/run_m04.py --output 新目录`，同时设置 `M04_CONFIG="$PWD/research/sta-rate-control/m06/iris_esta_roll_candidate03.json"`，解码用 `analyze_m04.py 目录`。AXES=3 同理使用 `M05_MODE=0/1`、`run_m05.py`、`analyze_m05.py`，设置 `M05_CONFIG="$PWD/research/sta-rate-control/m06/iris_esta_rp_candidate03.json"`。这里的0/1表示分开执行两次，不是直接输入的值；不指定CONFIG将使用历史M04/M05参数，而非本阶段冻结增益。不要把这些不同协议的日志混进 M06 六轮比较。

脚本记录源 HEAD/补丁/固件和日志哈希，每轮起飞—60秒悬停—降落上锁；上锁后先关闭该轮 ULog，再以 CLI 留存 1→3→7→PID 的模式切换和 nu=0 检查；最后恢复原参数并保存。若提前退出，检查 result.json、console.log、分析器错误和恢复参数文件后再继续，不能忽略失败。

## 手动配置与诊断

确保 disarmed，按 `iris_esta_rpy.json` 的顺序设置全部 12 项 R/P/Y 参数，最后 `MC_STA_AXES=7`、`MC_RTC_MODE=1`；同时采用v2协议中的 `MPC_LAND_SPEED=.3`、`LNDMC_Z_VEL_MAX=.3`、`MPC_YAW_MODE=3`。该航向模式在本静止悬停区域保持原航向，避免原mode=0自动航向重捕获引入额外±.785398前馈；两算法使用相同场景，结束恢复原值0。确认 `listener sta_rate_ctrl_status -n 1`：effective_mode=1、effective_axes=7、config_valid=True、pending=False、fault=0。回 PID 必须先降落上锁，再设置 MC_RTC_MODE=0、MC_STA_AXES=0、MC_RATT_TEST=0。不要空中切换或把 SITL 中止当成实机安全接管。

稳定悬停后 trigger=3 是 36秒仅 world-yaw 激励；trigger=4 是先12秒 yaw，再24秒三轴同步。重新触发必须先设置 MC_RATT_TEST=0，再设置3或4。yaw 世界轴注入会随姿态变换成机体三轴分量，不能把 R/P 上的这部分分量误判成重复发布者。

PlotJuggler 优先查看 sta_rate_ctrl_status：三轴 rate/rate_sp/s、nu_before/nu、a_raw/c_raw/c_applied、g/lambda1/lambda2、limits；用 research_elapsed 与 roll/pitch/yaw_addition 对齐窗口。AXES=7 时 pid_updated 应始终 false，pid_update_seq 在飞行中不增加；三轴 nu 独立变化。检查 fault/abort_requested/timing_status、motor_saturation/motor_valid、reset_reason、update_seq。高度看 local_position.z 和 setpoint.z；yaw 姿态误差用分析器的环绕角结果。原始 motor_limits 可能丢样，不能仅凭曲线平滑认定通过。

比较程序检查三轴×五窗口×三次，共45个 RMSE 比值，均须≤1.25；无自动修改门槛。yaw 饱和窗口 R/P 响应保存在 yaw_saturation_rp_response。查看报告中所有失败/调参尝试，不应只展示最终合格轮次。
