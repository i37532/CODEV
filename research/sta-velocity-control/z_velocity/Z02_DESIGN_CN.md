# Z02 真实 Z 速度接线（2026-09-27）

依据用户“现在开始对 z 轴的替换，不用我授权，一直到完成为止”，在
`research/sta-velocity-control` 从 `9f0dff53a25e01fbd9acfb97d7ce8da67e96930f`
继续 Z01→Z02→Z03。普通修复和新 SITL 批次已有持续授权，但每批仍须先冻结源码、
场景、种子、阈值与预算，首个必需失败停止该批，保留失败；不 push、不实机、不扩大 XY。

## 接口与边界

- 仅 SITL `MODE=1/AXES=4`，本地 NED 向下速度。X/Y 原速度 PID；位置 P、姿态、rate PID 不变。
- 原 MODE0/AXES0、MODE1/AXES1 含义保留；3/7、MODE2 不开放。
- 独立 `MPC_VC_L1_Z/L2_Z/NU_Z/A_Z` 默认均 0，未设有效增益不可选择；armed 修改仅 pending。
- `s=v_z-v_z_sp`，m/s；纠偏和 ν 为 m/s²；λ₂ 为 m/s³。旧 ν 算输出，候选每采样最多提交一次。
- 不使用角速度 g，不除质量；原加速度 FF 在适配层只加一次。XY NaN 配对原规则保留。

## 生命周期与日志

`sta_velocity_ctrl_status.z_phase`：0 非 Z；1 地面/起飞 ramp 的原 PID；2 单次 PID 交接；
3 Z ESTA；4 原加速度-only。实际 `active_axes/committed_axes/pid_axes` 与阶段对应，
不能将有效配置 AXES4 宣称成起飞全过程 ESTA。

地面/起飞状态沿用原 Takeoff 和 land detector。离地且 flight、无 ground_contact/landed 时，
首个合法速度样本仍计算原 PID，并令
`nu_entry=(a_pid-a_ff)+lambda1*sqrt(abs(s))*sign(s)`。
输出保持同帧 PID 值，不在边界样本积分 ESTA；下一样本开始 ESTA。
检查种子、纠偏限值及 Z 推力映射无削顶，不能表示时锁止，不能偷偷回退 PID。
正常空中只计算 XY PID，不更新/叠加闲置 Z PID。退出、接触、取消、纯加速度、disarm 后重新交接。

保留原 PID 的发布时间 dt/clamp；ESTA 使用原始 sample 差，2–40ms 有效域，重复/倒退/长停顿拒绝。
同帧失败重算不得第二次提交。无有效输出不等于安全悬停；宿主必须中止，非实机安全机制。
Z/vz EKF reset 都保守锁止：降落消费混合 vz/z_deriv，不能仅凭目标增量宣称协变。
所有原始 reset 及失败日志保留。

## HTE 与限幅

原映射 body_z 取决于 XY 加速度与倾角限制，不依赖 Z 加速度。固定同一 XY、误差和 FF 时，
`a_new=g+(H_old/H_new)*(a_old-g)` 保持限幅前整个推力向量。
因此 `nu_new=nu_old+(H_old/H_new-1)*(a_old-g)`；使用已经提交的当前 ν、上次消费误差/FF，
不是复制 PID 的积分补偿，也不是取旧输出忽略刚提交的 ν。
`z_hte_shift` 记录真实补偿。无效 H、Z 最小/最大推力削顶、状态/纠偏不能表示时锁止，
不 clamp 后假称连续。XY 推力余量仍由原 Z 优先分配决定。

理想 `a_sta/nu_ideal`、应用 `a_req/nu_applied` 和 `a_proxy=thrust*g/H+gravity` 分别记录。
后者仅为推力映射代理，非测得的真实加速度。保护依 NED Z 限幅残差只冻结加深约束的 ν 增量，
不引用机体 mixer 位或 PID `2/Kp` ARW 修改 ν。HTE/位置/姿态/电机滞后仍是对象动态。

## 下一阶段任务接口

新增默认关闭 `MPC_VCT_TEST=2`：复用已验收的一次性 12s settle、32s 平滑正弦，
幅值减半为 0.1m/s，仅加到 post-position-P 的 Z 速度目标，再通过原上下限。
唯一目标发布链仍是 Navigator→FlightTask→位置模块，没有竞争发布者。
TEST1 的 X 波形/时序不变。Z03 先独立 PID-only 小垂直任务，固定可实现日志/安全门槛后再配对。

本设计/离线通过不代表完成 Z03 飞行，不代表论文显著改善，不代表实机可用。
