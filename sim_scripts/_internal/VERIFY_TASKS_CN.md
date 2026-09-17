# 三入口与飞行任务验证

2026-09-16，在M06研究分支上新增日常脚本，不修改控制源码、冻结ESTA增益、原M06运行器或历史证据。顶层入口只有 `start.sh`、`switch.sh`、`fly.sh`；首版维护脚本及说明移入 `_internal/`，数据与备份保留。

11个脚本单元用例通过，包括参数与地面门禁、切换生效判定、8字端点平滑/闭合/范围/速度、飞行中模式/故障变化拒绝继续；全部shell语法检查通过。端口14550上只有任务程序提供模拟遥控/GCS心跳，8字任务以20Hz发送LOCAL_NED位置与固定yaw；原位置和姿态控制环生成角速度目标。请求LOCAL_POSITION_NED为50Hz，以仿真时间推进轨迹。

真实验证使用 `start.sh --headless` 启动一次Iris，按用户实际操作顺序在同一实例连续执行：

| 算法 | 任务 | 实际任务窗口 | 结果 |
|---|---|---:|---|
| PID | hover | 10.120秒 | 起飞、悬停、降落上锁、ULog解析通过 |
| PID | figure8 | 40.032秒 | 起降及一圈8字通过；实际N/E覆盖4.044/2.092米 |
| 三轴ESTA | hover | 10.148秒 | 起飞、悬停、降落上锁、ULog解析通过 |
| 三轴ESTA | figure8 | 40.192秒 | 起降及一圈8字通过；实际N/E覆盖4.012/2.066米 |

四轮 `result.json` success=true，任务窗口控制诊断更新无缺失；三轴ESTA的实际PID更新数均0。每轮结束后保持Gazebo运行，可以切换算法继续。任务结束恢复SDLOG_PROFILE和MIS_TAKEOFF_ALT，保留用户选择的算法。测试收尾用内部restore恢复最初参数，再正常关闭仿真。

所有数据位于 `sim_scripts/experiments/`：

| 运行子目录 | ULog SHA-256 |
|---|---|
| `20260916-200239-613559-pid-hover` | `ea471021c0098a230e87526de41141e357bbbe76b8eb89b336286324cf2cbd7b` |
| `20260916-200324-625124-pid-figure8` | `c1f1ab94940c78ee37e32da5632f534b1c5b09bef2d01c76468d177808726048` |
| `20260916-200456-959902-esta-hover` | `0d936e768fec5a564e4a84c1d21b3211e3ab7739801bbb52c3faf3afd2d921c4` |
| `20260916-200529-543829-esta-figure8` | `db9272ac25f72d8866176d71413b299bf8089e59776a7f32a050468f14c94294` |

每个运行目录包含实际执行的 `flight_source.py` 快照、所选参数、版本、参考序列、阶段时间、采样与日志指纹。前两轮后额外加强了姿态有限性和8字轨迹覆盖检查；PID的8字ULog已用最终分析器重新解码通过。其他飞行流程未更改；每轮源快照可追溯差异。

指标分别写在各目录的 `metrics.json`。这是四次功能验证，不是各算法三轮统计试验；连续运行的估计器/环境状态并非独立重置。未据此声明哪个算法整体更优，也未改写M06原场景验收结论。本次实际启动headless，GUI仍复用原Gazebo启动入口。

## yaw任务追加验证

新增 `fly.sh yaw`：起飞稳定后保持N/E/D位置和初始航向基准，以平滑五次时间缩放完成两轮±45°yaw摆动，40秒结束时yaw角、角速度和角加速度参考均平滑回到初值，再下降上锁。位置/姿态外环保持原PX4路径，角速度内环使用switch选择的PID或全轴ESTA。分析器检查参考和实际往返范围、yaw姿态误差、yaw角速度误差、R/P角速度及水平位置耦合。

同一headless Iris实例中，PID和三轴ESTA各实际运行1轮，均完成起飞、任务、回原航向、降落上锁，result/ULog解析通过，任务窗口控制诊断无缺失、三轴均无限幅；ESTA任务窗口PID更新数为0。

| 算法 | 窗口 | yaw姿态RMSE/峰值 | yaw角速度RMSE | 实际yaw范围 | R/P角速度RMSE |
|---|---:|---:|---:|---:|---:|
| PID | 40.100秒 | 3.809° / 10.366° | .01942 rad/s | 89.919° | .00431 / .00424 rad/s |
| 三轴ESTA | 40.188秒 | 4.054° / 10.838° | .02306 rad/s | 89.492° | .00627 / .00521 rad/s |

PID数据目录 `20260916-203620-822058-pid-yaw`，ULog SHA-256=`fc9121f920d30f9ac87b2bbe3f678e41fbe1c36fd957112994aa5d362fa010b5`；ESTA目录 `20260916-203807-332739-esta-yaw`，ULog SHA-256=`7cd37feb847718a3c0e1e4e9d149ff2f772d58ed105224a4bfc7fafd5cf0ad73`。这是功能性单轮比较，不能作为论文统计结论；正式比较应独立启动并各重复至少3次。最终共12个内部脚本用例通过，新增yaw参考的双向幅值、端点零速度与模式/故障门禁检查。测试收尾恢复最初参数，关闭仿真。

## ISTA 日常脚本追加验证（2026-09-17）

