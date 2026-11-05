# CODEV 项目交接（2026-11-05 现场核实）

先读 [AGENTS.md](AGENTS.md)。初次交接整理只做文档和只读核查，没有构建、起飞、切分支或安装。现有研究文档原样保留，不将旧报告中的历史“当前”当本轮指令。

发布说明：下列 Git 表、HEAD 与未提交统计是**交接文档提交前的审计快照**。用户随后授权仅提交并推送 `AGENTS.md`、`HANDOFF.md`；其他源码、未跟踪文件、Proper 分支和外部数据不在此次发布范围。文档提交用 `git log -1 --format=fuller -- AGENTS.md HANDOFF.md` 查看，是否已推送以实际远端分支为准。

## 1. 最重要的结论

1. 开发分支 `research/ista-velocity-regularized`，交接整理时本地/实时 GitHub 远端 HEAD 均为 **`e0c5271951b3997120a734a4811bbaf41c922c0a`**。E06 参数与结果已推送；后续交接文档提交不是新的飞行源码资格。
2. **GitHub clone 不等于这台电脑完整项目**：创建本交接前仍有8个已跟踪文件修改、168个未跟踪文件，另有 Proper PV02 的本地独有提交，以及约117 GiB外部 experiments。
3. 最近采用的候选是 **ISTA E06 XYZ**，Z `lambda1=3.3, lambda2=1.56, epsilon=0.06`；完整配置与环境必须一起保留，不能只搬三个增益。
4. 先迁移并核验，后重建/预检，再另冻新任务。**不要在新机直接续跑已完成的 E06、RI07 或旧失败清单。**

## 2. 项目目标与当前代码

目标是研究多旋翼 PX4 速度环的 PID、正则化显式 STA（R-STA）、补偿正则化隐式 STA（R-ISTA），比较跟踪、响应、波动及控制代价；论文需要可复现证据，不预设任何算法普遍获胜。

当前图中标签 PID/STA/ISTA 对应速度 MODE0/3/4。原位置 P、姿态控制与角速度 PID 保持。速度环在 **`mc_pos_control`**，不是 `mc_att_control`。

```text
位置/轨迹目标 → 位置 P + 速度前馈
             → 速度 PID / R-STA / R-ISTA（本研究替换处）
             → 加速度纠偏 + 一次加速度FF → 姿态/推力映射
             → 姿态环 → 角速度 PID → mixer/执行器 → 电机
```

XYZ 为本地 NED 北/东/下；不是 roll/pitch/yaw。关键入口见 AGENTS §2。速度 MODE2 仍拒绝；本分支 MODE3/4 只支持 AXES1/4/3/7、DIV1、SITL。Proper 的 MODE5不是这里的可用算法。

### 阶段进度

| 工作线 | 已确认状态 | 后续边界 |
|---|---|---|
| 旧角速度 STA/ISTA/Proper | 历史分支/报告保留；旧 Proper I05 分频门未最终完成 | 不自动继续旧17轮，不作为速度研究资格 |
| 旧速度 ESTA/按轴消融 | 历史 V/AX 研究资料保留 | 新主比较不含旧 ESTA；部分旧ULog已清理 |
| R-STA R03 | X/Z/XY/XYZ 开发验收完成 | 原 R04/R05 被 R-ISTA RI06/RI07 职责替代，不跑旧清单 |
| R-ISTA RI00–RI07 | XYZ接入、54轮等预算训练/验证、RI07正式200轮完成 | 已消费清单；不能重新当留出或接着调参 |
| Proper 速度 PV00–PV02 | 另一分支离线通过，PV03未执行；PV02本地未发布 | 生产准入关闭，零Proper速度飞行，不能自动并入当前分支 |
| 上游 SuperTwisting2.0 | 独立分支 `research/upstream-supertwisting2` 已推送 | 原样复现是系统级比较，不冒称只比较速度环 |
| 最近响应/起降调参与 E06 | 当前dirty工作区+外部实验链；E06 9/9接受/独立回放 | 只对本次小幅起降环境有效，非正式等预算新调参 |

