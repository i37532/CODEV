# RI05：XY→XYZ 两门固定参数开发协议

日期 2026-10-24；入口 bbc5396c272666bd20f526a54113e9698e87c16b，分支 research/ista-velocity-regularized。仅 Iris Gazebo Classic SITL。本文件是飞前协议，不预填通过。前置为 RI03 X、RI04 revision01 Z 已验收；Proper-ISTA 与 Z 带宽候选不加入本批。

## 门、预算、顺序

| 本阶段门 | 内部旧任务标识 | 新轴 | 任务 | 样本 |
|---|---|---:|---|---:|
| A | C/H/TEST6 | AXES3 | 固定 yaw 低速水平 8 字 | PID/RSTA/RISTA 各 3，共 9 |
| B，仅 A 通过后 | D/V/TEST8 | AXES7 | 相同 8 字加小幅平滑升降 | 同上，共 9 |

C 的 run001–009 配对种子候选83001–83003，D 的 run010–018候选83101–83103。须全历史查重注册后使用；每块顺序 PID/RSTA/RISTA、PID/RISTA/RSTA、PID/RSTA/RISTA。准确参数和顺序以不可覆盖的 execution.json、manifest.json 为准。每轮参数准备前记 attempt 即消费额度，未起飞不免计。首个必需失败停止整个 RI05；没有补飞或额外先导，总上限18。

每门分别提交源码/协议并取得干净资格。D 不能靠旧 R03 XYZ通过、手写 accepted=true 或 C 局部成功准入；必须完整核验本专项 C gate_pass、原账本/参数恢复和九进程回放/六对风险。后续生产准入改变另有 D 源码版本，C归档按其实际Git对象检查，不混称同一固件。

## 固定参数及物理范围

127项完整共同配置来自 ../ri00/results/interface.json（SHA37729b3d84309c899dce52803c234ef109f738ac0d1a4e1520a729dd18cbeb81）。X/Y λ1/λ2/epsilon/nu限/纠偏限=.5/.1/.01/.4/.8；Z=2/1/.02/4/6。PID水平P/I/D=2.16/.48/.24，Z=4/2/0。跨门、跨组合均不调参；MODE0/AXES0、MODE3/本门轴、MODE4/本门轴。新旧STA差异包含补偿预测，不称仅改变Euler形式。

原位置P、姿态/rate PID不变，MPC_VC_DIV=MC_RTC_DIV=1，MC_RTC_MODE=0、MC_STA_AXES=0、MC_RATT_TEST=0、MC_STA_TKO_MGT=0，MPC_USE_HTE=1。C中Z速度PID；D中XYZ正常阶段只计算所选算法，地面/ramp/有界交接仍单独记录，不谎称解锁全程纯隐式。2/5/6拒绝。默认PID不改，模型/传感器/滤波/land detector不改。

沿用 ./sitl/run.sh --headless --backend gazebo --model iris、empty_grey.world（09d9a334728b35a5ca0392e8751e3df5b8aea8b1d5019f8e850a4b0b8bc57b96）、合格软接触Iris（fe9900329b47f3afb3f2aafac164af047a6feb0e676ea74e658ada5e887b5150）、原插件与1×速度。仅IMU显式播种，其他传感器及宿主调度不声称独立受控。

## 唯一目标、波形和窗口

唯一目标链为 Navigator→FlightTask→trajectory_setpoint→现有模块任务适配器；中性RC/GCS心跳不发布第二套轨迹。每轮重启，完整自有日志后相对预热≥30s；原起飞后一次DO_REPOSITION建立机载参考约2.5m/固定yaw，保持原准备heading、reset、坐标和ACK检查。高度2–3m、|vz|<.2m/s连续3s，Z目标误差≤.05m、目标|vz|≤.05m/s，gate后10s内就绪，12s后主任务开始。

真实sample相对gate减12s为t；0<t<64s定义 E=sin⁴(πt/64)、ω=2π/32：

- Δx=.5 E sin(ωt)，Δy=.25 E sin(2ωt) m；
- C：Δz=0；D：Δz=.1 E sin(ωt) m，本地NED正Z向下；
- Δv=dΔp/dt，Δa=d²Δp/dt²；固定yaw，附加yaw/rate均0；
- 窗外p/v/a附加量0，端点连续。原位置P仍工作，原有效FF与任务导数各只加一次。