起点研究分支 HEAD=`4206cf8b302e2d5336727500923ccbf08a19e01c`，工作区原先干净。仅扩展日常脚本及说明，不修改飞控算法、冻结参数/历史证据，不开始M09。原三个入口不变，新增 `switch.sh ista`，读取M08 `iris_ista_rpy_candidate02.json` 并核对冻结SHA；MODE=2、AXES=7，P lambda1=2.0。ESTA继续读取M06冻结配置，P lambda1=2.4。

切换继续要求本仓库唯一Iris SITL、落地上锁；先进入PID清状态、加载参数，再启用目标模式，等待requested/effective一致、无pending/fault及零nu。旧参数备份不覆盖，恢复入口兼容原备份为ISTA的情况。任务目录使用`ista`名称，result记录算法名及实际控制器参数，ULog核对MODE2和全轴无闲置PID。PID/ESTA逻辑和三个轨迹生成器不变。

实际执行：`start.sh --headless`，依次`switch.sh ista`、`fly.sh hover`、`fly.sh figure8`、`fly.sh yaw`、`switch.sh esta`、`fly.sh hover`、`switch.sh pid`、`fly.sh hover`。五轮均退出0、降落上锁、result success=true，实际ULog解析通过：

| 算法/任务 | 任务窗口 | 诊断样本/缺失 | 任务内PID更新 | 额外检查 |
|---|---:|---:|---:|---|
| ISTA hover | 10.120s | 2531 / 0 | 0 | MODE2/AXES7，P lambda1=2.0 |
| ISTA figure8 | 40.140s | 10036 / 0 | 0 | 实际N/E覆盖3.944/2.076m |
| ISTA yaw | 40.200s | 10051 / 0 | 0 | 实际yaw范围89.539°，姿态RMSE4.030°、峰值11.091° |
| ESTA hover | 10.140s | 2536 / 0 | 0 | MODE1/AXES7，P lambda1=2.4 |
| PID hover | 10.120s | 2531 / 0 | 2531 | MODE0/AXES0 |

五轮任务窗口限制比例均为零。ISTA yaw的R/P角速度RMSE=.00649849/.00527266rad/s、yaw角速度RMSE=.02373995rad/s；所有完整指标保存在每轮metrics.json。ISTA首次10秒悬停pitch误差=.00950244rad/s，未把短暂调试任务冒充M08的60秒验收。五轮是在同一实例连续进行，不是独立随机试验，也不据此声称ISTA全面优于PID/ESTA。未重新比较三种算法各三轮8字/yaw，不覆盖正式论文统计。

数据仍在 `sim_scripts/experiments/`，均保留且不提交大型日志：

| 子目录 | ULog SHA-256 |
|---|---|
| `20260917-145807-107227-ista-hover` | `cda003e3dfbb2701b873f572515d9a6a5ea4559904479fc1c244ae28ae614a4e` |
| `20260917-145901-285523-ista-figure8` | `24c50fa7e105b6c1083f6a76d4a35a3d7cb661c47e689eb92c36c800c43817ca` |
| `20260917-150004-265565-ista-yaw` | `355c5c7f004255efdb86e1641a43ca8362d5c0269a193ea2695c7c8e19fff198` |
| `20260917-150111-386737-esta-hover` | `8ccc15af5c783107e1863dbfbc7747a6eecb34349c91338bc727db5d9ab83dc2` |
| `20260917-150145-505037-pid-hover` | `835c16777d24a45c38bbde0dea65fdc25fc100f7d46671cf2f9776f727858789` |

五轮固件SHA-256同为`de1e7509cba7ead26ea328056aa7d30aec289949e8566d19a51168b1c9e1fc1f`。启动器按原流程重建了Git版本元数据，不改变M08算法；不是M08历史批次的b210二进制。已飞flight.py SHA=`9fc93567ad75808e9932dd0a142362033735fa3fa8b7404889213cf071b40e2d`，toolbox.py SHA=`e6a3e5ef7eb6c2dc1fe10fc3c7b13810c182e41a36d474e4d1464e8ab786f062`。每轮保存flight_source.py，源码HEAD是上述起点加本次未提交脚本改动。

脚本18个单元用例、3个shell语法检查通过；新增覆盖ISTA候选02/指纹、三模式CLI分发、地面拒绝与半途加载失败、恢复ISTA备份、有效模式与闲置PID日志负例。M08离线验证入口只调整Python计数为“保留M08最低覆盖数并记录实际数量”，避免新增便捷测试被误报；不降低飞行验收阈值。实际运行：

```bash
python3 research/sta-rate-control/scripts/verify_m08.py \
  --output '/home/yr/Desktop/codev doc/experiments/ISTA-shortcuts-20260917/verification01'
```

退出0：80个C++、33+18=51个Python、6011个独立参考样本/36组对象回归、SITL构建与原数学/模型未改检查通过。完整命令/退出码在该目录evidence.json。MATLAB未运行。

第一次工具验证使用无交互stdin启动，PX4在收到EOF后正常退出，随后的switch按“无本仓库SITL”拒绝，未写参数/未起飞；改为保持交互终端后完成以上五轮。原始启动日志保留在rootfs日志目录，不将此启动方式错误算成控制器飞行失败。用户按README保持终端一开启即可。

收尾执行内部restore并核实MODE/AXES=0/0、disarmed/landed、nu三轴零、无pending/fault，再stop正常关闭自有PX4/Gazebo。备份归档 `.state/restored-20260917-150223-650876.json`。只做headless验证，GUI仍复用原启动方式；仅Iris SITL，非实机。此追加任务未自行commit或push。