RI07：[完整报告](research/sta-velocity-control/reports/RI07.md)、[正式结果包](research/sta-velocity-control/regularized_ista/ri07/results/final01/README_CN.md)。A组同参数 R-STA/R-ISTA，B组等预算分别调参；共200/200完成，不混A/B参数。正式结果不能与后来的E06小样本拼成同一试验。

Proper 进度来自外部 `VELOCITY_PROPER_ISTA_STATUS_CN.md` 和本地 Proper 分支，相关文件不在当前分支时要 `git show research/proper-ista-velocity:<路径>` 只读查看；不要为了阅读覆盖dirty工作区。

## 3. 要记住的 E06

固定档案：[e06_verified_20261105/README_CN.md](research/sta-velocity-control/regularized_ista/e06_verified_20261105/README_CN.md)。

| 项 | X/Y | Z |
|---|---:|---:|
| ISTA lambda1 | 0.55 | 3.3 |
| ISTA lambda2 | 0.11 | 1.56 |
| ISTA epsilon（m/s） | 0.01 | 0.06 |
| nu限值（m/s²） | 0.4 | 4 |
| 加速度纠偏限值（m/s²） | 0.8 | 6 |

`MPC_VC_MODE=4, MPC_VC_AXES=7`，双DIV1、rate PID、旧起飞管理关闭。完整三套参数在档案 `parameters/`。共同 `EKF2_BARO_NOISE=.3`、`EKF2_ACC_B_NOISE=.003`、`NAV_MC_ALT_RAD=.1`、HTE启用；派生模型加速度随机游走 **0**，其他噪声/初始偏置并未全部关闭。`MPC_VCT_TEST=5` 属实验接线；不能把JSON直接用于实机。

STA参照：XY `.45/.09/.01`，Z `3/1.3/.04`。PID Z速度I为1.1，STA/ISTA地面/交接PID对应值为2.2；必须保留披露，不能称所有阶段只差非线性公式。

| 三轮均值，越小越好 | PID | STA | ISTA E06 |
|---|---:|---:|---:|
| 真值上升90%时间（s） | 8.877333 | 7.598667 | 7.453333 |
| 真值悬停高度RMSE（mm） | 12.374418 | 14.172662 | 11.675586 |
| 真值悬停高度STD（mm） | 9.938412 | 9.552983 | 8.328423 |

起飞约2.5m，命令后30s统一下降，指标窗口20–30s。9轮无补飞；新IMU种子99601–99603已消费。三项均值门槛通过，但RMSE仅2/3轮胜出，平均高度偏差仍不是最小；n=3且仅IMU播种，不声称显著/普遍优势。旧E04未达标结果保留，不用E06覆盖。

E06档案提交：`e0c5271951b3997120a734a4811bbaf41c922c0a`；实际飞行HEAD：`8079e17177e3edb597d8da1597081a82cbd6747a` **加当时dirty工作区**；固件 SHA-256：`96f20a849bbd1ad0f1c9222c26ba2ebb79ed74bfda5ca10cbf67436b791cab00`。参数已精确恢复，未永久安装默认值。结果提交SHA不能冒充固件身份。

## 4. 关键决策及原因、已知问题

- 保留当前R-ISTA基线，Proper另分支：它的理想理论优势不保证滞后/噪声/限幅对象全面更好；原探针有极小数停止，PV阶段独立修复/验证，不能混入R-ISTA结论。
- 控制器以估计状态反馈：共同高度漂移不等于速度控制稳态误差。旧9日志已分解目标/估计跟踪/真值—估计偏差，不只给ISTA加人为高度偏置或真值反馈。
- 正则化epsilon会影响近零区反馈和积分，不能仅追最快首次碰目标。E06保持起飞领先，同时按预定RMSE/STD评价；不再自动扩大搜索。
- QGC/位置任务可能有ramp、目标交接和位置P限制。响应图必须同时看真实指令、实际v_sp、接管时刻、估计与真值，不能认定“理论上ISTA必定最快”。
- 日志检查修订来自实际双时钟/同刻消息/跨块/落地确认问题。已有白名单和边界规则不能简单全话题去重或放宽数值安全门槛。
- `USAGE_CN.md` 仍是 RI06/RI07 旧配置（例如ISTA Z2.2/1.1/eps.02），有效操作说明可保留，但**不是E06参数手册**。
- E06外部运行器依赖长链、绝对路径与旧源码/固件资格；当前新HEAD已不同，迁移后的新构建还会改变SHA。必须建立新迁移资格，不能修改旧qualification哈希绕过拒绝。
- 旧build含其他分支测试二进制，不证明当前分支测试通过。最新6个响应任务源/测试文件未跟踪，漏搬会破坏现有源码引用。
- 旧 `SITL_CN.md` 引用的 `GAZEBO_PX4_SITL_CN.md` 当前缺失；不依赖此断链完成安装。

