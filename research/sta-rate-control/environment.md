# M00 环境与复现边界

记录日期：2026-09-12。这里只验证原 PID 的 Gazebo Classic SITL，不是 DP1000 实机验收。

## 1. 源码与工作区

- 正确仓库：`/home/yr/Desktop/Codev-autopilot`。任务界面提供的带冒号路径不是本次目标仓库。
- 开始时分支 `main-v2_gps`，工作区干净；核实完整 HEAD 为 `9a3c4e3625474ce7fd2cd5c9687933ccf6a70bc7`。
- 从该提交新建 `research/sta-rate-control`，未删除或重建已有分支，未移动 `main-v2_gps`。
- PX4 describe：`v1.12.3-1.0.6-12-g9a3c4e3625`。构建/飞行期间没有飞控源码、airframe、mixer 或 PID 参数补丁；只有未提交的研究资料/脚本。
- 递归子模块版本和状态见 `baseline/host_and_submodules.txt`、`baseline/provenance.json`。Gazebo 子模块为 `822050a7ab6fd87972e59f16312f451bce217a56`；检查时全部与 gitlink 一致且干净。
- 三份外部计划在 `plan/` 中保留开始执行时的逐字节快照。快照状态表仍写“待开始”是历史事实；当前状态以本仓库阶段报告和外部进度表为准。

## 2. 主机与工具链

Ubuntu 22.04.5，Linux `6.8.0-138-generic`；GCC/G++ 11.4.0、CMake 3.22.1、Ninja 1.10.1、Python 3.10.12、Gazebo Classic 11.10.2；本项目 C++14。

构建使用项目已有 `.px4-python`，不要直接套用新版 PX4 的工具链要求：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
make px4_sitl_default
make tests TESTFILTER=RateControl
```

`arm-none-eabi-gcc` 10.3.1 存在，但本阶段未交叉编译或烧写 DP1000。没有进行 MATLAB/ESTA/ISTA 验证，它们不属于 M00。

分析及本地模拟遥控器依赖单独安装到外部实验目录 `python/`，精确版本见 `requirements-m00.txt`，没有替换项目构建依赖。主机缺少 venv 的 ensurepip，故本次使用 `pip --target` 隔离安装，不将这一情况误报为仿真依赖阻塞。

## 3. Iris 与实机严格区分

| 项目 | 本次实际运行 | 未运行的实机配置 |
|---|---|---|
| 对象 | Gazebo Classic Iris | CODEV DP1000 |
| SYS_AUTOSTART | 10016 | 4065 |
| airframe | `ROMFS/px4fmu_common/init.d-posix/airframes/10016_iris` | `ROMFS/px4fmu_common/init.d/airframes/4065_codev_dp_1000` |
| mixer | `quad_w` | `quad_x` |
| 构建 | `px4_sitl_default` | `boards/codev/dp1000-v2/default.cmake`，未验证 |

实际模型为 `Tools/sitl_gazebo/models/iris/iris.sdf`，不是 DP1000 的等效模型。`base_link` 质量 1.5 kg、惯量对角线 `[0.029125, 0.029125, 0.055225] kg·m²`；这不是整机总质量，另有 IMU、旋翼和外部引用的 GPS 链接。各显式 link 质量见 provenance。

电机模型参数：motorConstant `5.84e-6`、momentConstant `0.06`、timeConstantUp `0.0125 s`、timeConstantDown `0.025 s`。这里仅冻结模型参数，没有推导或标定 ESTA/ISTA 的归一化输入增益 g。

## 4. 启动与实验输入

沿用项目入口：

```bash
cd /home/yr/Desktop/Codev-autopilot
./sitl/run.sh --headless --backend gazebo --model iris
```

自动验证脚本也调用该入口，显式固定 `PX4_SITL_WORLD=/home/yr/Desktop/Codev-autopilot/sitl/worlds/empty_grey.world`、`GAZEBO_MASTER_URI=http://127.0.0.1:11345`。不使用其他启动器、不连接实机、不运行并发实例。项目底层启动器含全局进程清理逻辑，因此研究脚本检测到已有 px4/Gazebo/QGC 时会拒绝启动；执行时仍应保持该主机专用于本次仿真。

