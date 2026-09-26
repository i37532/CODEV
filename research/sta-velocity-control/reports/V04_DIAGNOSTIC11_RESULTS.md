# V04单次PID触地诊断：原因已收敛，时间修复生效

2026-09-26。**1次诊断、失败停止，无补飞；不计正式配对验收。** V04仍未通过：原九批9尝试/0接受，加本次诊断共10次尝试；ESTA飞行0。Z仍仅离线原型。

## 执行与证据

协议/源码提交：`55073c29b74fadab5ca910847ebed332b040e204`，分支research/sta-velocity-control。用户持续授权下冻结种子11001、预算1；授权记录明确是既有授权的绑定记录，不伪称新回复。309项源码/模型/协议资产及插件指纹在启动前检查。干净提交133项不同C++、351项Python、SITL/测试/Gazebo DONT_RUN构建通过；其中新增日志profile测试1项、诊断接线4项，保留原控制122项/selector10项和原Python347项，不重复累计。

仍是项目启动器Iris10016/quad_w/empty_grey.world/1倍速；所有控制参数、任务和守卫沿用protocol10，MPC_LAND_SPEED=0.7。只额外启用SDLOG_PROFILE位10（147→1171），提高已有话题频率，不改采样/控制频率，不改FIFO调度策略。原147配置已占满255个订阅槽，部分后加载视觉话题本来就加入失败；最终新位不增加订阅数量、不挤掉旧话题、不采FIFO数组。测试逐项核对旧订阅保留及目标话题全发布率；参数默认不变，日志位掩码元数据上限扩至2047。

飞行命令：

```bash
python3 research/sta-velocity-control/v04/diagnostic11/run.py --execute \
  --source-head 55073c29b74fadab5ca910847ebed332b040e204 \
  --authorization '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04/diagnostic11_authorization.json'
```

退出1；运行目录已经存在，预算已用尽，**不得原命令补飞**。外部根`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04/diagnostic11`。固件SHA `a8d79261ec073afbc7b053a06b967ca96302d076c029895104895e6b3014bd11`。

实际起飞命令30.956s；观察48.684–109.164s共60.480s，随后计划降落。控制台0→4→2的filter fault切换，监视器因`CLI reference representation changed: ref_alt`停止；没有落地上锁事件。停止自有仿真不是成功降落。EEPROM完整恢复SHA `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，无残留模拟器。真实日志速度MODE/AXES=0/0，rate=0/0/DIV1。

## 高频证据揭示的链条

| 事件 | 实录 |
|---|---|
| 触地前真值下降速度 | 113.660s发布vz约+0.7m/s（NED向下） |
| 触地速度骤降 | 113.664s发布vz=0；真值timestamp_sample为0，只用发布时间辅助诊断，不称精确采样同步 |
| 加速度计Z轴削顶 | 113.668s，3个sensor_accel的clip_counter=[0,0,1] |
| 未经FIFO整数限幅的1/2号读数 | Z约−186.6455m/s²，绝对值超过16g≈156.9064m/s² |
| 0号读数 | Z约−83.3733m/s²，是FIFO路径处理后的报告值，不能当未限幅瞬时峰值；本次没记录FIFO数组 |
| 积分IMU标志 | 三个vehicle_imu同刻delta_velocity_clipping=4（Z位） |
| 延迟滤波故障 | 113.776–113.784s六个实例出现bad_acc_clipping，随后selector切换 |
| 坐标参考/reset | 113.784s本地位置5类reset及ref_alt变化，113.788s再次reset |

4ms物理步长里将0.7m/s停止，量级约175m/s²，再考虑重力/接触与传感器处理，和实录冲击同量级。这是触地冲击→削顶→延迟EKF故障→切换/reset的有力证据，不是ESTA发散。没有屏蔽削顶、修改健康判据或全局land detector。

**上一轮selector修复在本次实际运行中生效：** vehicle_local_position及6实例local_position均无sample倒退，速度诊断timing始终0；本次激励故障只有0/计划降落Gate2，不再出现旧负dt对应的3。但正常换源的reset仍违反原冻结验收，因此不能宣称整轮通过。

日志主文件09_19_16.ulg共77,859,649字节，SHA `b9f9aeb7d122be458d969037cae5d8da1b94483520d8b8db72c499c179d91ede`，dropout0/无损坏。三个sensor_accel各28039条、间隔始终4ms；6实例位置约11215–11216条，最大12ms。vehicle_imu间隔存在8ms，不以配置250Hz推断无丢样；完整频率/等时/倒退统计见[audit.json](../v04/results11/audit.json)。高频记录改变日志负担，不能据本轮重算或替代旧性能结论。

## 可复核材料和开发失败

- [ledger](../v04/results11/ledger.json)、[175项工件索引](../v04/results11/artifacts.sha256)，大型日志留外部；只读分析命令为`audit_v04_diagnostic11.py RUN --output NEW_DIR`，退出0仅表示诊断完成，不代表飞行通过。
- 干净提交验证目录diagnostic11_committed01，manifest SHA `226c62d8a4f11f1b711160f15dc45dd4b78010ceeb8313aa7d08143fa699af77`；提交前verify01保留，后续仅将汇总计数改为从真实XML/日志读取，刷新尚未提交的初稿快照，再在最终干净提交完整复核。
- 开发期参数掩码最大值未同步导致构建退出2；C++14 constexpr被gtest引用导致链接退出2；修复后容量测试1项失败，揭露原配置满槽。删除新增FIFO请求、改为仅更新已有话题后最终测试通过，不是忽略已请求话题缺失；此前失败工具输出保留，未伪造XML。
- 未执行MATLAB、11项IMU专项/3项姿态专项、旧七八批完整重分析或ESTA飞行。不push、不实机、不V05；历史失败不改判。

## 下一步最小处理

不继续反复用0.7m/s硬触地，也不放松reset/时间验收。优先离线核实公共最大下降速度`MPC_Z_VEL_MAX_DN=0.5`（本项目元数据合法最小值）的真实模块限速路径：原代码在parameters_update和每回调VelocityLimits中限制Z下降速度，且对内部land_speed取min。验证实际目标/约束、生效时点、参数恢复及PID语义后，再冻结新的公共限速验证批次；PID和ESTA保持相同场景、相同限制，不单独给ESTA更容易的任务。

这不修改PID/ESTA控制律或增益、安全/性能验收值，也不直接把MPC_LAND_SPEED写到其文档最小值0.6以下。0.5方案尚未测试/飞行，不能预告必然通过。Z02接线及V04正式三组配对目标继续保留。