## 5. Git 审计：哪些已上云，哪些没有

远端用途：`codev=https://github.com/i37532/CODEV.git` 是研究发布库；`origin` 是 CodevDynamics 上游，`origin_gitee` 是旧 amovlab1/p600px4。认证请新机单独配置，不迁移密钥文件。

| 本地分支 | 本地SHA（短） | codev远端SHA（短） | 结论 |
|---|---|---|---|
| research/ista-velocity-regularized | e0c5271951 | e0c5271951 | 当前分支无未推送提交 |
| research/proper-ista-velocity | 0937abe34e | 1c9f019357 | **PV02领先1提交，尚无codev远端分支包含，必须单独保留** |
| research/sta-rate-control | 866bba6e0d | 1d64163b14 | 自身远端指针落后14；这些提交已包含在已推R-ISTA等分支，并非独有代码丢失 |
| research/sta-velocity-control | 0a5796c3ed | 0a5796c3ed | 一致 |
| research/sta-velocity-regularized | a286e40ec8 | a286e40ec8 | 一致 |
| research/upstream-supertwisting2 | 6d00b4ada7 | 6d00b4ada7 | 一致 |

`main-v2_gps` 相对旧gitee跟踪领先1，但提交已在GitHub研究分支里。上述是本轮实时 `ls-remote` 结果；换机前再查，不据本表强推或自动同步其他分支。

**创建这两份交接文件之前**：staged为空；8个已跟踪文件修改，358增/2删；168个未跟踪文件共65,609,481字节（约62.6MiB）。33个递归子模块已初始化、gitlink匹配、内部干净。本交接又新增根 `AGENTS.md` 与 `HANDOFF.md`，后续单独发布这两份文件不改变上述其他改动的未提交状态。

8个既有修改：

```text
research/sta-velocity-control/README_CN.md
research/sta-velocity-control/regularized_ista/README_CN.md
src/modules/mc_pos_control/MulticopterPositionControl.cpp
src/modules/mc_pos_control/MulticopterPositionControl.hpp
src/modules/mc_pos_control/PositionControl/CMakeLists.txt
src/modules/mc_pos_control/PositionControl/PositionControl.hpp
src/modules/mc_pos_control/RegularizedIstaVelocityModuleTest.cpp
src/modules/mc_pos_control/mc_pos_control_params.c
```

主要是SITL `MPC_VCT_TEST=9/10/11` 响应/分段/隔离Z任务、HTE getter、测试注册与274行模块回归；不是本轮交接新改控制律。必须连同下面6个未跟踪文件迁移，不能只复制diff：

```text
src/modules/mc_pos_control/PositionControl/VelocityResponseTask.hpp
src/modules/mc_pos_control/PositionControl/VelocityResponseTaskTest.cpp
src/modules/mc_pos_control/PositionControl/VelocitySegmentedResponseTask.hpp
src/modules/mc_pos_control/PositionControl/VelocitySegmentedResponseTaskTest.cpp
src/modules/mc_pos_control/PositionControl/VelocityZResponseTask.hpp
src/modules/mc_pos_control/PositionControl/VelocityZResponseTaskTest.cpp
```

其他未跟踪内容包括使用/代码手册、`actual_timeseries/hover10/response09/response_segmented/takeoff_settle/takeoff_snapshot/takeoff_snapshot_batch/z_response/z_unified`、上游STA2结果、HOVER10/RESPONSE9报告、旧ISTA展示脚本。`regularized_ista/ri06/results/plots01` 的56文件约62MiB，占大部分空间。完整实时清单用 `git ls-files --others --exclude-standard` 查看；本轮没有自动把它们提交。

## 6. 必须迁移的仓库外内容

