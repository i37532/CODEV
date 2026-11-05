# PX4 Gazebo PID / roll ESTA 快速运行与 PlotJuggler 查看指南

本文保留 M04 roll 单轴操作。M05 已增加经过名义 SITL 验收的 AXES=3；双轴参数、36秒组合激励和新增 pitch 曲线请看 [M05运行说明](m05/RUN_CN.md)。下文“当前M04只开放roll”指本文的历史版本范围。

适用仓库：`/home/yr/Desktop/Codev-autopilot`

适用分支：`research/sta-rate-control`

已验证版本：`1ddec5141bd30a836319b83d618eb588f49efdff`
仿真范围：Gazebo Classic、Iris 10016、`empty_grey.world`、roll 单轴 ESTA。**不是 CODEV DP1000 实机配置。**

## 1. 编译

打开终端：

~~~bash
cd /home/yr/Desktop/Codev-autopilot
git switch research/sta-rate-control
git status --short

export PYTHONPATH="$PWD/.px4-python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
make px4_sitl_default
~~~

`git status --short` 没有输出表示工作区干净。首次环境尚未准备好时先运行：

~~~bash
cd /home/yr/Desktop/Codev-autopilot
./sitl/setup.sh
~~~

## 2. 打开 Gazebo 并手动仿真

需要 Gazebo 图形界面时运行：

~~~bash
cd /home/yr/Desktop/Codev-autopilot
./sitl/run.sh --backend gazebo --model iris
~~~

这个终端同时是 PX4 控制台。看到系统完成初始化后，可以输入：

如果准备把这次手动试飞用于 PlotJuggler，先开启与 M04 相同的高频日志。本项目原 profile 为 131，加入 HIGH_RATE 位后为 147：

~~~text
logger stop
param set SDLOG_PROFILE 147
logger start -b 256 -r 1000 -t -f
~~~

然后执行飞行：

~~~text
commander takeoff
commander mode auto:loiter
commander mode auto:land
~~~

顺序是起飞、进入 Hold/Loiter、自动降落。命令被拒绝时，先等 GPS/EKF ready；手动飞行还应保持 QGroundControl 或有效 GCS/RC 连接，避免触发既有链路丢失策略。停止仿真，在 PX4 控制台输入：

~~~text
shutdown
~~~

仅看仿真画面可以使用本节。要公平比较 PID 和 ESTA，建议使用第 4 节自动脚本，因为它会统一起飞、60 秒悬停、激励、降落、日志和参数恢复。

## 3. 手动切换 PID 与 roll ESTA

### 3.1 PID

**必须在 disarmed（未解锁）状态切换。** PX4 控制台输入：

~~~text
param set MC_RTC_MODE 0
param set MC_STA_AXES 0
param set MC_RATT_TEST 0
listener rate_ctrl_selection -n 1
~~~

确认：

- `effective_mode = 0`：PID；
- `effective_axes = 0`；
- `request_status = 0`：请求被接受；
- `pending = false`。

### 3.2 roll ESTA

先确保飞行器已降落并上锁，再按“增益 → 轴 → 模式”的顺序设置：

~~~text
param set MC_STA_L1_R 2.5
param set MC_STA_L2_R 0.05
param set MC_STA_G_R 130.575283
param set MC_STA_NU_R 3.0
param set MPC_LAND_SPEED 0.3
param set LNDMC_Z_VEL_MAX 0.3
param set MC_STA_AXES 1
param set MC_RTC_MODE 1
listener rate_ctrl_selection -n 1
listener sta_rate_ctrl_status -n 1
~~~

确认：

- `effective_mode = 1`：ESTA；
- `effective_axes = 1`：只替换 roll；
- `request_status = 0`、`pending = false`；
- `config_valid = true`、`fault = 0`、`abort_requested = false`。

pitch 和 yaw 仍为原 PID。不要设置 `AXES=3/7`，也不要设置 `MODE=2`：当前 M04 只开放 Iris roll ESTA，其他组合会被拒绝。

需要手动触发与自动场景相同的 roll 激励时，等飞行器在 AUTO_LOITER 稳定悬停后输入一次：

~~~text
param set MC_RATT_TEST 1
~~~

它由原 `mc_att_control` 唯一发布者执行一次固定激励序列。不要再启动第二个 `vehicle_rates_setpoint` 发布者。激励完成后可设置回 0。

飞行中修改模式或实验增益只会进入 pending，不会立即安全切换。**不要用同一次空中飞行比较 PID/ESTA；每次都应降落上锁、重新启动独立场景。**

手动试验结束后恢复默认 PID 和原降落参数：

~~~text
param set MC_RTC_MODE 0
param set MC_STA_AXES 0
param set MC_RATT_TEST 0
param set MPC_LAND_SPEED 0.7
param set LNDMC_Z_VEL_MAX 0.5
logger stop
param set SDLOG_PROFILE 131
param save
~~~

