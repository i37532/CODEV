# AX02：按轴消融工具与 48 轮开发协议

**本目录冻结协议，不代表 48 轮已飞行或已通过。AX02 禁止起飞；下一阶段是单独启动 AX03。**
默认 PID，速度与 rate 都 DIV1；MODE2 不开放。仅 Iris Gazebo SITL，不适用 DP1000 实机。

## 入口

```bash
cd /home/yr/Desktop/Codev-autopilot
bash research/sta-velocity-control/axis_ablation/run.sh
```

无参数只显示精确 48 项清单，不连接飞控、不启动进程、不写 EEPROM。
`execution.json` 是唯一清单；每项 `parameters` 覆盖共同 `fixed_parameters`，展开后保存完整 job。
`parameters/*.json` 是八套完整配置，不额外调参。未知名称、轴、模式、DIV、顺序、预算或组合增益漂移均拒绝。

AX03 才能使用 `--execute --output <清单中的唯一目录> --source-head <干净源码SHA> --authorization <绝对路径凭据>`。
凭据必须绑定 AX03、当前干净 HEAD、execution 的 SHA-256、48 次预算和明确 AX03 请求；AX02 持续执行要求不冒充下一阶段授权。
本目录不生成真实授权文件。目录已存在即拒绝续跑/补飞；失败后由后续阶段另行处理，不自动扩大预算。

离线复核（输出必须是尚不存在的新目录）：

```bash
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
python3 research/sta-velocity-control/axis_ablation/ax02/verify.py \
  --require-clean --output '/home/yr/Desktop/codev doc/experiments/AX02-local-recheck01'
```

## 配置与研究问题

八组：PID=MODE0/AXES0；X/Y/Z/XY/XZ/YZ/XYZ=MODE1、AXES1/2/4/3/5/6/7。
正常飞行未选轴仍速度 PID；全选 XYZ 正常不计算闲置速度 PID。位置 P、姿态及所有角速度控制均保留。
含 Z 组保留地面/ramp 的原 PID 和单帧有界接管；这也是“轴配置”处理的一部分，不能声称只替换了孤立数学式。

| 每轴固定参数 | X/Y | Z |
|---|---|---|
| 速度 PID P/I/D | 2.16 / .48 / .24 | 4 / 2 / 0 |
| ESTA λ1 / λ2 | .5 / .1 | 2 / 1 |
| ESTA νmax / 纠偏 amax（m/s²） | .4 / .8 | 4 / 6 |

水平来源为 V08 pid2/esta0，Z 为 AX00 已核对的 Z03/E01 候选。所有组连**未选中的 PID/ESTA 参数**也相同。
这些候选还没有在统一 H/V 八配置矩阵飞行验收；没有每组合搜索，也不保证 ESTA 胜出。
速度误差 m/s，λ1 单位为 `(m/s²)/sqrt(m/s)`、λ2 为 m/s³；不套用角速度 g、不重复除质量。

## H/V 目标与唯一来源

取原任务采样时钟 t：首次满足原 airborne/AUTO_LOITER/内环 PID 等 gate 后先等待 12s；不以宿主墙钟积分、不在 armed 中重启时钟。
在 `0<t<64s` 内令 `b=π/64`、`w=2π/32`、`E=sin(bt)^4`：

```text
H: Δp = (.5 E sin(wt), .25 E sin(2wt), 0) m
V: Δp = (.5 E sin(wt), .25 E sin(2wt), .1 E sin(wt)) m
Δv = dΔp/dt；Δa = d²Δp/dt²
E' = 4b sin(bt)^3 cos(bt)
E'' = 4b²[3 sin(bt)² cos(bt)² − sin(bt)^4]
对 A E sin(kt)：
v = A[E' sin(kt)+E k cos(kt)]
a = A[E'' sin(kt)+2E'k cos(kt)−E k² sin(kt)]
```

端点及窗外 p/v/a 全零，净位移与速度积分为零，固定 yaw。Z 是 NED 向下，不是机体 yaw。
H 基准高度约 2.5m；V 目标上下摆动不超过 .1m，Z 速度/加速度保守上界 .04m/s、.02m/s²。
水平位移/速度/加速度保守上界 .56m、.18m/s、.08m/s²。

目标链：原 `Navigator→FlightTask→trajectory_setpoint` 唯一发布者；局部每帧副本加轨迹 p/v/a，再进原位置 P。
不修改缓存、不添加外部轨迹/姿态/rate 发布者。FF 每帧只加一次；位置 P 反馈意味着各算法实际消费 `v_sp` 可能不同。
V 用新增且默认关闭的 `MPC_VCT_TEST=8`；H 用原6，原5/6/7和旧 sim_scripts/V08入口不变。

起飞沿用 commander takeoff；原预热、航向对齐/参考冻结与一次 DO_REPOSITION 交接不变。
进入任务前要求日志中连续3s高度2–3m、`|vz|<.2m/s`，有效估计、armed/AUTO_LOITER、离地无接触；gate+10s前就绪。
观察90–92s，必须覆盖完整64s及0–32/32–64s两半；结束恢复零叠加，再唯一 auto:land，落地并自动上锁。
起飞/降落 wall timeout150s、启动/预热180s、观察240s，均沿用旧运行器。失败终止自有 SITL 进程不是实机安全降落策略。

## 冻结门槛与来源

