# AX04：正式轴消融协议（冻结，不飞行）

本包独立于 AX02/AX03、旧 V08/V09。正式执行属于 **AX05**，本阶段没有起飞、调参或任何正式结果。
研究问题是固定每轴参数下的轴配置效果，不是每组合最优参数竞赛。合格起降/日志与科学性能优越分别判断。

## 1. 精确预算、顺序和边界

8 配置 PID/X/Y/Z/XY/XZ/YZ/XYZ × H/V 两任务 × 20 个共同新种子块 = **320 次**。
H 160 次全部必要检查及140配对风险门通过，才执行 V 160 次；总280个配对风险检查。
清单以 [manifest.json](manifest.json) 为准；[40块顺序表](ORDER_CN.md) 列全320项。
[execution.json](execution.json) 冻结参数、任务、旧门槛和顺序，[outcomes_unattempted.json](outcomes_unattempted.json) 的320项全为未执行。

种子52001–52020在两个任务复用同一20块，不能说40个独立块，更不能说320个独立算法差或高频帧独立样本。
与开发510xx、V09的41001–41020隔离。仅IMU随机引擎播种；同种子各组/任务核验前5000创新相同，不同种子不同。
GPS/气压/磁力计及宿主调度不完全播种；同创新不等于真实闭环噪声/状态逐样本相同。

排序为8行 Williams 设计，两整套加4行；H补0–3行，V补4–7行，PCG64种子62001打乱块顺序并分配种子。
每任务每配置在各位置出现2或3次，合并两任务每位置恰5次，包括PID。不是任务内精确等次数，也不保证所有前后邻接均衡。
H固定先于V存在任务/时间混杂；每轮重启、同预热，不能通过合并H/V推断独立任务因果。
全部8配置的安全先导资格来自AX03；无需新增未登记PID先导。

由于PID不固定首位，单轮安全/日志立即检查；同块PID一旦可用，立即检查所有新可配对项，块结束必须7对全过。
没有PID时只称单轮有效、配对待定，不称配对通过；不能跨块或跨H门留下待定项。数值风险门与AX03完全相同，不是改变门槛换平衡。
首个必需失败立即停批，原日志、已尝试、失败和未执行均保留。不能重试、替换种子、使用余量另飞、删组、追加调参或正式数据出现后改n。
若后到PID触发某先行ESTA的风险失败，保留所有单轮有效数据和配对失败原因；本块不完整，不将其伪装成完整接受配对。

## 2. 参数、模型和任务保持什么

完整124项公共设置加明确MODE/AXES/任务覆盖；八份 [parameters](parameters) 与AX02逐项相同。
MODE0/AXES0为PID；MODE1/AXES1/2/4/3/5/6/7对应X/Y/Z/XY/XZ/YZ/XYZ。MODE2不启用、速度DIV1。
XY PID=2.16/.48/.24，Z PID=4/2/0；XY ESTA λ1/λ2/νmax/amax=.5/.1/.4/.8，Z=2/1/4/6。
每轴参数跨组合不变，含Z保留地面/ramp PID与有界接管。主窗按选中轴真实active/committed和互补PID轴核验。
位置P、姿态、全部rate PID保留；MC_RTC_MODE0/AXES0/DIV1/RATT_TEST0/TKO_MGT0，其他注入器关闭。
HTE策略/初始参数相同，不假设每轮估计轨迹相同。NED北/东/下，不是roll/pitch/yaw。

沿用原项目 `./sitl/run.sh --headless --backend gazebo --model iris`，1倍速、`empty_grey.world`。
模型是AX03合格派生Iris：base接触kp2500/kd50/max_vel.2/max_contacts4及原seeded IMU库路径；不改模型默认、质量、惯量、传感器或滤波。
仅Iris SITL，不是DP1000实机；[frozen.json](frozen.json) 引用模型/world/插件/完整依赖SHA。

轨迹沿用AX02：起飞约2.5m、原高度交接稳定门、等待12s，主激励64s；观测90–92s，再唯一AUTO_LAND并上锁。
E(t)=sin⁴(πt/64)，ω=2π/32，t∈[0,64]，区间外位置增量、速度和加速度均为0。
H位置增量=(.5E sinωt,.25E sin2ωt,0)m；V同水平轨迹且Z增量=.1E sinωt m。使用原解析一二阶导数，一次FF，yaw固定。
唯一目标源仍Navigator/FlightTask及模块已有SITL任务适配，不增加Offboard发布者。
共同的是外部位置轨迹和前馈：原位置P闭环产生的最终消费v_sp可能不同；另外报告位置误差，不假称开环输入相同。