先 `logger stop` 可确保 ULog 正常关闭。下次仍需记录时，PX4 启动后再正常启动 logger；自动脚本会自行处理日志启停和 profile 恢复。

## 4. 推荐：自动运行 PID/ESTA 对比

自动脚本会启动 headless Gazebo、等待估计器、起飞、进入 AUTO_LOITER、悬停 60 秒，在悬停第 15 秒触发 0.04/0.08/0.12 rad/s 的三个 roll 正弦激励，最后降落上锁并恢复原参数。输出目录必须事先不存在。

准备环境和数据根目录：

~~~bash
cd /home/yr/Desktop/Codev-autopilot

export M04_PYTHON='/home/yr/Desktop/codev doc/experiments/M00-20260912/python'
export PYTHONPATH="$M04_PYTHON"
export M04_DATA='/home/yr/Desktop/codev doc/experiments/M04-replay-20260915'
mkdir -p "$M04_DATA"
~~~

运行三轮 PID，并逐轮解码验收：

~~~bash
for M04_RUN in 01 02 03; do
  M04_MODE=0 python3 research/sta-rate-control/scripts/run_m04.py \
    --output "$M04_DATA/pid$M04_RUN" || exit 1
  python3 research/sta-rate-control/scripts/analyze_m04.py \
    "$M04_DATA/pid$M04_RUN" || exit 1
done
~~~

运行三轮相同参数的 roll ESTA，并逐轮解码验收：

~~~bash
for M04_RUN in 01 02 03; do
  M04_MODE=1 python3 research/sta-rate-control/scripts/run_m04.py \
    --output "$M04_DATA/esta$M04_RUN" || exit 1
  python3 research/sta-rate-control/scripts/analyze_m04.py \
    "$M04_DATA/esta$M04_RUN" || exit 1
done
~~~

六轮都通过后比较：

~~~bash
python3 research/sta-rate-control/scripts/compare_m04.py \
  --pid "$M04_DATA/pid01" "$M04_DATA/pid02" "$M04_DATA/pid03" \
  --esta "$M04_DATA/esta01" "$M04_DATA/esta02" "$M04_DATA/esta03" \
  --output "$M04_DATA/comparison.json"
~~~

成功时 `comparison.json` 中：

- `success` 应为 `true`；
- `pid_median_rmse` 是三轮 PID 的 roll RMSE 中位数；
- `esta_ratios` 是每轮 ESTA RMSE / PID 中位数；
- `hover` 和 `tracking` 两种窗口的比值都必须不大于 `1.25`。

若任意运行或分析退出非零，保留该目录，不要删除失败记录，也不要继续把它拼入“三轮通过”。换一个全新目录重新运行。

### 自动运行时临时打开 Gazebo 画面

`run_m04.py` 默认 headless。可先在终端 A 启动一轮，等 PX4/Gazebo 开始运行后，在终端 B 输入：

~~~bash
GAZEBO_MASTER_URI=http://127.0.0.1:11345 gzclient
~~~

画面仅用于观察，是否通过仍以 ULog 分析为准。下一轮开始前要关闭 `gzclient`，因为脚本会拒绝与已有 PX4/Gazebo/QGroundControl 进程冲突。

## 5. 用 PlotJuggler 打开 ULog

本机已安装 ULog 加载插件，启动命令为：

~~~bash
plotjuggler -n -d '/绝对路径/研究日志.ulg'
~~~

例如打开 M04 已验证的最终构建 PID/ESTA 日志：

~~~bash
plotjuggler -n -d '/home/yr/Desktop/codev doc/experiments/M04-20260914/resume/release_mode0/08_00_19.ulg'

plotjuggler -n -d '/home/yr/Desktop/codev doc/experiments/M04-20260914/resume/release_mode1/08_02_14.ulg'
~~~

一次运行目录可能同时包含很小的启动日志和约 20 MB 的研究日志。`m04_analysis.json` 的 `ulog_sha256` 指向正式分析使用的那一份；不要误选启动日志。可先执行：

