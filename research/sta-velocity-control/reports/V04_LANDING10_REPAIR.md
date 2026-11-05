# V04：降落监视器跨话题时间匹配离线修复

日期：2026-09-26。**offline_passed；V04 飞行验收仍 failed / needs_revision。本轮飞行 0 次。**

## 范围与结论

按用户“先离线修复降落监视器的时间匹配，测试通过后再申请新批次”执行。起点 `7755b003868c25e105616483cd92d95151b7d68a`，分支 `research/sta-velocity-control`，开始主仓库及递归子模块干净。完整读取速度计划/共同规则、实时进度表及 [protocol09 失败报告](V04_PROTOCOL09_RESULTS.md)。

修复仅新增隔离研究脚本和离线证据；原运行器、检查器、protocol09、历史数据均不覆盖。未改控制律、控制器 dt、参数、模型、EKF、起飞逻辑或数值安全/性能门槛。原位置 P、Y/Z 速度 PID、姿态及角速度 PID 主线保持。本次没有新的运行参数实测或飞行 ULog；最近实际内环 PID 证据仍来自 series08。

上轮错误是宿主把 107.932s 的旧 Hold 状态与 108.244s 的新 Gate=2 一起分类。新版用原始日志的命令、状态和诊断历史分类，不再以不同时刻 CLI 快照的组合决定降落 Gate。真实 series08 回放中 12 条 Gate=2 均符合原计划降落类别；但该轮缺落地上锁，**仍是失败，不改判通过**。

## 实现与边界

- [v04_landing10.py](../scripts/v04_landing10.py)：纯证据策略和带故障锁存的监视器。只有完整 60–62s 观察、成功且唯一的计划降落命令、原始 `DO_SET_MODE=176 / param1=1 / param2=4 / param3=6 / target=1/1`、armed、输出为 0、**此前或同刻**的 AUTO_LAND 才可解释单独 Gate=2。
- 不把宿主事件时间当作实际命令时间。新增 `command_lower_us` 在发命令前取样；真正命令时间来自 ULog。晚于 Gate 的 AUTO_LAND 不可用于回填，原始 fault 位保留。
- 未到齐的原始证据返回 **pending，而非 clear/成功**。从首次待定计时，模拟时间和宿主时间任一超过 0.5s 即拒绝；反复待定不刷新期限，模拟暂停也不能永久等待。当前 CLI 和原始诊断传输年龄均须在 0–0.5s，未来/倒退拒绝。
- 真正故障、first_fail/retry、错误内环、非零 Gate 输出、提前/非计划 Gate、重复/冲突命令、退出 AUTO_LAND 直接拒绝，不因 pending 隐藏。原始诊断历史逐条覆盖，短暂故障不能靠低频 CLI 抽样漏过。
- [v04_landing_live10.py](../scripts/v04_landing_live10.py)：保留所有原记录，额外读取 command/ack 话题。状态话题仍严格递增；没有给所有话题放开同刻、排序或去重。
- [v04_monitor10.py](../scripts/v04_monitor10.py)：只在 landing 阶段替换分类，保留已有机载参考、primary/reset、姿态、内环和包络检查。新增 reader 从航向阶段持续使用，避免在降落瞬间首次解析整个文件。CLI 上锁不能代替控制器及原始诊断已上锁清零。
- [run_v04_flight11.py](../scripts/run_v04_flight11.py)：隔离接线草案，**入口在任何文件/进程/连接副作用前无条件拒绝执行**。仅新增命令前时间下界、一次计划登记、完成待定守卫及 landing 宿主轮询 sleep 从 0.5s 改为 0.1s；150s 降落总超时不变。这是宿主轮询，不是控制器周期修改。
- [analyze_v04_landing10.py](../scripts/analyze_v04_landing10.py)：离线完整链包装，继承原全套指标、输出覆盖、模式和 reset 检查，再增加相同降落关联检查。合成来源正例验证全链可通过；包装器对外始终 `accepted=false`，不能用于新飞行验收或改判旧数据。新 protocol10 的可执行来源/授权绑定仍须单独冻结。

Commander 源码在状态变化时立即发布，平时约 2Hz 发布（`Commander.cpp` 中 `hrt_elapsed_time(&_status.timestamp) >= 500_ms || _status_changed || nav_state_changed`）。因此不要求各话题时间相等；也不拿姿态话题的高频规则套到该状态话题。这个匹配证明的是**已记录观测之间的关系**，不证明控制器实际消费了哪个跨话题样本，不承诺宿主实时调度安全。

规则与申请：[contract.json](../v04/landing10/contract.json)、[proposal.json](../v04/landing10/proposal.json)。本次新增 0.5s 有界待定策略明确登记；不是延长所有话题期限，也不是取消真实故障检查。

## 测试、失败和未执行项

