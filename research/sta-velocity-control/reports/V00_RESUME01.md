# V00 恢复批次01 — 测试修订通过，启动预检失败

2026-09-21。**needs_revision，V00仍未验收。**
已按用户授权保留现有起飞逻辑并补齐测试，37个C++/16个Python用例通过。
预定最多3次尝试，实际1次启动尝试、0次起飞、0次完成/接受、2次未运行。
第一轮在world核验处停止，未发起飞指令；不能称为飞行失败，也不能当作成功飞行。

## 授权、提交和范围

- 用户授权：“保留现有起飞逻辑，修订并补齐对应测试，再继续三轮基线”。
- 起点8462f8139e88b8976dcd89424c3c04525489b72b，分支research/sta-velocity-control，工作区干净。
- 飞行前协议/测试/运行器提交：`178c9a41c9dd19031f6b4c9202c19d1db2c6231e`。
  以该干净提交重建后启动，FW git-hash在控制台核对一致；没有dirty源码运行或push。
- Takeoff.cpp、PositionControl、ControlMath、HTE、failsafe、姿态与rate控制数学均无改动。
- Takeoff原三个断言改为零初值相符的.375/.75/1.125；新增6项测试：增益变化仍零初值、spoolup取消重计时、
  disarm/rearm斜坡重启、落地后新斜坡、短斜坡/skip、非均匀时间与目标变化。
- logger只在已有HIGH_RATE配置加三个话题的全发布率请求；没有新增消息或控制调度变化。
- 增加PID-only运行器、解码器及工具测试；修订verify工具区分初始快照与实时进度。

## 离线验证（真实执行）

数据根：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V00`。
verification01/02/03均保留，最终verification03/evidence.json含各命令、退出码和XML计数。

| 命令/目标 | 不同用例数 | 退出码 |
|---|---:|---:|
| make px4_sitl_default -j4 | 构建 | 0 |
| make tests TESTFILTER=PositionControl -j4 | 构建+重复15个PositionControl | 0 |
| unit-PositionControl | 15 | 0 |
| unit-ControlMath | 9 | 0 |
| unit-Takeoff | 8 | 0 |
| unit-RateControl | 1 | 0 |
| unit-RateControlDispatcher | 4 | 0 |
| python3 -m unittest discover -s research/sta-velocity-control/scripts -p 'test_*.py' -v | 16 | 0 |
| verify_v00.py --output …/verification03 | 总计37个C++，另16个Python | 0 |
| DONT_RUN=1 make px4_sitl_default gazebo_iris -j4（协议提交前、后） | 构建，无模拟器启动 | 0 |
| run_v00.py（不带--execute） | dry-run，无飞行 | 0 |

重复执行不累计为更多独立用例。原Takeoff失败证据仍在旧20260919数据根，未改成通过。
工具测试验证参数/BSON、PID门禁、时间匹配与RMSE计算；**未覆盖启动器不打印world这一实际控制台分支**。

## 冻结协议与实际尝试

协议、参数、门槛、清单见 [resume01](../v00/resume01/PROTOCOL_CN.md)。
原Iris模型、empty_grey.world、1倍lockstep、原默认随机引擎、seed=null。
计划每轮新进程、预热≥30s、起飞2.5m、悬停60s、降落上锁；第一次必需检查失败就停止。

实际命令（仓库根，配置PYTHONPATH为项目依赖和旧M00 Python依赖目录）：

```bash
python3 research/sta-velocity-control/scripts/run_v00.py --execute \
  --source-head 178c9a41c9dd19031f6b4c9202c19d1db2c6231e \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V00/series01'
```

总退出1；原启动器关闭退出0。ledger准确记录run01 failed、原始SystemExit(1)，
run01/result.json进一步保存实际异常`RuntimeError('Actual model/world not confirmed')`。
事件列表为空，尚未进入预热完成/起飞阶段。没有自动重试、补飞、换目录重跑或继续run02/03。

### 直接原因

运行器同时要求console有`Using: <iris.sdf>`与`empty_grey.world`字符串。
前者实际存在；后者在原Tools/sitl_run.sh用PX4_SITL_WORLD环境变量分支时并不打印。
该启动器早先的`world: none`是make目标形参，不是最终gzserver world选择。
这是一处运行器观测方式错误，**没有证据显示模型启动错误或无人机起飞不稳定**。
不能取消world核验或用预期路径冒充实际进程证据来放行；后续应读取自有gzserver的实际argv和环境/资产SHA，
并用合成启动记录测试“正确world未打印、错误world、其他进程、无有效实例”等分支后另冻协议。
本批次原检查结果保留为失败；不能追改成已验收，也未实施追加飞行。

## 实际参数、日志与恢复

- 起飞前完整CLI参数校验通过（错误发生在这一步之后）：MODE0、AXES0、DIV1、MC_RATT_TEST0、
  MC_STA_TKO_MGT0、SYS_AUTOSTART10016、MIS_TAKEOFF_ALT2.5、SDLOG_PROFILE147、SDLOG_DIRS_MAX1000。
- 启动ULog实际解码：effective_mode=0、effective_axes=0、div_eff=1、armed=0、fault=0。
  这里只确认未解锁启动状态，不能据此声明60秒飞行全过程已核验。
- 源码/固件：178c9a41c9…；固件SHA256
  `8525398de7f0723479795841f86d4c18c8c1a468bd494a579ff8036fe71548b5`。
- 唯一启动ULog：series01/run01/01_48_37.ulg，181541字节，SHA256
  `75d7d67c7ba05fc9d6b69e84cc8dcda1b0a70b63c776cb4be84c07e93edbb05c`。
- ULog dropout=0，仅是短启动记录；没有悬停窗口，所以不产生基线RMSE/周期分布/成功率。
- 控制台另有两个vision轨迹话题订阅数达到上限的警告，及启动阶段未解锁failsafe提示，均保留。
  不把这些称作飞行故障，也不掩盖日志profile并非所有话题都记录成功；后续应核验完整所需话题清单。
- 原EEPROM完整1129字节已逐字节恢复，前后SHA均为
  `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`。
  不是仅将五个模式参数改回去。旧7个日志目录全部仍在，新日志另存09-21目录，未删除旧数据。
- 无残留px4/gzserver/gzclient，工作区保持干净直至新增本结果文档；没有实机连接或旧ISTA试验。
- [结果证据索引](../v00/resume01/results/artifacts.sha256)保存171份外部文件指纹，逐份SHA校验通过。
  ledger、启动结果和解码审计的小型副本一并入库；原ULog保留在外部目录。

## 状态与下一步

Takeoff测试修订任务完成，但三轮PID基线未完成，V00保持needs_revision，V01禁止准入。
该工具错误消耗已开始的启动尝试；按预注册规则停下，余下2次未运行。
需要用户明确允许修正world证据核验、重新冻结批次和准确预算（若需三轮完整基线，建议另授权3次），
保留本次失败，不能自行把“未起飞”从尝试清单删除或追加一轮。

本结果另作明确范围提交；真实结果SHA写入外部进度表。未push。