world 是现有灰色地面；ODE quick、重力 `[0,0,-9.8066] m/s²`、最大步长 `0.004 s`、目标更新率 `250 Hz`、目标实时因子 1。Iris 插件 lockstep 开启。不设置加速因子；计时用 PX4 仿真时间，不把 60 秒墙钟时间冒充 60 秒仿真时间。

本地 MAVLink GCS 在 `127.0.0.1:14550` 接收 normal 链路（PX4 UDP 18570），发送 sysid 255/component 190 心跳及 10 Hz 墙钟中位 MANUAL_CONTROL（x=y=r=0、z=500）。保持原 RC-loss 策略，不用关闭 failsafe 的办法获得通过；它不抢占姿态/角速度设定值。实际 CLI 仅操作本次本地 instance 0。

场景：等待位置估计有效且仿真时间超过 30 s → `commander takeoff` → 本 CODEV 分支自动起飞完成进入 POSCTL → 脚本显式请求 `commander mode auto:loiter` → 至少稳定 3 s → Hold 至少 60 s → `commander mode auto:land` → 等待落地且自动 disarm → 正常退出实例。起飞完成切 POSCTL 的证据是 `src/modules/commander/Commander.cpp` 的 mission_result.finished 分支，不是推测。

## 5. 参数与采样

保留初始 EEPROM `build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016`，每次启动前另存 `startup_parameters.bson`；启动后保存 `parameters.bson`、`params_all.txt`，成功后保存 `params_end.txt`。ULog 初始参数的全精度 JSON 和跨运行差异由分析归档。测试脚本不设置 PID/外环/滤波/失联参数。

原角速度参数（R/P/Y）：P=`0.15/0.15/0.20`，I=`0.20/0.20/0.10`，D=`0.003/0.003/0`，K=`1/1/1`，FF=`0/0/0`。各轴限制和完整外环参数以实测参数快照为准，不能只凭本段重建全部参数。

`IMU_INTEG_RATE=250`，`IMU_GYRO_RATEMAX=800`，gyro LPF=40 Hz、D-gyro LPF=30 Hz。800 是参数上限，不是实测内环频率。实测模块回调计数差和各 ULog 话题记录率见每次 metrics。

`SDLOG_MODE=1`（启动记录，首次 disarm 停止）、`SDLOG_PROFILE=131`，没有提前实施 M03 的高频日志变更。控制输出等话题存在降采样，`sensor_gyro` 只约 1 Hz；因此原始传感器的地面统计仅是少量记录点的统计，不代表全带宽噪声 PSD。静止滤波角速度与原始 sensor_gyro 分别报告。控制 TV 字段明确标为记录样本 TV，不能用于全速抖振结论。perf 的执行次数可用于频率估算；lockstep 下 0 us 耗时不能作为真实计算成本。

## 6. 随机源与局限

未设置显式 Gazebo seed，未增加外力或改噪声参数。检查的 IMU/磁力计/GPS/气压计插件使用默认构造随机引擎；实际模型/插件二进制和源码版本均有指纹。GPS 插件 gpsNoise=true，气压计发布 50 Hz 且配置 baroDriftPaPerSec=0（仍有噪声），磁力计发布 100 Hz。并非所有噪声都可被单一全局 seed 控制；启动时序、调度、EKF 多实例选择也可能变化。

Iris SDF 的 gyro noise density 为 `0.00018665`、random walk 为 `3.8785e-05`、bias correlation time 为 `1000 s`、turn-on bias sigma 为 `0.0087`；accel 对应 `0.00186`、`0.006`、`300 s`、`0.196`。这些是插件模型系数，不是直接等同于每次采样标准差；实际离散噪声由插件结合 dt 生成。全部原始值以已哈希的 SDF 为准。

三次验证是同配置重新启动的可运行性重复，不是三个独立随机种子的论文统计样本，不保证逐位重现。地面阶段的 EKF reset 和 uORB 队列告警原样保存，不能删去失败试验后宣称总成功率 100%。正式统计与全带宽噪声/抖振测量留待后续相应里程碑。
