# V04：事件时间与接收器坐标检查的离线修复

日期：2026-09-23。**本次离线修复通过；V04 飞行验收仍为 failed / needs_revision。**

用户授权仅为“离线修复这两类日志检查”。本次没有新飞行、补飞、种子或预算，没有修改控制律、运行参数、安全/性能阈值、起飞逻辑、估计器、Gazebo 模型或历史判定；不 push、不进入 V05。

## 1. 版本与范围

仓库 `/home/yr/Desktop/Codev-autopilot`，分支 `research/sta-velocity-control`；起始 HEAD `110e3f667eaca57280519621d52fe6f63413a774`，起始工作区及递归子模块干净。已完整读取外部速度计划、共同规则、进度表和 protocol06 结果及相关实现；旧报告/协议保留。

Gazebo 子模块仍为 `822050a7ab6fd87972e59f16312f451bce217a56`、ECL 为 `b3fed06fe822d08d19ab1d2c2f8daf7b7d21951c`。实际递归版本、构建命令和退出码保存在外部 `logcheck07_verify04/regression`。所有改动限于 `research/sta-velocity-control` 中的新分析器、测试和文档；不覆盖旧检查器。提交完整 SHA 记录到外部实时进度表，避免报告自引用。

## 2. 两类修复

### 2.1 事件不等同连续采样

旧 accessor 对所有 topic 要求时间戳严格递增。series05 的起飞命令 22 和解锁命令 400 同为 30.200s，两条 ACK 同为 30.208s；不同事件同刻发布合法，不能据此报采样倒退。

新增 [v04_logcheck07.py](../scripts/v04_logcheck07.py) 的事件专用读取，仅允许 `vehicle_command` / `vehicle_command_ack`：保留每条记录及原始顺序，允许不同命令 ID 时间相等；拒绝倒退、无效时间/字段、同时间同 ID 的重复或歧义记录。不排序、不去重、不插值。连续控制/估计采样仍使用原严格递增与缺样规则。

新 [handoff 检查器](../scripts/analyze_v04_handoff07.py) 仍要求 DO_REPOSITION(192) 命令与 ACK 各唯一，核对来源/目标/载荷；ACK 必须接受且处于命令至交接完成之间。迟到、提前、错误地址、重复 ACK 均拒绝，不因新的事件时间规则放行。

### 2.2 按实际编译接收器定义唯一浮点参考

原始 COMMAND_INT 经度整数为 `85456078`。Python 直接除 `1e7` 得 `8.5456078`；接收器源码虽也写除法，但实际编译启用 `-freciprocal-math`，生成乘以 binary64 `1e-7` 的运算，得到 `8.545607799999999`。差异为 1 ULP，约 `1.77636e-15` 度；不是本地坐标参考漂移。

新增 [receiver_profile.json](../v04/logcheck07/receiver_profile.json) 固定接收器源文件 SHA、实际 g++11 编译器二进制 SHA、完整 compile command SHA 和数值优化选项。单一参考为 `binary64(int32) * binary64(1e-7)`，系数十六进制 `0x1.ad7f29abcaf48p-24`。源文件、编译器或命令变化一律要求重新审计，不自动选择最接近日志的表达式。

原始源记录、整数编码、投影和 XY 目标保持不变；另派生 `receiver_expected`，供原始命令及 Navigator 目标严格相等校验。没有增加 epsilon/ULP 容差带。CLI 仍按原显示精度处理；原始 ref_lat/ref_lon 和下游窗口/阈值不放宽。

独立 [C++ 探针](../v04/logcheck07/ReceiverCoordinateProbe.cpp) 使用实际 MAVLink C 编解码、原除法表达式和固定数值编译选项，与 Python 映射逐位比较 **578 个正负、零、边界及邻点输入**。它验证表达式/codec，并非启动完整接收器或飞行。非法整数/哨兵拒绝；在有效观察窗注入真实坐标 1 ULP 或一个 wire 单位的错误仍被拒绝。

## 3. 实际离线验证

最终 `logcheck07_verify04`：**109 个不同 C++、195 个 Python 用例通过**（其中本次新增 15 个 Python 方法；578 个输入不是 578 个额外测试）。SITL 固件、测试构建及 `DONT_RUN=1` Gazebo 构建均退出 0。没有启动模拟器。

新增测试覆盖事件白名单/顺序/重复/缺失、命令与 ACK 时序/地址/载荷、精确坐标映射/无效输入/源记录不变、编译配置变化、真实 ULog 交接与完整高度链、连续采样重复和原始参考变化拒绝、离线预算为零。原 PID/ESTA 速度与角速度、模块、起飞和姿态回归包含在上述总数中。