安全/日志/接管/两半窗风险继承AX02/AX03，不修改任何数值：倾角15°、XY速度1m/s、偏移2m、全程高度[-.5,4]m；观测高度2.5±1m、|vz|≤.6m/s、yaw≤20°。
三轴速度风险上限为ESTA≤1.25PID+[.02,.02,.01]m/s（全64s及两半窗），位置≤1.25PID+.05m，yaw≤1.25PID+.02rad。
限制占比≤.05、连续≤.5s；时间/序号/原始ULog完整性规则、姿态双时钟白名单、下游≥80%/最大250ms覆盖及降落健康保持。
不重新解释旧失败、不为了低误差剔除坏轮。风险门通过不要求指标获胜。

## 3. 指标和统计已固定

详见 [STATISTICS_CN.md](STATISTICS_CN.md)。每轴主窗时间加权RMSE；每任务主指标固定
`J=(RMSE_X+RMSE_Y+RMSE_Z)/3`，不看结果换权重。所有逐轴结果必须并列，尤其Z和控制TV代价。
14个主比较、200000联合种子块bootstrap、95%描述区间与99.642857% Bonferroni近似区间；sign-flip 100000次仅探索性敏感性。
最小实用差沿旧V08约定：平均差≤−.001m/s且同配对PID均值相对降低≥10%，调整区间上界<0；完整20接受配对才给合格改善标签。
不预设ESTA获胜，不把开发Z退化删掉。没有“足够显著就停止”规则。

## 4. 离线入口与以后运行

在仓库根目录执行（现有依赖，不安装新包）：

```bash
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/axis_ablation/ax04/run.py
python3 research/sta-velocity-control/axis_ablation/ax04/test_formal.py
python3 research/sta-velocity-control/axis_ablation/ax04/freeze.py --check
```

`run.py`默认只打印清单，不创建数据目录、不改参数、不启动仿真。即使给`--execute`，没有另行AX05明确授权/精确凭据也拒绝；本阶段没有生成已批准AX05凭据。
旧入口 `axis_ablation/run.sh`、旧sim_scripts和V08仍不改，不能误拿它们执行320项。
AX05需使用本阶段最终干净源码、其重建固件及外部`AX04/qualified_source.json`，凭据绑定完整SHA、协议/资产/资格/固件SHA及320预算。
启动器会make，故在**最终提交后**构建并记录精确固件，避免Git SHA与文件自身指纹循环。`frozen.json`中的先期固件只是历史构建记录，不是替代最终资格。
源码/固件不符就拒绝，不在正式运行入口自动重冻；原EEPROM完整备份/逐轮恢复、唯一输出目录、端口/磁盘/自有进程检查继续存在。
实际外部数据根固定`…/VELOCITY-AXIS-ABLATION-20261008/AX05/formal01`，当前不存在；正式日志不入仓库。

AX05完成或停批后先保留原始指纹、独立完整ULog回放，再把全320项（包括未执行）交给：

```bash
python3 research/sta-velocity-control/v08/evidence_tools/replay_batch.py \
  /绝对路径/formal01 --protocol research/sta-velocity-control/axis_ablation/ax04 \
  --output /新路径/replay
python3 research/sta-velocity-control/axis_ablation/ax04/collect.py \
  --batch /绝对路径/formal01 --replay /新路径/replay --output /新路径/outcomes.json
python3 research/sta-velocity-control/axis_ablation/ax04/package.py \
  --outcomes /绝对路径/outcomes.json --output /新路径/summary.json
```

接受项需绝对metrics/replay路径和各自SHA；不接受同路径、改变的指标、错配置或不同源码。输出拒绝覆盖已有文件。
失败数据仍需AX05单独保留/解码与指纹记录，不由仅回放接受项的工具把失败伪装为合格数据。
`analyze.py 原单轮目录 --output 新独立目录`保留原始记录；没有正式来源凭据的AX03旧日志不能充当AX05数据。
正式0次，下一阶段准确上限320次；不push、不自动AX05/V09/ISTA/实机。
