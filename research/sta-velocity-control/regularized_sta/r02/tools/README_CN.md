# R02 离线工具：不具备飞行执行权限

本目录不改变旧 `sim_scripts`、AX04/AX05、V08/V09 默认目标。`run.py` 默认只显示完整配置；`--execute` 在读取授权文件、创建输出目录或调用进程前无条件拒绝。即使传入伪造的 manifest、SHA 或授权，也不能打开 R02 飞行入口。

## 入口

从仓库根目录运行：

```bash
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/regularized_sta/r02/tools/run.py
python3 research/sta-velocity-control/regularized_sta/r02/tools/run.py --mode 3 --axes 1
python3 research/sta-velocity-control/regularized_sta/r02/tools/test_tools.py
```

- 明确允许 MODE 0/1/3，MODE 2 拒绝；MODE0 必须 AXES0，旧 MODE1 保留 AXES1–7，新 MODE3 只允许 1/4/3/7。
- 127 项参数来自有 SHA-256 绑定的 AX04 固定参数，仅覆盖模式、轴、任务 TEST0 和新增 epsilon。内环固定 PID、DIV1、旧起飞管理关闭；速度 DIV1。
- epsilon 域 `[.001,1] m/s`，初始 X/Y/Z `.01/.01/.02`。未知轴、布尔增益、缺少参数、非法任务/epsilon 拒绝，不默认为 X。
- 这是历史合格参数的来源记录，不是新算法全配置已验收，更不继承 AX04 的源码资格。

## 参数事务

`parameters.py` 通过显式传入的存储、CLI、状态接口，复用原 `run_v00` 的 BSON 编解码、CLI 解析、参数对照和实际内环检查。全档案备份/恢复按字节验证，保留无关参数及已有日志配置位。保存档案必须在模拟器停止时进行；若尚未停止，拒绝覆盖，保留原始备份等待恢复。

当前仅提供内存存储和 fake CLI 测试，**没有真实 EEPROM/进程后端**。测试覆盖成功、异常、运行中拒绝、恢复延后、错误模式/内环/有效 epsilon，以及 metadata 缺字段、非法布尔值/配置代数/数组长度；没有访问真实 EEPROM。后续运行器仍须将完整原始 BSON 持久保存到新批次外部目录，绑定进程所有权并在退出后恢复。

## 日志检查

`analyzer.py` 精确关联 `publish_seq` 和 `timestamp_sample`，同时核对 input 时间、调用数、模式/轴和 armed/enabled，不排序、不去重、不近邻补配。

MODE3 使用实际分段公式，不是 hypot 光滑函数：

```text
rho = s / max(abs(s), epsilon)
Psi = sqrt(max(abs(s), epsilon)) * rho
a_raw = nu_before - lambda1 * Psi
nu_ideal = nu_before - status.raw_dt * lambda2 * rho
```

`selection.h` 保留原 PID dt 定义，不能代替新算法真实 sensor h。分别检查理想候选、限幅后的纠偏、保护冻结后的 nu，以及一次 FF。日志的 `a_proxy` 只称推力映射代理，不是实测加速度。新 selection 的 variant、请求/有效 epsilon、配置代数也必须精确匹配；PID 未使用 STA 时 `sta_reject` 不等于模式拒绝。

非稳态检查覆盖地面、单帧 PID handover、正常接管、加速度-only 阶段，实际 PID 轴由有限的速度目标/测量/导数推导。地面全 NaN 速度目标时 PID 轴可以是 0，不硬写成 7。检查原子提交、nu 限制、状态连续和 Z HTE 重置关系。

`whole_flight_components()` 直接连接旧版姿态白名单/同刻歧义、完整边界及 reset、PositionLogView、消费目标/FF、height/handoff、landing、IMU、实际内环及执行器部分覆盖检查；不把新模式映射成旧模式，不修改旧模块全局变量。不允许只有激励小窗口合格就宣称飞行通过。MODE3 启用前必须有新日志，R02 所有组件结果均保留 `flight_accepted=false`。

## 已执行的离线验证

- `test_tools.py`：35 个 Python 测试，非零执行，最终退出码 0；重复执行不累计为新用例。
- `replay.py`：AX04 原完整分析器在独立子进程/新目录回放 4 个已检查的 AX05 ULog：H 的 PID/run007 与 XYZ/run008，V 的 PID/run163 与 XYZ/run165。4/4 通过，所有原目录文件 SHA 前后相同，历史判定不变。
- `check_archived_chain.py`：另外让新的完整组件组合真实处理同 4 个旧 ULog，4/4 通过。旧日志没有新 metadata，明确标记缺失；只允许旧 MODE0/1 走此路径，不向日志填入虚构字段。这仍是 **4 个唯一日志**，不是 8 次独立实验，更不是新 MODE3 飞行验证。
- 外部输出：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R02/tools_replay01/`；原完整回放证据为 `evidence.json`。新组合最终带输入 SHA 的输出为 `new_chain04_run*.json`；此前 `new_chain02_run*.json` 为已通过但尚未记录脚本输入 SHA 的版本，`new_chain03_run*.json` 对应参数 metadata 缺字段负例补齐之前的源码，全部保留不覆盖。

真实调试失败保留：首次直接用系统 Python 缺 numpy（退出 1）；带项目环境首次 26 测试出现 1 个错误（缺 cli_clock 路径）和 1 个失败（完整参数数量预期少计 SDLOG_PROFILE），修复后通过；新组合第一次把 `hover_end == land_command` 合法边界写成严格小于而拒绝 run007，失败文件 `new_chain_run007.json` 保留。修复只恢复 AX04 原有边界语义，没有放宽数值阈值、改判旧结果或补飞。

## R03 仍缺少的接线与准入

1. 独立、可审计的 MODE3 SITL 准入变更，默认 PID 不变；R02 生产模块仍拒绝 MODE3。
2. R03 准确任务/窗口/阈值/新种子/顺序/预算及源/固件/模型/分析器资格提交；本目录没有飞行清单和预算。
3. 真实运行器进程/参数事务后端、档案持久备份、失败停批与退出恢复接线；沿用项目 Iris 启动器和已验收接触资产。
4. R03 小激励任务的独立目标/全阶段验收器及完整 provenance/性能门。当前可复用的 H/V 波形检查不冒充未来不同任务已冻结。
5. 新模式真实起降日志、eps/variant 生效、全生命周期与公共保护的全部飞行证据。合成组件和旧模式回放不能替代这些证据。

本目录不能启动 Gazebo、PX4、飞行或调参搜索；不占用新实验种子，不查看未来留出数据。
