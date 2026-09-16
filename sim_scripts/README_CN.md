# 三个脚本：启动 → 选算法 → 飞任务

所有命令都在普通Linux终端执行。

**终端一：启动Gazebo并保持窗口打开。**

```bash
cd /home/yr/Desktop/Codev-autopilot
./sim_scripts/start.sh
```

**终端二：选择算法，然后执行任务。**

```bash
cd /home/yr/Desktop/Codev-autopilot
./sim_scripts/switch.sh pid
./sim_scripts/fly.sh hover
```

这会自动起飞到约2.5米，稳定后悬停10秒，然后下降、落地上锁。想换ESTA再做同一个实验：

```bash
./sim_scripts/switch.sh esta
./sim_scripts/fly.sh hover
```

想比较8字飞行：

```bash
./sim_scripts/switch.sh pid
./sim_scripts/fly.sh figure8

./sim_scripts/switch.sh esta
./sim_scripts/fly.sh figure8
```

| 脚本 | 做什么 |
|---|---|
| `start.sh` | 打开PX4 + Gazebo；`--headless`可关闭图形显示 |
| `switch.sh pid` / `switch.sh esta` | 落地上锁后切换PID或三轴ESTA，ESTA参数自动加载 |
| `fly.sh hover` | 起飞 → 悬停10秒 → 降落上锁 |
| `fly.sh figure8` | 起飞 → 固定高度飞一圈8字（40秒，约4米×2米）→ 降落上锁 |
| `fly.sh yaw` | 起飞 → 定点做两轮±45°平滑yaw摆动 → 回原航向 → 降落上锁 |

`fly.sh`使用**当前选好的算法**，任务结束后Gazebo保持打开，所以可直接切换算法再跑。8字任务发送平滑的位置目标，保留原位置/姿态外环和已选择的角速度内环；不需要手动控制油门或切飞行模式。飞行任务使用本机14550端口，执行时关闭QGC和其他设定值发布程序。

三轴yaw对比的运行方式：

```bash
./sim_scripts/switch.sh pid
./sim_scripts/fly.sh yaw

./sim_scripts/switch.sh esta
./sim_scripts/fly.sh yaw
```

每次任务自动生成 `sim_scripts/experiments/时间-算法-任务/`，终端显示保存路径与位置/角速度RMSE。yaw任务的 `metrics.json` 还会给出yaw姿态RMSE/最大误差、实际往返角度、roll/pitch角速度耦合及水平位置误差。目录里有：

- `.ulg`：PlotJuggler打开的原始飞行日志。
- `metrics.json`：本次任务的位置、角速度RMSE、限幅比例、诊断丢样等指标。
- `result.json`：任务、算法、参数协议、阶段时间和成功/失败结果。
- `reference.jsonl`：8字任务实际发出的位置参考。

比较时用相同任务分别跑PID、ESTA；建议各重复3次后比较同一指标。同一窗口连续飞行适合调试；正式统计每轮重新启动仿真并保持参数和初始条件一致。新任务不能直接套用M06原小激励场景的45项验收结论。停止仿真：落地后在终端一的 `pxh>` 输入 `shutdown`。

只需使用上面三个入口。其他维护实现收在 `_internal/`，旧日志和参数备份保留。状态检查、参数加载、恢复和故障处理由内部实现负责；飞行时切换算法会被拒绝。
