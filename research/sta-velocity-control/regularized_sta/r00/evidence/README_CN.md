# R00 基线、实际周期与环境证据

本目录只做离线只读审计；未启动仿真、未编译生产固件、未执行 MATLAB、未分配新种子、未读取 V09 或新留出数据。它不代替 AX05 的 320 轮验收重放，也不授予后续飞行权限。

## 复现和实际检查

在仓库根目录执行：

```bash
python3 research/sta-velocity-control/regularized_sta/r00/evidence/test_audit_baseline.py
python3 research/sta-velocity-control/regularized_sta/r00/evidence/audit_baseline.py
```

第二条仅向 stdout 打印 JSON，不写日志、不启动飞行。其固定资产核验针对 R00 的 AX05 基线；R01 以后如果生产源文件合法变化，旧资产指纹检查应当失败，不能以改写旧指纹让它通过。

2026-10-16 实际执行结果：Python 审计辅助函数单测 **8 项，退出码 0**；实际审计退出码 **0**。没有 C++ 用例或飞行用例被本子审计执行。8 项覆盖 8/12 ms 分布、倒退、重复（不去重）、不足两点、八配置共享参数、组合特有参数拒绝、内环误配、错误 MODE/AXES。多次复核同一套测试仍计 8 项，不叠加计数。

审计内含 15 条环境/版本命令，逐条 stdout 与退出码在最终 `baseline_audit02.json` 中。`baseline_audit.json` 保留首轮成功审计原件：它未包含后来追加的物理模型、容量估算、当前离线参数和脚本指纹字段，不代表最终脚本输出。`02` 是追加字段后真实重新执行并退出 0 的输出，不能把两次检查计成八份独立原始日志。`gazebo --version` 输出 11.10.2 但退出 255，明确只记版本诊断，不算 Gazebo 仿真成功；`pgrep -a -x 'px4|gzserver|gzclient'` 退出 1，表示检查时无这些残留进程。其余 13 条退出 0。

审计脚本 SHA-256 为 `8402317475fca669bb60d74725d57be6c2460cd1b69cf2f682b39782bc046f20`，与最终 `baseline_audit02.json` 的 `script_sha256` 一致；测试脚本为 `52c7939b38e6a96e057bd73d10495a284e50f3a4690e5abe545838d3fb178bbd`。下文所述 JSON 均指 `02`。

## 基线与参数

- 研究分支：`research/sta-velocity-regularized`。
- AX05 实际飞行源码：`794301664cc0aacee6b5c62987531ab6f0b33fdf`。
- AX05 结果及新分支起点：`0a5796c3ed69d2e415696cf2450fbde74d56e6ea`；二者 `src/msg/Tools/sitl/ROMFS` 无差异。不要把结果 SHA 当实际飞行源码 SHA。
- 33 个递归子模块提交匹配、内部无改动；完整列表见 JSON。500 个仓库冻结资产及 7 个外部资产 SHA-256 均匹配。R00 团队正在添加的研究文件单独出现在工作区快照，未清理或回退它们。
- 八配置参数位于 `research/sta-velocity-control/axis_ablation/ax04/parameters/{pid,x,y,z,xy,xz,yz,xyz}.json`。每份 124 项，122 项完全相同，仅 `MPC_VC_MODE/MPC_VC_AXES` 随配置变化；完整共享表、每份文件 SHA 在 JSON 中。
- 水平速度 PID 的 P/I/D 为 2.16/0.48/0.24，Z 为 4/2/0。ESTA X/Y 的 λ1/λ2/ν 上限/加速度上限为 0.5/0.1/0.4/0.8，Z 为 2/1/4/6。λ1 的单位是 `(m/s²)/sqrt(m/s)`，λ2 为 m/s³，ν 与输出纠偏为 m/s²；不能把这些值当角速度域参数。
- 位置 P、姿态及角速度环保留原算法；`MC_RTC_MODE=0, MC_STA_AXES=0, MC_RTC_DIV=1, MC_RATT_TEST=0, MC_STA_TKO_MGT=0, MPC_VC_DIV=1`。抽样运行实际参数和状态均核实；当前持久化参数与生成默认值合并后也满足这些值，但后者仅离线检查，不冒充新运行证明。
- `MPC_USE_HTE=1`，初始悬停推力 0.5，空中/着陆倾角上限 45°/12°，推力范围 0.12–1，降落速度参数 0.6 m/s、最大下行速度 0.55 m/s。其余联动参数不能因本段只列重点而省略加载。

## 四份旧原始 ULog 的实际时间源

从已完成 AX05 清单中固定抽取每任务最早的 PID 和 XYZ 主日志；先核对索引中的字节数与 SHA-256，解码后再次核对原文件未变。每份只选择原 64 秒激励窗口，共 **25,600 条状态样本**，并解码 `sta_velocity_ctrl_status`、`velocity_ctrl_selection` 和 `vehicle_local_position_log` 三话题。ULog 流无 dropout/损坏；这不是所有话题完整验收。

