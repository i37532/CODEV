# V04：IMU0 加速度转换链修复（仅离线）

2026-09-23。用户明确“授权修复转换链”。**本次获准的转换修复及离线回归通过；不是V04飞行验收通过。没有启动Gazebo、没有新飞行、没有修改降落reset准入或追加预算。**

## 1. 修了什么

生产代码仅修改 `src/modules/simulator/simulator_mavlink.cpp` 的加速度处理段：

1. **先检查有限性。** 一份HIL加速度向量任意轴为NaN/Inf时，不向正常工作的三个模拟加速度计发布这份部分无效向量；不转整数、不填零、不把缓存伪装成新测量。各实例通过原驱动 `increase_error_count()` 累计错误，下一份有效样本通过原 `sensor_accel.error_count` 报出。原blocked/stuck注入分支保持原语义。
2. **有限超量程先限幅，再转int16。** IMU0先在物理单位下检查可表示端点，避免FLT_MAX除scale先溢出；范围内保留原除法/截断，再以整数端点做防御性约束。负端−32768、正端+32767不对称，保留原可表示行为。
3. **沿用已有clipping传递。** 饱和后实际FIFO整数落在端点，原驱动便能识别clipping，原VehicleIMU将其传给 `delta_velocity_clipping`。没有修改驱动或另造一套clipping算法。

scale仍为 `9.80665/2048≈0.0047884034 m/s²/count`，FIFO仍单样本；量程/校准/驱动半样本平均/积分器/IMU发布调度均未改。IMU1/2仅共同拒绝非有限向量，**有限输入仍走原浮点路径，不额外裁幅**。这是修复无效共享输入传播，不是调整三个IMU的完整物理模型。

没有改陀螺转换、全局land detector、EKF/selector、位置P、速度PID/ESTA、姿态/rate控制、参数默认值、Gazebo模型或实验门槛。正常路径以外的裁幅/拒绝是本次有意修订，不宣称异常输入下与旧实现等价。

## 2. 关键结果与尚存边界

通过真实 `Simulator::update_sensors → PX4Accelerometer → uORB → VehicleIMU::Run → vehicle_imu` 注入每轴正负脉冲。以下为零输入基线、默认无旋转校准下，一个4ms样本的**机体系比力积分**，不是融合后NED速度或一次飞行结果：

| 输入 | 原IMU0总Δv / m/s | 修复IMU0总Δv / m/s | IMU1/2总Δv / m/s | IMU0冲击clipping |
|---|---:|---:|---:|---|
| −250 m/s² × 4ms | +0.255260229 | −0.627625704 | −1.000000000 | 原0 → 修复1 |
| +250 m/s² × 4ms | −0.255260229 | +0.627606452 | +1.000000000 | 原0 → 修复1 |

三轴结果一致。**反向及漏报被修复，但裁幅仍损失真实峰值/面积**；它不是冲击信号重建。有限幅值浮点IMU1/2仍与FIFO有差异，因此不能保证主EKF以后不切换，不能宣称已证实旧series06的唯一根因。

非有限输入的处理边界：

- 单个无效帧不发布加速度、不推进FIFO的last-valid时间；下一份有效加速度报告真实8ms间隔，而非伪造4ms或插入零。
- 连续20帧无效后首个有效FIFO间隔为84ms；原积分器对超出自身窗口的间断执行原reset规则，测试确认随后可恢复有限输出，不强迫它生成一个假的84ms积分。
- 原gyro/accel异步对齐机制未改，恢复时 `vehicle_imu.timestamp_sample` 与最新加速度时间不必相等；没有声称全异步/lockstep调度已验证。
- 错误计数在有效样本恢复后发布；若一直无有效输入，则呈现缺样，不能把“未发布”称安全悬停或已验证故障接管。没有新增自动接管/飞行中止协议。
- FLT_MAX极值只验证Simulator转换和驱动报告；不以IMU1/2对极大浮点数的积分作为物理/数值安全结论。陀螺转换不在本次授权修复中。

## 3. 实际测试

新入口：[verify_v04_imu0_repair.py](../scripts/verify_v04_imu0_repair.py)。使用既有测试编译数据库/链接环境，GCC11.4.0、C++14，保留与默认SITL相同的数值选项。同步功能夹具使用实际生产实现与真实uORB；仅测试访问权限及备用HRT调度被替换，没有调用Simulator网络/start/run。测试配置无生产lockstep宏，不冒称整机调度复现。

`imu0_repair_verify01` 总退出0，实际 **11个不同C++用例通过**，包括原审计4个范围有效用例及新增7个：

- 三轴正负饱和脉冲的方向、面积、原clipping及三个IMU下游标志。
- ±16g、整数端点/邻点、±157/250/1e20/FLT_MAX；物理单位预限幅防止缩放先溢出。
- XYZ分别NaN/±Inf，共9个无效向量组合；原子拒绝、错误计数、last-valid时间和恢复。
- 未置齐ACCEL字段的7种掩码、连续20帧无效和长间断恢复。
- 首包无效不初始化FIFO，后续首次有效报告保留原半样本启动行为。
- 原blocked/stuck故障注入及解除后的路径。
- 2048帧固定三轴序列，与从Git冻结的**原Simulator实现**分别编译运行，FIFO整数、sensor_accel值/设备/计数及vehicle_imu积分/间隔/clipping记录逐样本完全一致。序列含零、负零、正规/次正规小值和量程内变化输入；不比较非确定墙钟发布timestamp。

