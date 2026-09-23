# V04 protocol07 / series06：日志修复后的新授权批次

2026-09-23。用户明确要求“重新冻结并授权新批次”。起始提交 `2f273cff7f54d929bcfe8558285c5af3e111aaff`，分支 `research/sta-velocity-control`。本文件为运行前冻结，不是通过报告。先提交协议/源码并在干净提交重建、完成离线回归，再运行；结果单独提交。

## 准确清单与预算

| 顺序 | 新种子 | 速度模式/轴 |
|---|---:|---|
| run01 | 9601 | PID 0/0 |
| run02 | 9601 | ESTA X 1/1 |
| run03 | 9602 | PID 0/0 |
| run04 | 9602 | ESTA X 1/1 |
| run05 | 9603 | PID 0/0 |
| run06 | 9603 | ESTA X 1/1 |

最多六次（启动失败也消耗），三对开发样本，任何单轮或配对必需条件失败立即停止。无重试、补飞、额外冒烟或调参；不复用旧五轮，不执行 V05、ISTA、实机或 push。只有六轮和三对均通过才准入 V04 验收；不要求 ESTA 必胜。

种子注册前结构化扫描21469份JSON，无匹配或未解释的无效JSON；源文本中9601.5/9602.0等为历史耗时而非种子。注册审计21472份，允许排除的只有本新协议 execution.json/seed_audit.json；启动前重新扫描。只有IMU引擎显式播种，其他噪声源/宿主调度不独立。逐对前5000创新记录差<1e-10、跨种子差>1e-6；固定PID先行可能有顺序偏差，不声称6个全随机独立样本。

## 不变的参数、任务和门槛

- 原位置P、Y/Z速度PID、姿态及全部角速度PID保持，真实rate MODE/AXES/DIV=0/0/1，MC_RATT_TEST=0、MC_STA_TKO_MGT=0。
- 唯一候选λ1=1、λ2=.2、ν限.4m/s²、加速度纠偏限.8m/s²；无搜索，原FF、HTE、滤波不变。只替换NED北向X，不是roll；AXES3/7不可用。
- 原起飞，正常首次航向对齐/健康primary完整证据，POSCTL连续稳定1秒后固定一次yaw；保持原本地XY目标，经单次COMMAND_INT交接。目标源仍Navigator→flight_mode_manager→原位置P/实验X激励，无第二个位置/姿态/rate发布者。
- 2.5m目标、2–3m且|vz|<.2m/s连续3秒入口；激励gate后10秒内就绪。12秒等待后32秒X正弦：0.2*sin(2*pi*t/8)*sin(pi*t/32)^2 m/s。完整60–62秒观察后正常降落上锁；原准备/飞行超时不变。
- 原倾角15°、XY速度1m/s、偏移2m、悬停高度误差1m、垂速.6m/s、yaw20°，约束占比≤5%且连续≤.5s；fault/failsafe/首次失败/重算拒绝。原始sample/序号/时间、输出和下游部分覆盖门槛不变。
- 逐对每轴32秒速度RMSE：ESTA≤1.25×PID+[.02,.02,.01]m/s；位置/yaw原窗口与绝对余量不变。是开发非劣门槛，不是科学优越性结论。缺窗口/错模式/错内环/丢样/边界失败不删样换通过。

完整继承字段及数值以 `v04_protocol07.load_protocol()` 为准；本加载器锁定 protocol06/execution.json SHA，并只允许新阶段/预算登记/日志适配说明变化。新 pid/esta/frozen.json 与上一版逐字节相同。

## 唯一日志适配

使用提交2f273cff7f的 `analyze_v04_handoff07.py` / `v04_logcheck07.py`：命令事件允许不同ID同时间戳，仍保持原顺序、唯一192命令及新鲜正确ACK；连续采样仍严格递增。坐标只接受固定接收器编译行为的唯一binary64值，不增加ULP/epsilon容差。源文件/编译器/完整编译命令改变即停止，启动前和解码时均核验。原参考/编码来源、下游目标连续性保持严格。

新增 `analyze_v04_protocol07.py` 把已离线通过的检查用于新批次前瞻性验收，并拒绝不属于本清单的旧job；原logcheck07仍强制历史accepted=false，所有旧脚本/协议/结果不修改。没有生产控制代码改动。

199项执行资产在frozen.json；模型/world/固件/插件/参数/命令/ULog指纹逐轮保存。原始目录固定为 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series06`，必须不存在；参数完整备份，每轮字节恢复，只关闭自有仿真实例。

## 命令

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/research/sta-velocity-control/scripts:$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/scripts/verify_v04_protocol04.py --output <全新验证目录>
python3 research/sta-velocity-control/scripts/run_v04_protocol07.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series06' \
  --source-head <本协议提交完整SHA>
# 上面默认dry-run；完成干净提交验证后，仅本次授权可追加：
# --execute --authorization V04-protocol07-series06-six-attempts
```

绑定新 `run_v04_flight08.py`；实际启动仍为项目 `./sitl/run.sh --headless --backend gazebo --model iris`，Iris10016/quad_w、empty_grey.world、1倍速，不是DP1000。失败后不得更换目录/令牌重跑。历史失败与新结果分开报告，不追改旧接受数。

提交前 `protocol07_verify01` 实际109个不同C++/204个Python全部通过，SITL与DONT_RUN Gazebo构建退出0；本轮新增9个批次/接线测试，含新旧数值规则一致、错误授权无副作用、最多6次/3对、失败停止/参数恢复、真实旧日志修复链及旧job不可改判。合成批次不算飞行。本轮无新开发测试失败；干净提交验证与真实结果另行记录。