| 路径（旧电脑） | 本轮占用/作用 |
|---|---|
| `/home/yr/Desktop/Codev-autopilot` | 约14GiB，含.git约1.6GiB、build约11GiB；保留所有本地分支、dirty/untracked |
| `/home/yr/Desktop/codev doc/experiments` | 约117GiB，ULog、协议、实际模型/插件、源码快照、运行/分析链 |
| `/home/yr/Desktop/codev doc/plan` | 约900KiB，实时TODO/STATUS/PROMPTS，不等于仓库v1快照 |
| `/home/yr/Desktop/codev doc/algorithms` | 约68KiB，算法公式/接口资料 |
| `/home/yr/Desktop/STA-ISTA-MATLAB-PX4` | 约1.8MiB，R系列原始来源包 |
| `/home/yr/Downloads/MATLAB-ISTA` | 约2.9MiB，旧算法来源 |
| `/home/yr/Documents/PID_STA_ISTA_F4_HEIGHT_AUDIT_20261104` | 约1.9MiB，3个脚本仍在E06依赖链中 |
| `/home/yr/Documents/PID_STA_ISTA_F4_TAKEOFF_20261104` | 约345MiB，另zip约105MiB，旧展示/日志包按需保留 |

E06原始包：`experiments/VELOCITY-ISTA-E06-VERIFY-20261105`（约743MiB）。**只带这个目录不够**：档案 `provenance.json` 列1820个源码/模型/工具依赖，本轮1820/1820路径存在（没有重算全部1820哈希），跨25个 experiments 根及上述来源/Documents目录。依赖版本不能用新下载“最新版”无声替换。

特别保留：`.px4-python`（约87MiB、Git忽略）、`experiments/M00-20260912/python`（约148MiB）、`experiments/M10-20260917/plot_dependencies01/python`（约160MiB）。它们虽在旧实验名目录下，当前工具仍使用。

历史清理限制：`experiments/HISTORY-CLEANUP-20261026/README_CN.md` 记录已授权永久删除2595份旧ULog约68.7GiB，涉及旧M10、轴消融、VELOCITY-STA-20260929。报告/参数/摘要并非原始备份；这三包不能再完整回放。清理索引和保留的依赖日志要带走，不能恢复成“全部旧日志尚在”的表述。

## 7. 新电脑运行环境

以下是旧机**实测版本**，不是已验证的新机安装承诺：

| 组件 | 已核实版本 |
|---|---|
| 系统/架构 | Ubuntu 22.04.5 LTS / x86_64 |
| PX4基线 | `v1.12.3-1.0.6`，当前describe为 `v1.12.3-1.0.6-229-ge0c5271951-dirty`；自定义研究分支，不是原版release |
| Gazebo | Classic 11.10.2，命令 `gazebo`，不是新版 `gz sim` |
| GCC/G++ | 11.4.0 |
| CMake / Ninja / Git | 3.22.1 / 1.10.1 / 2.34.1 |
| Python | 3.10.12 |
| Eigen / Protobuf / OpenCV | 3.4.0 / 3.12.4 / 4.5.4 |

需 Git、make、编译器、CMake/Ninja、Python/pip、Gazebo Classic及其开发依赖。系统软件源可用性、显卡/显示驱动、不同CPU/OS兼容性待新机确认；本轮没有安装或下载。旧 `sitl/setup.sh` 会额外下载本地JDK11/Ant、修执行权限和构建jMAVSim，不能把它当纯Gazebo依赖检查。

`.px4-python` 是 `pip --target` 目录，不是venv。主要实测版本：`empy==3.3.4`、`Jinja2==3.1.6`、`numpy==1.26.4`、`pyros-genmsg==0.5.8`、`kconfiglib==14.1.0`、`jsonschema==4.26.0`，另有packaging/toml/PyYAML/pyserial/future等。先保留旧包清单和字节，再在新机匹配Python/架构重装；不要直接升级empy4或numpy2。

外部研究依赖：M00/python 中 `pyulog==1.2.4`、`pymavlink==2.4.49`；M10绘图依赖中 `matplotlib==3.8.4`。SciPy当前未安装，不是已确认的本项目必备项。ROS、QGC不是现有自动实验必需；PlotJuggler可选，具体安装/ULog插件版本待新机核实。