| 旧运行 | 任务/配置 | 种子 | 样本/间隔数 | sample 周期分布 | 平均频率 |
| --- | --- | ---: | ---: | --- | ---: |
| run007 | H / PID | 52020 | 6400 / 6399 | 8 ms×3200；12 ms×3199 | 100.0031 Hz |
| run008 | H / XYZ | 52020 | 6400 / 6399 | 8 ms×3200；12 ms×3199 | 100.0031 Hz |
| run163 | V / PID | 52016 | 6400 / 6399 | 8 ms×3199；12 ms×3200 | 99.9969 Hz |
| run165 | V / XYZ | 52016 | 6400 / 6399 | 8 ms×3199；12 ms×3200 | 99.9969 Hz |

`timestamp_sample` 与 `input_timestamp`、状态发布时间分别计算分布，不互相替代；`raw_dt/input_dt/used_dt` 和 selection 的 h 均为 8/12 ms。DIV=1 在这批证据中意味着每有效回调更新，**不是固定 10 ms，也不是 250 Hz**。后续离散仿真必须覆盖实际 8/12 ms 变步长，而不能只跑理想固定 10 ms；抽样分布不构成所有未来回调的上界。

四份窗口实际 PID 为 MODE=0/AXES=0/PID_AXES=7，XYZ 为 MODE=1/AXES=7/PID_AXES=0；均角速度 PID、DIV1，无 held 更新。XYZ 接管阶段 `z_phase=3`，PID 为 0。相同外部任务不代表两算法消耗的合成速度目标逐样本相等。

## 真实模型、启动链与随机源

启动器仍是 `./sitl/run.sh --headless --backend gazebo --model iris`，但合格试验由 AX04 运行器配置 `GAZEBO_MODEL_PATH` 以优先加载派生 Iris，以及插件路径、种子与独立日志目录。仅手工调用启动器而不加载这些资产不能声称复现合格模型。

派生模型为 `research/sta-velocity-control/axis_ablation/ax02/models/iris.sdf`，SHA-256 `fe9900329b47f3afb3f2aafac164af047a6feb0e676ea74e658ada5e887b5150`；world 为 `sitl/worlds/empty_grey.world`，SHA-256 `09d9a334728b35a5ca0392e8751e3df5b8aea8b1d5019f8e850a4b0b8bc57b96`。模型沿用已验收接触设置 kp=2500 N/m、kd=50 N·s/m、max_vel=0.2 m/s、max_contacts=4，而非重新修改动力学。

base_link 质量 1.5 kg、IMU link 0.015 kg、四个 rotor 各 0.005 kg，另有 `model://gps` include；不能把 base_link 质量称整机精确总质量。基座惯量对角为 0.029125/0.029125/0.055225 kg·m²；电机上升/下降时间常数分别 0.0125/0.025 s，推力常数 5.84e−6、力矩系数 0.06。外部 MATLAB 所用简化质量/单一电机滞后不能自动当此模型的标定值。

world 的 ODE 最大步长 0.004 s、实时因子 1、物理更新 250 Hz，不等于速度控制频率。AX05 的主要受控随机源是 `M10_IMU_SEED` 指定的 IMU 引擎；seeded IMU 插件及其他外部插件指纹已核对，插件加载与任务元数据见每份日志的 model/world 记录。宿主调度、启动初始化等不由该 seed 完全控制，不能宣称所有随机源相互独立或完全确定。本审计未登记/使用新种子，也未读取保留正式数据。

本地 g++ 11.4.0、CMake 3.22.1、Ninja 1.10.1、Python 3.10.12、NumPy 1.26.4；全部版本/命令原文见 JSON。现有固件 SHA-256 `3c31069dc295edfa535b87909e39544d09a42acb2c54182421324e435386fa09` 仅证明磁盘现有旧基线文件，不能代替 R01 以后新源码构建。

## 空间估算与停止边界

本次快照磁盘可用约 **64.93 GiB**，`/dev/shm` 可用约 **7.53 GiB**。AX05 320 轮 `formal01 + replay01 + audit01` 实占 41,186,611,200 字节；线性折算后续最多 290 轮约 **34.76 GiB**，再保留 10 GiB 系统/编译余量，总需约 **44.76 GiB**。此刻未显示容量阻塞，但这是依旧任务时长及旧日志规模的估算，不是上界或完成承诺。新日志增量、构建产物和其他进程可能消耗空间，应每阶段重查；本审计不删除旧数据。

## 完整阅读清单

以下 13 份文档已完整阅读，分段输出遇截断处已补读；这是本子审计的阅读范围，不代替团队其他成员负责的原主计划、Z02/Z03 与历史日志专项审计。

外部 `/home/yr/Desktop/codev doc/plan/`：

1. `VELOCITY_STA_REGULARIZED_TODO_CN.md`（含后追加的持续授权）
2. `VELOCITY_STA_REGULARIZED_PROMPTS_CN.md`（含后追加的持续授权）
3. `VELOCITY_STA_REGULARIZED_STATUS_CN.md`（含后追加的持续授权）
4. `VELOCITY_STA_STATUS_CN.md`（983 行版本，含历史失败及后续修订）
5. `VELOCITY_AXIS_ABLATION_STATUS_CN.md`（124 行版本）

仓库 `research/sta-velocity-control/reports/`：

6. `AX01.md`
7. `AX04.md`
8. `AX05.md`
9. `V07.md`
10. `V08.md`
11. `E01_XYZ.md`
12. `V06.md`
13. `V06_SOFT_LANDING.md`

历史文档中的失败、旧授权边界与不同阶段的接管配置均保留；当前阶段仅以新的 R00 范围行动，不将旧飞行成功扩写成新算法成功。
