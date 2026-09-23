# V04：X 单轴 ESTA 预注册协议

本地 NED X 是北向速度，不是 roll。仅 Iris Gazebo Classic SITL；默认 MODE0/AXES0。
MODE1 仅接受 AXES1、有效非零参数且编译为 SITL；MODE2、AXES3/7 不开放。
位置P、Y/Z速度PID、姿态和全部rate PID保持。原Takeoff、HTE、估计器、land detector未改。

## 唯一候选与数学

`s=v-v_sp`；旧nu计算 `a_sta=-lambda1*sqrt(abs(s))*sign(s)+nu_before`；
理想 `nu_next=nu_before-h*lambda2*sign(s)`。采样h来自sensor timestamp，不夹限；
实验纠偏限幅之后只加原a_ff一次，再走原倾角、最小推力、Z优先和XY余量映射。
输出单位m/s²，无角速度g、不除质量。实际加速度响应仍包含姿态/角速度/电机滞后。

| 参数 | 固定值 | 单位/含义 |
|---|---:|---|
| MPC_VC_L1_X | 1 | (m/s²)/sqrt(m/s) |
| MPC_VC_L2_X | 0.2 | m/s³ |
| MPC_VC_NU_X | 0.4 | nu绝对限值，m/s² |
| MPC_VC_A_X | 0.8 | 加速度纠偏绝对限值，m/s²，原FF之前 |

四个生产默认均0，不能默认启用。候选基于低幅包络与离线滞后筛查，仅一个，不是最优调参。
独立对象检查增益0.8/1/1.2、姿态滞后40/80ms、额外电机30ms、恒扰0.02m/s²；
Iris实际四电机timeConstantUp/Down为12.5/25ms、base_link质量1.5kg（另有附件links）。
简化对象不是完整Iris证明；符号测试还核对yaw=0/90°时姿态四元数转换回NED推力方向。

## 生命周期与输出

参数在armed暂存、取消恢复、disarm才生效；原PID增益/HTE更新仍保留原语义。
X无旧PID叠加或X积分/ARW；Y/Z保留原算式及公共映射造成的真实耦合。不是保证Y/Z轨迹不变。
未flight、地面/contact、disabled或disarm重置nu；首次空中prime一步只给原FF/零纠偏，后续才提交。
XY目标必须成对合法；纯加速度模式不推进nu。位置/航向reset不旋转NED；原目标先按EKF delta调整，
速度reset同时拿到新目标而无法证明同量平移时拒绝。
每sample至多一次提交；重复回调/无效目标/时间/反馈锁存，disarm才能清除。
理想a_sta、nu_ideal与受约束nu_applied分别记录；保护后量不是无约束理论解。

原failsafe函数不变。新增实验路径的非法最终输出禁止发布，宿主判失败并停止自有SITL；
不自动切PID，不把停止发布后暂留的旧目标或零纠偏称安全悬停，不作实机接管承诺。
PID的发布条件和数学保持原状。MODE1不能在非SITL构建获得准入。

新增日志committed_axes、sta_flags、sta_fault、config_pending、config_generation。
sta_flags继承保护枚举：1 prime、2 inactive、4 duplicate、8 nu限幅、16纠偏限幅、32向外冻结、64 latch、128 reset。
sta_fault：1时间、2测量、4不匹配reset、8数值、16反馈。config_generation计有效增益/模式变更。
pid_calls在混合模式表示包含Y/Z PID的一次update调用，不代表仍计算X PID。

## 场景、随机性、准确顺序

原启动器 `./sitl/run.sh --headless --backend gazebo --model iris`，1倍仿真。
预热至少30s、原2.5m起飞转Hold、60s观察（12s settle后32s X小速度激励）、降落上锁。
原CODEV起飞保持，不能称精确定高2.5m；实际高度按日志和原包络验收。
δv_X=0.2 sin(2πt/8) sin²(πt/32)，四周期零积分，原位置P仍作用；不保证真实净位移恰为0。
固定yaw、Y/Z不激励，flight_mode_manager唯一trajectory发布者，实验项仅在合法有效模式内合成速度。

| 尝试 | 新开发种子 | 算法 |
|---|---:|---|
| run01 | 9101 | PID |
| run02 | 9101 | ESTA X |
| run03 | 9102 | ESTA X |
| run04 | 9102 | PID |
| run05 | 9103 | PID |
| run06 | 9103 | ESTA X |

总预算6，任何单轮或配对必需门槛失败即停止后续，无重试/补飞/额外调参。
复用旧build_m10_plugins.py的隔离IMU插件：原方程/频率/密度，只显式seed和记录噪声。
实验派生Iris只改IMU库filename，原模型和子模块不改，未使用外力矩插件。
同种子前5000条IMU创新最大差<1e-10，不同种子差>1e-6。GPS/mag/baro仍默认引擎，不能声称全随机源独立。
新种子只用于开发，不是正式留出；历史结构化seed登记和文本检查需完成后才飞。

## 冻结验收

继承V03已固定的阈值，不因ESTA结果更改。主误差：完整32秒内实际消费v-v_sp，按sample时间权重算XYZ RMSE/IAE。
每对逐轴 ESTA≤1.25×同seed PID+绝对容差（X/Y0.02、Z0.01m/s）。
60秒观察窗位置每轴≤1.25×PID+0.05m、yaw RMSE≤1.25×PID+0.02rad。
同窗X/Y/Z均报，不将Z平均进X指标隐藏退化。
倾角≤15°、XY偏移≤2m、水平速度≤1m/s、观察高度误差≤1m、|vz|≤0.6m/s；起降原界限不变。
约束比例≤5%、连续≤0.5s，计公共限制和nu/纠偏限幅/冻结；无fault/failsafe/termination。
状态双时间、发布/更新号完整，原PID dt语义不变；hover诊断覆盖边界≤40ms，sample gap≤40ms。
实际ESTA状态/符号/旧nu、理想候选与保护提交逐步复核；PID轴nu须NaN。实际内环始终PID/AXES0/DIV1。
ULog dropout0，rate更新序列完整；异步下游仅精确匹配≥80%、最大间隔≤0.25s、匹配差0，不插值伪造。
TV仅真实算法更新的加速度请求，不能解读为电机能耗；lockstep HRT不是板载耗时。

## 执行与复现

先通过全部非零自动测试、审查diff并提交本协议/源码；干净提交重建，填写真实完整SOURCE_SHA后仅执行一次：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/scripts/run_v04.py --source-head SOURCE_SHA --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series01' --execute
```

省略--execute为dry-run，不改参数或启动仿真。拒绝已有目录；完整EEPROM逐次备份恢复，实际参数首尾验证。
单轮只重分析：`python3 research/sta-velocity-control/scripts/analyze_v04.py '绝对单轮目录'`。
frozen.json固定源码/参数/原模型/world/插件及分析器指纹；运行ledger固定真正固件SHA。
保留所有失败及大日志在外部，结果提交与协议提交分开，不push，不V05，不实机。
