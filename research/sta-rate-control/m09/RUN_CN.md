# M09：分频、日志与耗时

仅 Iris Gazebo SITL，不用于 DP1000 实机。默认 `MC_RTC_DIV=1`，PID/ESTA/ISTA 都使用同一个分频器。
这里不改 gyro、D-term 滤波器或 Gazebo 步长。只有角速度控制器计算降频，外环、回调、安全检查和推力保持原频率。

## 单轮自动实验

先关闭已有 PX4/Gazebo/QGC 实例；脚本发现冲突会拒绝启动，不会杀掉其他实例。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
make px4_sitl_default

# MODE: 0 PID，1 ESTA，2 ISTA；DIV: 1、2、4。输出目录必须尚不存在。
M09_MODE=2 M09_DIV=4 python3 research/sta-rate-control/scripts/run_m09.py \
  --output '/home/yr/Desktop/codev doc/experiments/my_m09_ista_div4'
python3 research/sta-rate-control/scripts/analyze_m09.py \
  '/home/yr/Desktop/codev doc/experiments/my_m09_ista_div4'
```

脚本沿用 `./sitl/run.sh --headless --backend gazebo --model iris`，加载 M08 冻结的算法参数，
自动起飞、悬停60秒（包含36秒yaw及三轴小幅激励）、降落上锁；检查后恢复启动前参数并退出自有实例。
ISTA 使用 `m08/iris_ista_rpy_candidate02.json`。ESTA/ISTA的pitch lambda1不同，不是同增益离散化论文比较。

完整九格开发检查（每格一次，不是M10论文重复试验）：

```bash
python3 research/sta-rate-control/scripts/verify_m09.py --output '/home/yr/Desktop/codev doc/experiments/my_m09_verify'
python3 research/sta-rate-control/scripts/run_m09_batch.py --output '/home/yr/Desktop/codev doc/experiments/my_m09_series'
```

顺序 PID 1/2/4 → ESTA 1/2/4 → ISTA 1/2/4；任一运行或解码失败立即停止，不挑选成功数据、不自动重试。
图形界面的普通飞行仍使用原 `sim_scripts/start.sh`；不要同时启动上述自动脚本和另一控制实例。

## 已启动仿真时修改分频

只在已落地上锁后，在 **PX4控制台（不是普通bash）** 执行：

```text
param set MC_RTC_DIV 2
listener sta_rate_ctrl_status -n 1
```

检查 `div_req=2, div_eff=2, div_ok=true, div_wait=false` 后才能解锁。
飞行中请求只暂存，disarm后生效；无效值（如3）不替换上一个有效值，`div_ok=false`。
普通仿真结束请恢复 `param set MC_RTC_DIV 1`，不要无意把分频带入其他任务。
算法 MODE/AXES 切换仍按原日常脚本操作；这份说明没有新增另一套算法增益。

## PlotJuggler 重点字段

打开实际 ULog 的 `sta_rate_ctrl_status`：

| 字段 | 含义 |
|---|---|
| `timestamp_sample`, `publish_seq` | 传感器时间及每回调发布序号 |
| `update_seq`, `updated`, `held` | 真实算法更新计数；保持周期不会增加 |
| `div_req/div_eff/div_ok/div_wait` | 请求/实际分频、请求有效性、armed暂存 |
| `raw_dt`, `dt` | 回调间隔/算法真实间隔；保持周期dt为NaN，不是假零步长 |
| `c_held[0..2]`, `c_applied[0..2]` | 未缩放缓存力矩/实际应用指令 |
| `c_raw`, `a_raw`, `nu_candidate`, `xi` | 只在真正计算时有意义；保持周期为NaN |
| `nu_before`, `nu`, `pid_integral_before/after` | 检查保持期间状态没有推进 |
| `thrust`, `battery_scale` | 推力每回调刷新；缩放不会在历史命令上累乘 |
| `sat_bits/sat_valid/sat_n` | 上次更新后的饱和方向OR、全区间有效性、观察数 |
| `motor_saturation/motor_valid/motor_update_seq` | 本次消费的最新mixer反馈，不是上面的区间合并值 |
| `kern_ns`, `mod_ns`, `clock` | 选定算法及保护/混合耗时、模块耗时、时钟来源；Linux宿主clock=1 |
| `fault/reset_reason/abort_requested` | 保留原保护编码和SITL中止要求 |

字段采用短名是为适配旧PX4的1500字节格式字符串上限；构建验证会检查该限制。
估计频率应选 `updated=true` 的 `timestamp_sample`，不能用整个话题的250Hz冒充控制器计算频率。
预计DIV=1/2/4对应约250/125/62.5Hz，最终以每轮 `m09_analysis.json` 的实测结果为准。

## 指标解释

- `tv_actual_updates`：只用真实更新序列；总TV除以同一个36秒激励窗口，另列实际首末更新跨度。
- `m09_spectra.npz`：原生更新序列PSD与共同带宽PSD分开保存。后者使用回调网格ZOH输出，
  513点Blackman FIR（基频250Hz时截止22Hz）抗混叠后降至62.5Hz，比较0–20Hz，边缘各去掉1.024秒。
- 原生20Hz以上RMS的Nyquist范围随DIV变化，不能不加说明直接宣称其中一组“抖振更小”。
- `kern_ns` 包括选定算法、公共保护及混合，不是剥离保护的纯公式计时；保持周期为0。
- `mod_ns` 是Run入口至本诊断发布前的宿主墙钟跨度，包含普通输出发布，不含本诊断发布或调度等待。
  包含抢占和计时开销，不等于CPU周期、硬实时上界或板级成本。报告median/p95/p99/max及每模拟秒合计。
- 原始motor_limits可能丢样，需查看独立计数；没有状态序号完整性就不接受TV/频谱结论。
- 故障时抑制输出并请求宿主停止SITL；没有自动PID接管，也不把零力矩称为安全。

本次验收数据中的最终频谱使用带`_v2`后缀的文件（修正奇数窗口的一侧PSD归一化，原文件保留）。
后续新运行默认分析器已采用修正公式。已有数据想保留初版，可用 `--suffix _v2` 输出新文件。
补充全飞行审计：`python3 research/sta-rate-control/scripts/audit_m09.py <九格目录>`。

开发结果提醒：ISTA在DIV4下的pitch RMSE约为自身DIV1的2.23倍。DIV4可用于分频研究，
不表示性能更好；日常基线仍保持DIV1，不据此直接部署实机。
