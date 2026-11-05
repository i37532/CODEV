# V03 协议01：离线保护 + 唯一一次PID日志验证

本说明与JSON在首次飞行前冻结；任何必需失败停止，无诊断补飞。

## 保护契约

StaVelocityProtection是独立C++14测试专用适配器；MODE1仍不可用。不能称飞行启用ESTA保护。

1. configure校验X/Y增益、nu/纠偏限值和掩码；armed只pending，取消请求即取消pending，disarm才生效reset。
   参数只存在离线Config，没有可飞默认增益。Z研究仍拒绝。
2. begin以sample时间确定h，域2–40ms，倒退/超域锁存；首个有效空中帧prime/reset，下一帧才提交。
   每sample最多一次事务，failsafe重算不能积分两次；即使重复sample，退出/接触/disarm仍立即reset。
3. 未armed、disabled、原Takeoff未到flight、landed/contact：reset抑制。取消/ramp超时/接触/弹跳/退出均不积累旧nu。
   恢复后重新prime，不改全局land detector/Takeoff、不用Gazebo真值。如果原起飞状态永久不释放，不强行放行。
4. XY目标成对NaN表示纯加速度，不积分；半组、无穷目标、选中轴无效测量锁存。有效性恢复不能自行清故障，需disarm。
   EKF同量平移后误差不变则保留nu；先由调用者执行原目标reset变换，非协同平移的选中轴mask拒绝。
   位置/heading reset不旋转NED轴。V04须验证此接口与模块实际接线，不把离线测试当接线证明。
5. 旧nu计算理想a_sta；纠偏限幅后只一次加入原a_ff，NaN表示无FF。不套角速度g，不重复除质量。
6. 原推力映射：倾角→最小集体推力→最大Z→XY余量。a_proxy=(g/hover)*thrust+[0,0,g]只是模型代理。
   原映射XY包含Z需求缩放，未限幅也可能与a_req不等，不能仅凭差值冻结nu；不套机体mixer位或PID的2/Kp ARW。
7. finish先整体校验，再nu独立限幅。若Δnu*(a_req-a_proxy)>0且该NED轴确有限制，或增量加深纠偏限幅，冻结未来nu。
   帮助脱离约束的增量可提交；不重算当步旧nu输出。理想/应用nu分开，不称受保护输出为理想STA解。
8. fault latch不自动切PID，不把零推力/加速度称安全；本次PID飞行只有宿主监控中止策略，限定自有SITL。

## 日志与单位

每个local_position回调一条、queue8；publish_seq对应输入、update_seq累计真实update（包括failsafe第二次）。
最终调用覆盖第一次失败输入/输出，pid_calls=2必须拒绝为正常单次控制。PID active_axes=0，pid_axes由有限目标/状态判断。
V03无分频或成功研究模式切换，因此不虚构held样本/生效代次；V04接线后须扩展相应证据。

- input_timestamp=local_position.timestamp，另存timestamp_sample；input_dt/used_dt保留PID语义，raw_dt检查采样源。
- p_sp/v_ff/a_ff为调用前输入；v/v_dot实际传入（包括混合Z）；v_sp为位置P、测试项及限速后目标。
- a_req为PID+FF；a_proxy是代理而非实测加速度；thrust/q_sp和真实发布内容同值，以各自output时间戳精确匹配。
- constraint_bits：1倾角、2最小推力、4最大Z、8水平余量；不是机体mixer位。
- reset_bits：1速度XY、2速度Z、4位置XY、8位置Z、16heading、32原地面抑制。
- timing：0有效、1首帧、2重复/倒退、3超域。生产PID只观察，新离线保护则锁存。
- clock0=HRT，在lockstep可能0us，不是板载CPU成本。controller_time包含PID调用及观察，不是STA核耗时。
- PID nu/a_sta均NaN；新保护未运行所以fault0。内环mode来自实际rate诊断且须100ms以内新鲜。

## 场景、阈值与分析

Iris10016/quad_w、empty_grey.world，原启动器与RC中立心跳、Hold流程；seed=null默认引擎，不称独立配对种子。
MPC_VCT_TEST默认0，本轮启动前置1。SITL、空中、AUTO_LOITER、速度和内环PID门禁满足后12s，单次32s：

δv_X(t)=0.2 sin(2πt/8) sin²(πt/32)，0<t<32秒。

四周期、函数及一阶导数端点0、积分0；离线积分位移包络<0.55m。不保证真实飞行净位移0，原位置P仍反馈。
测试项位于原位置P后并经ControlMath合速度限制，唯一轨迹发布者不变；Y/Z/yaw不注入，门禁断开不在本次解锁重启。
60s观察窗必须完整包住32s激励。保留原2.5m起飞转Hold逻辑，实际高度另报，不冒称精确2.5m定高。

主指标是实际消费s=v-v_sp的sample时间加权三轴RMSE/IAE；TV只用真实更新，32s与60s分别报告。缺样不插值补造。
主窗口序号完整、双时间单调、raw_dt真实；整个飞行mode0/内环PID-div1、无故障/failsafe且必需状态有效。
异步下游只精确时间戳相交：最低80%、最大间隔0.25s、匹配值误差0。来源V00/V01实测约90%，不是要求虚构100%。
本轮必须证实可实现性，不事后改门槛。

V04预门槛见JSON：逐轴paired RMSE≤1.25×PID+固定绝对容差（基于V00/V01噪声）；Y/Z/yaw/位置也有门槛。
保留倾角15°、高度误差1m、XY偏移2m、水平速度1m/s、悬停垂直速度0.6m/s；约束占比≤5%、连续≤0.5s、故障0。
未来一个候选/6次配对飞行，额外参数搜索预算0；仅冻结规则，V04参数/种子/源提交及执行仍需另行授权。
