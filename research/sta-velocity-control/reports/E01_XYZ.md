# E01-XYZ：三轴速度 ESTA 集成与验收

2026-09-27，**passed（开发准入，仅 Iris Gazebo SITL）**。

已按用户授权插入 **V05 → E01-XYZ → V06**。原先分别完成的 XY 与 Z 路径，现在完成同时 XYZ 速度 ESTA 的集成和六轮验收。**不是三轴角速度 ESTA，不是实机验收，也不代表三轴性能都超过 PID。** 本阶段无追加调参、无补飞、无阈值放宽；未执行 V06、未 push。

## 1. 版本、范围和交付

| 项目 | 实际记录 |
|---|---|
| 分支 | `research/sta-velocity-control` |
| 起点 | `af3edfd2bbaf3e9e6f012e77f3df92890c11615c`，开始时工作区/递归子模块干净 |
| 协议及飞行源码 | `045f642bf2bad5e532761e59b3d6810be360be58`；全部六轮运行同一干净提交 |
| 固件 SHA-256 | `9867837ae50f9dba8164de32d1f7dd6f00a4067969d1356ba2882bb4b5d58b2b` |
| Gazebo 子模块 | `822050a7ab6fd87972e59f16312f451bce217a56`；33项递归版本见冻结清单 |
| 仿真 | Iris / SYS_AUTOSTART=10016 / quad_w；`sitl/worlds/empty_grey.world` |
| 启动器 | `./sitl/run.sh --headless --backend gazebo --model iris` |
| 环境 | Gazebo 11.10.2、G++ 11.4.0、CMake 3.22.1、Ninja 1.10.1、Python 3.10.12、本地 `.px4-python` 与已有 M00 pymavlink |
| 结果提交 | 独立于源码提交；提交后完整 SHA 写外部 `VELOCITY_STA_STATUS_CN.md`，不在报告内预写自身 SHA |

前置 V05 与 Z03 通过；读取新计划/共同规则/进度及前置设计，保存三份新计划快照，不覆盖旧 v1。实现说明见 [飞前报告](E01_XYZ_PROTOCOL01.md) 和 [冻结接线设计](../e01_xyz/README_CN.md)；后者保留飞前时点，最终结论以本文为准。

新增独立 `_velocityControlEstaXYZ`，仅 SITL 开放 MODE=1/AXES=7；默认 PID 和原 X/XY/Z-only 路径保留。位置 P、姿态及全部角速度 PID 不变。地面/ramp 仍原速度 PID；首个有效空中样本三轴有界原子初始化，之后正常飞行只计算 ESTA，不运行闲置速度 PID。FF 仅加一次；三轴 ν 独立、统一校验后提交，失败不部分写状态。

起飞交接使用 `nu_i=(a_pid_i-a_ff_i)+lambda1_i*sqrt(|s_i|)*sign(s_i)`；完整推力映射无削顶且状态有界才接受，不把分轴代理误称实际加速度。HTE 只补偿 Z，保留非零倾角下的原推力映射；异常、重复 sample、reset 和混合目标变化均有离线测试。原限速、倾角、Z 优先/XY 剩余推力规则不改。无新增估计器或 land detector 修改。

交付：[合格 XYZ 配置](../e01_xyz/qualified_xyz.json)、[冻结协议](../e01_xyz/protocol01/execution.json)、[逐轮与配对结果](../e01_xyz/results01/ledger.json)、[独立回放汇总](../e01_xyz/results01/validation_summary.json)。配置只是开发基准，未写为固件默认值；默认关闭的 TEST4 只在本冻结实验启用。

## 2. 预先冻结的任务和门槛

一组固定候选：X/Y 为 λ1=1、λ2=0.2、ν 上限0.4、纠偏上限0.8；Z 为2、1、4、6。沿用 V05/Z03 参数，不追加优化。s 单位 m/s；a、ν、纠偏限值单位 m/s²；λ2 单位 m/s³。

每轮重启/预热、起飞约2.5m、正常航向对齐与高度目标交接、固定 yaw、观察90–92s、降落上锁。唯一目标链为 Navigator→FlightTask→原位置 P；默认关闭的 TEST4 在速度目标合成处添加小信号，没有第二个外部发布者。

按控制 sample 时间稳定12s后依次 **Z16s → XY16s → XYZ32s**，8s 周期、sin²包络的零面积正弦，水平向量幅值≤0.2m/s，Z≤0.1m/s。零面积指添加的速度激励积分，不保证实际零位移；位置 P 仍在工作，两控制器最终合成 v_sp 不保证逐样本相同。

