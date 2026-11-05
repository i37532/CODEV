# CODEV 开发约定

本文件记录长期规则。当前进度、分支、待迁移内容见 [HANDOFF.md](HANDOFF.md)。优先用中文沟通。现有 README、阶段报告和冻结证据保留有效内容；历史文档中的“当前/未通过/未push”只代表其日期，必须结合实际 Git 和最终报告判断。

## 1. 开工与范围

- 先核实真实仓库目录，旧电脑为 `/home/yr/Desktop/Codev-autopilot`；不要采用带意外后缀的工作目录。
- 每次检查分支、HEAD、工作区、递归子模块；不 reset/clean，不删除重建已有研究分支，不覆盖用户未提交改动。
- 当前主要研究是**速度环** PID / R-STA / R-ISTA；图中允许写 PID / STA / ISTA，但正文必须说明算法身份。Proper-ISTA、旧 ESTA/ISTA、上游 SuperTwisting2.0 是不同研究，不混称。
- 仅 Gazebo Classic Iris SITL。DP1000 实机不是同一模型或已验收配置；不自动部署硬件。
- 只做用户当前明确的阶段/批次；历史“直到成功”不构成永久无限飞行、调参、扩预算或 push 授权。迁移、审计、出图请求本身不授权起飞。
- 正式阶段先完整阅读对应 TODO/STATUS/PROMPTS、共同规则、前置验收和日志契约。外部实时计划在旧机 `Desktop/codev doc/plan/`，仓库 `plan/v1` 是只读初始快照，不拿旧快照覆盖实时进度。

```bash
git branch --show-current
git rev-parse HEAD
git status --short --branch
git submodule status --recursive
git diff --check
```

## 2. 控制器与接口

主要代码在 `src/modules/mc_pos_control/`，不是 `mc_att_control`：

- `MulticopterPositionControl.cpp/.hpp`：Run、状态/时间输入、参数、起降、HTE、failsafe、诊断接线。
- `PositionControl/PositionControl.cpp/.hpp`：位置 P、速度控制分派、加速度到姿态/推力映射。
- `PositionControl/RegularizedStaVelocityControl.*`、`RegularizedIstaVelocityControl.*`：独立 C++14 速度算法。
- `PositionControl/StaVelocityProtection.*`、`VelocityControlSelector.hpp`：保护、生命周期、requested/effective/pending/reject。
- `mc_pos_control_params.c`、`msg/sta_velocity_ctrl_status.msg`、`msg/velocity_ctrl_selection.msg`：参数/日志入口；新增诊断前核对实际消息文件、生成格式长度、注册、队列与丢样。

当前 R-ISTA 分支语义：`MPC_VC_MODE=0` PID，`1` 旧 ESTA，`2` 保留且拒绝，`3` R-STA，`4` R-ISTA。MODE3/4 在 SITL 接受 AXES1/4/3/7（X/Z/XY/XYZ），拒绝2/5/6。Proper 的模式5属于另一分支且有独立准入限制，不能在这里假设可用。

- XYZ 是本地 NED 北/东/下，不是机体 roll/pitch/yaw。
- 速度误差 `s=v−v_sp`，单位 m/s；纠偏加速度与 `nu` 为 m/s²；epsilon 为 m/s。速度核不套角速度的输入增益 g，不重复除质量。
- 原位置 P、姿态环、角速度 PID 保持，默认固件 PID 不变。常规 R 系列对比固定 `MC_RTC_MODE=0`、`MC_STA_AXES=0`、`MC_RTC_DIV=1`、`MC_RATT_TEST=0`、`MC_STA_TKO_MGT=0`、`MPC_VC_DIV=1`。
- 保留合法 XY 成对 NaN、一次加速度 FF、未选择 PID 轴、HTE、地面/ramp/有界交接；同 sample 的 failsafe 二次 update 不重复积分或提交。三轴候选整体裁决、原子提交，reset/重新解锁不继承陈旧状态。
- R-STA 用旧 nu 计算当拍输出；R-ISTA 理想 p/候选 nu 参与当拍输出，evaluate 与 commit 分开。保护后的 applied 值不是严格隐式解，不能照搬另一算法冻结后重构公式。
- 算法/参数切换仅在落地上锁状态进行，核对实际 effective 模式而不只看 param 请求。armed 暂存/取消、disarm、生效、重启、故障、termination 必须测试；零力矩/零输出不等于安全。

## 3. 启动、构建、测试

所有 bash 命令在仓库根目录。此处是可执行参考，不要求每次文档工作自动构建或飞行。新机环境及外部依赖先按 HANDOFF 配好。

```bash
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/.px4-python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
make px4_sitl_default -j4

make tests TESTFILTER=Velocity -j4
ctest --test-dir build/px4_sitl_test --output-on-failure --no-tests=error \
  -R '(PositionControl|ControlMath|Takeoff|RateControl|Regularized|Velocity)'
```