在原Simulator转换位置启用 `-fsanitize=float-cast-overflow -fno-sanitize-recover=float-cast-overflow` 后，同11个用例再次全部退出0；这是重复验证，不累计成22个独立用例，也不称整个固件全部未定义行为都已排查。

**负对照保留：** 同一个新的正向/饱和标志测试换回冻结旧Simulator时，确实失败1个用例/退出1；修复版本通过。旧实现来自提交 `e9d824d06d5b253937d739da57f53bd531169fb6`，源码SHA `843c1cb93c0046cc39c7d332015e52eec4f0db6c2000cfb24535e7b821196212`。不是复制新限幅公式生成一个必然通过的参考。旧缺陷夹具/预期和报告全保留，新入口明确筛选，不静默改旧断言。

`imu0_repair_regression01` 总退出0：**原109个C++、211个Python用例通过**，包含原PID两组各2048步等价、速度/角速度及生命周期回归；SITL构建、测试构建、`DONT_RUN=1 make px4_sitl_default gazebo_iris -j4` 均退出0。回归器自带的旧复制表达式sanitizer探针仍预期退出1，不把它误称新生产转换失败。

这次C++编译及修复正向测试无意外失败；制作验证脚本时一次JS方法名笔误 `index`（应为 `indexOf`）在文件生成前报错，改正后执行，未产生飞行或修改旧工件。负对照的退出1是预设检出，不隐藏为“零失败”。所有原失败、原ULog和旧验收判定不变。

## 4. 版本、指纹和复现

- 起点/测试基线：`research/sta-velocity-control`，HEAD `e9d824d06d5b253937d739da57f53bd531169fb6`；开始主仓库/递归子模块干净。测试在该起点加本次修复工作区运行，以源码SHA绑定，不冒称未来提交已飞行。
- 修复源码SHA：`faad1a51786e9ebfbd21bb9ab61f2e895e22e50004e75cf4a7adad81ccf90320`。提交前固件SHA：`fb91cadaac2ede677974ada3ad16c363b8eec7d74fcc0604608f2e792cd77d9e`，没有用它飞行。
- Gazebo/ECL子模块仍 `822050a7ab6fd87972e59f16312f451bce217a56` / `b3fed06fe822d08d19ab1d2c2f8daf7b7d21951c`；原驱动、积分器、EKF2逐字节未变。完整性检查确认生产diff只有一个文件，且加速度块前后代码都与旧版一致。
- 原protocol07的199项资产仍匹配，但**旧清单没有包含本转换源码，不能因此声称执行环境不变或复用旧协议飞行**；下一批必须冻结新的完整提交、固件和转换源码/依赖。旧源码/结果快照不覆盖。
- 原series06的42份工件、前次EKF审计59份和IMU链审计175份均全量SHA复核通过。EEPROM仍 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，无残留PX4/Gazebo进程。静态/持久化内环配置没有修改；本轮没有运行参数/新ULog验证，不伪称再次实测模式。
- 本轮84份外部工件含命令日志、XML、冻结旧源码、逐样本轨迹及二进制，均保留在 `VELOCITY-STA-20260923/V04/imu0_repair_verify01` 和 `imu0_repair_regression01`。仓库仅小证据/指纹，索引SHA `3b7f725673417a6dde4dcd06481a7a4f07dc2c2d168ce55053268bdfc7b3861f`。

证据：[命令/退出码和等价摘要](../v04/imu0_repair01/verification.json)、[面积](../v04/imu0_repair01/areas.json)、[原控制回归](../v04/imu0_repair01/regression.json)、[回归汇总](../v04/imu0_repair01/regression_summary.json)、[范围/旧资产核对](../v04/imu0_repair01/integrity.json)、[工件指纹](../v04/imu0_repair01/artifacts.sha256)。

复现以下命令使用尚不存在的输出目录；下面02是未来占位，未执行。先确保本机测试构建依赖可用：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/research/sta-velocity-control/scripts:$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/scripts/verify_v04_landing_ekf_audit.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/imu0_repair_regression02'
python3 research/sta-velocity-control/scripts/verify_v04_imu0_repair.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/imu0_repair_verify02'
```

旧 `verify_v04_imu0_chain.py` 是历史缺陷复现入口；修复HEAD上不应再满足其“反向且clipping=0”断言。本轮使用独立修复入口，同时编译冻结旧源码做对照，不能修改旧报告来假装从未出现过缺陷。

## 5. 验收与停止点

只对本次有限范围的转换修复及离线测试标 `offline_passed`。完整阅读速度计划/共同规则/进度和前置审计，审查生产及研究diff，明确路径提交；提交SHA写入外部进度表。没有实机、MATLAB、完整EKF融合/selector验证、Gazebo接触试验或新算法飞行。

V04仍 `failed / needs_revision`：series06本批1尝试/0完整起降/0接受、ESTA0、余5停止，累计6尝试/0接受不变。本次不push、不续跑余5、不V05。下一步如需飞行，须另行冻结修复源码上的准确场景/观测字段/种子/顺序/预算并获准执行；不能自动追加诊断飞行，也不能把裁幅后仍可能存在的估计差异改判为通过。
