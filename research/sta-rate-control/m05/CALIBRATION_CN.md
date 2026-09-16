# M05 Iris pitch 输入增益与冻结试验规范

开始 HEAD：`e9570f52389bae0aa492a9fb7bfaee4ebcfd96af`，研究分支工作区干净。模型与 M04 相同，沿用实际 Iris SDF、GPS 附属质量、生成后的 quad_w mixer、PWMSim 和 Gazebo 电机映射；不是 DP1000 实机。

## pitch 映射

以 FLU 模型位置减去合成质心，转为 PX4 FRD：`x_FRD=x_FLU, y_FRD=-y_FLU, z_FRD=-z_FLU`。向上升力在 FLU 为正 z，故 `tau_pitch_FRD = sum((x_j-x_COM)*F_j)`。正 pitch 混控指令应产生正 pitch 角加速度，控制误差定义仍为 `s=rate-rate_sp`。

稳态无饱和模型：`q_j=r_j*c_R+p_j*c_P+y_j*c_Y+T`，`omega_j=100+1000*q_j`，`F_j=5.84e-6*omega_j^2`。计算使用实际四电机位置与生成的混控系数；没有假设模型几何与 mixer 完全相同。

总质量 1.55 kg，合成 `Iyy=0.03073440787096774 kg m²`；pitch 力臂依电机编号为 `[0.129032258,-0.130967742,0.129032258,-0.130967742] m`，pitch 混控系数为 `[0.707107,-0.707107,0.707107,-0.707107]`。在 `T=.707, c_R=0, c_P=.004, c_Y=0` 工作点，按完整惯量张量求解并中心差分：

```text
g_P = d(alpha_P)/d(c_P) = 112.7635334435299 rad/s² / normalized command
c_raw_P = a_P / g_P
a_P[k] = -lambda1_P sqrt(|s_P[k]|) sign(s_P[k]) + nu_P[k]
nu_P[k+1] = nu_P[k] - h lambda2_P sign(s_P[k])
```

roll 沿用 M04 标定 `g_R=130.5752831836131`；两轴不共用 g 或 nu。FRD 惯量张量仅有很小 x-z 耦合，计算的 R/P 推力局部 Jacobian 对角项为 130.575283199、112.763533444，R/P 交叉项为零。这里的 Jacobian 不含电机反扭矩、气动力、滤波和动态耦合，不能据此宣称自由飞行完全解耦。

`calibration.json` 保存 `T=.65/.707/.75`、pitch 增量 `±.001/±.005/±.01` 的 18 组正负扫描、资产指纹和局部变化率。模型准静态标定不等于飞行动态辨识；±20% 增益与 25 ms 电机滞后仅用于独立对象的工程敏感性检查，不是统计置信区间。核对脚本：`calibrate_m05.py --output <新文件>`。

## 预先冻结的 M05 开发协议

协议机器可读版本为 `protocol.json`。60 秒 AUTO_LOITER，悬停 15 秒后触发 `MC_RATT_TEST=2`：依次 12 秒 roll、12 秒 pitch、12 秒同步 R/P；每段含幅值 .04/.08/.12 rad/s 的三个 4 秒整周期正弦，正负半周积分相抵。原 mc_att_control 仍是唯一 rates setpoint 发布者，姿态/位置外环继续提供其余轴和推力。

保持 M04 的倾角≤15°、高度误差≤1 m、各轴角速度≤1 rad/s、选中轴输出≤.15、每轴 |nu|≤3、每轮 RMSE 比值≤1.25；禁止故障/中止/回退/failsafe，要求降落上锁。降落场景仍统一使用 MPC_LAND_SPEED=.3、LNDMC_Z_VEL_MAX=.3，清理时恢复启动前实际参数。

在看到 M05 ESTA 结果之前，将非命令轴判据明确为：完整悬停、36 秒跟踪，以及三个 12 秒阶段内，**R/P/Y 每个轴的 rate-rate_sp RMSE 均不超过同场景三次 PID 中位数的 1.25 倍**。不使用事后噪声下限或重新挑选窗口。另报告高度、包裹到 ±pi 的 yaw 姿态误差、交叉轴实际角速度/控制输出、正负 mixer 饱和、nu 连续性与冻结比例。yaw PID 输出通过独立 float32 逐样本重算验证。

初始独立 pitch 参数为 lambda1_P=2.5、lambda2_P=.05、g_P 如上、nu_P 上限3；roll 保持 M04 验收参数。虽初值 lambda 相同，参数槽、状态、饱和位及计算完全独立。若需要调参，保留每个候选和失败，不放宽门槛；最终六轮必须同固件、同场景及同 ESTA 参数。

原 M04 `MC_RATT_TEST=1`、AXES=1 的 roll 场景另外复跑两种模式，各一次，作为原路径回归，不混入 M05 三次重复。自动运行沿用项目 `./sitl/run.sh --headless --backend gazebo --model iris`。开发期间原始 ULog、命令、参数、补丁保存在 `/home/yr/Desktop/codev doc/experiments/M05-20260916`。