基础构建/测试/启动命令见 AGENTS §3。研究Python的旧机示例：

```bash
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python:/home/yr/Desktop/codev doc/experiments/M10-20260917/plot_dependencies01/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
```

上述路径含空格必须引用；不要覆盖整个PATH。首次测试要下载固定gtest `8b6d3f9c4a774bef3081195d422993323b6bb2e0`，需网络。旧build/CMakeCache和.so插件不要当新机构建直接使用；保留已测固件作为历史证据，新机另行重建/冻结，SHA不同不伪装成旧版本。

## 8. 迁移与下一步清单

### 离开旧电脑前

1. 停止自有仿真，确认参数已恢复；核对目标磁盘空间。完整保留这两份新文档。
2. 最稳妥是整体复制仓库（含 `.git`、子模块metadata、dirty/untracked和被忽略依赖/历史固件），再复制上表外部资料。**不使用 `--delete`、不复制整个home、不包含凭据目录。** `rsync -a` 应先 `--dry-run`，目的地必须由用户实际确认。
3. 若走Git迁移，先审查这8个源码/文档修改及168个新文件，拆成明确范围提交；单独决定是否发布Proper PV02。不用本次“整理交接”代替提交/推送授权。
4. 可另外做 `git bundle create <明确备份文件> --all` 保存全部本地refs，但bundle**不含dirty/untracked或外部数据**；单独 `git diff --binary` 又不含6个新头文件/测试。二者都不能代替完整备份。
5. 复制后比较文件数量/容量与关键SHA，至少校验E06 `verify_archive.py`、ULog索引、固件、模型/插件；不要删除旧机数据后才验证。

### 到新电脑后

1. 初期尽量使用相同 `/home/yr/...` 目录结构，减少绝对路径问题；若不同，建立显式迁移映射并调整新运行配置。**不要全局替换旧冻结JSON/报告中的路径或哈希。**
2. 若只clone云端，使用正确仓库和分支，但还需恢复本地备份：

   ```bash
   git clone -o codev --branch research/ista-velocity-regularized \
     https://github.com/i37532/CODEV.git Codev-autopilot
   cd Codev-autopilot
   git submodule update --init --recursive
   ```

   此命令不是完整迁移方案；Proper PV02、dirty/untracked、外部包必须另外恢复。不在已有目录覆盖clone。
3. 先核对分支/HEAD/dirty/子模块和E06纯档案校验。不要先切Proper、清理文件或运行旧批。
4. 保存旧build中的实际固件及哈希作证据，在新的构建目录/已归档旧缓存后重建SITL、实际非零控制测试；按AGENTS命令确认未漏测。不要删除唯一历史二进制。
5. 审计E06长依赖链与新机Gazebo/插件ABI，解决缺文件/绝对路径，再做新机只读dry-run和参数备份恢复测试。必要时将路径配置整理成新的可迁移版本，保留旧证据。
6. 用户明确开始新实验后，冻结**新**有限清单、种子、源/固件/模型/分析器资格，先PID冒烟，再按新协议比较。先维持E06，不无故重新搜索或要求ISTA一定赢。
7. 若后续要Proper，先恢复/发布本地PV02并在独立工作树核对其计划，再决定PV03；不沿用E06资格直接开放模式5。

## 9. 本轮检查与待确认

已执行：Git状态/实际远端refs/子模块检查；脚本阅读、`bash -n`/`--help`；环境版本检查；E06档案校验exit0（20文件、9轮）；`ctest -N` 的选定正则枚举24个目标。**枚举不是执行测试；没有本轮新构建、控制测试、ULog全链回放或飞行。**

待确认：新电脑用户名/架构/磁盘/显示环境、软件源可用性、PlotJuggler插件、迁移方法、哪些本地改动要正式提交，以及是否推送Proper本地提交。本文不保存认证信息。旧秘密凭据应在新机重新配置，不复制到Git/文档/交接压缩包。

交接文档发布范围仅为 `AGENTS.md`、`HANDOFF.md`，原有有效文档与源码保持。即使这两份文档已推送，其他未提交改动、本地独有 Proper 提交与外部数据仍须按上述清单另行备份或明确范围发布，不能仅 clone 云端后删除旧机资料。