开发期间失败不删除：

- `logcheck07_verify01` 退出 1：测试夹具属性 `run` 覆盖 unittest 方法，导致 Python 测试中断，不声称完整测试数。
- `logcheck07_verify02` 退出 1：195 项中有 27 个错误，离线复制日志对象漏转发 `dropouts` 等元数据；补齐只读转发。
- `logcheck07_verify03` 退出 1：195 项中 1 失败，坐标篡改测试使用倒数第二行，未保证位于目标观察窗；改为真实 `handoff_ready` 对应行，未改变检查窗或放宽断言。
- `logcheck07_verify04` 退出 0：195 项全通过，109 个 C++ 全通过。失败迭代不累加为成功用例数。

主要命令（工作目录为仓库；复跑需使用新的独立输出目录）：

```bash
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/research/sta-velocity-control/scripts:$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/scripts/verify_v04_protocol04.py --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/logcheck07_verify04'
# 退出0；命令清单见 verification.json 及外部 regression/evidence.json
python3 research/sta-velocity-control/scripts/analyze_v04_logcheck07.py '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series05/run01' --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/logcheck07_reanalysis02'
# 退出0：只表示 revised_checks_passed=true，accepted 强制为 false
python3 research/sta-velocity-control/scripts/analyze_v04_protocol06.py '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series05/run01' --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/logcheck07_historical01'
# 预期退出1：旧检查器仍报 Empty/nonmonotonic vehicle_command
```

新 CLI 强制使用独立新目录，不在原始 run 目录及其子目录写分析结果。可执行加载配置与 [离线范围](../v04/logcheck07/protocol.json) 均为 `flight_authorized=false`、预算 0、任务/种子空；没有新增飞行入口。未执行 MATLAB/Octave、实机、任何新飞行或 PID/ESTA 成对性能比较。

## 4. 旧日志回放与历史判定

用相同 series05/run01 原始 ULog 进行独立 `reanalysis01/02`，均退出 0；最终 [新结果](../v04/logcheck07/reanalysis.json) 为 `revised_checks_passed=true`、`accepted=false`、`historical_acceptance_changed=false`、`new_flights=0`。旧版重新分析退出 1，仍有原错误，见 [旧检查拒绝](../v04/logcheck07/historical_rejection.json)。

真实新检查确认：4 条命令与 4 条 ACK 全保留；192 于 38.756s 接收、38.764s 应答和发布目标，39.064s 交接完成；3 秒高度入口有 301 样本，高度 2.5454–2.5615m，距激励 gate 的就绪时间 8.812s（原上限 10s）。60.160 秒观察/32 秒激励、起降窗口与下游检查通过。期间 Navigator 是事件保持目标，仅 1 条观察目标发布，不伪造为连续采样。

这些属于已知旧日志的**探索性离线适配证据**，不是新的前瞻性验收或独立样本。原批次仍为 1 尝试/1 完整/0 接受，剩余 5 停止；历次累计 5 尝试/0 接受，ESTA 飞行 0、配对 0。因此 V04 不能改为 passed，也不能据此宣称 ESTA 优于 PID。

## 5. 保存与后续边界

主 ULog SHA-256 `d8d97dfd7b54fb512c42669e1b874ea49911abe332495b893a269f0ce5e82f16`。旧 `results06/original_artifacts.sha256` 的 50 个文件校验通过；protocol06 的 **185 个冻结资产逐个未变**。

新增外部证据在 `VELOCITY-STA-20260923/V04/logcheck07_*`，300 个文件（含失败验证及隔离回放副本）列于 [SHA-256 索引](../v04/logcheck07/artifacts.sha256)，索引自身 SHA `decbe9631eb9f684112b45d1e405c9f0be3544807325f0cc87a4d6fe30eaf592`。仓库只保留小型证据、脚本、测试和报告，不纳入 ULog 或构建二进制。最终 [验证证据](../v04/logcheck07/verification.json)、[Python 测试日志](../v04/logcheck07/python_tools.log) 可直接查看；其中 source_head 是本次修改前的真实 HEAD，本次修复文件归属随后提交，不伪称测试时已为干净提交。

EEPROM 参数 SHA 仍为 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，无 px4/gzserver/gzclient 残留。需要再次飞行时，应另行冻结接入新检查器的运行协议、版本和准确预算，取得新批次授权，并在干净源码提交运行；不能直接恢复旧五轮，也不复用旧种子作为新留出。