~~~bash
ls -lh "$M04_DATA/esta01"/*.ulg
sha256sum "$M04_DATA/esta01"/*.ulg
grep ulog_sha256 "$M04_DATA/esta01/m04_analysis.json"
~~~

需要叠加 PID/ESTA 时，先加载一份 ULog，再在 PlotJuggler 中通过 **File → Load Data** 加载另一份并使用文件名前缀。两次仿真的绝对时间不同，视觉对齐建议以 `research_elapsed = 0` 为激励开始点；数值结论仍以 `analyze_m04.py` 和 `compare_m04.py` 为准。

## 6. PlotJuggler 建议查看的曲线

PlotJuggler 左侧字段的分隔符可能显示为 `/`、`.` 或数组索引，但话题和字段名如下。

### A. 首要：roll 跟踪效果

同一图拖入：

- `sta_rate_ctrl_status.rate[0]`：实际 roll 角速度；
- `sta_rate_ctrl_status.rate_sp[0]`：roll 角速度设定值；
- `sta_rate_ctrl_status.s[0]`：误差，定义为 `rate-rate_sp`；
- `sta_rate_ctrl_status.research_roll_addition`：注入的小幅测试信号；
- `sta_rate_ctrl_status.research_elapsed`：激励时间，重点查看 0～24 秒。

PID 与 ESTA 最主要比较：roll 跟踪误差幅值、振荡、超调和恢复过程。不要只看某一个峰值，正式指标使用完整 60 秒和激励 24 秒窗口 RMSE。

### B. ESTA 内部状态和输出

同一或相邻图拖入：

- `s[0]`；
- `nu_before[0]`：计算当前输出时使用的旧状态；
- `nu[0]`：本步更新后的状态；
- `a_raw[0]`：虚拟角加速度；
- `c_raw[0]`：`a_raw/g_R`，尚未做 roll 输出限幅；
- `c_applied[0]`：实际发布的归一化 roll 控制量；
- `limits[0]`：限制/冻结位。

当前限值：`|nu|≤3 rad/s²`、`|c_applied[0]|≤0.15`。`limits[0]` 位含义：1=mixer 方向冻结，2=反馈无效，4=nu 限幅，8=输出限幅；数值可按位组合。

PID 模式下 `nu/a_raw` 不适用或为零/NaN；PID 的 `c_raw[0]` 与 `c_applied[0]` 才是主要输出曲线。

### C. 确认实际运行的控制器

- `requested_mode` / `effective_mode`：0=PID，1=ESTA；
- `requested_axes` / `effective_axes`：0=PID，1=roll ESTA；
- `request_status`：0=接受，1=不支持，2=模式非法，3=轴非法；
- `pending`、`config_pending`、`config_valid`；
- `armed`、`landed`、`maybe_landed`、`rate_enabled`。

有效 ESTA 段应看到 `effective_mode=1`、`effective_axes=1`、`config_valid=true`，飞行中不应出现配置漂移。

### D. 保护与时间戳

- `fault`：0 才是无故障；1=首样本，2=重复时间，3=时间倒退，4=长间断，5=过短 dt，6=测量无效，7=配置错误，8=数值错误；
- `abort_requested`：正常应始终为 false；
- `timing_status`：armed 正常段应为 0；
- `raw_dt`：正常约 0.004 s；
- `measurement_valid`、`output_valid`、`updated`：飞行有效段应为 true；
- `publish_seq`、`update_seq`：用于看日志和实际控制更新是否丢序号。

IMU 切换诊断：

- `gyro_sample_status.reason`：0=接受，1=重复，2=旧/倒退，3=零时间，4=未到发布周期；
- `published`、`switched`；
- `duplicate_count`、`backward_count`、`switch_count`；
- `sensor_selection.gyro_device_id`。

切换时允许看见被拒绝的重复/旧 FIFO 事件，但这些事件必须 `published=false`；控制器的 `timestamp_sample` 仍应严格递增。

### E. pitch/yaw、姿态、高度和饱和

- `rate[1]/rate_sp[1]/s[1]`：pitch，仍为 PID；
- `rate[2]/rate_sp[2]/s[2]`：yaw，仍为 PID；
- `c_applied[1]`、`c_applied[2]`：非替换轴输出；
- `vehicle_local_position.z` 与 `vehicle_local_position_setpoint.z`：高度及设定；NED 坐标中向上通常是更负的 z；
- `vehicle_attitude.q[0..3]`：姿态四元数；可用 PlotJuggler Quaternion 工具转换为 roll/pitch/yaw；
- `sta_rate_ctrl_status.motor_saturation`、`motor_valid`、`motor_update_seq`：控制器实际消费的 mixer 反馈；
- `multirotor_motor_limits.saturation_status`、`update_seq`：原始 mixer 日志。

当前实验中原始 `multirotor_motor_limits` 话题存在日志丢样，因此全速 TV/频谱优先使用控制器状态中嵌入的 `motor_update_seq/motor_saturation` 判断已消费反馈，不能因为 ULog dropout=0 就认为原始话题无损。

## 7. 最小判断清单

一次有效的 ESTA 仿真至少应满足：

1. `effective_mode=1`、`effective_axes=1`，pitch/yaw 仍为 PID；
2. `fault=0`、`abort_requested=false`，armed 段 `timing_status=0`；
3. `raw_dt≈0.004 s`，时间戳递增；
4. `|rate|≤1 rad/s`、倾角≤15°、高度误差≤1 m；
5. `|nu[0]|≤3`、`|c_applied[0]|≤0.15`；
6. 完成起飞、60 秒悬停、降落并自动上锁；
7. 三轮 ESTA 的全窗口和激励窗口 roll RMSE 各自不超过三轮 PID 中位数的 1.25 倍。

PlotJuggler 适合看曲线、解释现象；是否通过实验门槛，以自动分析脚本的非零检查和 `comparison.json` 为准。
