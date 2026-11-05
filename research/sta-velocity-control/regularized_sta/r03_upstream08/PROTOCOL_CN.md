# UP08：两次上游时间链诊断，不计 R03 接受

依据 `AUTHORIZATION_R03_UPSTREAM08_CN.md`，仅项目 Gazebo Classic Iris SITL。本目录是独立诊断，不续旧 revision06，不产生 R03 gate_pass，不进入 R04/R05。

## 预算、顺序与原判

历史九批共52尝试、51起飞指令、46接受、6失败全部保留。其ledger/journal、源版本、逐轮result/restore及既有接受metrics均由 `retained_history()` 精确核验。revision06 D的2接受/1失败不拼入完整D门；其六项未执行仍未执行。

最多新增2次，总实际尝试上限54。准确清单见manifest：diag001为PID MODE0/AXES0，diag002为旧ESTA MODE1/AXES7；固定顺序，使用一个新IMU种子配对。无RSTA/MODE3、ISTA、其他掩码、调参或额外先导。第一轮完整检查通过才第二轮；预解锁失败同样消耗一次。首个必需失败停止，不恢复旧批、不重试、不换种子、不追加第三次。

诊断 `accepted/flight_accepted` 始终false，`accepted_for_R03=0`；只单独记录物理完成、科学检查完整性、诊断完整性和是否观察到上游事件。两次不复现不能证明罕见故障消失，更不能证明算法因果或修复成功。后续完整D矩阵和预算需另冻，不能用本诊断抵扣。

## 不变任务和配置

两轮必须同一新干净源码、同一固件；包含经过真实离线验证的最小IMU修复和新增日志配置，不能第一轮旧源码第二轮新源码。两轮完整127项参数逐字段来自旧06对应算法job；固定原位置P、姿态和rate PID、速度DIV1、旧起降/HTE/FF/限制。内环实际核验 `MC_RTC_MODE=0/MC_STA_AXES=0/MC_RTC_DIV=1/MC_RATT_TEST=0/MC_STA_TKO_MGT=0`。

沿用D XYZ TEST8：64s主窗、两个32s半窗，12s settle；固定yaw、原2.5m起飞、单次DO_REPOSITION、90–92s观察、原auto:land/自动上锁及完整尾窗。窗口0<t<64有E=sin⁴(πt/64)、ω=2π/32，p=(.5E sinωt,.25E sin2ωt,.1E sinωt)，v/a用原解析导数、FF一次。唯一目标源为原Navigator/FlightTask与既有模块适配，无外部竞争发布者。

全部原数值安全、同帧/reset、双时钟、原始目标/height/handoff、落地保护及配对开发风险条件不改。原数据要求dropout0、关键序号无缺失、主窗≥6390样本且≥63.96s、完整下游部分覆盖及尾窗保留；新增原始gyro覆盖检查复用既有vehicle_imu的12ms双时钟/完整边界规则，不用新结果改阈值。

日志唯一增量是新增SDLOG_PROFILE bit11=2048：原现场运行profile1041保留全部位，最终3089，sensor_gyro实例0/1/2 interval0。不是gyro FIFO bit8；不改变物理采样/噪声、滤波或队列。若原EEPROM推导的旧运行profile不是1041，飞前停止。127参数清单不含profile；此日志参数增量单独公开，不声称所有参数都未变。完整原BSON恢复包括profile和无关参数。

## 运行器接线与资格

默认 `python3 runner.py` 仅打印dry-run清单。只有显式 `--execute --qualification <新资格绝对路径>` 才可能起飞，且必须同时满足本版授权、清单canonical精确一致、原历史不变、新源码干净资格、固件/源码/模型/world/插件/metadata及全33子模块正确。旧06资格不可使用。

新 `flight_main` 是封印旧06函数的私有副本，只改唯一开头authority表达式；逆变换必须恢复完全相同AST。私有namespace只绑定新authority和真实新runner身份，不改旧模块或共享globals。完整飞行主体、进程拥有权、异常归档不变。新Checks继承原选择/监视/落地方法，环境方法只替换新来源前置，模型派生正文经AST回归。prearm04 OwnedWarmReader及500000µs规则保留。完整分析由旧06显式full_analysis接口复用numeric05/handoff06，使用新严格来源检查及非接受保存器。

新 `frozen.json` 位于本目录，保留原control_parameters，并绑定窄生产修复和日志注册、源码/固件/全部依赖。资格字段由 `qualification_binding()` 集中定义：stage/revision、52+2=54、new_matrix_attempts0、diagnostic_only、profile1041→3089、历史与ABC、执行/冻结/授权/固件SHA、source_head、clean和new_flights0。真实测试至少525个不同C++和800个Python，并含functional-VehicleIMU、functional-EKF2SelectorTiming、functional-EstimatorDiagnosticTopics；实际计数/命令/退出码不能预填。

仅用原项目启动器，1×速度、原empty_grey.world和合格软接触资产。使用与所有旧批共享且去重的flock，端口/进程不得冲突；不杀用户其他进程。启动前原磁盘12GiB余量、每轮10GiB及tmpfs512MiB余量保留。每轮完整BSON备份、fsync、启动前账本追加、退出后确认无sim再精确恢复；双ULog持久归档和SHA确认后才释放对应tmpfs。新诊断目录已存在、未知新批、原种子已消费等都拒绝，不当作resume。

## 种子及证据

本版一个配对种子在登记前完整历史JSON查重（研究目录、外部experiments、plan），并作独立文本查询。旧已用和未飞预留不复用；只有本版initial audit/execution/manifest/unattempted四份准确SHA登记可豁免，没有历史目录豁免。资格/授权收据不复制具体新seed列表。只有IMU随机源明确播种，其他传感器和宿主调度不声明独立。

新输出根为外部 `R03_upstream08/diagnostic01`；每轮 `diagnostic_metrics.json` 保留真实原始ULog/来源、全部保护检查以及raw gyro→IMU→EKF→selector时序。原日志/失败/未执行保持，独立回放只写全新目录。科学检查失败可继续离线提取已有诊断数据，但不能改判、补齐不存在的尾窗或启动下一轮。

全速gyro只是新增观测，不能代替未记录的uORB消费generation或宿主调度顺序；新日志I/O也可能影响宿主负担，应如实记录。原安全超时、健康门槛和多EKF自动切换不得降低或关闭。