第一条测试命令构建全部已注册测试、先运行 Velocity 子集，第二条再运行完整相关子集。旧 Makefile 会无引号展开 `TESTFILTER`，不要向它传入含括号或 `|` 的正则；复杂筛选交给带引号的 `ctest -R`。单独 `make px4_sitl_test` 不会构建所有被 EXCLUDE_FROM_ALL 的测试。

测试必须记录实际非零用例数、命令和退出码；`ctest -N` 仅枚举，构建成功不等于测试/飞行通过。先按改动范围选相关回归，再按阶段计划全量资格。旧 build 可能残留其他分支二进制，不能冒充当前源码验证。首次 gtest 下载和系统依赖失败应如实记录。

基础 Gazebo 图形/无头启动（**不是 E06 冻结实验**，只有明确需要仿真时执行）：

```bash
./sitl/run.sh --backend gazebo --model iris
# 或
./sitl/run.sh --headless --backend gazebo --model iris
```

`sitl/run.sh` 无参数默认 jMAVSim；启动可能编译并改变固件版本 SHA。Gazebo 默认 world 为 `sitl/worlds/empty_grey.world`。没有依赖时脚本可能调用 `sitl/setup.sh`，后者会安装依赖、修执行位、准备 Java/Ant 并构建，绝非只读预检。

- 根 `sim_scripts/` 服务旧**角速度**研究，不用其 switch/fly 切当前速度算法。
- V06 `start.sh --execute` 可查看软接触 Iris；V06 `switch.sh esta` 是旧速度 MODE1，不能当 R-STA。
- 旧 `regularized_ista/USAGE_CN.md` 是 RI06/RI07 演示参数，不是 E06。仅导入 E06 JSON 不会自动得到随机游走0/播种插件/任务链。
- 研究自动任务使用项目启动器，关闭 QGC、ROS/其他目标发布者争抢；唯一目标源、推力/其余轴来源须明确。ROS 不是当前任务链的必需条件。

无需 PX4/外部包的纯档案检查：

```bash
python3 -B research/sta-velocity-control/regularized_ista/e06_verified_20261105/verify_archive.py
```

## 4. 实验、日志与结论

- 正式实验顺序：离线回归 → 冻结任务、参数、窗口、阈值、种子、顺序、有限预算、源码/固件/模型/插件/分析器 → 明确提交并在合格版本执行 → 独立 ULog 回放/指纹检查 → 独立结果提交。快速探索也要记录实际 dirty 源码和限制，不能冒充干净冻结版本。
- 安全或必需有效性首败停批，保留全部失败/无效/未执行；不补飞、换种子、混源码或改门槛换通过。修改协议另存新版本并确定授权范围，不覆盖旧批。
- 每轮重启、相对日志预热、完整参数备份/精确恢复；只管理自己启动的进程。预检容量，不擅自删除历史数据。
- 时间必须区分 publication `timestamp`、`timestamp_sample` 与真实更新序号；保留白名单、同刻歧义、完整边界/reset、增量解析和落地尾窗语义。禁止所有话题统一去重、clamp 掩盖坏 dt、缺样填补有效性或拿 dropout=0 替代覆盖证明。
- 真值只做离线诊断。估计高度、真实高度、实际位置目标分别命名，起飞原点和 EKF reset 有依据；不只给某算法加真值补偿。共同外部轨迹不等于内部 v_sp 逐样本相同。
- RMSE、均值偏差、STD分别报告；控制 TV 不等于能耗，宿主耗时不等于板级 CPU。不得预设 ISTA 必胜、选最佳轮/窗口、把均值优势当每轮优势，或将3个IMU种子说成全部随机源独立。
- MATLAB 未实际运行就写未运行；已有 CSV/fixture 不称本次 MATLAB 重跑。历史数据缺失也要显式说明，摘要不是原始回放。
- 大 ULog 留外部，仓库保存参数、摘要/图、路径、SHA-256和复核入口。训练/验证/留出隔离；已消费种子与已结束清单不复用。

## 5. 文件与 Git

- 先 `rg` 查找，编辑用明确范围；保留用户文件，旧冻结记录不重写。
- 提交前检查 diff、非零测试和文件列表；不要 `git add .` 夹带源码、日志或旧图。没有当前明确要求不自动 push；不得强推。
- 研究发布远端通常为 `codev`（`https://github.com/i37532/CODEV.git`），而非 `origin` 上游。每次先核对真实 URL/分支，移机 clone 的 remote 名称可能不同。
- 不保存令牌、密码、SSH私钥、Git credential 文件、会话cookie或完整环境变量转储。只记录依赖/版本/公开URL/非敏感路径；认证在新电脑单独配置。
- 维护长期规则写 AGENTS；状态、SHA、未完成事项写 HANDOFF/实时进度。新增协议不自动替代既有 E06/RI07 结论。