不使用新 ESTA 结果选择门槛。来源是 V04 最终冻结规则、V03/V00 PID 尺度，以及 V06/软着陆和 V08 已验收的 64s 任务检查器。
其源码、JSON、模型和分析依赖指纹列在 frozen.json；具体数值在 execution.protocol_overrides 和实际检查器中一致复用。

| 检查 | 数值/条件 |
|---|---|
| 全飞行 | 倾角≤15°，离原点XY≤2m，XY速度≤1m/s，高度[-.5,4]m，起降`|vz|≤3.5m/s` |
| 观察期 | 高度偏离2.5m≤1m，`|vz|≤.6m/s`，yaw偏差≤20° |
| 限制 | 每64s/32s窗口受限比例≤5%，最长连续≤.5s；归一化控制≤1.001 |
| 逐轴开发风险 | ESTA速度RMSE≤1.25×同seed PID+[.02,.02,.01]m/s；完整64s及两个32s半窗分别检查 |
| 位置/yaw | 90s逐轴位置RMSE≤1.25×PID+.05m；yaw RMSE≤1.25×PID+.02rad |
| 诊断时钟 | 发布、输入、采样分别严格递增，间隔≤40ms；序号无缺失；raw_dt匹配sample差，不混用发布时间 |
| 原始日志 | ULog dropout=0，rate/速度必要序号缺失=0，第一次update失败或同帧重算=0 |
| 下游匹配 | 精确记录交集≥80%，含边界/子窗口最大缺口≤250ms；缺项不插值、不伪造yaw/FF |
| 消费目标 | 唯一精确setpoint_timestamp，源年龄≤40ms；所有目标和一次FF误差≤2e-6 |
| steady配置 | requested/effective/active/committed/PID轴准确；含Z phase3；无reset/priming/latch/回退 |

原姿态话题专用双时钟白名单、同刻歧义拒绝、边界/reset、落地IMU/估计器健康门完整保留，不推广成所有话题可去重。
倾角只约束水平状态冻结；Z仅推力上下限位2/4影响冻结，不能把任意约束位当Z饱和。HTE变换明确反映在Z ν连续性，PID轴仍独立重构原积分/ARW。
理想候选与保护后状态分别检查，不把推力映射代理称实测加速度。

## 48 项清单与停止规则

每行表示连续8次；组内同 seed，H/V 种子互斥。完整参数展开由运行器核验。

| 次序 | 任务/seed | 顺序 |
|---|---|---|
| 01–08 | H / 51001 | PID,X,Y,Z,XY,XZ,YZ,XYZ |
| 09–16 | H / 51002 | PID,XYZ,YZ,XZ,XY,Z,Y,X |
| 17–24 | H / 51003 | PID,XY,XZ,YZ,XYZ,X,Y,Z |
| 25–32 | V / 51011 | PID,X,Y,Z,XY,XZ,YZ,XYZ |
| 33–40 | V / 51012 | PID,XYZ,YZ,XZ,XY,Z,Y,X |
| 41–48 | V / 51013 | PID,XY,XZ,YZ,XYZ,X,Y,Z |

H24必须全部接受及21配对通过，才运行V；第25次 V PID 是**预算内安全门**，不是额外先导。
每个非PID组立即与本task/seed PID做逐项配对；合计48次/42配对。任何门失败都停，后面记未执行，保留失败，不补飞、不调参、不删异常、不放宽阈值。
PID固定排在各块第一是安全/配对门控要求，候选顺序反转/轮换但非完全随机；披露时间顺序混杂。
六种子只配对 IMU 引擎，首5000创新同seed差<1e-10、不同seed差>1e-6；GPS/磁计/气压/宿主调度不声称独立可复现。
3种子/任务是开发准入，不是正式统计充分性依据。41001–41020留给旧V08正式矩阵，禁止占用。

## 模型、参数恢复与指标

沿用 `./sitl/run.sh --headless --backend gazebo --model iris`、empty_grey.world、1倍仿真。
派生 Iris 仅已合格接触 kp2500/kd50/max_vel.2/max_contacts4 和原 seeded IMU 插件路径；无质量/惯量/噪声默认更改。
`models/iris.sdf` 是精确派生快照，启动时重新派生并比对SHA，原模型/世界路径与进程归属另外核验。

每轮完整 EEPROM 原字节备份→覆盖同一固定参数+轴/任务→实际起始/结束参数+ULog核验→退出自有进程→原字节精确恢复。
保留 SDLOG_PROFILE 已有位并 OR16/1024。若仍有飞行进程不强行覆盖其EEPROM，记录未恢复并停批；下一阶段不能隐瞒或继续。

主指标使用**实际消费的角标为X/Y/Z的速度 v−v_sp**，不是角速度误差或仅画面轨迹。
64s及两半逐轴RMSE/IAE/均值/标准差；XY合成仅补充展示，不覆盖Z或单轴退化。
TV按真正更新计算；原生频谱与共同0–7Hz频谱分开，共同513tap 8Hz FIR→25Hz，仅分析重采样、不用于修补验收。
加速度/推力TV不是电机能耗；耗时为宿主核路径/模块墙钟，不是板级CPU。
`result.json`、`xyz_metrics.json`、`axis_pair.json`、完整参数/目标/模型/ULog指纹和 ledger 保存外部目录。
PlotJuggler重点看 `sta_velocity_ctrl_status` 的 v/v_sp/s、a_ff/a_sta/a_req/a_proxy、ν三种状态、active/committed/pid_axes/z_phase/constraint_bits，以及 selection、rate模式、local_position/attitude/推力。