环境沿用 `.px4-python` 与已存在的 M00 pymavlink 目录。工作目录为仓库根目录，外部证据根为 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04`。

| 命令/证据目录 | 实际数量与退出码 |
|---|---|
| `python3 -m unittest discover -s research/sta-velocity-control/scripts -p test_v04_landing10.py -v`，targeted01 | 24 项，1 失败，退出 1；实现已提前拒绝 AUTO_LAND-before-command，测试误要求后续错误字符串 |
| 同命令，targeted02 | 30 项，退出 0；只修正错误文本断言，未放宽拒绝条件 |
| `python3 research/sta-velocity-control/scripts/verify_v04_protocol09.py --output …/landing10_verify01` | 109 控制 C++ + 11 IMU C++ = 120 个不同用例，332 Python，退出 0 |
| 同验证器内 SITL/测试及 `DONT_RUN=1 make px4_sitl_default gazebo_iris -j4` | 构建退出 0，无 Gazebo 启动 |
| 同验证器 IMU 附加检查 | 同 11 项 sanitizer 重跑通过、不重复累计；2048 帧冻结旧源码等价；旧源码负对照预期失败/退出 1 |
| `python3 -m unittest discover -s research/sta-velocity-control/scripts -p 'test_*.py' -v`，python_final01 | 333 项，退出 0；补上锁竞态保护后 |
| 同命令，python_final02 / python_final03 | 均 **334 项，退出 0**；最终 24.570s，新增共 32 项，含 reader 复用及必需 first_input 缺字段拒绝 |
| `python3 research/sta-velocity-control/scripts/replay_v04_landing10.py --output …/landing10_replay01` | 八批离线回放，退出 0；284 份原输入指纹不变 |

最后修改只涉及 Python 上锁守卫/reader 复用及保留 first_input 必需字段检查，最终 334 项覆盖它们；没有再次累计此前的 C++ 或构建数量。主控制回归保留两组各 2048 步 PID 等价及原 STA/rate 测试。完整命令、输出、XML、退出码见 [verification.json](../v04/landing10/verification.json) 及索引。

反例覆盖：旧 Hold/新诊断、晚到/未来状态、精确时间边界和邻点、待定期间故障、重复命令、未计划/提前 Gate、非零输出、disarm 未到齐、超时/模拟暂停、非有限/倒退时间、真实内环错误、完整链 reset 和错误目标地址。原脚本逐字保持；新飞行草案的差异范围也有自动契约测试。

未执行 MATLAB、仿真启动、实机、ESTA 新飞行、V05；没有新参数优化。完整异步 Commander/控制器调度不由离线夹具证明；正式运行前仍需新协议接线及干净提交复核。

## 八批旧日志：只回放，不改判

| 历史批次 | 新降落组件 | 其他证据/限制 |
|---|---|---|
| series01–04 | 未运行：缺完整观察或降落命令 | 原失败保留；series02 原参考不满足较新原始参考规范 |
| series05 | 704 条预期 Gate 通过 | 仅组件；原历史验收失败保留，合成新来源正例另作全链测试 |
| series06 | 436 条计划降落 Gate 可分类 | **reference/EKF 变化仍拒绝**，不能因降落 Gate 合法而豁免 |
| series07 | 未运行：没有进入降落 | 姿态时钟规则仍独立适用，原中止保留 |
| series08 | 12 条预期 Gate 通过 | 未完成落地上锁；完整验收仍拒绝 |

八批都没有新完整接受结论。旧日志不含新 `landing_context.json` 时，仅在独立组件诊断使用注明来源的旧宿主事件下界；不伪造新原始证据供完整验收使用。当前累计仍 **8 次尝试 / 0 次接受 / ESTA 飞行 0 次**。

## 资产、提交与新批次申请

外部证据目录：`landing10_offline01`（所有测试输出，包括首次失败）、`landing10_verify01`（完整构建/回归）、`landing10_replay01`（隔离八批回放）。[artifacts.sha256](../v04/landing10/artifacts.sha256) 引用本轮证据及完整验证索引；大型日志仍保留原位置。持久参数前后 SHA 为 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，无活动模拟器。

本次结果按明确文件范围提交，不 push；提交 SHA 写外部实时进度表。构建生成的新固件 SHA 为 `20699ef4af12647ebb8300dd9631a8824897cda75b65895a4a06fdf15826c0c1`，是离线验证产物，**不是已冻结新飞行源码的固件**。

申请新的条件预算：**9901 PID→ESTA X、9902 PID→ESTA X、9903 PID→ESTA X，最多 6 次 Iris SITL**。参数、2.5m 高度、60s 观察/32s X 激励、安全/配对门槛沿用 protocol09，仅采用本次显式降落观测修订。22971 份历史 JSON 扫描无复用/无未解释无效文件；原 M06 空文件例外保留。源码文本命中仅是旧报告 SHA 的数字子串，不是该种子登记。仅 IMU 播种、PID 先行偏差继续披露，飞前必须再查。

**申请不等于已授权或可直接执行。** 获准后先冻结 protocol10 的新配置、运行器与最终分析器来源绑定、准确清单/资产/源码提交，再在干净提交完成回归、固件/参数/端口核对和独立授权回执后执行。禁止仅删 flight11 的禁用守卫启动。任一必需单轮或配对失败停止；不补飞、不重试、不调参、不复用旧剩余五轮、不 push、不 V05。预留 series09 目录目前不存在。
