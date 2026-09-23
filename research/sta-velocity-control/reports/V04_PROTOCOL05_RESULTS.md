# V04 protocol05 / series04：POSCTL 与 Navigator 目标接口不匹配

日期：2026-09-23。状态：**failed / needs_revision**，不是依赖 blocked，V04 未验收。

本次用户批准新种子9401–9403、各PID后ESTA、最多六次的新批次。已独立冻结协议、明确提交，在干净提交完成构建和离线验证后执行。**实际尝试1、离地1、完整任务0、接受0、ESTA0、配对0、后五次停止。** 首轮PID完成首次空中航向对齐及任务yaw冻结，随后运行器在高度命令前检查无效的Navigator航点而中止。没有补飞、放宽门槛或改变旧结果。

## 1. 源码、协议与实际环境

- 分支`research/sta-velocity-control`，起始修复提交`85b8647644c5d316d41005ce0ddd26f250fa5a81`；完整阅读外部计划、共同规则、状态和前置报告，工作区及递归子模块干净。
- 独立protocol05/实际飞行源码提交：**`95cc6fe33db5051774174219e73a724a851c64ad`**。11个新增研究文件；新运行器/分析器只作protocol05命名与配置隔离，共享已修复的CLI表示检查，未改飞控生产代码、模型或原协议。
- 新[执行配置](../v04/protocol05/execution.json)SHA-256：`a61ffac6b782ad91d744a1cf1af65c0150a8b4ebc088c64611cf9f060248a143`；170项[资产冻结](../v04/protocol05/frozen.json)SHA-256：`0e876083273d02968108296ed68c32c4613a2b693206d5ae8ab4a50f5c4e3ce1`。飞前逐项核对，固件版本含上述完整源码SHA。
- 固件SHA-256：`cef3f8520fe5f51de2d2aae2a47e71fcd7b67b020f020af2c318067262ba0d82`。项目启动器`./sitl/run.sh --headless --backend gazebo --model iris`，Iris10016 / quad_w / empty_grey.world / 1倍；实际进程、world及IMU种子消费均核验。不是DP1000实机。
- Gazebo子模块`822050a7ab6fd87972e59f16312f451bce217a56`，ECL`b3fed06fe822d08d19ab1d2c2f8daf7b7d21951c`，全部递归版本见[记录](../v04/results05/submodules.log)。
- 本轮实际速度MODE0/AXES0、MC_RTC_MODE0、MC_STA_AXES0、MC_RTC_DIV1、MC_RATT_TEST0、MC_STA_TKO_MGT0、SDLOG_PROFILE147。原位置P、XYZ速度PID、姿态及角速度PID、原Takeoff/估计器不变。
- 唯一ESTA候选λ1=1、λ2=0.2、nu限制0.4、纠偏限制0.8，仍未飞行。原32秒零净参考位移正弦、60秒观察、2.5m高度、固定yaw及全部安全/性能门槛未放宽。
- 新目录`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series04`；种子注册审计扫描21210份JSON，无未解释复用（飞前再扫记录在批次目录）。仅IMU明确播种，其他随机源与调度不独立，PID先行顺序偏差保留披露。本轮未完成配对创新或跨种子检查。

## 2. 真实事件与根因

| PX4时间 | 日志/源码证据 |
|---|---|
| 30.076s | 预热完成，固定原始地面参考，记录起飞命令事件 |
| 30.208s | 解锁，AUTO_TAKEOFF |
| 31.228s | 实际takeoff_time，检测离地 |
| 36.684s | 同一primary=0首次空中磁对齐，heading/quat计数2→3，delta约−0.145°、相对地面高1.557m |
| 36.688s | 对齐证据确认 |
| 36.916s | 转POSCTL；Navigator发布current.valid=false、lat/lon=NaN的空triplet |
| 38.044s | 连续安静1.128s后一次冻结task_yaw=1.5756663rad |
| 约38.10s | 运行器解析空triplet，报`Invalid navigator target`，在发送高度命令前停止 |

证据见[只读诊断](../v04/results05/diagnosis.json)、[实际打印](../v04/results05/triplet_before.txt)和[原始结果](../v04/results05/run01.json)。

这次不是CLI小数精度问题，也不是已证明PID控制不稳定，而是**任务运行器的目标接口前提互相矛盾**：

1. `run_v04_flight04.py`要求进入POSCTL并完成航向稳定后，才准备发高度命令。
2. 原`navigator_main.cpp`的POSCTL分支没有活动Navigator模式；切换时及无活动模式时会`reset_triplets()`，把current.valid清零、lat/lon置NaN。原始ULog与CLI完全一致，不是解析舍入或消息短暂丢失。
3. 同一阶段，FlightModeManager仍发布合法本地`trajectory_setpoint`。59个样本的XY/yaw均有限；Z有35个样本通过有限vz制动（Z为NaN），随后Z位置有限。不能把合法Z混合速度目标误判为“控制目标整体无效”。
4. 运行器的`current_triplet()`却要求Navigator全局current有效且经纬度有限。这个前提在它主动等待的POSCTL阶段不成立。
5. **不能只删除检查继续发命令**：当前源码对“param5/6为NaN、param7有限”的DO_REPOSITION，复制`curr->current.lat/lon`，并非自动使用实际位置。此时会复制NaN；必须先重新审计并明确位置保持目标的建立与交接。

