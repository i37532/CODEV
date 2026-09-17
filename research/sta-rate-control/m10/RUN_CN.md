# M10 论文实验包（仅 Iris SITL）

先读 [预注册规范](PROTOCOL_CN.md)。正式结果以 reports/M10.md 为准；命令可用不等于实验已完成。
所有目录参数使用尚不存在的绝对路径。关闭自己的PX4/Gazebo/QGC；发现冲突脚本会拒绝启动。
不要同时启动日常sim_scripts，不能连接实机。

## 环境与构建

本次Python为3.10.12，NumPy1.26.4、pyulog1.2.4、pymavlink2.4.49，
其依赖lxml6.1.3、fastcrc0.3.6；Gazebo11.10.2、g++11.4.0。
下列M00/python是本机已有依赖目录，不是仓库自带文件。新机器需先按原PX4环境说明安装构建依赖，
并将这些Python运行依赖放入该副本的`.px4-python`或提供相同外部依赖路径，再执行实验。
不必在当前已配置的机器上重复安装或覆盖环境。绘图依赖另见下文。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
make px4_sitl_default
python3 research/sta-rate-control/scripts/verify_m09.py --output '/home/yr/Desktop/codev doc/experiments/my_m10_verify'
python3 -m unittest discover -s research/sta-rate-control/scripts -p test_m10.py
python3 research/sta-rate-control/scripts/build_m10_plugins.py --output '/home/yr/Desktop/codev doc/experiments/my_m10_plugins'
python3 research/sta-rate-control/scripts/scalar_m10.py --output '/home/yr/Desktop/codev doc/experiments/my_m10_scalar.json'
```

插件在外部目录编译：原IMU方程只加显式seed与增量日志；力矩插件只作用于Gazebo。
不修改Tools/sitl_gazebo子模块或日常Iris模型。完整编译命令及原始/生成源码指纹保存在插件目录。

绘图另用独立外部依赖目录，不覆盖系统/PX4 Python。已安装可跳过安装，仅设置路径：

```bash
python3 research/sta-rate-control/scripts/setup_m10_plot.py --output '/home/yr/Desktop/codev doc/experiments/my_m10_plot'
export M10_PLOT_PYTHON='/home/yr/Desktop/codev doc/experiments/my_m10_plot/python'
```

## 训练与先导（不算正式数据）

```bash
python3 research/sta-rate-control/scripts/batch_m10.py train \
  --output '/home/yr/Desktop/codev doc/experiments/my_m10_train' \
  --plugins '/home/yr/Desktop/codev doc/experiments/my_m10_plugins' --speed 5

python3 research/sta-rate-control/scripts/batch_m10.py pilot \
  --output '/home/yr/Desktop/codev doc/experiments/my_m10_pilot' \
  --plugins '/home/yr/Desktop/codev doc/experiments/my_m10_plugins' \
  --frozen '/home/yr/Desktop/codev doc/experiments/my_m10_train/selected.json' --speed 5

python3 research/sta-rate-control/scripts/summarize_m10.py \
  '/home/yr/Desktop/codev doc/experiments/my_m10_pilot' \
  --output '/home/yr/Desktop/codev doc/experiments/my_m10_pilot_summary' --pilot
```

训练36轮；先导90轮（6场景×3种子×5配置）。失败耗费预算，不重试覆盖。
若某算法没有合格候选，selection会失败：需记录blocked并重新设计下一版训练，不能冒充已冻结。
先导用于检查可运行性、种子配对和方差估计。不能用测试seed来调参。

## 冻结后正式实验

本仓库的`FROZEN.json`是原实验冻结件，复现时直接使用，不能覆盖。
若在新的研究副本中从头执行且该文件尚不存在，完成训练、先导及汇总后用：

```bash
python3 research/sta-rate-control/scripts/freeze_m10.py \
  --train '/home/yr/Desktop/codev doc/experiments/my_m10_train' \
  --pilot '/home/yr/Desktop/codev doc/experiments/my_m10_pilot' \
  --summary '/home/yr/Desktop/codev doc/experiments/my_m10_pilot_summary' \
  --plugins '/home/yr/Desktop/codev doc/experiments/my_m10_plugins' \
  --output research/sta-rate-control/m10/FROZEN.json
```

先审查并提交所有脚本、训练选择、先导证据和规范；提交后重新构建，使ULog内嵌提交匹配。
在干净的冻结提交上执行：

```bash
make px4_sitl_default
python3 research/sta-rate-control/scripts/batch_m10.py formal \
  --output '/home/yr/Desktop/codev doc/experiments/my_m10_formal' \
  --plugins '/home/yr/Desktop/codev doc/experiments/my_m10_plugins' \
  --frozen research/sta-rate-control/m10/FROZEN.json --speed 5

python3 research/sta-rate-control/scripts/summarize_m10.py \
  '/home/yr/Desktop/codev doc/experiments/my_m10_formal' \
  --output '/home/yr/Desktop/codev doc/experiments/my_m10_results'
```

正式600轮，通常需要数小时。脚本顺序启动单实例，每轮都有自己的job、运行/解析退出码、ULog和模型副本。
基础设施/数据质量异常会停止；已记录的控制失败保留在分母。相同命令可跳过已完成且已记录的job，
但不跳过halt、不自动重试中断目录，不允许更改jobs.json后续跑。停止后的恢复需先审查实际状态。
若且仅若属于规范中的“一条首次解锁前诊断丢样”，可运行
`python3 research/sta-rate-control/scripts/adjudicate_prearm_gap_m10.py <批次目录> <运行目录名>`。
它校验原日志后记录该轮仍失败、禁止补指标/补飞，再允许原batch命令续跑。
不适用于飞行期丢样、多个缺样、控制故障或其他数据异常；不是通用忽略失败开关。

## 一条命令复现某一轮并分析

使用该轮保存的 `*.job.json`，指定正确的源码提交和插件目录：

```bash
python3 research/sta-rate-control/scripts/replay_m10.py \
  --job '/原始实验目录/某轮.job.json' \
  --plugins '/原始实验目录/插件目录' \
  --output '/home/yr/Desktop/codev doc/experiments/my_m10_replay'
```

formal job中的frozen_head必须与干净HEAD一致；结果提交上直接重跑会拒绝，需要独立checkout冻结提交。
不建议为了复现而覆盖当前工作区。重放只能控制已明确seed化的源，不保证每个闭环浮点样本逐位相同。

## 查看

- 每轮 `m10_analysis.json`：实际模式/频率、误差、输出负担、恢复/删失、时序及噪声证据。
- `m09_spectra.npz`：原生/共同带宽谱；状态丢样则不能接受频谱。
- `imu_innovations.csv`：真实IMU增量和simTime；不是从控制误差猜测噪声。
- `torque.csv`：真正施加的物理力矩、起止时间和变化率；Gazebo FLU坐标。
- 汇总 `summary.json`、`runs.json`、`rmse.svg/png`：包含失败分母和配对差值，不能只拷贝成功曲线。
- ULog的PlotJuggler字段沿用M09说明；尤其看 `effective_mode`、`div_eff`、`s`、`nu`、
  `c_raw/c_applied`、`updated`、`limits`、`fault`、`research_elapsed`、`kern_ns/mod_ns`。

大型数据不入Git；跨机器复现实验需要另行复制原数据并用SHA-256索引核对。
