# V06 protocol03：合格软接触下完整任务回归

2026-09-28，飞前冻结说明，尚未称飞行通过。

前置：V06-SL最终源码94da9279307147154c1bc89de161f3b46b1c6ac9、结果48d6d6d27fac9338820c32b786329120712e5767。专项6/6起降、3/3配对、196 C++/461 Python及独立回放通过；旧失败保留。qualified_contact.json绑定原始证据，运行前核验所有指纹，不拿历史飞行拼接新矩阵。

## 新有限矩阵

| 顺序 | 任务 | 新IMU种子 | 算法与轮数 |
|---|---|---|---|
| 1–6 | hover，TEST5 | 27001–27003 | 每种子PID→XYZ速度ESTA，共6 |
| 7–12 | 固定yaw低速8字，TEST6 | 27004–27006 | 同上，共6 |
| 13–18 | 同8字+平滑heading，TEST7 | 27007–27009 | 同上，共6 |

上一任务六轮/三对都接受才进入下一任务。总预算18、无额外调参；首个必需失败立即停批、不补飞/换种子重试。沿用用户V06持续授权及新增软着陆专项授权；不重复询问起飞、不扩大V07/ISTA/实机、不push。

唯一新接触基准为已合格派生Iris kp2500、kd50、max_vel.2、max_contacts4，正式IMU播种插件保持原样。原模型/world、生产代码/参数/默认值零修改。速度XYZ ESTA合格参数、位置P/姿态/rate PID、HTE、.6/.55下降、64s主窗/90–92s观察、所有原逐轴安全/配对/日志门槛不变。比较的是新接触条件的任务回归，不与旧硬接触数据合组。

## 接线与检查

新增protocol03独立版本，复用合格落地后真实尾段收集及全实例健康检查，未放宽任何时间匹配规则。新增qualification前置指纹拒绝测试；独立v06/scripts转向该新矩阵，手动start也生成同接触派生模型但使用原IMU插件，不作为配对实验。旧sim_scripts不修改。

命令（仓库根，依赖路径按现有脚本配置）：
```bash
python3 research/sta-velocity-control/v06/protocol03/capture.py
python3 research/sta-velocity-control/v06/protocol03/verify.py --output <新外部验证目录>
./research/sta-velocity-control/v06/scripts/fly.sh all
python3 research/sta-velocity-control/v06/protocol03/run.py --execute --source-head <完整冻结SHA> --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260928/V06/series03' --authorization <绑定本次持续授权的JSON绝对路径>
```

实际验证数量、退出码和干净源码SHA由验证evidence/外部进度记录；结果另提交，不把本文当完成结果。完整分析继续检查每半窗/全窗速度误差、位置/yaw/Z、nu与限制、实际算法/输出/时钟、IMU/EKF健康、丢样及配对随机序列。模型/软件与大日志SHA进仓库索引，大日志留外部新series03。

本轮准备曾有一次apply_patch因文档上下文不匹配被原子拒绝，重核工作区后修正；未造成部分代码或飞行改动。未运行MATLAB/硬件/正式论文实验。

提交前verification_working03实际196个不同C++、467个Python全部通过，757资产核对、SITL/Gazebo构建及各命令退出0。手动派生模型启动、真实地面PID→XYZ ESTA→PID已通过，实际gzserver/gzclient及本仓库PX4在场，未解锁。第一次非TTY启动因stdin EOF正常退出（0），没有做切换；保留manual_compliant03.log，随后TTY会话记录于manual_compliant03_tty.log及esta/pid.log。原启动器对带空格路径有既有shell警告，但Using行确认为独立派生模型，不改上游启动器。
