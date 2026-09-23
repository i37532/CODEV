# V04 protocol04 / series03：CLI 坐标精度检查失败

日期：2026-09-23。状态：**failed / needs_revision**，不是依赖 blocked；V04 未验收。

用户在 protocol04 独立运行器/分析器完成离线验证并提出准确六次申请后回复“允许”。本次据此执行原冻结清单，首轮 PID 在已解锁、未检测离地时中止，其余五轮停止。**计划6、尝试1、检测离地0、完整任务0、接受0、ESTA0、配对0、未执行5。** 没有补飞、改阈值、增加候选或启动 V05。

## 1. 版本、授权与边界

- 分支 `research/sta-velocity-control`，协议/实际运行源码均为 `5b5dc2c0d05986cc7cded7e4477ad79ae4315ce9`；执行前工作区及递归子模块干净。完整阅读速度计划、共同规则、实时进度和前置实现报告。
- 固件 SHA-256 `4d94c6c768dd4bb72039d49a5aab5511e54d6a15cb24bc8717c5e9546aafa027`，执行后仍相同；版本头与源码完整 SHA 一致。
- execution.json SHA `d910b97a31075d609668d6b955d1dc2f2c779a7ff164a06b03afeda2337d7238`；原设计 SHA `c071d1648ee260fcfde411514d11feef6926cf165113739c61bbfd63b4d1db8d`；160项资产快照 SHA `001cdd319bca80873e6e42c5683532deb114f6230daf7d219fd2b91cba7f45c7`。冻结文件不追改；其 `flight_authorized=false` 是申请时历史状态，本次明确用户批准由精确执行令牌落实。
- 原计划顺序：9301 PID→ESTA、9302 PID→ESTA、9303 PID→ESTA。只消耗9301的首个 PID 尝试；不把其余五轮当作可继续执行授权。
- 沿用 `./sitl/run.sh --headless --backend gazebo --model iris`；实际 Iris10016 / quad_w、empty_grey.world、自有进程及 IMU 播种消费均由运行器核验。Gazebo 子模块 `822050a7ab6fd87972e59f16312f451bce217a56`，ECL `b3fed06fe822d08d19ab1d2c2f8daf7b7d21951c`。仅 Iris SITL，不是 DP1000。
- 实际参数：速度 MODE0/AXES0，MC_RTC_MODE0、MC_STA_AXES0、MC_RTC_DIV1、MC_RATT_TEST0、MC_STA_TKO_MGT0，SDLOG_PROFILE147。位置P、XYZ速度PID、姿态/rate PID、Takeoff/EKF/模型未改。

## 2. 失败原因：把打印舍入当成坐标原点变化

| PX4 时间 | 事件 |
|---|---|
| 30.036 s | 预热完成 |
| 30.056 s | 固定原始 ULog 地面参考；记录起飞命令事件 |
| 30.172 s | vehicle_status 记录解锁、AUTO_TAKEOFF |
| 30.456 s | 已解锁监控调用 `check_reference`，报 `Coordinate/reset changed: ref_lat` |
| 30.464 s | 主 ULog 最后的位置样本；本次自有仿真关闭 |

`start_heading()` 改为保存原始 ULog double 坐标；随后 `monitor()` 却仍用 CLI `listener` 输出做比较。生成的 `build/px4_sitl_default/msg/topics_sources/vehicle_local_position.cpp` 对经纬度使用 `%.6f`：

| 字段 | 原始 ULog / 冻结参考 | CLI 打印值 | 舍入差绝对值 | 当前比较门槛 |
|---|---:|---:|---:|---:|
| ref_lat | 47.3977508 | 47.397751 | 约2×10⁻⁷° | 1×10⁻⁷° |
| ref_lon | 8.5456073 | 8.545607 | 约3×10⁻⁷° | 1×10⁻⁷° |

实际同一 timestamp 的原始样本通过现有 `check_reference`，归档 CLI 样本则重现原异常。整个已记录准备段的原始经纬度、ref_timestamp、ref_alt、位置/速度/航向 reset 计数均未变化；primary 保持0。**这是 protocol04 新工具混用原始数值与六位小数显示的缺陷，不是证实飞控坐标重置或 PID 失稳。** 前期合成用例没有覆盖真实 CLI 打印格式与精确 ULog 参考的组合，131项通过不能替代真实链路验证。

纬度是第一个触发项；经度也有同类问题，不能只修本次纬度常数。今后若修复，应区分 CLI 表示一致性与原始 ULog 严格不变性，并覆盖真实重置/微小变化/缺样拒绝，不能把所有参考检查改成宽容差。本次**没有实施该修复或重新冻结协议**。

## 3. 实际日志与未完成项