新配对 IMU 种子22001–22003，各 PID→XYZ ESTA，预算6次。飞前扫描未复用；每对前5000个噪声创新完全相同。仅 IMU 受控播种，其他传感器及宿主调度未独立播种，固定先后顺序；n=3为开发验收，不作正式显著性或普遍稳定性结论。

逐 Z/XY/XYZ 窗和合并64s逐轴 RMSE ≤配对 PID×1.25+[0.02,0.02,0.01]m/s；观察期逐轴位置 RMSE ≤PID×1.25+0.05m，yaw ≤PID×1.25+0.02rad。约束占比≤5%、连续≤0.5s；沿用原绝对安全、时间、reset、完整日志门槛（包括观察高度偏差≤1m、倾角≤15°）。下降参数共同0.6m/s，速度下降上限0.55m/s。**这些是带加性容差的开发门槛，不是性能胜出或统计非劣界。**

## 3. 实际飞行和结果

| 顺序 | 模式/轴掩码 | 种子 | 观察时长(s) | 完整起降/日志/配对 |
|---|---|---:|---:|---|
| run01 | PID/0 | 22001 | 90.108 | 通过 |
| run02 | ESTA/7 | 22001 | 90.080 | 通过 |
| run03 | PID/0 | 22002 | 90.568 | 通过 |
| run04 | ESTA/7 | 22002 | 90.120 | 通过 |
| run05 | PID/0 | 22003 | 90.260 | 通过 |
| run06 | ESTA/7 | 22003 | 90.660 | 通过 |

计划6，尝试6，完整完成6，接受6，配对3/3；新飞行失败0、回退0、重飞0。每个 ESTA 运行恰好一次起飞交接；任务中 active_axes=committed_axes=7、pid_axes=0，requested/effective=1/7。地面阶段和交接帧的 PID 来源明确标记，不能把整段起降称纯 ESTA。HTE 非零补偿次数分别10625/10575/10609；故障、首次 update 失败、同帧重试和时间异常均0。

下表为每种模式3轮的逐轴速度 RMSE 均值，单位 **m/s**；比较实际估计速度和控制器实际消费的合成速度目标，不是位置误差，也不是角速度误差。

| 窗口 | PID X / Y / Z | XYZ ESTA X / Y / Z |
|---|---|---|
| Z单独16s | 0.010137 / 0.010005 / 0.004322 | 0.014590 / 0.017087 / 0.009694 |
| XY组合16s | 0.035313 / 0.034111 / 0.002700 | 0.014918 / 0.016614 / 0.009739 |
| XYZ组合32s | 0.032190 / 0.030526 / 0.004068 | 0.014576 / 0.017192 / 0.009723 |
| 合并64s | 0.029264 / 0.028000 / 0.003852 | 0.014667 / 0.017025 / 0.009720 |

XYZ组合窗口 X/Y 分别降低约54.7%/43.7%，但 Z 误差约为 PID 的2.39倍。Z单独窗口中非命令 X/Y 误差也增加约43.9%/70.8%；XY窗口非命令 Z 增加约260.8%。全部逐窗逐对在原加性门槛内，**不能省略非命令轴退化，只报告水平改善**。

合并64s真实更新序列的加速度请求 TV 均值：PID `[6.1303, 6.4386, 5.6349]`，ESTA `[46.0937, 49.7199, 270.7038]`，约7.52/7.72/48.04倍。TV为 `sum(|a_req[k]-a_req[k-1]|)`，单位m/s²；不是电机能耗或实测加速度。较高请求变化量是本候选的明确代价，不能据此直接量化实机磨损。

观察期高度 RMSE 均值 PID0.050328m、ESTA0.048926m；全部运行最大高度偏差0.171255m。yaw RMSE 均值0.000161→0.000251rad，虽有退化仍通过预定门槛。位置RMSE均值PID `[0.054292,0.059119,0.050294]`m，ESTA `[0.044426,0.051818,0.048888]`m。约束占比/连续时间及有效 mixer 饱和占比本任务均0；不能把未触发真实饱和说成已在飞行中验证极端饱和。

## 4. 测试、日志与复现证据

在干净飞行源码上真实运行 **190个不同C++测试、424个Python测试**，全部通过、全部子命令退出0；SITL、测试和 Gazebo build-only 通过。含 XYZ12、XY11、真实模块27、参数保存5，以及原 PID 逐样本、核心、保护、起降和旧日志工具回归。原 PID 两组各2048步逐样本参考保留。参数重载/0/1/3/4/7切换、armed暂存、disarm/reset、混合NaN、第三轴失败原子性、HTE、倾角/垂直优先、带滞后交叉轴独立对象均有测试；这些不是额外独立飞行。

