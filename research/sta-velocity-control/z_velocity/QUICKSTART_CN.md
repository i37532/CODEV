# Z 速度 ESTA：已验收配置与查看方法

仅适用于本仓库 Iris Gazebo SITL；不是 CODEV DP1000 实机参数。
[完整验收报告](../reports/Z03.md)。默认 PID；Z ESTA开发接入通过，但本候选的Z速度误差和请求TV更大。
此处不是新一轮正式实验协议，旧六轮预算已用完；再次比较需新目录/种子/冻结清单，不覆盖旧结果。

## 启动

终端：

```bash
cd /home/yr/Desktop/Codev-autopilot
./sitl/run.sh --backend gazebo --model iris
```

沿用项目启动器。自动验收使用同一脚本的 `--headless` 选项。
旧 `sim_scripts/switch.sh` 是角速度研究切换器，**不要用它当速度环切换器**。

## Z 模式配置

必须在已降落且上锁状态操作；解锁时修改只暂存，不在空中立即换控制器。
以下在 PX4 控制台运行。先确认速度/角速度选择和独立增益；不要未经备份保存覆盖个人参数。

```text
param set MC_RTC_MODE 0
param set MC_STA_AXES 0
param set MC_RTC_DIV 1
param set MC_RATT_TEST 0
param set MC_STA_TKO_MGT 0
param set MPC_VC_L1_Z 2
param set MPC_VC_L2_Z 1
param set MPC_VC_NU_Z 4
param set MPC_VC_A_Z 6
param set MPC_VC_AXES 4
param set MPC_VC_MODE 1
param set MPC_VCT_TEST 0
listener velocity_ctrl_selection
```

应确认 effective_mode=1、effective_axes=4，pending/reject=0；实际armed状态还要看日志。
原地面/ramp仍PID，交接后Z ESTA，XY速度和全部rate PID。
正式六轮还冻结了 HTE、旧起飞管理关闭、下降速度 .55/降落速度 .6、日志profile1171等完整参数；
不能仅复制上述几项便宣称与已验收场景相同。全部参数在 `results03/run*/runtime_parameters_start.json`。
`MPC_VCT_TEST=2` 是自动协议的单次垂直激励接口，正常手动使用保持0，不与其他任务源混用。

切回 PID，同样先落地上锁：

```text
param set MPC_VC_MODE 0
param set MPC_VC_AXES 0
param set MPC_VCT_TEST 0
listener velocity_ctrl_selection
```

## 该看什么

ULog 中 `sta_velocity_ctrl_status`：`v[2]` 与 `v_sp[2]` 是真正消费的Z速度及目标；
`s[2]` 为二者差，NED正方向向下。看 `a_sta[2]/a_req[2]`、
`nu_before[2]/nu_ideal[2]/nu_applied[2]`、`z_hte_shift`、`constraint_bits`、
`timestamp_sample/raw_dt/update_seq`、模式和掩码。
`z_phase`：1地面PID，2单次交接，3 Z ESTA；不能仅凭effective_mode就认定全过程ESTA。
`a_proxy`只是推力映射代理，不是实际测得加速度；同时看高度、XY误差、yaw及motor限制。
原始日志位于外部 `VELOCITY-STA-20260927/Z03/paired01/run01–06`，每轮主日志约80MB。