- 两份 ULog 均真实解码、原始 SHA 核验通过，dropout0、无解析损坏。无 dropout 不代表所有异步话题完整无损。
- 起飞命令事件后42条速度诊断，最大间隔12ms，发布/更新号连续；first_fail/retry/fault/sta_fault/timing/failsafe/excitation_fault均0，pid_calls1、valid1，真实内环 PID0/axes0/div1。
- 同窗口104条rate诊断，最大间隔4ms，发布/更新号连续、fault0。原始位置42条，最大间隔12ms，估计相对地面高度范围约−0.000013至0.005665m；landed/contact仍1、takeoff_time仍0，故报告“未检测离地”，不称完成一次飞行。
- 只观测一次在线原始日志回放，传输年龄40ms；不能据此证明完整飞行阶段的在线时延。日志离线回放通过原参考检查但 ready=false：没有首次空中对齐/安静段准入，更没有 task_yaw 固定。
- DO_REPOSITION、3秒高度准入、60秒观察、32秒激励、正常降落上锁均未执行；excitation始终0、time=-1。不存在完整RMSE窗口，不给算法改善率或虚构性能指标。
- 同种子配对创新、跨种子独立性、配对性能/非命令轴门槛未执行。仅IMU显式seed，其他随机源及宿主调度不独立；本轮不能证明三组配对有效。
- 源码关闭自有仿真并非正常降落、实机安全接管或起降通过。所有旧失败及本次失败保留，不将工具缺陷改判为成功。

## 4. 实际命令、测试与退出码

工作目录为仓库，环境沿用 `.px4-python` 及 M00 Python 依赖目录。

| 检查 | 实际结果 | 退出码 |
|---|---|---:|
| 飞前干净提交 `verify_v04_protocol04.py`，protocol04_committed01 | 109个不同C++、131个Python、SITL及DONT_RUN Gazebo构建通过；本次复核证据指纹，不重复计数 | 0 |
| `run_v04_protocol04.py --execute` | 第1次尝试失败、停止后5次 | **1** |
| `audit_v04_protocol04_failure.py`，独立目录 | 8项真实日志诊断检查通过，复现旧异常；不是8个C++单测，也不是飞行通过 | 0 |
| `python3 -m unittest discover -s research/sta-velocity-control/scripts -p 'test_*.py'` | 本轮实际131项通过；未覆盖的CLI/raw集成缺陷仍在，未伪称已修复 | 0 |
| `analyze_v04_protocol04.py`，独立重分析目录 | accepted=false，缺`hover_start`，预期拒绝，原失败文件不覆盖 | **1** |

本次执行命令仅作历史记录，**禁止复用目录重跑**：

```bash
python3 research/sta-velocity-control/scripts/run_v04_protocol04.py \
  --execute --authorization V04-protocol04-series03-six-attempts \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series03' \
  --source-head 5b5dc2c0d05986cc7cded7e4477ad79ae4315ce9
```

可重复只读审计（输出目录必须全新）：

```bash
python3 research/sta-velocity-control/scripts/audit_v04_protocol04_failure.py \
  '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series03/run01' \
  --output <全新的离线诊断目录>
```

本轮结果整理未再次编译或执行C++，没有生产变更；未运行MATLAB、ESTA飞行、旧ISTA、V05或实机。

## 5. 归档、恢复与提交范围

外部根：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04`。

- 原始批次 `series03`（32个普通文件，不含原模型mesh符号链接的目标），原始索引见 [original_artifacts.sha256](../v04/results04/original_artifacts.sha256)。两份ULog分别196307和9115271字节，SHA完整记录在[run01.json](../v04/results04/run01.json)。主ULog SHA为 `e31d4e5fe706d36d6ddf245d1596fef44808ef5a7e179362b501caeefa4cfaa3`。
- 只读审计 `protocol04_flight_audit01`，完整新分析 `protocol04_reanalysis01`，执行/诊断/测试日志同级保留；[diagnosis.json](../v04/results04/diagnosis.json)和[ledger.json](../v04/results04/ledger.json)保留失败判定。
- EEPROM前后全字节恢复，SHA `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`；无残留模拟器。源固件不变，没有删除旧日志。
- 本次明确提交范围仅本报告、README/V04入口、只读诊断脚本、小JSON/日志/指纹快照。无生产控制、运行器/分析器修复、冻结协议或模型修改。提交前审查diff、原始/飞前证据指纹及工作区，提交后外部进度表记录完整结果SHA，不在报告内自引用。

后续需要另行授权：先修复CLI/raw表示一致性、补真实打印链及严格原始重置拒绝回归，离线通过后重新冻结并申请准确新批次；不得直接续跑当前剩余五轮。本次不push，不进入下一阶段。