ULog格式1475字节（<1500）、队列8、保留日志profile原位后得到1171。12个原始ULog（每轮启动短日志+飞行日志）均无记录dropout、无解析损坏。实际速度控制约99.998–100Hz，最大sample间隔12ms，不能称250Hz速度环。内环数据年龄≤4ms；本任务位置输出/姿态输出匹配覆盖均100%、最大差0，最大输出间隔16ms。有效 mixer 反馈100%，其非零bit1是valid位，**不是100%饱和**。

完整姿态双时间白名单、reset、入口高度/航向、降落与输出来源检查沿用冻结链；正常降落时 TEST4 gate退出明确分类，raw标记不擦除。`landing10.consumed_status_proven=false`保留：降落监视器没有逐调用内部消费凭证，不能把它写成额外的消费级证明；控制输出与内环关联证据另由完整分析链检查。

六轮各自新目录独立解码重放，退出0，`xyz_metrics.json`与原结果逐字一致。归档与汇总退出0，逐文件验证310项原始工件指纹。验证/回放文件指纹另在validation_summary保存。原始日志仅留外部，仓库保存约0.56MB小结果/配置/路径/哈希。

历史分析器的原始目标快照含表示未设限的`Infinity`，在6份逐轮metrics中原样保留（Python JSON扩展，不是严格JSON）；这不是控制测量或RMSE允许非有限值。跨语言读取这些快照时需显式处理，不应悄悄重写原始证据。

外部根目录：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260927/E01-XYZ`。

- `paired01/`：真实日志、实际参数、派生模型/进程、命令、事件、种子和ledger。
- `verification_committed01/evidence.json`及`controls/evidence.json`：准确命令、退出码、XML数量与构建记录。
- `replay01/run01`至`run06`：隔离回放；六次analyze与cmp均退出0。
- `final_state01.log`：432冻结资产/33递归子模块/EEPROM恢复实核；SHA-256 `aa9c1bba1634095d8be8ff46f81d7a86db2c21441b01187b8d15dd62843efe32`。
- 仓库 `results01/raw_artifacts.sha256` 自身指纹 `3d9a6197a6c88b5922c61d693727b01a3a1c8bcf949fa80f8a21ead062681a37`。

关键命令如下，均在仓库根目录；实际命令和参数详见上述evidence/result文件。历史运行预算已耗尽，不直接重跑旧run入口或覆盖输出目录。

```bash
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/e01_xyz/protocol01/verify.py --output <新验证目录>
# 已执行并退出0的飞行命令：
python3 research/sta-velocity-control/e01_xyz/protocol01/run.py --execute \
  --source-head 045f642bf2bad5e532761e59b3d6810be360be58 \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260927/E01-XYZ/paired01' \
  --authorization '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260927/E01-XYZ/authorization01.json'
# 只读历史输入，在新隔离输出目录重放；不能覆盖replay01：
python3 research/sta-velocity-control/e01_xyz/protocol01/analyze.py <paired01/runNN> --output <新的隔离目录>
```

## 5. 失败、审查和下一步

离线开发曾有编译、映射核对与测试夹具失败，详见飞前报告；`development/`、`controls01/02`、`verification01/`全部保留。包括理想方向与原`limitTilt`有限精度映射差、旧7拒绝断言、Python三输出接线错误；修复后才冻结。一次早期组合shell末命令成功掩盖前命令失败，按日志披露，不计为通过；最终验证逐子命令记录退出码。本批飞行前后未改生产代码/协议/数值门槛，历史失败不追认。

源码审查覆盖新增XYZ路径、selector、原子状态/HTE、TEST4及日志生成；原位置P/PID/Takeoff/default、X/XY/Z函数体与上游估计器不改。结果提交只包含报告、合格配置、小工件和路线完成说明，不改冻结432资产或原快照。默认/原参数已逐字恢复，EEPROM SHA-256 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`；实际核实速度0/0、TEST0，rate0/0/DIV1、RATT0/TKO0，无残留仿真。

未执行MATLAB、实机、完整任务集、调参搜索、分频、ISTA、V06或正式统计留出。**下一步可以单独开展V06**：明确采用已合格XY或XYZ配置，再冻结悬停/8字/航向变化的任务及预算；不能把这里的低幅固定yaw任务当作已完成8字或转向任务。Z误差和TV代价需继续如实展示，本阶段不以追求胜出追加调参。
