# V04 protocol09 / series08：待授权新批次

2026-09-26。本次仅离线接线、回归和冻结申请，**未获得新批飞行授权，不自动执行**。旧七批失败不改判，V04仍未通过。

## 清单与预算

| 顺序 | IMU种子 | 速度模式/轴 |
|---|---:|---|
| run01 | 9801 | PID 0/0 |
| run02 | 9801 | ESTA X 1/1 |
| run03 | 9802 | PID 0/0 |
| run04 | 9802 | ESTA X 1/1 |
| run05 | 9803 | PID 0/0 |
| run06 | 9803 | ESTA X 1/1 |

申请最多6次新尝试，启动失败也计次；任何必需单轮/配对检查失败立即停批。没有重试、补飞、额外冒烟、调参或旧剩余五轮复用。六轮/三对全部通过才可验收V04。每轮重启、完整备份/恢复EEPROM；只清理自有进程，中止不等于实机安全着陆。

登记前结构化扫描22023份历史JSON无冲突，文本搜索登记前无9801–9803命中；既有空M06文件例外保留。启动前重扫，仅排除本目录execution.json/seed_audit.json的设计登记。仅IMU显式播种，GPS/气压/磁场和宿主调度不保证独立；保留PID先行偏差。原5000条创新记录配对及跨种子检查不变，不宣称6次完全独立。

新运行目录固定为 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04/series08`，必须不存在。

## 原场景、参数、安全门槛保持

- Iris10016 / quad_w / empty_grey.world，Gazebo Classic、1倍速，原项目启动器；不是DP1000实机。
- 原位置P、姿态、Y/Z速度PID及全部rate PID；rate MODE/AXES/DIV=0/0/1、MC_RATT_TEST=0、MC_STA_TKO_MGT=0。
- ESTA仅本地NED北向X，λ1=1、λ2=.2、ν限.4m/s²、加速度纠偏限.8m/s²。FF、HTE、滤波、默认PID及其他参数不改。
- 原起飞/初次正常磁航向对齐取证，POSCTL稳定1s后固定一次yaw；单次COMMAND_INT保留XY目标并交接至2.5m。唯一目标链Navigator→FMM→位置P/实验X激励。
- 高度2–3m、|vz|<.2m/s连续3s准入，gate后10s内就绪。等待12s，32s激励 `0.2*sin(2*pi*t/8)*sin(pi*t/32)^2` m/s，观察60–62s再降落上锁。准备150s、ACK5s等原超时不变。
- 倾角15°、XY速度1m/s、偏移2m、悬停高度误差1m、垂速.6m/s、yaw20°；约束占比≤5%、连续≤.5s。故障、首次失败/重算、错内环、缺窗口/丢样仍拒绝。任务yaw冻结后至降落上锁的primary/reference/reset变化仍拒绝。
- 配对速度RMSE要求ESTA≤1.25×PID+[.02,.02,.01]m/s；位置/yaw及下游部分覆盖仍用原值，只是开发非劣门槛，不要求ESTA胜出。

完整数值以 `v04_protocol09.load_protocol()` 的继承检查为准。仅允许批次/种子/清单/目录/授权和已获准clock09语义绑定变化。PID/ESTA配置与protocol08逐字节相同。

## 时间检查如何接通

仅vehicle_attitude实例0允许发布同刻，sample必须严格递增；不去重、排序、插值或放宽其他话题。沿用clock09的20ms年龄、250ms覆盖、完整边界/前驱/reset和唯一输出键检查；位置/诊断40ms及在线传输0.5s仍各自独立检查。

实时ULog的最新同刻组可能只写了一半。新入口等待严格更晚的姿态发布，取小于最新姿态发布时间的最后一条position作为封口时点；每次从原参考重查完整历史。尾组保留、后续再查，不永久丢弃；年龄仍受0.5s限制，不无限等待或强制flush。最终分析必须检查完整闭区间至落地上锁，不能用在线时点裁掉末尾。

预起飞参考→在线航向→目标交接内部capture，以及最终核心→输出匹配→首次update→降落分类→高度/交接复核全部接通新检查。在线逐记录检查原15°上限，不仅看CLI快照。旧入口、旧协议、控制律、控制器dt及数值安全阈值均不改。

描述性yaw保留每条记录的原权重；需要唯一姿态关联时同刻组报歧义。没有实际消费sample键，不宣称已证明姿态→rate消费因果。主速度指标保持。

## 授权与命令

冻结execution的 `flight_authorized=false` 如实记录尚未授权。用户后续明确批准本源码/协议/清单后，执行者才可在仓库外记录回执，包含approved=true、stage、完整source_head、execution_sha256、maximum_attempts=6、user_approval原文。回执是审计记录，不是密码/电子签名，不能自行伪造批准。新入口要求当前HEAD和协议哈希精确匹配，旧口令无效；回执复制到批次和逐轮证据。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/research/sta-velocity-control/scripts:$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
# 离线验证，不飞行，目录必须全新
python3 research/sta-velocity-control/scripts/verify_v04_protocol09.py --output <全新验证目录>
# 默认dry-run，不启动、不写运行目录/参数
python3 research/sta-velocity-control/scripts/run_v04_protocol09.py \
  --source-head <本批已批准完整SHA> \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04/series08'
# 仅获得明确授权、干净源码复核通过后追加：
# --execute --authorization <仓库外授权回执绝对路径>
```

飞前仍核对分支/HEAD/工作区/递归子模块、资产/插件/receiver编译profile、种子、参数、端口、磁盘和固件版本SHA。实际启动为 `./sitl/run.sh --headless --backend gazebo --model iris`。新结果另行提交；不push、不V05。
