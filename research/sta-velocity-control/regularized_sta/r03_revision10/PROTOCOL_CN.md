# R03 revision10：仅XYZ九轮，日志重启后相对预热

入口为eb25fecbdba9a499132a16ce16f6b847e4a218d3。revision09 A/X、B/Z、C/XY各9接受、9独立回放、6配对检查已通过，保持其原源码和固件身份。D首轮在预解锁因Missing attitude boundary predecessor失败、零起飞，其余八项未执行作废保留。累计82尝试/80起飞/73接受/7失败/2诊断。

根据用户持续授权，有限新预算9，总上限91=82+9，仅较原90增加1。全历史查重登记种子71731–71733，每块PID先行、ESTA/RSTA顺序沿用原D；准确顺序见manifest.json，run028–036为新目录内编号，不是续旧run028。九轮须全部接受、六配对风险检查及九次独立解码一致才验收D。

## 唯一运行语义修订

旧ready条件是PX4自开机超过30秒。源码/前门证据预检较久时，日志重启后第一次完整读取即满足这个条件，却缺参考时刻之前的姿态样本。真实失败前缀101918字节完整复现原拒绝，不能去重或放宽边界。

本版在首次完整读取新owned日志的warmup sample上定锚，额外等待至少30秒仿真发布时间差后才允许预解锁。仍要求旧定位/高度/遥测条件；180秒宿主超时、500ms新鲜度、完整reference/reset/边界检查不变。新增收据与samples及原增量解析收据独立交叉核验。时钟倒退/重复、读者丢失、已有失败、收据缺失均拒绝，不捕获原检查后重试。

不修改生产控制、dt、保护、参数、传感器、估计器或模型。保留revision09生产修复、全速gyro记录及其已知局限。ABC与新D有运行器提交/固件版本戳及地面预热差异；明确取代revision09未达成的同HEAD36要求，不把不同任务混池、不称同二进制36次。

## 任务、参数和门槛原样继承

仅D/本地NED XYZ、AXES7、TEST8、主激励64秒，约2.5m起飞、90秒观察、降落上锁，DIV1；PID用MODE0/AXES0，旧ESTA MODE1/AXES7，RSTA MODE3/AXES7，MODE2不使用。位置P、姿态、角速度PID固定，内环实际MC_RTC_MODE/MC_STA_AXES/MC_RATT_TEST/MC_STA_TKO_MGT=0、MC_RTC_DIV=1。

127参数和完整任务波形精确继承revision05 D并与revision09核对。水平lambda1/lambda2=.5/.1，nu/纠偏上限=.4/.8；Z=2/1/4/6；RSTA epsilon=.01/.01/.02，无搜索。唯一目标源、一次FF、Navigator/FlightTask与守卫任务适配器、heading和软着陆资产不变。使用项目sitl/run.sh的Gazebo Classic Iris、empty_grey.world、1倍速及冻结播种IMU插件。

每轴主窗/两半窗速度RMSE≤1.25×同种子PID+[.02,.02,.01]m/s；位置RMSE≤1.25×PID+.05m；yaw RMSE≤1.25×PID+.02rad；其他全部安全/日志/限制/reset/time检查按冻结分析链执行，不另改数值。SDLOG_PROFILE=3089保留1041并加2048全速gyro，三个gyro原12ms双时钟及边界规则不变，六路time_slip仅描述。

实际消费v−v_sp时间加权逐轴RMSE、三轴均值、偏差/方差、位置/高度/yaw、nu/限制、真实更新TV、共同带宽与原生谱及宿主成本均保留。三IMU种子块仅小规模开发，不保证全部随机源独立；外部轨迹相同不表示合成v_sp逐样本相同。TV不是能耗，宿主耗时不是板级CPU证据。

## 执行约束

先离线真实非零回归、冻结协议/源码资产并提交，再干净构建资格；入口默认dry-run，明确--execute与源码SHA才飞。前门原始数据和独立回放重验证，全参数逐轮备份恢复、重启；至少12GiB磁盘及512MiB tmpfs，仅管理自有进程。

首个安全/必需有效性/配对/恢复失败立即停批，保留所有失败和未执行项，不续跑、补飞、调参或放宽门槛。必要下一修订只能定位后另冻有限清单。完整R03验收后单独结果提交并按授权普通push，停止R03，不R04/R05/ISTA/实机。本协议冻结时新飞行0，outcomes全部unattempted，不预宣称通过。