C与D水平波形相同。每条轨迹在X/Y都有正负位置、速度和加速度段；这构成预算内的双向复跑，不另加未登记单轴飞行。离线另覆盖X/Y独立正负输入、状态隔离、两级内环/电机滞后。D只在A通过后加Z。积分归零不等于真实飞机回零；共同外部轨迹不意味着位置P合成后的v_sp逐样本相同。

主窗64s、半窗0–32/32–64s，完整观察90–92s。原auto:land自动上锁、双话题封口和落地尾窗原样保留。主窗速度误差、完整观察位置误差、名义2.5m高度偏离和主动Z轨迹跟踪分别标注，不混称。

## 不变的安全、数值和开发风险阈值

沿 R03 最终、RI04 revision01 与 AX04 execution（308aa5a4e52828585bbf6ee3ec0be339a8081475663ceb759de0aee40167d2d3）：

- 主/两半窗逐轴速度RMSE≤1.25×配对PID+[.02,.02,.01] m/s；位置RMSE≤1.25×PID+.05m；yawRMSE≤1.25×PID+.02rad。每对13项，每门6对78项，不要求胜过PID/RSTA。
- 倾角≤15°、XY速≤1m/s、位置偏移≤2m、观察|vz|≤.6m/s、名义高度偏差≤1m、yaw偏差≤20°；约束占比≤.05、连续≤.5s。
- 故障/回退/首调用失败/同帧retry=0；有效模式、轴、DIV、rate PID和完整边界/reset/健康检查正确。
- raw_dt按sample真实差，范围[.002,.04]s，间隙≤.04s；主窗≥6390样本、span≥63.96s。变化仅按既有64s任务长度对应，不放宽时间规则。
- dropout=0、必需序号缺失0，输出精确配对覆盖≥.8、含边界空洞≤.25s、已配对输出差0；不填补缺失。播种前5000条同种子创新差<1e−10、异种子>1e−6。
- 隐式scaled残差≤3e−6、输出/clip绝对容差2e−6、保护nu2e−7、限值1e−6、epsilon1e−7；核h等于raw_dt。理想p/a/nu候选、保护后的应用值和发布值分别核验；不把受保护输出当严格隐式解。

HTE仍用已闭合实际纠偏/FF缓存与实际nu平移，StateLimit-only允许缓存，其余保护和不闭合禁止；不得照搬RSTA旧nu重构。XYZ无闲置正常PID以pid_axes=0核验；pid_calls记录PositionControl::update调用数，正常XYZ也为1，不能误按0筛掉HTE证据。三轴先整体裁决再原子提交，同sample最多一次。无新起飞管理或临时回退。

## 日志、证据、停止与解释

完整复用 R03 最终 prearm04→warmup10→position11、RI02 MODE4数学与RI04 HTE审计：相对预热/增量读取、publication/sample/连续序号、已审计白名单、同刻组歧义、完整边界/reset/健康和落地尾窗，不简单去重。保持500ms新鲜度、40ms位置间隙、20ms目标配对。生成格式/注册/队列须实测不变。

完整BSON备份/写回/实际读回/精确恢复；保留SDLOG_PROFILE原位OR16/1024/2048（3089）。批前12GiB、逐轮10GiB磁盘和512MiB tmpfs原余量。只停自有进程，持久归档和SHA核验后才释放本轮临时日志，不删历史。

首败立即停止，不因性能没赢就自行调参，也不为凑9或18重飞。只有每门9接受、9独立进程全ULog重解码、6对独立风险重算、全部恢复/清理通过才签门。所有失败/未执行保留；旧RI03/RI04/R03样本仅前置/兼容，不拼入新统计。

报告逐轴时间加权RMSE及J、主半窗、位置/高度/yaw、p/nu/限制/HTE/输出/接管/模式/时序与实际采样频率。TV用真实更新，不是能耗；共同频谱按旧100HzZOH→513tap/8Hz FIR→25Hz/裁2.56s/0–7Hz，原生谱另外保留，不重采样验收。核/模块墙钟不是板级CPU/WCET。n=3仅开发描述，无显著性或实机保证。MATLAB未重跑必须注明。

默认dry-run；显式执行须完整本门SHA/资格与冻结资产。收尾报告RI05分A/B、单独结果提交和进度SHA；不push、不RI06/旧R04/R05、不分频、不实机。
