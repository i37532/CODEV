# V04 protocol04：独立运行器/日志分析器及飞行申请

日期：2026-09-23。起点 `57bf4892a8698938db421da78ec8afee21c8c39e`，分支 `research/sta-velocity-control`；开始主仓库/递归子模块干净。完整阅读速度计划/共同规则/实时状态、前置航向审计、protocol03报告及protocol04设计。

本轮仅实现和离线验证。**实际飞行0、种子消耗0，未授权新飞行、未push，V04仍未验收。** 原失败与停止预算不复用。

## 1. 交付与实际改动

- 新 `run_v04_protocol04.py` / `run_v04_flight04.py`：沿用项目 Iris Gazebo 启动器及唯一 navigator 目标链，默认只打印清单。独立授权令牌、准确HEAD/干净工作区/参数/固件/模型/插件/新目录/种子检查；每对通过才继续，任意失败停，不重试。
- 新 `v04_heading_stream.py`：只读当前自有 logger 的连续 ULog。按记录边界增量读取，未写完的尾部留待下次；只过滤不需要的话题以减轻解析成本，原始文件不改。保留实际 primary 多实例、时间/计数/标志，按原40ms样本限制、0.5s确认上限重建证据，缺失/过期/切换/二次reset拒绝。
- 旧 ground/reference 改为准确记录的解锁前 ULog 样本，不依赖CLI四舍五入值；完整原始坐标、时间、heading/counters保留。确认后POSCTL稳定1秒，才一次固定task_yaw；不再加delta、不改变地面/全局参考。单独保存 `height_reference.json`、`task_yaw.json`、`heading_live.jsonl`。
- 新 `analyze_v04_protocol04.py` / `analyze_v04_core04.py`：完整ULog独立重建一次对齐/冻结、2.5m导航指令/ACK/读回/3秒入口、60秒观察内32秒激励、正常计划降落、首次失败与原PID/ESTA数值门槛。CLI重分析必须另给新目录，不覆盖旧结果。
- 保留旧protocol03全部脚本/结果不动。生产 `src/msg/sitl/Tools` 没有改动：控制律、EKF、Takeoff、logger/滤波/默认参数与模型均不变；原位置P、Y/Z速度PID、姿态/rate PID保持。
- 自有SITL关闭有session身份检查与SIGTERM/SIGKILL后备，只操作自身进程组；批次核查无残留后全字节恢复EEPROM。没有把停止输出或宿主中止称为实机安全措施。

## 2. 实现澄清（不是放宽控制性能门槛）

原协议 `selection_gate` 已区分 enabled 时调用1次、disabled时0次；旧通用分析器却把整段一律按1次检查。新版在完整发布序列上检查 `Δupdate_seq=pid_calls`，明确校验disabled调用0；只有实际enabled区间核对控制输出。悬停/激励主指标仍使用全部原始窗口，不删除异常样本、不补零；异常退出重入仍拒绝。新旧PID/ESTA数值核在相同enabled夹具输出逐项一致。

在线CLI依然不是每回调监控。连续ULog用原始时间重建样本和事件；另加“最新CLI位置时间−已解码水位≤0.5s”的传输停止检查。它不放宽原始40ms样本/目标间隔或0.5s对齐确认窗；文件落后/截断/替换/缺话题就停止，不能降级为快照放行。logger正常按至少4096字节块写文件，fsync周期不等于文件可读延迟。本轮没有实测新飞行下的传输时延或CPU影响；若现场不满足仍失败，不能临时加大阈值。

`protocol.json` 保留上一提交的设计；`execution.json` 明确新清单、传输实现和未获授权状态。`execution_ready=true` 仅表示离线实现具备申请条件；仍需用户批准、该提交干净重建及飞前资产/种子再检查。运行入口需精确批次令牌，当前任务没有传入令牌或执行飞行。

## 3. 离线测试与证据

