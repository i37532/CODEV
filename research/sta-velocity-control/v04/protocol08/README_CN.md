# V04 protocol08 / series07：IMU0 转换修复后的新授权批次

2026-09-23。用户明确“重新冻结并授权新批次”。起点/转换修复提交 `1f743f779f591abd57585911f391f64f292497f9`，分支 `research/sta-velocity-control`，主仓库及递归子模块干净。本文件是飞行前协议，不是通过报告。先提交协议/源码，再在干净提交重建、回归后运行；结果另行提交，不 push、不 V05。

## 清单及一次性预算

| 顺序 | 新种子 | 速度模式/轴 |
|---|---:|---|
| run01 | 9701 | PID 0/0 |
| run02 | 9701 | ESTA X 1/1 |
| run03 | 9702 | PID 0/0 |
| run04 | 9702 | ESTA X 1/1 |
| run05 | 9703 | PID 0/0 |
| run06 | 9703 | ESTA X 1/1 |

最多六次，启动失败也消耗。任一必需单轮或配对检查失败立即停止剩余清单。没有重试、补飞、额外冒烟或调参；旧批次剩余五轮不复用。六轮及三对全部通过才可验收 V04，不要求 ESTA 必胜。

登记前结构化扫描21566份JSON，没有种子复用或未解释无效文件；历史空M06诊断例外原样保留。源文本9702.149999999998为历史耗时，不是种子。登记后/启动前再次审计，只排除本新协议 execution.json/seed_audit.json 的设计登记。只播种IMU引擎，GPS/气压/磁场/宿主调度不保证独立。配对前5000创新记录最大差<1e-10、跨种子最大差>1e-6；固定PID先行的顺序偏差如实保留，不称六次完全独立随机样本。

## 原参数、场景和门槛不变

- 原位置P、Y/Z速度PID、姿态和全部rate PID；核实rate MODE/AXES/DIV=0/0/1、MC_RATT_TEST=0、MC_STA_TKO_MGT=0。只替换本地NED北向X，不是roll，AXES3/7仍不开放。
- 唯一ESTA候选 λ1=1、λ2=.2、ν限.4m/s²、纠偏限.8m/s²，原FF/HTE/滤波/推力与其他参数不改。pid/esta/frozen.json与protocol07逐字节相同。
- 唯一目标链Navigator→flight_mode_manager→位置P/实验X激励，保持本地XY目标，以单次COMMAND_INT交接到2.5m高度。原起飞、航向对齐准入及POSCTL稳定1s后固定一次yaw不变，不用真值闭环或第二发布者。
- 高度2–3m且|vz|<.2m/s连续3s后准入；激励gate后10s内就绪。12s等待、32s零净X速度正弦 `0.2*sin(2*pi*t/8)*sin(pi*t/32)^2` m/s；完整60–62s观察后降落上锁，原超时不变。
- 倾角15°、XY速度1m/s、偏移2m、悬停高度误差1m、垂速.6m/s、yaw20°；约束占比≤5%且连续≤.5s。fault/failsafe/首次失败/重算/错内环/缺窗口/日志丢样按原协议拒绝。
- 每对32s各轴速度RMSE：ESTA≤1.25×PID+[.02,.02,.01]m/s；位置/yaw及下游部分覆盖仍用原数值。只是开发非劣门槛，不是优越性结论。
- 正常准备期初次磁航向对齐仍必须有完整准入证据。任务yaw固定后直至降落上锁，**仍拒绝EKF primary/reference/reset改变**；不因已修转换而豁免降落切换，不放宽容差、时间和缺样标准。

完整数值以 `v04_protocol08.load_protocol()` 为准；锁定protocol07/execution.json SHA，仅允许批次/种子/路径/授权登记变化。运行器09/分析器08与前版仅隔离绑定新批次，新增测试逐字核实这一点；沿用logcheck07事件时间和固定编译接收器检查，旧结果不改判。

## 修复边界与冻结内容

IMU0有限超量程输入现先限幅再int16转换，非有限向量拒绝并累计错误；有效范围原量化保持，IMU1/2有限浮点路径不变。修复由前置报告单独验收，本批不再改生产控制/估计器/模型或参数默认值。

**裁幅仍损失冲击面积，不能保证EKF不切换，也未证明旧飞行唯一根因。** 旧HIL输入峰值缺失不补造；本批按现有日志诊断边界报告，不把是否切换单独当作因果试验。

frozen.json覆盖继承的控制/运行/日志资产，另明确加入Simulator、加速度驱动、VehicleIMU/Integrator、EKF消费者、对应消息和修复夹具。启动前逐项核对，并要求主仓库/递归子模块干净、HEAD完全一致、固件版本含执行提交SHA；每轮记录真实固件、模型、插件、参数、命令及ULog指纹。旧199资产表未含转换源码，不能作为新环境未变证据。

Iris10016/quad_w、empty_grey.world，Gazebo Classic 11.10.2、1倍速；不是CODEV DP1000实机。Gazebo子模块 `822050a7ab6fd87972e59f16312f451bce217a56`，ECL `b3fed06fe822d08d19ab1d2c2f8daf7b7d21951c`，完整版本另存。编译器/接收器编译配置由已有profile核验，实际构建命令、测试数和退出码随证据保存。

独立原始目录 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series07` 必须不存在。原EEPROM全量备份/每轮恢复，起始SHA `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`；只清理本运行器拥有的SITL进程，中止不等于实机安全着陆。

## 执行命令

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/research/sta-velocity-control/scripts:$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/scripts/verify_v04_protocol04.py --output <全新回归目录>
python3 research/sta-velocity-control/scripts/verify_v04_imu0_repair.py --output <全新转换链目录>
python3 research/sta-velocity-control/scripts/run_v04_protocol08.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series07' \
  --source-head <本协议提交完整SHA>
# 默认dry-run。干净提交构建及离线验证通过后，本次授权仅追加：
# --execute --authorization V04-protocol08-series07-six-attempts
```

实际启动仍为 `./sitl/run.sh --headless --backend gazebo --model iris`。飞前必须运行非零旧控制/保护/日志回归和实际转换链测试，分别记录期望负对照失败与真实回归通过；不以构建代替飞行。执行后无论成功或失败另写结果，保留所有原始数据及未执行项。

## 提交前离线验证

冻结253项资产。`protocol08_verify02`实际109个不同C++、222个Python用例通过，SITL/测试/DONT_RUN Gazebo构建退出0；新增11个批次测试包含仅换绑定、修复链资产、参数不变、失败停止和全量参数恢复。`protocol08_imu01`实际转换链11个C++和同11个sanitizer用例通过，2048帧与冻结旧源码等价；旧源码运行新方向/clipping用例预期1失败/退出1，不作为回归通过数。109+11=120个不同C++，重复执行不累计。

保留开发失败`protocol08_verify01`：222个Python中1个新增夹具引用了不存在的历史metrics文件名；改回series05原protocol06文件后全套通过。没有更改历史数据或数值门槛；此失败仅离线，不消耗飞行预算。干净协议提交验证与实际飞行结果另行记录。
