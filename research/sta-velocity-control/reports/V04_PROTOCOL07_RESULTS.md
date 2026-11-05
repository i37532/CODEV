# V04 protocol07 / series06：降落期 EKF 切换，按协议停止

2026-09-23。**failed / needs_revision，V04 未通过。** 本批已按用户“重新冻结并授权新批次”执行：首轮 PID 完成起飞、60.388 秒观察及32秒X激励，降落期间发生真实主 EKF 切换和参考/reset变化，触发冻结检查；未完成降落上锁。后续5次停止，没有补飞、调参、改阈值或push。

## 1. 冻结与版本

- 起点 `2f273cff7f54d929bcfe8558285c5af3e111aaff`，`research/sta-velocity-control` 分支，起始主仓库/递归子模块干净；完整阅读速度计划及共同规则、实时进度表、logcheck07修复和protocol06结果。没有回退或清理已有数据。
- 新协议/实际飞行源码提交 **`658e57e8ff549cdb89780c61c53ca8b3ec4faa0d`**；先提交，再在该干净提交构建、回归和运行。新运行器07/飞行入口08绑定已离线验证的handoff07；原协议和旧分析器不修改，生产控制/估计器/模型/参数默认值不改。
- [protocol07清单](../v04/protocol07/README_CN.md)：9601 PID→ESTA、9602 PID→ESTA、9603 PID→ESTA，最多6次。注册前21469份JSON无复用，注册审计21472份；启动前再次扫描，只有本协议注册文件可排除。仅IMU引擎播种，其他噪声/宿主调度不独立，固定PID先行偏差保留。
- 199项冻结资产SHA `4051d5fad43e724db9b3792f55831ecfbfb81eb2ba53279edac36f1ed5420fac`；execution SHA `b26942a6c63f009657585cd80b4e4d3b023a053cf62fcd037408d3bffcb87466`。飞后199项仍全部一致。
- Gazebo子模块 `822050a7ab6fd87972e59f16312f451bce217a56`、ECL `b3fed06fe822d08d19ab1d2c2f8daf7b7d21951c`，递归版本在frozen.json和验证日志。固件SHA `5b2c6c0ce7b32d3d9d86a9bbb9945ead40a90cfa42fa0b69e29d41f7ae001a5f`。
- 原项目启动器 `./sitl/run.sh --headless --backend gazebo --model iris`，实际Iris10016/quad_w、empty_grey.world、1倍速，不是DP1000。原位置P、Y/Z速度PID、姿态及rate PID不变；ESTA候选λ1=1/λ2=.2/ν限.4/纠偏限.8保持，未实际飞ESTA。

## 2. 执行事实

| 项目 | 实际结果 |
|---|---|
| 计划 / 尝试 / 接受 | 6 / 1 / 0 |
| 起飞并完整观察 / 完整起降上锁 | 1 / 0 |
| ESTA飞行 / 配对 | 0 / 0 |
| 未执行 | 5，首轮必需条件失败后停止 |
| 起飞命令事件 | 30.064s |
| 高度交接命令 / 实际接收 / 目标发布 | 38.384s / 38.392s / 38.404s |
| handoff_ready / hover_start | 38.704s / 47.156s |
| hover_end / land_command | 107.544s / 107.544s，观察60.388s |
| 实际AUTO_LAND | 107.680s |
| 原始EKF切换及参考变化 | 111.656s |
| 宿主检出样本时间 | 112.028s，随后关闭自有SITL |

运行器退出1；原始错误 `ValueError('CLI reference representation changed: ref_timestamp')`。没有 `landed_disarmed` 事件，记录到的末端状态仍 armed、AUTO_LAND、landed=false/ground_contact=false；正常退出仿真进程不等于无人机完成正常降落。原 `result.success=false` 和ledger失败保留。

## 3. 不是重复出现的日志精度误报

独立解码两份ULog并逐个核对指纹，原始数据证实在111.656s：

- `estimator_selector_status.primary_instance` 从0→1，instance_changed_count从1→2。
- `vehicle_local_position.ref_timestamp` 从1196000→1192000us；ref_lat/ref_lon未变，ref_alt从488.4815063→488.4812622m。
- XY位置计数2→3、Z位置0→1、XY速度2→3、Z速度1→2、heading3→4。日志delta_z约−0.16417m、delta_vz约−1.27109m/s、delta_heading约−0.00159454rad。这是状态估计切换，不应解释为真实飞机瞬间位移或速度突跳。
- 原始流回放同样拒绝 `Coordinate/reset changed: ref_timestamp`；CLI归档可以独立复现原拒绝。因此不能再通过修打印格式、放宽一ULP容差或只忽略ref_timestamp来处理。

切换前后已记录的实例0/1健康位均为1，gyro/accel fault标志为0；切换前combined_test_ratio约0.23953与0.01611，替代实例累计相对分数向负值移动。这与本版 [EKF2Selector.cpp](../../../src/modules/ekf2/EKF2Selector.cpp) 中“替代实例累计误差显著更低、满足时间条件后，即使当前实例健康也可切换”的机制相符，**不是已证明PID控制失稳、传感器故障或ESTA问题**。这些日志不足以确定创新差异的物理根因，未做上游策略修改。

