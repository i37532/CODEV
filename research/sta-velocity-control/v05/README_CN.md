# V05：XY ESTA + Z PID

仅 Iris Gazebo SITL，研究分支 `research/sta-velocity-control`。位置 P、姿态、Z 速度 PID、全部角速度 PID 均保留。
`MODE=1, AXES=3` 选择本地 NED 北/东速度，不是 roll/pitch 角速度。XYZ=7 仍拒绝。
保留此前 X-only=1、Z-only=4 的实现/数据；V05 不启用 Z ESTA，不延续旧 ISTA 实验。

## 控制与保护

两轴分别使用 `s=v-v_sp`、`a_sta=-lambda1*sqrt(abs(s))*sign(s)+nu_old`、
`nu_candidate=nu_old-raw_dt*lambda2*sign(s)`；加速度 FF 各加一次，没有角速度 g 或质量除法。
新增 Y 的 `MPC_VC_L1_Y/L2_Y/NU_Y/A_Y`，默认均为 0（未配置），不改变默认 PID。
本轮单一候选 X/Y 均 1/0.2/0.4/0.8，独立储存，不共用状态；不同增益另有离线测试。
XY 使用共同倾角/水平推力矢量约束，Z 推力优先。保护用映射代理的逐轴残差冻结向外积分；
该代理不是真实加速度，也不对 ν 使用 PID 的 2/Kp tracking ARW。
先验证两轴候选与反馈，再一起提交；一次采样最多提交一次。无效事务拒绝发布并锁存，不自动宣称零力矩或 PID 接管安全。
解锁中改模式/轴或有效 Y 增益只暂存，恢复当前请求可取消，disarm 后生效并清状态。

## 任务、预算和准入

协议 `protocol01/execution.json`；新 IMU 种子 20001–20003，每个种子 PID→XY ESTA，共六轮，每轮重启。
唯一目标源沿用 Navigator/FlightModeManager 及已审计的定高/航向交接；无额外 offboard 发布者。
内部默认关闭的 `MPC_VCT_TEST=3` 在原位置 P 后、速度控制前添加平滑速度目标；Z/推力来源不变。
12 秒稳定后依次 X 32 秒、Y 16 秒、XY 16 秒。每窗口有正负速度、零积分和光滑零端点。
X 完全重用 V04 波形；XY 取 X=-Y、各 0.2/sqrt(2) m/s，水平范数不超过既有 0.2 m/s。
定高约 2.5 m，固定 yaw；观测期从 60 秒改为 90 秒，仅为容纳三窗口，不放宽安全数值。
随后原 AUTO_LAND、落地上锁。共同降落参数保持 `MPC_LAND_SPEED=0.6, MPC_Z_VEL_MAX_DN=0.55`。

各窗口和全部激励分别按真实更新与 sample 时间加权计算 XYZ 速度 RMSE/IAE、加速度请求 TV、限制比例/持续时间。
每轴 RMSE ≤ 1.25×配对 PID + [0.02,0.02,0.01] m/s；位置 RMSE ≤ 1.25×PID+0.05 m；yaw ≤ 1.25×PID+0.02 rad。
限制比例≤5%，连续≤0.5秒；原高度、姿态、速度、reset、日志缺样与时间规则保留。
绝不将不同长度窗口的 TV 直接当作算法优劣。三对仅为开发准入，不是论文显著性试验。

## 日志与复现

`sta_velocity_ctrl_status.excitation` 为 X，新增 `excitation_y` 为 Y；`excitation_time` 是统一受保护时钟。
核对 requested/effective=1/3、pid_axes=4、active/committed_axes=3；Z ν 必须 NaN，内环0/0/DIV1。
逐轴核对旧 ν 输出、理想候选、保护后提交和 FF；不把受保护输出称理想解。
保留 V04 的姿态消息白名单/同刻歧义、落地双时钟、reset 和部分下游发布匹配规则；无插值补样或通用去重。
种子只控制 IMU RNG；GPS/气压计/磁力计和主机调度未独立控制。原始日志放外部 experiments，仓库仅保存配置、摘要和指纹。

先运行 `protocol01/capture.py` 冻结，再 `protocol01/verify.py --output <新外部目录>`。
源码/协议明确提交后，重建并再次验证；`run.py` 默认 dry-run，执行时须明确 `--execute --source-head <完整SHA> --output <冻结目录> --authorization <记录文件>`。
授权记录绑定本次用户“不再逐次授权、完成 XY”的原话，不是额外授权请求。
六轮任一必需检查失败立即停止该批，保存失败；仅离线定位后新冻结源/种子/预算，不自动补飞或改判历史失败。
最终独立回放六份 ULog、核对 EEPROM 完整恢复，报告和结果另提交。不 push、不进入 V06。