最终验证命令（复跑必须使用新的未存在输出目录）：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/research/sta-velocity-control/scripts:$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/scripts/verify_v04_protocol04.py --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/protocol04_verify05'
```

测试覆盖：正负/零修正与边界、uint8回绕/跳变、准备/后续reset、异步pending/不得借未来标志、主估计器切换含切回、参考不重置、四元数方向、原始时钟/消费样本关联、发布/积分计数、首次失败、事件流缺失/跳号、元数据过期、安静段打断、一次yaw与伪造记录拒绝、完整合成高度/观察任务链、源模式、六次上限/失败即停、EEPROM精确恢复及只关闭自有进程组。

测试数量以最终 `implementation01/evidence.json` 为准：106个既有控制C++ + 3个既有姿态C++ = **109个C++**；原99项加本轮32项 = **131个Python**。PID两组各2048步回归、SITL及DONT_RUN Gazebo构建均通过，不启动Gazebo。批次与高度任务夹具是离线合成/故障注入，不算飞行或独立随机试验。

真实 series02 失败ULog只读回放：增量解析结果与独立pyulog完整解码逐字段数组相同；能确认首次对齐，但只有约0.088s安静段，不能准入。完整新分析器对该旧失败记录返回 `accepted=false`、退出1（缺hover_start，符合预期），不改历史结果；其余验证命令退出0。旧日志没有完整新任务，不宣称真实六轮新链已验收。

开发记录：新增合成降落reset拒绝测试初次1项失败，原因是注入时间在已上锁验收终点之后约10ms；把注入放回降落区间后通过，没有改变验收终点或放宽分析器。初次补丁因上下文顺序未匹配未落盘，已更正。验证04新增启动失败清理夹具把git二进制输出错误mock成字符串，131项中1项error，验证器退出1；改为遵守text/bytes接口后另存05，04原日志保留。重复测试不累计数量。

外部验证目录位于 `VELOCITY-STA-20260923/V04/protocol04_verify01` 至 `protocol04_verify05`，小证据和完整外部指纹索引在 [implementation01](../v04/protocol04/implementation01/)。真实旧日志1049个字段数组与独立解码一致，主ULog SHA仍 `f41c005af1008fbd6fb1441e15b576b5ed2181e86a736141708905da9ca5ccae`。未执行MATLAB、实机、ISTA、V05或新飞行。EEPROM SHA仍为 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`。

## 4. 准确新批次申请（尚未执行）

| 顺序 | 种子 | 速度模式 | 速度轴 |
|---|---:|---|---|
| run01 | 9301 | PID 0 | 0 |
| run02 | 9301 | ESTA 1 | X/1 |
| run03 | 9302 | PID 0 | 0 |
| run04 | 9302 | ESTA 1 | X/1 |
| run05 | 9303 | PID 0 | 0 |
| run06 | 9303 | ESTA 1 | X/1 |

每轮重启、预热、原起飞及确认航向对齐、明确2.5m任务、60秒观察（内含32秒小幅X速度正弦）、降落上锁。内环始终PID；ESTA唯一候选仍λ1=1、λ2=0.2、ν限0.4、加速度纠偏限0.8，Y/Z PID不变。

准确新目录：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series03`，当前不存在。最多6次，包含启动失败；无额外冒烟/调参/补飞。任意必需单轮/配对失败立即停止，旧剩余预算不复用。

种子登记检查见 `seed_audit.json`：初次扫描21101份结构化历史JSON未发现历史种子复用；旧空M06诊断例外保留。源码文本9301/9302另有计数/耗时数值，并非种子使用。最终再扫描并登记，飞前再次核查。仅IMU随机引擎显式播种，其他传感器默认引擎与调度不独立；PID总在每对之前，顺序偏差披露，不能称6次全随机独立样本。

最终提交前登记扫描21143份JSON，除本版自身登记外无复用、无未解释无效JSON；冻结160项源码/模型/插件资产。270份本轮外部验证工件以及旧series02的149份工件均全量指纹复核通过。后续提交后的干净重建证据路径/指纹另记外部实时进度表。

只打印计划（不启动、不改参数）：

```bash
python3 research/sta-velocity-control/scripts/run_v04_protocol04.py --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series03' --source-head "$(git rev-parse HEAD)"
```

授权后才由执行任务加入 `--execute --authorization V04-protocol04-series03-six-attempts`，并先核实该干净提交的重建/全部资产。此文不代表授权。最终明确范围提交SHA记录外部进度表；不push、不提前飞行。