本协议仅允许准备段证据完整的首次磁航向对齐，不允许任务yaw固定后直到降落上锁再切换primary/reference/reset。原门槛确实被违反，不能因发生在降落或悬停已完成而自动豁免。

## 4. 部分窗口证据（不是整轮验收）

新增只读 [失败审计脚本](../scripts/audit_v04_protocol07_failure.py) 使用原始事件，**没有伪造landed_disarmed来拼成完整飞行**；全部13项诊断检查通过仅表示诊断复现成功，最终accepted仍false。

- 原始命令/ACK均4条，新事件时间语义与固定编译接收器参考检查通过；显式XY来源、目标保持及观察下游检查通过。本次前两项修复没有再造成误拒绝。
- 原始航向链核对到hover_end通过；扩展到原始记录末尾则如实拒绝此次切换。未执行完整高度/起降验收替代；仅计算已完成窗口的描述性指标。
- 真实速度MODE/AXES=0/0，rate0/0/1，MC_RATT_TEST=0、MC_STA_TKO_MGT=0、SDLOG_PROFILE147。到中止的8198条速度诊断中first_fail/retry/fault/failsafe/timing均0、pid_calls1、valid1；内环证据年龄0–4ms。
- 60.388秒观察6039条诊断，约100Hz、最大12ms；完整32秒激励3200条，时间加权X/Y/Z速度RMSE为 **0.044121 / 0.012771 / 0.002278m/s**。约束占比0、真实mixer方向饱和0；不能把包含valid位的raw非零比例1解释成100%饱和。
- 观察期local输出和姿态目标逐位匹配均6039/6039，差0、最大间隔12ms。未完成原完整基线/actuator整轮验收，不声称所有下游无损。
- 补充描述：等权local_position样本高度RMSE约0.06777m、最大误差0.14594m，yaw RMSE约0.00024785rad；口径与32秒时间加权主指标区分。这些只是失败运行的部分窗口数据，不作为合格PID基线或配对改善率。
- 两个ULog均dropout0、无解析损坏；完整分析器仍accepted=false/缺`landed_disarmed`，预期退出1。没有ESTA结果、配对噪声比较或性能结论。

## 5. 测试、命令与退出码

环境和完整启动命令见[冻结说明](../v04/protocol07/README_CN.md)。

| 实际执行 | 结果 / 退出码 |
|---|---|
| verify_v04_protocol04.py --output .../protocol07_verify01 | 提交前109个不同C++/204个Python，SITL和DONT_RUN Gazebo构建通过；0 |
| 同上 .../protocol07_committed01 | 干净658e57e8ff上再次109C++/204Python与构建通过；0 |
| run_v04_protocol07.py --execute --authorization V04-protocol07-series06-six-attempts --output .../series06 --source-head 658e57e8ff549cdb89780c61c53ca8b3ec4faa0d | 首轮降落期参考变化，余5停止；1 |
| analyze_v04_protocol07.py .../series06/run01 --output .../protocol07_reanalysis01 | 未完成降落，accepted=false，缺landed_disarmed；1（预期） |
| audit_v04_protocol07_failure.py .../series06/run01 --output .../protocol07_audit01 | 13项只读诊断通过，不是gtest或飞行验收；0 |
| python3 -m unittest discover -s research/sta-velocity-control/scripts -p 'test_*.py' -v | 结果阶段204项通过；0 |

本次新增9个批次接线测试包含授权/清单/停止/恢复、实际旧日志新检查链及旧job不能改判；包含在204中，不累计多次执行。109个C++含两组各2048步原PID等价及控制/保护/生命周期/姿态回归。没有本轮新增离线测试失败，历史失败保持。未运行MATLAB/Octave、ISTA、V05或实机；未扩大到XY。

## 6. 数据、提交与停止点

大型数据留在 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04` 的series06、protocol07_verify01/committed01/reanalysis01/audit01/results_validation01。仓库 [results07](../v04/results07/) 只纳入小证据和索引。

- 主ULog35055648字节：`46a50a2c0678ead8efd093ee7ad193144a46a0f5c116e202fc1ed6f26b0c523b`。
- 启动ULog201696字节：`b68cb8e04397f4426758ef2d399605db4408c35c8343fc8f5a194a8712f88499`。
- 42份原始工件索引SHA：`4bf1ca3dc0f75f16c0a6b3a1c90b22f981c34aa017e182abd44c973e049043c9`；另163份验证/审计证据索引SHA：`a6c29c568bf0fe6fc74ba4b42a9bf99a96b2bfe50a3c090e300e35b740b5afaf`。全量校验通过，上一批50份原始文件及本批199项冻结资产不变。
- 原EEPROM逐字节恢复SHA：`06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`；无残留仿真进程。失败时只停止自有SITL，不宣称这是实机安全处置。

结果按明确文件列表另行提交，完整SHA写外部实时进度表；本结果提交仅只读诊断/文档/证据，不改冻结执行资产。六批累计6次尝试、仅此前series05完成过1次全任务、0接受；ESTA累计飞行0，V04仍未验收。

下一步建议先离线审计降落期主EKF切换、位置/速度/姿态目标reset传播，以及固定参考验收与多估计器正常行为的关系。需要在“保持严格拒绝”与“另立有充分证据的阶段化切换协议”之间作明确决定；不能自动禁用估计器、只删检查、补飞或续跑剩余5次。此处停止，不push、不V05。