源码位置：Navigator的POSCTL分支/重置在`src/modules/navigator/navigator_main.cpp:663`附近，reset实现在`:985`，高度单独修改复制XY在`:320`附近；运行器入口在`research/sta-velocity-control/scripts/run_v04_flight04.py:250`，检查在`v04_task04.py:21`。本次只读核对，**未修改这些文件，未修订下一版任务协议**。

## 3. 实际日志及不能声称完成的项目

- 两份ULog真实解码、指纹核验：主日志11545414字节，SHA`88b9cd401f5e410dac6b50f6ee07073597b01a7a7e910646fe89d321f429e086`；启动日志206779字节，SHA`07f2dff288574f49f5b9f1a18b1ad1a77fb7af5bb444d0601031684fa122d833`。均dropout0、无解析损坏；这不等于所有异步下游覆盖已经验收。
- 命令事件后803条速度诊断，最大间隔12ms；2007条rate诊断，最大间隔4ms。发布/更新序号连续；first_fail/retry/fault/sta_fault/timing/failsafe/excitation_fault均0，PID每次调用1，内环PID、AXES0、DIV1。没有发现起飞同帧重算故障。
- 原始地面全局参考及位置/速度reset计数全程不变；航向事件按冻结规则确认，原始回放ready=true。27次在线读取年龄28–68ms，只证明本段，不外推整段任务和降落时延。
- 已记录相对地面高度范围−0.136至1.887m；尚未执行2.5m高度命令与3秒入口，不把这个准备阶段高度当作已完成悬停的误差。
- DO_REPOSITION发送0次、激励0，60秒观察/32秒主窗口/正常降落上锁全部未执行；没有有效RMSE与PID/ESTA改善率。关闭自有SITL不是正常降落或实机安全保护验证。
- 四个V04批次累计尝试4/接受0、ESTA飞行总计0；旧失败均不改判。本轮剩余5次停止，不能当作继续飞行的授权。

## 4. 测试、命令、退出码与开发失败

| 实际执行 | 数量/结果 | 退出码 |
|---|---|---:|
| 新protocol05专属测试首次执行 | 6项中5过1失败：尚未生成frozen.json；保留targeted01日志 | 1 |
| 完成捕获后的precommit完整验证`protocol05_verify01` | 109个不同C++、147个Python，SITL和DONT_RUN Gazebo构建通过 | 0 |
| 干净源码提交后的`verify_v04_protocol04.py --output .../protocol05_committed01` | 实际109个不同C++、147个Python，构建通过；重复执行不累计成更多独立用例 | 0 |
| `run_v04_protocol05.py --execute` | 首次PID尝试失败，后五次未执行 | **1** |
| 只读诊断首次`protocol05_flight_audit01` | 10项诊断9过1失败：额外诊断错误要求Z位置始终有限，遗漏合法vz制动 | 1 |
| 修正诊断表达后的`protocol05_flight_audit02` | 10项真实数据诊断通过，不是10项gtest，也不改变飞行判定 | 0 |
| 独立完整`analyze_v04_protocol05.py ... --output .../protocol05_reanalysis01` | accepted=false，缺hover_start；预期拒绝 | **1** |
| 结果阶段Python discovery | 147项通过；新只读诊断另执行，不虚增为148项单测 | 0 |

首次诊断的修订只纠正证据解释，飞前门槛、运行器、分析器与原始ULog未改；两份诊断都保存。合成测试通过没有覆盖真实POSCTL→Navigator目标交接，本次明确承认该集成缺口，不用147项通过代替飞行验收。

执行环境为仓库`.px4-python`、研究scripts及M00 Python依赖目录。历史执行命令（**不能复用目录重跑**）：

```bash
python3 research/sta-velocity-control/scripts/run_v04_protocol05.py \
  --execute --authorization V04-protocol05-series04-six-attempts \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series04' \
  --source-head 95cc6fe33db5051774174219e73a724a851c64ad
```

只读复现（输出须全新）：

```bash
python3 research/sta-velocity-control/scripts/audit_v04_protocol05_failure.py \
  '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series04/run01' \
  --output <新的离线诊断目录>
python3 -m unittest discover -s research/sta-velocity-control/scripts -p 'test_*.py'
```

## 5. 归档、恢复与下一步边界

- 原始series04共34个普通文件（不沿模型mesh符号链接收集），见[原始SHA索引](../v04/results05/original_artifacts.sha256)；验证/诊断/重分析及所有失败记录见[外部证据索引](../v04/results05/artifacts.sha256)。大型ULog/CSV只保留外部，仓库保存小摘要与指纹。
- EEPROM全字节恢复，SHA`06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`；无残留模拟器。未删除原始或历史数据。
- 结果提交仅本报告、入口、只读诊断工具和小证据。源码/协议提交与结果提交分离；结果完整SHA在提交后写外部进度表，避免文内自引用。
- 下一步应另获准后**先离线审计并修订POSCTL到AUTO_LOITER的目标交接契约**，明确有效XY保持目标如何产生、坐标转换/航向/唯一发布者以及命令后真实读回；结合本次原始日志覆盖整个状态链，不能只让`valid`检查放行。必要时重新冻结任务/日志规范，再单独申请准确新种子和预算。
- 本阶段到此停止：未修复运行器、未再飞、未push、不V05、不ISTA、不实机、未运行MATLAB。
